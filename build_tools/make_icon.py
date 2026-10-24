"""SRTCONV.ico / SRTCONV.png 생성.
베이블링 캐릭터 '바브'(말풍선 버전, build_tools/vave_speech_bubble.png)를 둥근 배경 위에 올리고
말풍선 안에 'SRT' 글자를 넣습니다. 원본: E:/app/vaveling/assets/images/vave/lv1/vave_27_speech_bubble.png
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor, QFont, QPen, QLinearGradient, QPainterPath

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'vave_speech_bubble.png'
OUT_PNG = HERE / 'SRTCONV.png'
OUT_ICO = HERE / 'SRTCONV.ico'
SIZES = [256, 128, 64, 48, 32, 16]


def render(size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.TextAntialiasing)
    # 둥근 배경 (파란 그라데이션)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor('#5B8DEF'))
    grad.setColorAt(1, QColor('#1E3A8A'))
    p.setBrush(grad)
    p.setPen(Qt.NoPen)
    radius = size * 0.22
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    # 캐릭터: 원본 비율 유지, 가로를 꽉 채우고 아래쪽 정렬
    char = QImage(str(SOURCE)).convertToFormat(QImage.Format_ARGB32)
    target_w = size * 0.96
    scale = target_w / char.width()
    target_h = char.height() * scale
    x = (size - target_w) / 2
    y = size - target_h - size * 0.01
    p.drawImage(QRectF(x, y, target_w, target_h), char)
    # 말풍선 안에 SRT 글자 (말풍선은 원본 기준 대략 x 3~176, y 117~172 영역)
    bubble = QRectF(x + 6 * scale, y + 118 * scale, 170 * scale, 50 * scale)
    font = QFont('Segoe UI', max(5, int(size * 0.17)), QFont.Black)
    p.setFont(font)
    p.setPen(QPen(QColor('#1E3A8A')))
    p.drawText(bubble, Qt.AlignCenter, 'SRT')
    p.end()
    return img


def main():
    QGuiApplication(sys.argv)
    if not SOURCE.exists():
        print(f'원본 캐릭터 이미지가 없습니다: {SOURCE}')
        return 1
    big = render(256)
    big.save(str(OUT_PNG))
    try:
        from PIL import Image
        Image.open(OUT_PNG).save(OUT_ICO, sizes=[(s, s) for s in SIZES])
        print('ico (multi-size):', OUT_ICO)
    except ImportError:
        big.save(str(OUT_ICO), 'ICO')
        print('ico (single 256):', OUT_ICO)
    print('png:', OUT_PNG)
    return 0


if __name__ == '__main__':
    sys.exit(main())
