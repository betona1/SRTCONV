"""SRT 자막 데이터 구조와 읽기/쓰기, 긴 구간 분할 유틸리티."""
from dataclasses import dataclass, field
from pathlib import Path
import re

SENTENCE_END = ('.', '?', '!', '。', '？', '！', '…')


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class Word:
    start: float
    end: float
    word: str


def timestamp(seconds):
    ms = max(0, round(seconds * 1000))
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'


def parse_timestamp(text):
    h, m, rest = text.strip().split(':')
    s, ms = rest.replace('.', ',').split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def split_words(start, end, text, words, max_duration=5.0, max_chars=45, min_chars=12):
    """단어 타임스탬프를 기준으로 긴 구간을 자막용 짧은 큐로 나눕니다."""
    text = text.strip()
    words = [w for w in (words or []) if w.word.strip()]
    if not words or (end - start <= max_duration and len(text) <= max_chars):
        return [Cue(start, end, text)] if text else []
    chunks = []
    chunk = []

    def flush():
        if chunk:
            chunks.append(Cue(chunk[0].start, chunk[-1].end, ''.join(x.word for x in chunk).strip()))
            chunk.clear()

    for word in words:
        candidate = ''.join(x.word for x in chunk + [word]).strip()
        duration = word.end - (chunk[0].start if chunk else word.start)
        # 공백 없이 이어지는 토큰(하이픈 단어, CJK 문자열 등) 앞에서는 끊지 않습니다.
        continuation = bool(chunk) and not word.word.startswith(' ')
        if chunk and not continuation and (len(candidate) > max_chars or duration > max_duration):
            flush()
        chunk.append(word)
        current = ''.join(x.word for x in chunk).strip()
        if current.endswith(SENTENCE_END) and len(current) >= min_chars:
            flush()
    flush()
    # 너무 짧은 조각은 앞 큐에 합칩니다.
    merged = []
    for cue in chunks:
        if merged and len(cue.text) < min_chars and len(merged[-1].text) + 1 + len(cue.text) <= max_chars * 2:
            prev = merged[-1]
            merged[-1] = Cue(prev.start, cue.end, f'{prev.text} {cue.text}')
        else:
            merged.append(cue)
    return [c for c in merged if c.text and c.end > c.start]


def to_srt(cues):
    lines = []
    for index, cue in enumerate(cues, 1):
        lines.append(f'{index}\n{timestamp(cue.start)} --> {timestamp(cue.end)}\n{cue.text}\n')
    return '\n'.join(lines) + ('\n' if lines else '')


def write_srt(path, cues):
    Path(path).write_text(to_srt(cues), encoding='utf-8-sig')


def read_srt(path):
    text = Path(path).read_text(encoding='utf-8-sig')
    cues = []
    for block in re.split(r'\n\s*\n', text.strip()):
        rows = block.strip().splitlines()
        if len(rows) < 2:
            continue
        timing = rows[1] if '-->' in rows[1] else rows[0]
        body_start = 2 if '-->' in rows[1] else 1
        start, end = [parse_timestamp(part) for part in timing.split('-->')]
        cues.append(Cue(start, end, '\n'.join(rows[body_start:]).strip()))
    return cues


def reserve_output(source, suffix, directory=None):
    """원본 옆(또는 지정 폴더)에 덮어쓰지 않는 새 파일 경로를 확보합니다."""
    source = Path(source)
    directory = Path(directory) if directory else source.parent
    directory.mkdir(parents=True, exist_ok=True)
    for number in range(1, 10000):
        tail = '' if number == 1 else f'_{number}'
        target = directory / f'{source.stem}_{suffix}{tail}.srt'
        if not target.exists():
            return target
    raise RuntimeError('저장할 파일 이름을 확보하지 못했습니다.')
