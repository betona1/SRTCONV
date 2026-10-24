"""파일 하나를 끝까지 처리: 전사 -> 원문 SRT -> (선택) 번역 SRT."""
from dataclasses import dataclass, field
from pathlib import Path

from . import languages
from . import transcriber
from . import translator
from .srt_utils import Cue, write_srt, reserve_output

MEDIA_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.ts', '.mpg', '.mpeg', '.wmv', '.flv',
                    '.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg', '.opus', '.wma'}


def is_media(path):
    return Path(path).suffix.lower() in MEDIA_EXTENSIONS


@dataclass
class Options:
    model: str = transcriber.DEFAULT_MODEL
    device: str = 'auto'
    source_language: str = languages.AUTO
    translate: bool = False
    targets: list = field(default_factory=lambda: ['ko'])
    engine: str = 'auto'
    output_dir: str = ''
    allow_download: bool = False
    max_duration: float = 5.0
    max_chars: int = 45
    nllb_dir: str = ''


@dataclass
class Result:
    source: Path
    original: Path = None
    detected: str = ''
    translated: dict = field(default_factory=dict)   # target -> path
    cue_count: int = 0
    errors: list = field(default_factory=list)


def process_file(path, options, model, chain=None, progress=None, should_cancel=None, log=None):
    """progress(stage, fraction) 로 진행률을 알립니다. stage: 'transcribe' | 'translate'."""
    source = Path(path)
    result = Result(source=source)
    if not source.is_file():
        raise FileNotFoundError(f'파일을 찾을 수 없습니다: {source}')
    language = None
    if options.source_language != languages.AUTO:
        lang = languages.get(options.source_language)
        language = lang.whisper if lang else options.source_language
    cues, detected, _duration = transcriber.transcribe(
        model, source, language=language,
        progress=(lambda f: progress('transcribe', f)) if progress else None,
        should_cancel=should_cancel, log=log,
        max_duration=options.max_duration, max_chars=options.max_chars)
    if not cues:
        raise RuntimeError('인식된 대사가 없습니다.')
    result.detected = detected
    result.cue_count = len(cues)
    out_dir = options.output_dir or None
    detected_lang = languages.get(detected)
    label = detected_lang.code if detected_lang else detected
    result.original = reserve_output(source, f'자막_{label}', out_dir)
    write_srt(result.original, cues)
    if log:
        log(f'원문 자막 저장: {result.original.name} ({len(cues)}개)')
    if options.translate and options.targets:
        texts = [c.text for c in cues]
        targets = []
        skipped = []
        for t in options.targets:
            lang = languages.get(t)
            if lang and lang.whisper == detected:
                skipped.append(t)
            else:
                targets.append(t)
        if skipped and log:
            log('원문과 같은 언어라 번역 생략: ' + ', '.join(languages.display_name(t) for t in skipped))
        for index, target in enumerate(targets):
            if should_cancel and should_cancel():
                raise transcriber.Cancelled()
            try:
                translated = translator.translate_cues(chain or [], texts, label, target, log=log)
                out = reserve_output(source, f'자막_{target}', out_dir)
                write_srt(out, [Cue(c.start, c.end, t) for c, t in zip(cues, translated)])
                result.translated[target] = out
                if log:
                    log(f'번역 자막 저장: {out.name}')
            except Exception as error:
                result.errors.append(f'{languages.display_name(target)} 번역 실패: {error}')
                if log:
                    log(result.errors[-1])
            if progress:
                progress('translate', (index + 1) / len(targets))
    return result
