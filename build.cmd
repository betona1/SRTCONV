@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
  echo Python 3.12 를 찾을 수 없습니다: %PY%
  pause & exit /b 1
)
echo [1/4] 단위 테스트
"%PY%" -m unittest discover -s tests || (echo 테스트 실패 & pause & exit /b 1)
echo [2/4] 아이콘 생성 (바브 캐릭터)
"%PY%" build_tools\make_icon.py
echo [3/4] PyInstaller 빌드 (몇 분 걸립니다)
"%PY%" -m PyInstaller build_tools\SRTCONV.spec --noconfirm --distpath dist --workpath build || (echo 빌드 실패 & pause & exit /b 1)
echo [4/4] 오프라인 번역 모델·문서 복사
if exist models\m2m100_418M-ct2-int8 (
  robocopy models\m2m100_418M-ct2-int8 dist\SRTCONV\models\m2m100_418M-ct2-int8 /E /NFL /NDL /NJH /NJS >nul
) else (
  echo   models\m2m100_418M-ct2-int8 가 없어 오프라인 번역 모델을 건너뜁니다. (README 의 변환 명령 참고)
)
copy /Y README.md dist\SRTCONV\README.md >nul
copy /Y LICENSE dist\SRTCONV\LICENSE >nul
copy /Y THIRD_PARTY_NOTICES.md dist\SRTCONV\THIRD_PARTY_NOTICES.md >nul
echo.
echo 완료: dist\SRTCONV\SRTCONV.exe
pause
