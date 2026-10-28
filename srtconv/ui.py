"""SRTCONV 메인 창: 끌어다 놓기, 파일 목록, 설정, 진행률, 로그."""
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QUrl, QSize
import sys

from PySide6.QtGui import QDesktopServices, QIcon, QDragEnterEvent, QDropEvent


def _asset(name):
    """빌드 번들(assets/) 또는 소스 트리(build_tools/)에서 리소스 파일을 찾습니다."""
    bases = []
    if getattr(sys, 'frozen', False):
        bases.append(Path(sys._MEIPASS) / 'assets')
    bases.append(Path(__file__).resolve().parents[1] / 'build_tools')
    for base in bases:
        if (base / name).exists():
            return base / name
    return None
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QComboBox, QCheckBox, QLineEdit,
    QGroupBox, QListWidget, QListWidgetItem, QListView, QPlainTextEdit, QFileDialog, QMessageBox,
    QAbstractItemView, QScrollArea, QToolButton,
)

from . import APP_NAME, APP_VERSION, ORG_NAME, languages, transcriber, translator
from .pipeline import Options, is_media, MEDIA_EXTENSIONS, OUTPUT_MODES, downloads_dir, resolve_output_dir, export_files
from .worker import Worker, ModelCache
from .viewer import SrtViewerDialog

STYLE = """
QWidget { color: #1F2937; font-family: 'Malgun Gothic', 'Segoe UI', sans-serif; font-size: 10pt; }
QMainWindow { background: #F5F7FB; }
QScrollArea { background: transparent; border: none; }
QLabel#title { font-size: 20pt; font-weight: 700; color: #1E3A8A; }
QLabel#subtitle { color: #6B7280; }
QFrame#drop { border: 2px dashed #93A3C9; border-radius: 14px; background: #FFFFFF; }
QFrame#drop[active="true"] { border-color: #2563EB; background: #EFF6FF; }
QLabel#dropText { font-size: 13pt; color: #374151; }
QLabel#dropHint { color: #6B7280; }
QGroupBox { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px; margin-top: 12px; padding: 12px 10px 8px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #1E3A8A; }
QPushButton { background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 8px; padding: 6px 14px; }
QPushButton:hover { background: #F3F4F6; }
QPushButton:disabled { color: #9CA3AF; background: #F9FAFB; }
QPushButton#primary { background: #2563EB; color: white; border: none; font-weight: 600; padding: 9px 22px; }
QPushButton#primary:hover { background: #1D4ED8; }
QPushButton#primary:disabled { background: #93C5FD; }
QPushButton#danger { background: #FFFFFF; color: #B91C1C; border: 1px solid #FCA5A5; }
QPushButton#danger:hover { background: #FEF2F2; }
QTableWidget, QListWidget, QPlainTextEdit, QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; }
QTableWidget { gridline-color: #F3F4F6; selection-background-color: #DBEAFE; selection-color: #1F2937; }
QHeaderView::section { background: #F9FAFB; border: none; border-bottom: 1px solid #E5E7EB; padding: 6px; font-weight: 600; color: #374151; }
QComboBox, QLineEdit { padding: 5px 8px; }
QComboBox::drop-down { border: none; width: 22px; }
QProgressBar { border: 1px solid #E5E7EB; border-radius: 6px; background: #F3F4F6; text-align: center; height: 16px; }
QProgressBar::chunk { background: #3B82F6; border-radius: 5px; }
QPlainTextEdit { font-family: Consolas, 'D2Coding', monospace; font-size: 9pt; color: #374151; }
QListWidget::item { padding: 2px 6px; }
QCheckBox { spacing: 6px; }
"""


class DropZone(QFrame):
    def __init__(self, on_files, parent=None):
        super().__init__(parent)
        self.setObjectName('drop')
        self.setAcceptDrops(True)
        self.on_files = on_files
        self.setMinimumHeight(92)
        self.setMaximumHeight(120)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        text = QLabel('🎬  영상·음성 파일을 여기에 끌어다 놓으세요')
        text.setObjectName('dropText')
        text.setAlignment(Qt.AlignCenter)
        hint = QLabel('또는 클릭하여 파일 선택  ·  mp4, mkv, mov, avi, webm, mp3, wav, m4a 등')
        hint.setObjectName('dropHint')
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(text)
        layout.addWidget(hint)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window().choose_files()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty('active', True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty('active', False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.dragLeaveEvent(event)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        self.on_files(paths)
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    COL_FILE, COL_STATUS, COL_PROGRESS, COL_LANG, COL_RESULT = range(5)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} {APP_VERSION} - 자막 생성·번역')
        icon_path = _asset('SRTCONV.png')
        if icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(960, 680)
        self.resize(1180, 820)
        self.setAcceptDrops(True)
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.cache = ModelCache()
        self.worker = None
        self.results = {}
        self._build()
        self._load_settings()
        self.setStyleSheet(STYLE)

    # ---------- UI 구성 ----------
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName('title')
        subtitle = QLabel('로컬 Whisper 자막 생성 + 다국어 자동 번역 (언어 자동 감지)')
        subtitle.setObjectName('subtitle')
        header.addWidget(title)
        header.addSpacing(12)
        header.addWidget(subtitle, 1, Qt.AlignBottom)
        self.gpu_label = QLabel('GPU 사용 가능' if transcriber.cuda_available() else 'CPU 모드')
        self.gpu_label.setObjectName('subtitle')
        header.addWidget(self.gpu_label, 0, Qt.AlignBottom)
        outer.addLayout(header)

        self.drop = DropZone(self.add_paths)
        outer.addWidget(self.drop)

        body = QHBoxLayout()
        body.setSpacing(12)
        outer.addLayout(body, 1)

        # 왼쪽: 파일 목록
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        buttons = QHBoxLayout()
        self.btn_add = QPushButton('파일 추가')
        self.btn_add.clicked.connect(self.choose_files)
        self.btn_folder = QPushButton('폴더 추가')
        self.btn_folder.clicked.connect(self.choose_folder)
        self.btn_remove = QPushButton('선택 제거')
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_clear = QPushButton('목록 비우기')
        self.btn_clear.clicked.connect(self.clear_list)
        for b in (self.btn_add, self.btn_folder, self.btn_remove, self.btn_clear):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.btn_view = QPushButton('자막 보기')
        self.btn_view.setToolTip('선택한 파일의 원문·번역 SRT 를 나란히 봅니다. 완료된 행을 두 번 클릭해도 열립니다.')
        self.btn_view.clicked.connect(self.view_srt)
        self.btn_view_file = QPushButton('SRT 열기…')
        self.btn_view_file.setToolTip('아무 SRT 파일이나 골라서 봅니다.')
        self.btn_view_file.clicked.connect(self.view_srt_file)
        self.btn_open_folder = QPushButton('결과 폴더 열기')
        self.btn_open_folder.setToolTip('선택한 파일의 자막이 저장된 폴더를 탐색기로 엽니다.')
        self.btn_open_folder.clicked.connect(self.open_result_folder)
        self.btn_save_to = QPushButton('다른 폴더에 저장…')
        self.btn_save_to.setToolTip('완성된 자막 파일을 원하는 폴더(예: 다운로드)에 복사해 저장합니다.')
        self.btn_save_to.clicked.connect(self.save_results_to)
        left_layout.addLayout(buttons)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['파일', '상태', '진행률', '언어', '결과'])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_FILE, QHeaderView.Stretch)
        hh.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_PROGRESS, QHeaderView.Fixed)
        hh.setSectionResizeMode(self.COL_LANG, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_RESULT, QHeaderView.Stretch)
        self.table.setColumnWidth(self.COL_PROGRESS, 120)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._open_row_folder)
        left_layout.addWidget(self.table, 1)
        results = QHBoxLayout()
        result_label = QLabel('결과 자막')
        result_label.setObjectName('subtitle')
        results.addWidget(result_label)
        for b in (self.btn_view, self.btn_view_file, self.btn_open_folder, self.btn_save_to):
            results.addWidget(b)
        results.addStretch(1)
        left_layout.addLayout(results)
        body.addWidget(left, 1)

        # 오른쪽: 설정 (높이가 모자라면 스크롤)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 6, 0)
        scroll = QScrollArea()
        scroll.setWidget(right)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(384)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        right.setAutoFillBackground(False)

        g1 = QGroupBox('음성 인식')
        f1 = QGridLayout(g1)
        f1.setVerticalSpacing(8)
        f1.setColumnStretch(1, 1)
        self.cmb_source = QComboBox()
        self.cmb_source.addItem('자동 감지 (권장)', languages.AUTO)
        for lang in languages.LANGUAGES:
            if lang.code == 'zh-TW':
                continue
            self.cmb_source.addItem(lang.name_ko, lang.code)
        self.cmb_model = QComboBox()
        self.cmb_model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_model.setMinimumContentsLength(16)
        self._fill_models()
        self.cmb_device = QComboBox()
        self.cmb_device.addItem('자동 (GPU 우선)', 'auto')
        self.cmb_device.addItem('GPU (CUDA)', 'cuda')
        self.cmb_device.addItem('CPU', 'cpu')
        self.chk_download = QCheckBox('모델이 없으면 자동 다운로드')
        f1.addWidget(QLabel('음성 언어'), 0, 0)
        f1.addWidget(self.cmb_source, 0, 1)
        f1.addWidget(QLabel('모델'), 1, 0)
        f1.addWidget(self.cmb_model, 1, 1)
        f1.addWidget(QLabel('장치'), 2, 0)
        f1.addWidget(self.cmb_device, 2, 1)
        f1.addWidget(self.chk_download, 3, 0, 1, 2)
        right_layout.addWidget(g1)

        g2 = QGroupBox('자동 번역')
        f2 = QGridLayout(g2)
        f2.setVerticalSpacing(8)
        self.chk_translate = QCheckBox('번역 자막도 함께 만들기')
        self.chk_translate.toggled.connect(self._toggle_translate)
        self.targets_box = QWidget()
        grid = QGridLayout(self.targets_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        self.target_checks = {}
        for index, lang in enumerate(languages.LANGUAGES):
            box = QCheckBox(lang.name_ko)
            self.target_checks[lang.code] = box
            grid.addWidget(box, index // 3, index % 3)
        self.cmb_engine = QComboBox()
        for key, name in translator.ENGINES.items():
            self.cmb_engine.addItem(name, key)
        found = translator.find_offline_model()
        if found:
            kind = 'M2M100 (MIT)' if found[1] == 'm2m100' else 'NLLB (비상업용 전용)'
            offline_text = f'오프라인 번역 모델: {kind} 사용 가능'
        else:
            offline_text = '오프라인 번역 모델 없음 → 온라인 엔진 사용 (models 폴더에 모델을 넣으면 오프라인 가능)'
        self.nllb_label = QLabel(offline_text)
        self.nllb_label.setObjectName('subtitle')
        self.nllb_label.setWordWrap(True)
        f2.setColumnStretch(1, 1)
        f2.addWidget(self.chk_translate, 0, 0, 1, 2)
        f2.addWidget(QLabel('대상 언어 (여러 개 선택 가능)'), 1, 0, 1, 2)
        f2.addWidget(self.targets_box, 2, 0, 1, 2)
        f2.addWidget(QLabel('번역 엔진'), 3, 0)
        f2.addWidget(self.cmb_engine, 3, 1)
        f2.addWidget(self.nllb_label, 4, 0, 1, 2)

        g3 = QGroupBox('저장 위치')
        f3 = QGridLayout(g3)
        f3.setVerticalSpacing(8)
        f3.setColumnStretch(1, 1)
        self.cmb_output_mode = QComboBox()
        for key, name in OUTPUT_MODES.items():
            self.cmb_output_mode.addItem(name, key)
        self.cmb_output_mode.currentIndexChanged.connect(self._update_output_mode)
        self.edt_output = QLineEdit()
        self.edt_output.setPlaceholderText('폴더를 지정하세요')
        self.edt_output.textChanged.connect(self._update_output_mode)
        self.btn_output = QToolButton()
        self.btn_output.setText('…')
        self.btn_output.clicked.connect(self.choose_output)
        self.lbl_output_path = QLabel('')
        self.lbl_output_path.setObjectName('subtitle')
        self.lbl_output_path.setWordWrap(True)
        self.cmb_maxlen = QComboBox()
        for n in (32, 38, 45, 55, 70):
            self.cmb_maxlen.addItem(f'{n}자', n)
        f3.addWidget(QLabel('저장 폴더'), 0, 0)
        f3.addWidget(self.cmb_output_mode, 0, 1)
        row = QHBoxLayout()
        row.addWidget(self.edt_output, 1)
        row.addWidget(self.btn_output)
        f3.addLayout(row, 1, 0, 1, 2)
        f3.addWidget(self.lbl_output_path, 2, 0, 1, 2)
        f3.addWidget(QLabel('자막 한 줄 최대'), 3, 0)
        f3.addWidget(self.cmb_maxlen, 3, 1)
        right_layout.addWidget(g3)
        right_layout.addWidget(g2)
        right_layout.addStretch(1)
        body.addWidget(scroll)

        # 하단: 진행률 + 버튼
        bottom = QHBoxLayout()
        self.total_bar = QProgressBar()
        self.total_bar.setRange(0, 100)
        self.total_bar.setValue(0)
        self.status_label = QLabel('대기 중')
        self.status_label.setObjectName('subtitle')
        self.btn_start = QPushButton('자막 만들기 시작')
        self.btn_start.setObjectName('primary')
        self.btn_start.clicked.connect(self.start)
        self.btn_stop = QPushButton('중지')
        self.btn_stop.setObjectName('danger')
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        bottom.addWidget(self.status_label)
        bottom.addWidget(self.total_bar, 1)
        bottom.addWidget(self.btn_start)
        bottom.addWidget(self.btn_stop)
        outer.addLayout(bottom)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(112)
        self.log_view.setPlaceholderText('진행 기록이 여기에 표시됩니다.')
        outer.addWidget(self.log_view)
        self._toggle_translate(False)

    def _fill_models(self):
        self.cmb_model.clear()
        for name, (_repo, desc) in transcriber.MODELS.items():
            mark = '' if transcriber.is_model_cached(name) else ' · 다운로드 필요'
            self.cmb_model.addItem(f'{name} · {desc}{mark}', name)
            self.cmb_model.setItemData(self.cmb_model.count() - 1, f'{name}: {desc}{mark}', Qt.ToolTipRole)

    # ---------- 설정 저장/복원 ----------
    def _load_settings(self):
        s = self.settings
        self._select(self.cmb_source, s.value('source', languages.AUTO))
        self._select(self.cmb_model, s.value('model', transcriber.DEFAULT_MODEL))
        self._select(self.cmb_device, s.value('device', 'auto'))
        self._select(self.cmb_engine, s.value('engine', 'auto'))
        self._select(self.cmb_maxlen, int(s.value('maxlen', 45)))
        self.chk_download.setChecked(s.value('download', 'false') in ('true', True))
        self.chk_translate.setChecked(s.value('translate', 'true') in ('true', True))
        targets = s.value('targets', ['ko'])
        if isinstance(targets, str):
            targets = [targets]
        for code, box in self.target_checks.items():
            box.setChecked(code in targets)
        self.edt_output.setText(s.value('output', ''))
        # 예전 버전: 출력 폴더가 적혀 있으면 '직접 지정' 으로 이어받습니다.
        default_mode = 'custom' if self.edt_output.text().strip() else 'source'
        self._select(self.cmb_output_mode, s.value('output_mode', default_mode))
        self._update_output_mode()

    def _save_settings(self):
        s = self.settings
        s.setValue('source', self.cmb_source.currentData())
        s.setValue('model', self.cmb_model.currentData())
        s.setValue('device', self.cmb_device.currentData())
        s.setValue('engine', self.cmb_engine.currentData())
        s.setValue('maxlen', self.cmb_maxlen.currentData())
        s.setValue('download', self.chk_download.isChecked())
        s.setValue('translate', self.chk_translate.isChecked())
        s.setValue('targets', self.selected_targets())
        s.setValue('output', self.edt_output.text())
        s.setValue('output_mode', self.cmb_output_mode.currentData())

    @staticmethod
    def _select(combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _toggle_translate(self, on):
        self.targets_box.setEnabled(on)
        self.cmb_engine.setEnabled(on)

    def selected_targets(self):
        return [code for code, box in self.target_checks.items() if box.isChecked()]

    # ---------- 저장 위치 ----------
    def output_mode(self):
        return self.cmb_output_mode.currentData() or 'source'

    def current_output_dir(self):
        """현재 설정으로 정해지는 저장 폴더 문자열. '' 이면 원본 파일 옆. ('ask' 는 시작할 때 고른 폴더)"""
        mode = self.output_mode()
        if mode == 'ask':
            return getattr(self, '_asked_output', '') or ''
        return resolve_output_dir(mode, self.edt_output.text())

    def _update_output_mode(self, *_):
        mode = self.output_mode()
        custom = mode == 'custom'
        self.edt_output.setVisible(custom)
        self.btn_output.setVisible(custom)
        if mode == 'source':
            text = '각 영상·음성 파일이 있는 폴더에 "파일이름_자막_언어.srt" 로 저장됩니다.'
        elif mode == 'downloads':
            text = f'저장 위치: {downloads_dir()}'
        elif mode == 'custom':
            folder = self.edt_output.text().strip()
            text = f'저장 위치: {folder}' if folder else '저장할 폴더를 … 버튼으로 고르세요. 비워 두면 원본 파일 옆에 저장됩니다.'
        else:
            text = '"자막 만들기 시작"을 누르면 저장할 폴더를 물어봅니다.'
        self.lbl_output_path.setText(text)

    def ask_output_dir(self):
        """'시작할 때마다 폴더 선택' 모드: 폴더 대화상자를 띄웁니다. 취소하면 None."""
        start = self.settings.value('askdir', '') or str(downloads_dir())
        folder = QFileDialog.getExistingDirectory(self, '자막을 저장할 폴더 선택', start)
        if not folder:
            return None
        self.settings.setValue('askdir', folder)
        self._asked_output = folder
        return folder

    def open_result_folder(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows and self.table.rowCount():
            rows = [self.table.rowCount() - 1]
        folder = None
        for row in rows:
            files = self._result_files(row)
            if files:
                folder = files[0].parent
                break
        if folder is None:
            out = self.current_output_dir()
            if out and Path(out).is_dir():
                folder = Path(out)
            elif rows:
                folder = Path(self.table.item(rows[0], self.COL_FILE).data(Qt.UserRole)).parent
        if folder is None:
            QMessageBox.information(self, APP_NAME, '열 폴더가 없습니다. 먼저 파일을 추가하세요.')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def save_results_to(self):
        """선택한(없으면 완료된 모든) 행의 자막 파일을 사용자가 고른 폴더에 복사합니다."""
        rows = sorted({i.row() for i in self.table.selectedIndexes()}) or list(range(self.table.rowCount()))
        files = []
        for row in rows:
            for f in self._result_files(row):
                if f not in files:
                    files.append(f)
        if not files:
            QMessageBox.information(self, APP_NAME, '저장할 자막 파일이 아직 없습니다.\n먼저 "자막 만들기 시작"으로 자막을 만드세요.')
            return
        start = self.settings.value('savedir', '') or str(downloads_dir())
        folder = QFileDialog.getExistingDirectory(self, f'자막 {len(files)}개를 저장할 폴더 선택', start)
        if not folder:
            return
        self.settings.setValue('savedir', folder)
        try:
            copied = export_files(files, folder)
        except Exception as error:
            QMessageBox.warning(self, APP_NAME, f'저장 실패: {error}')
            return
        for _src, dst in copied:
            self.log(f'저장: {dst}')
        self.status_label.setText(f'{len(copied)}개 파일을 {folder} 에 저장했습니다.')
        QMessageBox.information(self, APP_NAME, f'자막 {len(copied)}개를 저장했습니다.\n{folder}')

    def options(self):
        return Options(
            model=self.cmb_model.currentData(), device=self.cmb_device.currentData(),
            source_language=self.cmb_source.currentData(), translate=self.chk_translate.isChecked(),
            targets=self.selected_targets(), engine=self.cmb_engine.currentData(),
            output_dir=self.current_output_dir(), allow_download=self.chk_download.isChecked(),
            max_chars=int(self.cmb_maxlen.currentData()))

    # ---------- 파일 목록 ----------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])

    def add_paths(self, paths):
        existing = {self.table.item(r, self.COL_FILE).data(Qt.UserRole) for r in range(self.table.rowCount())}
        added = skipped = 0
        for raw in paths:
            p = Path(raw)
            candidates = sorted(x for x in p.iterdir() if x.is_file()) if p.is_dir() else [p]
            for f in candidates:
                if not is_media(f):
                    skipped += 1
                    continue
                key = str(f.resolve())
                if key in existing:
                    continue
                existing.add(key)
                self._add_row(f)
                added += 1
        if added or skipped:
            msg = f'{added}개 파일 추가'
            if skipped:
                msg += f', 지원하지 않는 파일 {skipped}개 제외'
            self.log(msg)

    def _add_row(self, path):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = QTableWidgetItem(path.name)
        name.setData(Qt.UserRole, str(path.resolve()))
        name.setToolTip(str(path))
        self.table.setItem(row, self.COL_FILE, name)
        self.table.setItem(row, self.COL_STATUS, QTableWidgetItem('대기'))
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        self.table.setCellWidget(row, self.COL_PROGRESS, bar)
        self.table.setItem(row, self.COL_LANG, QTableWidgetItem(''))
        self.table.setItem(row, self.COL_RESULT, QTableWidgetItem(''))

    def choose_files(self):
        pattern = ' '.join(f'*{e}' for e in sorted(MEDIA_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(self, '영상·음성 파일 선택', self.settings.value('lastdir', ''),
                                                f'영상·음성 ({pattern});;모든 파일 (*.*)')
        if files:
            self.settings.setValue('lastdir', str(Path(files[0]).parent))
            self.add_paths(files)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '폴더 선택', self.settings.value('lastdir', ''))
        if folder:
            self.settings.setValue('lastdir', folder)
            self.add_paths([folder])

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, '저장 폴더 선택', self.edt_output.text() or str(downloads_dir()))
        if folder:
            self.edt_output.setText(folder)

    def remove_selected(self):
        if self.worker and self.worker.isRunning():
            return
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def clear_list(self):
        if self.worker and self.worker.isRunning():
            return
        self.table.setRowCount(0)
        self.results.clear()

    def _result_files(self, row):
        """해당 행의 결과 SRT 목록. 결과가 없으면 원본 옆에 있는 같은 이름의 SRT 를 찾습니다."""
        result = self.results.get(row)
        if result and result.original:
            return [p for p in [result.original] + list(result.translated.values()) if p.exists()]
        item = self.table.item(row, self.COL_FILE)
        if not item:
            return []
        source = Path(item.data(Qt.UserRole))
        folders = [Path(self.current_output_dir() or source.parent), source.parent]
        for folder in folders:
            found = sorted(folder.glob(f'{source.stem}_자막_*.srt')) if folder.is_dir() else []
            if found:
                return found
        return []

    def _open_row_folder(self, index):
        files = self._result_files(index.row())
        if files:
            self.open_viewer(files)
            return
        item = self.table.item(index.row(), self.COL_FILE)
        if item:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(item.data(Qt.UserRole)).parent)))

    def view_srt(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows and self.table.rowCount():
            rows = [self.table.rowCount() - 1]
        files = []
        for row in rows:
            files.extend(self._result_files(row))
        if not files:
            QMessageBox.information(self, APP_NAME, '볼 수 있는 자막 파일이 아직 없습니다.\n'
                                    '먼저 자막을 만들거나 "SRT 열기…"로 파일을 고르세요.')
            return
        self.open_viewer(files)

    def view_srt_file(self):
        names, _ = QFileDialog.getOpenFileNames(self, 'SRT 파일 열기', self.settings.value('lastdir', ''),
                                                'SRT 자막 (*.srt);;모든 파일 (*.*)')
        if names:
            self.open_viewer(names)

    def open_viewer(self, files):
        dialog = SrtViewerDialog(files, self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()
        return dialog

    # ---------- 실행 ----------
    def pending_jobs(self):
        jobs = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, self.COL_STATUS).text() in ('대기', '실패', '취소됨'):
                jobs.append((row, self.table.item(row, self.COL_FILE).data(Qt.UserRole)))
        return jobs

    def start(self):
        jobs = self.pending_jobs()
        if not jobs:
            QMessageBox.information(self, APP_NAME, '처리할 파일을 먼저 추가하세요.')
            return
        if self.output_mode() == 'ask' and self.ask_output_dir() is None:
            return
        options = self.options()
        if options.translate and not options.targets:
            QMessageBox.warning(self, APP_NAME, '번역 대상 언어를 하나 이상 선택하세요.')
            return
        if not options.allow_download and not transcriber.is_model_cached(options.model):
            QMessageBox.warning(self, APP_NAME, f'모델 {options.model} 이 PC에 없습니다.\n'
                                '다른 모델을 선택하거나 "모델이 없으면 자동 다운로드"를 켜세요.')
            return
        self._save_settings()
        self.log('저장 위치: ' + (options.output_dir or '원본 파일과 같은 폴더'))
        self._set_running(True)
        self.total_bar.setValue(0)
        self._job_count = len(jobs)
        self._done_count = 0
        for row, _ in jobs:
            self._set_status(row, '대기')
            self._bar(row).setValue(0)
        self.worker = Worker(jobs, options, self.cache, self)
        self.worker.log.connect(self.log)
        self.worker.file_started.connect(lambda r: self._set_status(r, '처리 중'))
        self.worker.file_progress.connect(self._on_progress)
        self.worker.file_done.connect(self._on_done)
        self.worker.file_failed.connect(self._on_failed)
        self.worker.all_done.connect(self._on_all_done)
        self.worker.start()

    def stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText('중지 요청 중…')
            self.btn_stop.setEnabled(False)

    def _set_running(self, running):
        for w in (self.btn_start, self.btn_add, self.btn_folder, self.btn_remove, self.btn_clear,
                  self.cmb_source, self.cmb_model, self.cmb_device, self.chk_download, self.chk_translate,
                  self.targets_box, self.cmb_engine, self.cmb_output_mode, self.edt_output, self.btn_output,
                  self.cmb_maxlen):
            w.setEnabled(not running)
        if not running:
            self._toggle_translate(self.chk_translate.isChecked())
        self.btn_stop.setEnabled(running)
        self.status_label.setText('처리 중…' if running else '대기 중')

    def _bar(self, row):
        return self.table.cellWidget(row, self.COL_PROGRESS)

    def _set_status(self, row, text):
        self.table.item(row, self.COL_STATUS).setText(text)

    def _on_progress(self, row, stage, fraction):
        translate = self.chk_translate.isChecked() and self.selected_targets()
        if stage == 'transcribe':
            value = fraction * (80 if translate else 100)
        else:
            value = 80 + fraction * 20
        bar = self._bar(row)
        if bar:
            bar.setValue(int(value))
        self.total_bar.setValue(int(100 * (self._done_count + value / 100) / max(self._job_count, 1)))

    def _on_done(self, row, result):
        self.results[row] = result
        self._done_count += 1
        self._bar(row).setValue(100)
        self._set_status(row, '완료' if not result.errors else '일부 실패')
        self.table.item(row, self.COL_LANG).setText(languages.display_name(result.detected))
        names = [result.original.name] + [p.name for p in result.translated.values()]
        self.table.item(row, self.COL_RESULT).setText(f'{result.cue_count}개 큐 · ' + ', '.join(
            ['원문'] + [languages.display_name(t) for t in result.translated]))
        self.table.item(row, self.COL_RESULT).setToolTip(
            f'저장 폴더: {result.original.parent}\n' + '\n'.join(names)
            + ('\n' + '\n'.join(result.errors) if result.errors else ''))
        self.total_bar.setValue(int(100 * self._done_count / max(self._job_count, 1)))

    def _on_failed(self, row, message):
        self._done_count += 1
        self._set_status(row, '취소됨' if message == '취소됨' else '실패')
        self.table.item(row, self.COL_RESULT).setText(message[:80])
        self.table.item(row, self.COL_RESULT).setToolTip(message)
        self.total_bar.setValue(int(100 * self._done_count / max(self._job_count, 1)))

    def _on_all_done(self, success, failure, cancelled):
        self._set_running(False)
        text = f'완료: 성공 {success}개 / 실패 {failure}개' + (' (중지됨)' if cancelled else '')
        self.status_label.setText(text)
        self.log(text)
        self._fill_models_keep()

    def _fill_models_keep(self):
        current = self.cmb_model.currentData()
        self._fill_models()
        self._select(self.cmb_model, current)

    def log(self, text):
        self.log_view.appendPlainText(text)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, APP_NAME, '작업이 진행 중입니다. 중지하고 종료할까요?') != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(5000)
        self._save_settings()
        super().closeEvent(event)
