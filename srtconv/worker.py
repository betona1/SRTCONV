"""백그라운드 작업 스레드: 모델 로드 -> 파일별 전사/번역. GUI 와 시그널로 통신합니다."""
from PySide6.QtCore import QThread, Signal

from . import transcriber, translator
from .pipeline import process_file


class ModelCache:
    """같은 모델·장치 설정이면 다시 불러오지 않도록 보관합니다."""

    def __init__(self):
        self.key = None
        self.model = None
        self.device = None
        self.chain_key = None
        self.chain = None

    def get_model(self, name, device, allow_download, log):
        key = (name, device)
        if self.key != key or self.model is None:
            self.model, self.device = transcriber.load_model(name, device, allow_download, log)
            self.key = key
        return self.model

    def get_chain(self, engine, device, nllb_dir, log):
        key = (engine, device, nllb_dir)
        if self.chain_key != key or self.chain is None:
            self.chain = translator.build_chain(engine, device, nllb_dir or None, log)
            self.chain_key = key
        return self.chain


class Worker(QThread):
    log = Signal(str)
    file_started = Signal(int)
    file_progress = Signal(int, str, float)     # row, stage, 0~1
    file_done = Signal(int, object)              # row, Result
    file_failed = Signal(int, str)
    all_done = Signal(int, int, bool)            # success, failure, cancelled

    def __init__(self, jobs, options, cache, parent=None):
        """jobs: [(row, path), ...]"""
        super().__init__(parent)
        self.jobs = jobs
        self.options = options
        self.cache = cache
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _should_cancel(self):
        return self._cancel

    def run(self):
        success = failure = 0
        try:
            model = self.cache.get_model(self.options.model, self.options.device, self.options.allow_download, self.log.emit)
            self.log.emit(f'모델 준비 완료 ({self.cache.device}).')
            chain = None
            if self.options.translate and self.options.targets:
                chain = self.cache.get_chain(self.options.engine, self.options.device, self.options.nllb_dir, self.log.emit)
                self.log.emit('번역 엔진: ' + ' -> '.join(e.name for e in chain))
        except Exception as error:
            self.log.emit(f'준비 실패: {error}')
            for row, _ in self.jobs:
                self.file_failed.emit(row, str(error))
            self.all_done.emit(0, len(self.jobs), False)
            return
        for row, path in self.jobs:
            if self._cancel:
                self.file_failed.emit(row, '취소됨')
                failure += 1
                continue
            self.file_started.emit(row)
            self.log.emit(f'▶ {path}')
            try:
                try:
                    result = process_file(
                        path, self.options, model, chain,
                        progress=lambda stage, f, r=row: self.file_progress.emit(r, stage, f),
                        should_cancel=self._should_cancel, log=self.log.emit)
                except Exception as error:
                    if self.options.device == 'cpu' or not transcriber.is_cuda_error(error):
                        raise
                    # GPU 런타임(cuBLAS/cuDNN) 문제 -> CPU 로 다시 불러와 한 번 더 시도
                    self.log.emit(f'GPU 실행 실패 ({error}). CPU 로 전환해 다시 시도합니다.')
                    self.options.device = 'cpu'
                    model = self.cache.get_model(self.options.model, 'cpu', self.options.allow_download, self.log.emit)
                    if chain is not None:
                        chain = self.cache.get_chain(self.options.engine, 'cpu', self.options.nllb_dir, self.log.emit)
                    result = process_file(
                        path, self.options, model, chain,
                        progress=lambda stage, f, r=row: self.file_progress.emit(r, stage, f),
                        should_cancel=self._should_cancel, log=self.log.emit)
                self.file_done.emit(row, result)
                success += 1
            except transcriber.Cancelled:
                self.file_failed.emit(row, '취소됨')
                failure += 1
            except Exception as error:
                self.log.emit(f'실패: {error}')
                self.file_failed.emit(row, str(error))
                failure += 1
        self.all_done.emit(success, failure, self._cancel)
