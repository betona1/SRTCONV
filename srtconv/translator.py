"""번역 엔진: 오프라인 CTranslate2 모델(M2M100 기본, NLLB 선택) 우선, 온라인 Google/MyMemory 보조."""
import json
import os
import re
import sys
import time
from pathlib import Path

from . import languages

# 오프라인 모델 폴더 이름 -> 종류. 앞에 있는 것을 우선합니다.
#  - m2m100_418M : MIT 라이선스 (상업 이용 가능) -> 기본 배포 모델
#  - nllb-200     : CC-BY-NC-4.0 (비상업 전용) -> 배포하지 않으며, 사용자가 직접 넣은 경우에만 사용
OFFLINE_MODELS = [
    ('m2m100_418M-ct2-int8', 'm2m100'),
    ('m2m100_1.2B-ct2-int8', 'm2m100'),
    ('nllb-200-distilled-600M-ct2-int8', 'nllb'),
]


class TranslationError(Exception):
    pass


def app_root():
    """실행 파일(또는 소스) 기준 루트 폴더."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def _model_kind(folder):
    """폴더 이름 또는 config 로 모델 종류를 판별합니다."""
    name = Path(folder).name.lower()
    for dir_name, kind in OFFLINE_MODELS:
        if dir_name.lower() in name:
            return kind
    try:
        cfg = json.loads((Path(folder) / 'config.json').read_text(encoding='utf-8'))
        if any(str(v).startswith('__') for v in (cfg.get('bos_token'), cfg.get('decoder_start_token'))):
            return 'm2m100'
    except Exception:
        pass
    return 'nllb' if 'nllb' in name else 'm2m100'


def find_offline_model(extra=None):
    """사용 가능한 오프라인 번역 모델 폴더를 찾습니다. (Path, kind) 또는 None."""
    bases = []
    if extra:
        bases.append(Path(extra))
    env = os.environ.get('SRTCONV_MODEL_DIR') or os.environ.get('SRTCONV_NLLB_DIR')
    if env:
        bases.append(Path(env))
    roots = [app_root() / 'models', Path.home() / '.cache' / 'srtconv']
    candidates = []
    for base in bases:
        candidates.append(base)
    for root in roots:
        for dir_name, _kind in OFFLINE_MODELS:
            candidates.append(root / dir_name)
    for folder in candidates:
        if (folder / 'model.bin').exists() and (folder / 'sentencepiece.bpe.model').exists():
            return folder, _model_kind(folder)
    return None


# 하위 호환
def find_nllb_dir(extra=None):
    found = find_offline_model(extra)
    return found[0] if found else None


class CT2Translator:
    """CTranslate2 로 변환한 M2M100 / NLLB-200 모델로 오프라인 번역합니다."""

    def __init__(self, model_dir, device='auto', kind=None):
        import ctranslate2
        import sentencepiece as spm
        self.kind = kind or _model_kind(model_dir)
        self.name = 'M2M100 (오프라인)' if self.kind == 'm2m100' else 'NLLB (오프라인)'
        # 한글 등 비ASCII 경로에서 sentencepiece 의 파일 열기가 실패하므로 바이트로 읽어 넘깁니다.
        self.sp = spm.SentencePieceProcessor(model_proto=(Path(model_dir) / 'sentencepiece.bpe.model').read_bytes())
        from .transcriber import cuda_available
        use_cuda = device != 'cpu' and cuda_available()
        dev = 'cuda' if use_cuda else 'cpu'
        compute = 'int8_float16' if use_cuda else 'int8'
        try:
            self.translator = ctranslate2.Translator(str(model_dir), device=dev, compute_type=compute)
        except Exception:
            self.translator = ctranslate2.Translator(str(model_dir), device='cpu', compute_type='int8')

    def _lang_token(self, lang):
        if self.kind == 'm2m100':
            return f'__{lang.m2m}__'
        return lang.nllb

    def translate(self, texts, source, target):
        src = languages.get(source)
        tgt = languages.get(target)
        if not src or not tgt:
            raise TranslationError(f'{self.name} 가 지원하지 않는 언어: {source} -> {target}')
        src_token, tgt_token = self._lang_token(src), self._lang_token(tgt)
        out = []
        batch = 16
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            tokens = [[src_token] + self.sp.encode(t, out_type=str) + ['</s>'] for t in chunk]
            results = self.translator.translate_batch(
                tokens, target_prefix=[[tgt_token]] * len(chunk), beam_size=4,
                max_decoding_length=256, repetition_penalty=1.1)
            for r in results:
                hyp = r.hypotheses[0]
                if hyp and hyp[0] == tgt_token:
                    hyp = hyp[1:]
                out.append(self.sp.decode(hyp).strip())
        return out


# 하위 호환 이름
NLLBTranslator = CT2Translator


class GoogleTranslator:
    name = 'Google (온라인)'

    def translate(self, texts, source, target):
        from deep_translator import GoogleTranslator as DT
        src = languages.get(source)
        tgt = languages.get(target)
        client = DT(source=src.google if src else 'auto', target=tgt.google if tgt else target)
        return _translate_lines(client, texts, limit=4500)


class MyMemoryTranslator:
    name = 'MyMemory (온라인)'

    def translate(self, texts, source, target):
        from deep_translator import MyMemoryTranslator as DT
        src = languages.get(source)
        tgt = languages.get(target)
        if not src or not tgt:
            raise TranslationError(f'MyMemory 가 지원하지 않는 언어: {source} -> {target}')
        client = DT(source=src.mymemory, target=tgt.mymemory)
        out = []
        for t in texts:
            out.append(_retry(lambda t=t: client.translate(t[:500])) if t.strip() else t)
        return out


def _retry(func, attempts=3, delay=1.5):
    last = None
    for i in range(attempts):
        try:
            return func()
        except Exception as error:
            last = error
            time.sleep(delay * (i + 1))
    raise TranslationError(str(last))


def _translate_lines(client, texts, limit):
    """여러 줄을 묶어 요청 횟수를 줄이고, 줄 수가 어긋나면 한 줄씩 다시 번역합니다."""
    out = []
    group = []
    size = 0

    def flush():
        nonlocal group, size
        if not group:
            return
        joined = '\n'.join(group)
        result = _retry(lambda: client.translate(joined))
        lines = (result or '').split('\n')
        if len(lines) != len(group):
            lines = [_retry(lambda t=t: client.translate(t)) if t.strip() else t for t in group]
        out.extend(line.strip() for line in lines)
        group, size = [], 0

    for text in texts:
        if size + len(text) + 1 > limit:
            flush()
        group.append(text)
        size += len(text) + 1
    flush()
    return out


ENGINES = {
    'auto': '자동 (오프라인 우선)',
    'offline': '오프라인 모델 (M2M100/NLLB)',
    'google': 'Google (온라인)',
    'mymemory': 'MyMemory (온라인)',
}
# 하위 호환: 예전 설정값 'nllb'
ENGINE_ALIASES = {'nllb': 'offline'}


def build_chain(engine='auto', device='auto', model_dir=None, log=None):
    """선택한 엔진(또는 자동)에 대해 시도할 번역기 목록을 만듭니다."""
    engine = ENGINE_ALIASES.get(engine, engine)
    chain = []
    found = find_offline_model(model_dir)
    if engine in ('auto', 'offline'):
        if found:
            folder, kind = found
            try:
                chain.append(CT2Translator(folder, device, kind))
            except Exception as error:
                if log:
                    log(f'오프라인 번역 모델을 불러오지 못했습니다: {error}')
        elif engine == 'offline':
            raise TranslationError('오프라인 번역 모델 폴더를 찾을 수 없습니다. models 폴더를 확인하세요.')
        elif log:
            log('오프라인 번역 모델이 없어 온라인 엔진을 사용합니다.')
    if engine in ('auto', 'google'):
        chain.append(GoogleTranslator())
    if engine in ('auto', 'mymemory'):
        chain.append(MyMemoryTranslator())
    return chain


SENTENCE_END = ('.', '?', '!', '。', '？', '！', '…')
NO_SPACE_LANGS = {'ja', 'zh', 'zh-TW', 'th'}


def group_sentences(texts, max_group=4, max_chars=240):
    """연속된 큐를 문장 단위로 묶습니다. [(start_index, end_index_exclusive), ...]"""
    groups = []
    start = 0
    size = 0
    for i, text in enumerate(texts):
        size += len(text)
        count = i - start + 1
        if text.rstrip().endswith(SENTENCE_END) or count >= max_group or size >= max_chars:
            groups.append((start, i + 1))
            start, size = i + 1, 0
    if start < len(texts):
        groups.append((start, len(texts)))
    return groups


def distribute(translated, weights, no_space=False):
    """번역된 문장을 원문 큐 길이 비율에 맞춰 조각으로 나눕니다."""
    n = len(weights)
    if n == 1:
        return [translated]
    total = sum(weights) or n
    if no_space:
        # 글자 단위로 나누되 라틴 문자·숫자 덩어리(이름 등)는 한 단위로 묶어 중간이 끊기지 않게 합니다.
        units = re.findall(r'[A-Za-z0-9À-ÿ]+|.', translated)
        joiner = ''
    else:
        units = translated.split(' ')
        joiner = ' '
    if len(units) < n:
        return [translated] + [''] * (n - 1)
    pieces = []
    pos = 0
    for i, w in enumerate(weights):
        if i == n - 1:
            take = len(units) - pos
        else:
            take = max(1, round(len(units) * w / total))
            take = min(take, len(units) - pos - (n - 1 - i))
        pieces.append(joiner.join(units[pos:pos + take]).strip())
        pos += take
    return pieces


def translate_cues(chain, texts, source, target, log=None):
    """문장 단위로 묶어 번역한 뒤 각 큐에 다시 배분합니다. 결과 길이는 texts 와 같습니다."""
    groups = group_sentences(texts)
    sentences = [' '.join(t.strip() for t in texts[a:b]) for a, b in groups]
    translated = translate_texts(chain, sentences, source, target, log=log)
    no_space = target in NO_SPACE_LANGS
    out = []
    for (a, b), sentence in zip(groups, translated):
        out.extend(distribute(sentence, [max(1, len(t)) for t in texts[a:b]], no_space))
    return out


def translate_texts(chain, texts, source, target, log=None):
    """체인을 차례로 시도해 첫 성공 결과를 돌려줍니다."""
    errors = []
    for engine in chain:
        try:
            result = engine.translate(texts, source, target)
            if len(result) != len(texts):
                raise TranslationError('번역 결과 줄 수가 원문과 다릅니다.')
            if log:
                log(f'번역 엔진: {engine.name} ({languages.display_name(source)} -> {languages.display_name(target)})')
            return result
        except Exception as error:
            errors.append(f'{engine.name}: {error}')
            if log:
                log(f'{engine.name} 실패, 다음 엔진 시도: {error}')
    raise TranslationError(' / '.join(errors) or '사용 가능한 번역 엔진이 없습니다.')
