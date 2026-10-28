"""SRT 보기 창: 여러 SRT(원문·번역본)를 같은 타이밍 기준으로 나란히 보여주고, 수정·저장할 수 있습니다."""
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QMessageBox, QCheckBox,
)

from . import languages
from .srt_utils import Cue, read_srt, write_srt, timestamp, unique_path

FIXED_COLUMNS = 2   # 번호, 시간


def column_title(path):
    """파일 이름의 _자막_xx 꼬리표로 언어 이름을 만듭니다."""
    match = re.search(r'_자막_([A-Za-z\-]+)(?:_\d+)?$', Path(path).stem)
    if match:
        name = languages.display_name(match.group(1))
        return name if name != match.group(1) else match.group(1)
    return Path(path).stem


class SrtViewerDialog(QDialog):
    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.setWindowTitle('SRT 자막 보기')
        self.resize(1100, 680)
        self.files = []          # [Path, ...]  열 순서
        self.cues = []           # [[Cue, ...], ...] 파일별
        self.modified = set()    # 수정된 열 인덱스
        self._loading = False

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('자막 내용 검색 (입력하면 해당 줄만 표시)')
        self.search.textChanged.connect(self._apply_filter)
        self.btn_open = QPushButton('SRT 파일 열기…')
        self.btn_open.clicked.connect(self._open_file)
        self.btn_save = QPushButton('수정 저장')
        self.btn_save.setObjectName('primary')
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.save)
        self.btn_save_as = QPushButton('다른 이름으로 저장…')
        self.btn_save_as.setToolTip('지금 보이는 자막(수정 내용 포함)을 원하는 위치에 새 파일로 저장합니다.')
        self.btn_save_as.clicked.connect(self.save_as)
        self.chk_wrap = QCheckBox('줄바꿈')
        self.chk_wrap.setChecked(True)
        self.chk_wrap.toggled.connect(self._toggle_wrap)
        top.addWidget(self.search, 1)
        top.addWidget(self.chk_wrap)
        top.addWidget(self.btn_open)
        top.addWidget(self.btn_save)
        top.addWidget(self.btn_save_as)
        layout.addLayout(top)

        self.table = QTableWidget(0, FIXED_COLUMNS)
        self.table.setHorizontalHeaderLabels(['#', '시간'])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setWordWrap(True)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        self.info = QLabel('')
        self.info.setObjectName('subtitle')
        layout.addWidget(self.info)

        for path in files:
            self.add_file(path)

    # ---------- 파일 ----------
    def add_file(self, path):
        path = Path(path)
        if path in self.files:
            return
        try:
            cues = read_srt(path)
        except Exception as error:
            QMessageBox.warning(self, 'SRT 보기', f'파일을 읽지 못했습니다:\n{path}\n{error}')
            return
        self.files.append(path)
        self.cues.append(cues)
        self._rebuild()

    def _open_file(self):
        start = str(self.files[0].parent) if self.files else ''
        names, _ = QFileDialog.getOpenFileNames(self, 'SRT 파일 열기', start, 'SRT 자막 (*.srt);;모든 파일 (*.*)')
        for name in names:
            self.add_file(name)

    # ---------- 표 ----------
    def _rebuild(self):
        self._loading = True
        self.table.setSortingEnabled(False)
        rows = max((len(c) for c in self.cues), default=0)
        self.table.setRowCount(rows)
        self.table.setColumnCount(FIXED_COLUMNS + len(self.files))
        headers = ['#', '시간'] + [column_title(p) for p in self.files]
        self.table.setHorizontalHeaderLabels(headers)
        for col, path in enumerate(self.files):
            item = self.table.horizontalHeaderItem(FIXED_COLUMNS + col)
            item.setToolTip(str(path))
        base = max(self.cues, key=len) if self.cues else []
        mono = QFont('Consolas')
        for row in range(rows):
            cue = base[row]
            num = QTableWidgetItem(str(row + 1))
            num.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            num.setTextAlignment(Qt.AlignCenter)
            time = QTableWidgetItem(f'{timestamp(cue.start)} → {timestamp(cue.end)}')
            time.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            time.setFont(mono)
            time.setForeground(QColor('#6B7280'))
            self.table.setItem(row, 0, num)
            self.table.setItem(row, 1, time)
            for col, cues in enumerate(self.cues):
                text = cues[row].text if row < len(cues) else ''
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                if row >= len(cues):
                    item.setBackground(QColor('#F3F4F6'))
                self.table.setItem(row, FIXED_COLUMNS + col, item)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for col in range(len(self.files)):
            hh.setSectionResizeMode(FIXED_COLUMNS + col, QHeaderView.Stretch)
        self.table.resizeRowsToContents()
        self._loading = False
        self._apply_filter(self.search.text())
        self._update_info()

    def _update_info(self):
        parts = [f'{column_title(p)} {len(c)}줄' for p, c in zip(self.files, self.cues)]
        suffix = '  ·  수정됨 (저장 필요)' if self.modified else ''
        self.info.setText('  |  '.join(parts) + suffix + '    셀을 두 번 클릭하면 바로 수정할 수 있습니다.')

    def _toggle_wrap(self, on):
        self.table.setWordWrap(on)
        self.table.resizeRowsToContents()

    def _apply_filter(self, text):
        needle = text.strip().lower()
        for row in range(self.table.rowCount()):
            show = True
            if needle:
                show = any(needle in (self.table.item(row, c).text().lower() if self.table.item(row, c) else '')
                           for c in range(FIXED_COLUMNS, self.table.columnCount()))
            self.table.setRowHidden(row, not show)

    # ---------- 수정/저장 ----------
    def _on_item_changed(self, item):
        if self._loading or item.column() < FIXED_COLUMNS:
            return
        col = item.column() - FIXED_COLUMNS
        row = item.row()
        cues = self.cues[col]
        text = item.text().strip()
        if row < len(cues):
            if cues[row].text == text:
                return
            cues[row].text = text
        else:
            # 짧은 파일에 새 줄 추가: 가장 긴 파일의 타이밍을 사용
            base = max(self.cues, key=len)
            while len(cues) < row:
                cues.append(Cue(base[len(cues)].start, base[len(cues)].end, ''))
            cues.append(Cue(base[row].start, base[row].end, text))
        self.modified.add(col)
        self.btn_save.setEnabled(True)
        self._update_info()

    def save(self):
        saved = []
        for col in sorted(self.modified):
            path = self.files[col]
            try:
                write_srt(path, [c for c in self.cues[col] if c.text])
                saved.append(path.name)
            except Exception as error:
                QMessageBox.warning(self, 'SRT 보기', f'저장 실패: {path}\n{error}')
                return
        self.modified.clear()
        self.btn_save.setEnabled(False)
        self._update_info()
        if saved:
            self.info.setText('저장 완료: ' + ', '.join(saved))

    def save_copies(self, directory):
        """모든 열을 directory 에 새 파일로 저장합니다 (덮어쓰지 않음). 저장한 경로 목록을 돌려줍니다."""
        saved = []
        for col, path in enumerate(self.files):
            target = unique_path(directory, path.name)
            write_srt(target, [c for c in self.cues[col] if c.text])
            saved.append(target)
        return saved

    def save_as(self):
        if not self.files:
            return
        from .pipeline import downloads_dir
        start = str(downloads_dir())
        if len(self.files) == 1:
            name, _ = QFileDialog.getSaveFileName(self, '다른 이름으로 저장', str(Path(start) / self.files[0].name),
                                                  'SRT 자막 (*.srt)')
            if not name:
                return
            try:
                write_srt(name, [c for c in self.cues[0] if c.text])
            except Exception as error:
                QMessageBox.warning(self, 'SRT 보기', f'저장 실패: {name}\n{error}')
                return
            saved = [Path(name)]
        else:
            folder = QFileDialog.getExistingDirectory(self, f'자막 {len(self.files)}개를 저장할 폴더 선택', start)
            if not folder:
                return
            try:
                saved = self.save_copies(folder)
            except Exception as error:
                QMessageBox.warning(self, 'SRT 보기', f'저장 실패: {error}')
                return
        self.info.setText(f'저장 완료 ({saved[0].parent}): ' + ', '.join(p.name for p in saved))

    def closeEvent(self, event):
        if self.modified:
            answer = QMessageBox.question(self, 'SRT 보기', '수정한 내용을 저장할까요?',
                                          QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Yes:
                self.save()
        super().closeEvent(event)
