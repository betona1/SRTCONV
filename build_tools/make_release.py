"""릴리스용 zip 3개 생성 (GitHub 릴리스 파일 2GB 제한 대응).
사용: python build_tools/make_release.py v1.0.0   (먼저 build.cmd 로 dist/SRTCONV 를 만들어 둘 것)
  release/SRTCONV-<ver>-win64.zip          본체 (CUDA DLL·models 제외, CPU 동작)
  release/SRTCONV-<ver>-cuda-pack.zip      CUDA/cuDNN DLL (_internal 에 풀어 넣기)
  release/SRTCONV-<ver>-model-m2m100.zip   오프라인 번역 모델 (models 폴더로 풀기)
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist' / 'SRTCONV'
OUT = ROOT / 'release'
CUDA_DLLS = {
    'cublas64_12.dll', 'cublasLt64_12.dll', 'cudart64_12.dll', 'zlibwapi.dll',
    'cudnn64_9.dll', 'cudnn_adv64_9.dll', 'cudnn_cnn64_9.dll', 'cudnn_graph64_9.dll',
    'cudnn_heuristic64_9.dll', 'cudnn_ops64_9.dll',
    'cudnn_engines_precompiled64_9.dll', 'cudnn_engines_runtime_compiled64_9.dll',
}
CUDA_NOTICE = """SRTCONV GPU 가속 팩 (선택 설치)

이 zip 의 DLL 들을 SRTCONV\\_internal\\ 폴더 안에 넣으면 NVIDIA GPU(CUDA 12, 드라이버 525 이상)로
음성 인식과 번역이 가속됩니다. GPU 가 없으면 필요 없습니다.

포함 파일: NVIDIA CUDA Runtime / cuBLAS 12, cuDNN 9, zlibwapi
라이선스:
  - CUDA Toolkit EULA        https://docs.nvidia.com/cuda/eula/index.html
  - cuDNN Software License   https://docs.nvidia.com/deeplearning/cudnn/sla/index.html
  - zlib License             https://zlib.net/zlib_license.html
이 라이브러리들은 NVIDIA 가 애플리케이션과 함께 재배포를 허용한 런타임 구성 요소입니다.
"""
MODEL_NOTICE = """SRTCONV 오프라인 번역 모델 (M2M100_418M, CTranslate2 int8 변환본)

압축을 풀어 나온 models 폴더를 SRTCONV\\ 안에 넣으세요. (SRTCONV\\models\\m2m100_418M-ct2-int8\\model.bin)
원본: https://huggingface.co/facebook/m2m100_418M  (MIT License, Meta AI)
"""


def add_tree(zf, folder, arc_root, skip=None):
    for path in sorted(folder.rglob('*')):
        if path.is_dir():
            continue
        rel = path.relative_to(folder)
        if skip and skip(rel):
            continue
        zf.write(path, str(Path(arc_root) / rel))


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    if not (DIST / 'SRTCONV.exe').exists():
        print('dist/SRTCONV/SRTCONV.exe 가 없습니다. 먼저 build.cmd 를 실행하세요.')
        return 1
    OUT.mkdir(exist_ok=True)
    internal = DIST / '_internal'

    base = OUT / f'SRTCONV-{version}-win64.zip'
    with zipfile.ZipFile(base, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        add_tree(zf, DIST, 'SRTCONV', skip=lambda rel: (
            rel.parts[0] == 'models' or (rel.parts[0] == '_internal' and len(rel.parts) == 2 and rel.name in CUDA_DLLS)))
    print('본체:', base, f'{base.stat().st_size / 1e6:.0f} MB')

    cuda = OUT / f'SRTCONV-{version}-cuda-pack.zip'
    with zipfile.ZipFile(cuda, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        missing = []
        for name in sorted(CUDA_DLLS):
            path = internal / name
            if path.exists():
                zf.write(path, name)
            else:
                missing.append(name)
        zf.writestr('README-CUDA.txt', CUDA_NOTICE)
    print('CUDA 팩:', cuda, f'{cuda.stat().st_size / 1e6:.0f} MB', ('누락: ' + ', '.join(missing)) if missing else '')

    model_dir = DIST / 'models' / 'm2m100_418M-ct2-int8'
    if model_dir.exists():
        model = OUT / f'SRTCONV-{version}-model-m2m100.zip'
        with zipfile.ZipFile(model, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            add_tree(zf, model_dir, 'models/m2m100_418M-ct2-int8')
            zf.writestr('README-MODEL.txt', MODEL_NOTICE)
        print('모델:', model, f'{model.stat().st_size / 1e6:.0f} MB')
    else:
        print('models/m2m100_418M-ct2-int8 가 dist 에 없어 모델 zip 을 건너뜁니다.')
    for path in OUT.glob(f'SRTCONV-{version}-*.zip'):
        if path.stat().st_size > 2 * 1024 ** 3:
            print(f'경고: {path.name} 이 2GiB 를 넘어 GitHub 릴리스에 올릴 수 없습니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
