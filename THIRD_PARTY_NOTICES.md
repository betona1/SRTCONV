# Third-Party Notices / 서드파티 고지

SRTCONV 자체는 GPL-3.0 으로 배포됩니다 (LICENSE 참고). 아래 구성 요소는 각자의 라이선스를 따릅니다.

## 실행 파일(배포본)에 포함되는 구성 요소

| 구성 요소 | 라이선스 | 비고 |
|---|---|---|
| Python 3.12 | PSF License | |
| PySide6 (Qt for Python) 6.8 | LGPL-3.0 | 동적 링크(별도 DLL)로 사용. 사용자는 Qt 라이브러리를 교체할 수 있습니다. https://www.qt.io/licensing |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| Silero VAD (faster-whisper 동봉 onnx) | MIT | https://github.com/snakers4/silero-vad |
| onnxruntime | MIT | |
| PyAV | BSD-3-Clause | https://github.com/PyAV-Org/PyAV |
| FFmpeg (PyAV 동봉 DLL) | **GPL-2.0-or-later** | libx264, libx265 를 포함한 GPL 빌드입니다. 이 때문에 SRTCONV 배포본 전체가 GPL 호환 조건으로 배포됩니다. https://ffmpeg.org/legal.html |
| libx264 / libx265 | GPL-2.0 / GPL-2.0 | FFmpeg 에 포함 |
| sentencepiece | Apache-2.0 | |
| tokenizers, huggingface_hub | Apache-2.0 | |
| deep-translator | MIT | 온라인 보조 엔진. Google 번역은 비공식 무료 엔드포인트를 사용하므로 Google 약관을 확인하세요. MyMemory 는 https://mymemory.translated.net 이용 약관을 따릅니다. |
| numpy | BSD-3-Clause | |
| tqdm | MPL-2.0 AND MIT | |
| PyInstaller | GPL-2.0-or-later **with bootloader exception** | 빌드 결과물에 라이선스 제약을 두지 않습니다. |
| Pillow (아이콘 생성 도구에서만 사용) | MIT-CMU | 배포본에 포함되지 않음 |

## 별도 내려받는 모델·런타임 (릴리스에 분리 제공)

| 구성 요소 | 라이선스 | 비고 |
|---|---|---|
| Whisper 모델 (Systran/faster-whisper-large-v3 등) | MIT | OpenAI Whisper 가중치. 앱이 HuggingFace 에서 내려받거나 사용자가 미리 받아 둡니다. |
| M2M100_418M (facebook/m2m100_418M, CTranslate2 int8 변환본) | **MIT** | 기본 오프라인 번역 모델. 상업 이용 가능. https://huggingface.co/facebook/m2m100_418M |
| NLLB-200 (facebook/nllb-200-distilled-600M) | **CC-BY-NC-4.0 (비상업 전용)** | **배포본에 포함하지 않습니다.** 비상업 용도의 사용자가 직접 변환해 `models/` 에 넣은 경우에만 앱이 인식합니다. |
| NVIDIA CUDA Runtime / cuBLAS 12 | NVIDIA CUDA Toolkit EULA | GPU 가속 팩(선택 설치)에 포함. 재배포 허용 목록에 있는 런타임 라이브러리입니다. https://docs.nvidia.com/cuda/eula/index.html |
| NVIDIA cuDNN 9 | NVIDIA cuDNN Software License Agreement | GPU 가속 팩(선택 설치)에 포함. https://docs.nvidia.com/deeplearning/cudnn/sla/index.html |
| zlibwapi | zlib License | cuDNN 의존성 |

## 아트워크

- 앱 아이콘의 캐릭터 '바브'는 베이블링(Vaveling) 앱(betona1)의 자산이며, SRTCONV 프로젝트의 아이콘 용도로만 사용을 허락합니다. 캐릭터 이미지 자체는 GPL-3.0 의 적용 대상이 아니며, 별도 허락 없이 다른 용도로 재사용할 수 없습니다.

## 라이선스 전문

각 구성 요소의 라이선스 전문은 배포본의 `_internal` 폴더 안 `*.dist-info/LICENSE*` 및 `PySide6/` 폴더, 그리고 위 링크에서 확인할 수 있습니다.
