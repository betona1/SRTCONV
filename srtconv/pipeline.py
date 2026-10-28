"""파일 하나를 끝까지 처리: 전사 -> 원문 SRT -> (선택) 번역 SRT."""
import ctypes
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import languages
from . import transcriber
from . import translator
from .srt_utils import Cue, write_srt, reserve_output, unique_path

MEDIA_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.ts', '.mpg', '.mpeg', '.wmv', '.flv',
                    '.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg', '.opus', '.wma'}


def is_media(path):
    return Path(path).suffix.lower() in MEDIA_EXTENSIONS


# 저장 위치 선택지 (GUI 설정값 -> 표시 이름)
OUTPUT_MODES = {
    'source': '원본 파일과 같은 폴더',
    'downloads': '다운로드 폴더',
    'custom': '직접 지정한 폴더',
    'ask': '시작할 때마다 폴더 선택',
}


def downloads_dir():
    """사용자 다운로드 폴더. Windows 는 알려진 폴더 API 로 실제 위치를 묻고, 그 외는 ~/Downloads."""
    if sys.platform == 'win32':
        try:
            from ctypes import wintypes
            class GUID(ctypes.Structure):
                _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                            ('Data4', ctypes.c_ubyte * 8)]
            folder_id = GUID(0x374DE290, 0x123F, 0x4565, (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(out)) == 0:
                path = Path(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                return path
        except Exception:
            pass
    return Path.home() / 'Downloads'


def resolve_output_dir(mode, custom=''):
    """저장 위치 모드를 실제 폴더 문자열로 바꿉니다. '' 이면 원본 파일 옆. 'ask' 는 GUI 가 직접 묻습니다."""
    if mode == 'downloads':
        return str(downloads_dir())
    if mode == 'custom':
        return (custom or '').strip()
    return ''


def export_files(files, directory):
    """결과 SRT 들을 다른 폴더로 복사합니다 (덮어쓰지 않음). [(원본, 복사본), ...]"""
    copied = []
    for src in files:
        src = Path(src)
        if not src.is_file():
            continue
        if Path(directory).resolve() == src.parent.resolve():
            continue   # 이미 그 폴더에 있는 파일
        dst = unique_path(directory, src.name)
        shutil.copy2(src, dst)
        copied.append((src, dst))
    return copied


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
