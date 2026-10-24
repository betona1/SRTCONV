# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 스펙: SRTCONV.exe(GUI) + SRTCONV-cli.exe(콘솔) 를 한 폴더(onedir)에 만듭니다.
실행: python -m PyInstaller build_tools/SRTCONV.spec --noconfirm  (프로젝트 루트에서)
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SITE = Path(sys.prefix) / 'Lib' / 'site-packages'

# CUDA / cuDNN 런타임 DLL: ctranslate2 GPU 실행에 필요. torch 가 설치돼 있으면 그 안의 DLL 을 복사합니다.
CUDA_DLLS = [
    'cublas64_12.dll', 'cublasLt64_12.dll', 'cudart64_12.dll', 'zlibwapi.dll',
    'cudnn64_9.dll', 'cudnn_adv64_9.dll', 'cudnn_cnn64_9.dll', 'cudnn_graph64_9.dll',
    'cudnn_heuristic64_9.dll', 'cudnn_ops64_9.dll',
    'cudnn_engines_precompiled64_9.dll', 'cudnn_engines_runtime_compiled64_9.dll',
]
binaries = []
for name in CUDA_DLLS:
    for folder in (SITE / 'torch' / 'lib', SITE / 'nvidia' / 'cublas' / 'bin', SITE / 'nvidia' / 'cudnn' / 'bin',
                   SITE / 'nvidia' / 'cuda_runtime' / 'bin'):
        candidate = folder / name
        if candidate.exists():
            binaries.append((str(candidate), '.'))
            break
    else:
        print(f'[spec] CUDA DLL 없음 (CPU 전용 빌드가 됩니다): {name}')

datas = []
if (ROOT / 'build_tools' / 'SRTCONV.png').exists():
    datas.append((str(ROOT / 'build_tools' / 'SRTCONV.png'), 'assets'))
datas += collect_data_files('faster_whisper')      # silero VAD onnx 모델 등
datas += collect_data_files('deep_translator')

hiddenimports = (
    collect_submodules('faster_whisper') + collect_submodules('ctranslate2') + collect_submodules('deep_translator')
    + ['sentencepiece', 'onnxruntime', 'av', 'tokenizers', 'huggingface_hub', 'tqdm', 'numpy']
)

excludes = [
    'torch', 'torchaudio', 'torchvision', 'torchcodec', 'torchmetrics', 'torch_audiomentations', 'torch_pitch_shift',
    'transformers', 'matplotlib', 'scipy', 'pandas', 'IPython', 'jupyter', 'notebook', 'PyQt5', 'PyQt6', 'tkinter',
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.Qt3DCore', 'PySide6.QtQuick', 'PySide6.QtQml',
    'PySide6.QtMultimedia', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtPdf', 'PySide6.QtBluetooth',
    'pytest', 'unittest',
]

icon = str(ROOT / 'build_tools' / 'SRTCONV.ico')
if not os.path.exists(icon):
    icon = None

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
# PyInstaller 가 의존성 추적으로 torch\lib 의 CUDA DLL 을 중복 수집하므로 제거 (루트에 이미 복사됨)
a.binaries = [b for b in a.binaries if not b[0].replace('\\', '/').startswith('torch/')]
a.datas = [d for d in a.datas if not d[0].replace('\\', '/').startswith('torch/')]
pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='SRTCONV',
    debug=False, strip=False, upx=False,
    console=False,
    icon=icon,
)
exe_cli = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='SRTCONV-cli',
    debug=False, strip=False, upx=False,
    console=True,
    icon=icon,
)
coll = COLLECT(
    exe_gui, exe_cli, a.binaries, a.datas,
    strip=False, upx=False,
    name='SRTCONV',
)
