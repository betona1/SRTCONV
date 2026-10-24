"""SRTCONV 진입점. 인자가 없으면 GUI, --cli 가 있으면 콘솔 모드로 동작합니다."""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')

# 콘솔 코드페이지가 출력 문자를 지원하지 않아도(예: cp949 에서 중국어) 멈추지 않도록 합니다.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(errors='replace')
        except Exception:
            pass

if getattr(sys, 'frozen', False):
    # PyInstaller 번들: CUDA/cuDNN DLL 이 들어 있는 폴더를 DLL 검색 경로에 추가합니다.
    base = Path(sys._MEIPASS)
    for folder in (base, base / 'ctranslate2', base / 'cuda'):
        if folder.is_dir():
            os.add_dll_directory(str(folder))
            os.environ['PATH'] = str(folder) + os.pathsep + os.environ.get('PATH', '')


def run_cli(args):
    from srtconv import languages, transcriber, translator
    from srtconv.pipeline import Options, process_file

    options = Options(
        model=args.model, device=args.device, source_language=args.lang,
        translate=bool(args.translate), targets=[t.strip() for t in (args.translate or '').split(',') if t.strip()],
        engine=args.engine, output_dir=args.output or '', allow_download=args.download, max_chars=args.max_chars)
    log = lambda text: print(text, flush=True)
    model, device = transcriber.load_model(options.model, options.device, options.allow_download, log)
    print(f'모델 준비 완료 ({device})', flush=True)
    chain = translator.build_chain(options.engine, options.device, None, log) if options.translate else None
    failures = 0
    last = [-1]

    def progress(stage, fraction):
        pct = int(fraction * 100)
        if pct >= last[0] + 10 or pct == 100:
            print(f'  {stage} {pct}%', flush=True)
            last[0] = pct

    for index, path in enumerate(args.files, 1):
        print(f'\n[{index}/{len(args.files)}] {path}', flush=True)
        last[0] = -1
        try:
            try:
                result = process_file(path, options, model, chain, progress=progress, log=log)
            except Exception as error:
                if options.device == 'cpu' or not transcriber.is_cuda_error(error):
                    raise
                print(f'GPU 실행 실패 ({error}). CPU 로 전환해 다시 시도합니다.', flush=True)
                options.device = 'cpu'
                model, device = transcriber.load_model(options.model, 'cpu', options.allow_download, log)
                chain = translator.build_chain(options.engine, 'cpu', None, log) if options.translate else None
                result = process_file(path, options, model, chain, progress=progress, log=log)
            print(f'완료: {result.original}', flush=True)
            for target, out in result.translated.items():
                print(f'  번역({languages.display_name(target)}): {out}', flush=True)
            if result.errors:
                failures += 1
        except Exception as error:
            failures += 1
            print(f'실패: {error}', flush=True)
    print(f'\n처리 종료: 성공 {len(args.files) - failures}개 / 실패 {failures}개', flush=True)
    return 1 if failures else 0


def run_gui(smoke=False):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from srtconv import APP_NAME, ORG_NAME
    from srtconv.ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    if smoke:
        QTimer.singleShot(1500, lambda: (print('SMOKE_OK', flush=True), app.quit()))
    return app.exec()


def main():
    parser = argparse.ArgumentParser(prog='SRTCONV', description='로컬 Whisper 자막 생성 + 다국어 자동 번역')
    parser.add_argument('files', nargs='*', help='영상·음성 파일 (GUI 에서는 목록에 미리 추가)')
    parser.add_argument('--cli', action='store_true', help='GUI 없이 콘솔에서 바로 처리')
    parser.add_argument('--lang', default='auto', help='음성 언어 코드 (기본 auto)')
    parser.add_argument('--model', default='large-v3')
    parser.add_argument('--device', default='auto', choices=['auto', 'cuda', 'cpu'])
    parser.add_argument('--translate', default='', help='번역 대상 언어 코드, 쉼표 구분 (예: ko,ja,zh)')
    parser.add_argument('--engine', default='auto', choices=['auto', 'offline', 'nllb', 'google', 'mymemory'],
                        help='번역 엔진 (offline: M2M100/NLLB 로컬 모델, nllb 는 offline 의 옛 이름)')
    parser.add_argument('--output', default='', help='출력 폴더 (기본: 원본 옆)')
    parser.add_argument('--download', action='store_true', help='모델이 없으면 다운로드 허용')
    parser.add_argument('--max-chars', type=int, default=45)
    parser.add_argument('--smoke', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.cli:
        if not args.files:
            parser.error('--cli 모드에는 파일이 하나 이상 필요합니다.')
        return run_cli(args)
    return run_gui(smoke=args.smoke)


if __name__ == '__main__':
    sys.exit(main())
