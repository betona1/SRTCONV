"""faster-whisper 래퍼: 모델 탐색/로드, 전사, 진행률·취소 지원."""
import os
from pathlib import Path

from .srt_utils import Word, split_words

os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')

# 표시 이름 -> (HuggingFace 저장소, 설명)
MODELS = {
    'large-v3': ('Systran/faster-whisper-large-v3', '최고 정확도 · 약 3GB'),
    'large-v3-turbo': ('mobiuslabsgmbh/faster-whisper-large-v3-turbo', '빠르고 정확 · 약 1.6GB'),
    'large-v2': ('Systran/faster-whisper-large-v2', '높은 정확도 · 약 3GB'),
    'medium': ('Systran/faster-whisper-medium', '중간 · 약 1.5GB'),
    'small': ('Systran/faster-whisper-small', '빠름 · 약 0.5GB'),
    'base': ('Systran/faster-whisper-base', '매우 빠름 · 약 0.15GB'),
}
DEFAULT_MODEL = 'large-v3'


class Cancelled(Exception):
    pass


def hf_cache_dir():
    return Path(os.environ.get('HF_HOME', Path.home() / '.cache' / 'huggingface')) / 'hub'


def is_model_cached(name):
    repo = MODELS.get(name, (name,))[0]
    folder = hf_cache_dir() / ('models--' + repo.replace('/', '--')) / 'snapshots'
    if not folder.is_dir():
        return False
    return any((snap / 'model.bin').exists() for snap in folder.iterdir())


CUDA_RUNTIME_DLLS = ('cublas64_12.dll', 'cudnn64_9.dll')
CUDA_ERROR_HINTS = ('cublas', 'cudnn', 'cuda', 'cudart')


def cuda_runtime_present():
    """GPU 드라이버가 있어도 cuBLAS/cuDNN DLL(GPU 팩)이 없으면 실행 중 실패하므로 미리 확인합니다."""
    if os.name != 'nt':
        return True
    import ctypes
    for name in CUDA_RUNTIME_DLLS:
        try:
            ctypes.WinDLL(name)
        except OSError:
            return False
    return True


def cuda_available():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0 and cuda_runtime_present()
    except Exception:
        return False


def is_cuda_error(error):
    """실행 중 발생한 예외가 CUDA 런타임 문제인지 판별합니다 (CPU 재시도 판단용)."""
    text = str(error).lower()
    return any(hint in text for hint in CUDA_ERROR_HINTS)


def resolve_device(choice='auto'):
    """'auto' | 'cuda' | 'cpu' -> (device, compute_type)"""
    if choice == 'cpu':
        return 'cpu', 'int8'
    if choice == 'cuda' or (choice == 'auto' and cuda_available()):
        return 'cuda', 'float16'
    return 'cpu', 'int8'


def load_model(name=DEFAULT_MODEL, device='auto', allow_download=False, log=None):
    from faster_whisper import WhisperModel
    repo = MODELS.get(name, (name,))[0]
    dev, compute = resolve_device(device)
    cpu_threads = max(1, min(8, (os.cpu_count() or 4) - 2))
    local_only = not allow_download
    if log:
        log(f'모델 불러오는 중: {name} ({dev}, {compute})' + ('' if is_model_cached(name) else ' - 다운로드 필요'))
    attempts = [(dev, compute)]
    if dev == 'cuda':
        attempts.append(('cpu', 'int8'))
    last = None
    for d, c in attempts:
        try:
            model = WhisperModel(repo, device=d, compute_type=c, cpu_threads=cpu_threads, local_files_only=local_only)
            if log and (d, c) != (dev, compute):
                log('GPU 초기화 실패로 CPU로 전환했습니다.')
            return model, d
        except Exception as error:
            last = error
    raise RuntimeError(f'모델을 불러오지 못했습니다 ({name}): {last}')


def transcribe(model, path, language=None, progress=None, should_cancel=None, log=None,
               max_duration=5.0, max_chars=45):
    """파일을 전사해 (cues, detected_language, duration) 을 돌려줍니다."""
    segments, info = model.transcribe(
        str(path), language=language, task='transcribe', beam_size=5,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
        word_timestamps=True, condition_on_previous_text=False,
        compression_ratio_threshold=2.4, no_speech_threshold=0.6)
    if log:
        log(f'감지 언어: {info.language} (확률 {info.language_probability:.0%}), 길이 {info.duration:.1f}초')
    cues = []
    duration = max(info.duration, 0.001)
    for segment in segments:
        if should_cancel and should_cancel():
            raise Cancelled()
        if not segment.text.strip() or segment.end <= segment.start:
            continue
        words = [Word(w.start, w.end, w.word) for w in (segment.words or [])]
        cues.extend(split_words(segment.start, segment.end, segment.text, words, max_duration, max_chars))
        if progress:
            progress(min(1.0, segment.end / duration))
    if progress:
        progress(1.0)
    return cues, info.language, info.duration
