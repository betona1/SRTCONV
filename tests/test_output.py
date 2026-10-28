"""저장 위치 기능 테스트: 다운로드 폴더, 폴더 복사, GUI 저장 버튼 (오프스크린)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from srtconv import pipeline  # noqa: E402
from srtconv.srt_utils import Cue, write_srt, read_srt, unique_path  # noqa: E402
from srtconv.viewer import SrtViewerDialog  # noqa: E402
from srtconv.ui import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])


class OutputDirTests(unittest.TestCase):
    def test_downloads_dir_exists(self):
        folder = pipeline.downloads_dir()
        self.assertTrue(folder.name.lower() in ('downloads', '다운로드') or folder.is_dir())

    def test_resolve_modes(self):
        self.assertEqual(pipeline.resolve_output_dir('source'), '')
        self.assertEqual(pipeline.resolve_output_dir('ask'), '')
        self.assertEqual(pipeline.resolve_output_dir('custom', '  C:/x  '), 'C:/x')
        self.assertEqual(pipeline.resolve_output_dir('downloads'), str(pipeline.downloads_dir()))
        self.assertEqual(set(pipeline.OUTPUT_MODES), {'source', 'downloads', 'custom', 'ask'})

    def test_unique_path_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a = base / 'clip_자막_en.srt'
            write_srt(a, [Cue(0, 1, 'hi')])
            self.assertEqual(unique_path(base, 'clip_자막_en.srt').name, 'clip_자막_en_2.srt')
            out = base / 'out'
            copied = pipeline.export_files([a, base / 'missing.srt'], out)
            self.assertEqual([d.name for _s, d in copied], ['clip_자막_en.srt'])
            copied = pipeline.export_files([a], out)
            self.assertEqual(copied[0][1].name, 'clip_자막_en_2.srt')
            self.assertEqual(read_srt(copied[0][1])[0].text, 'hi')
            # 같은 폴더로 복사하면 건너뜀
            self.assertEqual(pipeline.export_files([a], base), [])


class MainWindowOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.video = self.base / 'clip.mp4'
        self.video.write_bytes(b'0')
        write_srt(self.base / 'clip_자막_en.srt', [Cue(0, 1, 'Hello')])
        self.win = MainWindow()

    def tearDown(self):
        self.win.close()
        self.tmp.cleanup()

    def _select_mode(self, mode):
        self.win.cmb_output_mode.setCurrentIndex(self.win.cmb_output_mode.findData(mode))

    def test_modes_resolve(self):
        self._select_mode('source')
        self.assertEqual(self.win.current_output_dir(), '')
        self.assertFalse(self.win.edt_output.isVisibleTo(self.win))
        self._select_mode('downloads')
        self.assertEqual(self.win.current_output_dir(), str(pipeline.downloads_dir()))
        self.assertIn(str(pipeline.downloads_dir()), self.win.lbl_output_path.text())
        self._select_mode('custom')
        self.assertTrue(self.win.edt_output.isVisibleTo(self.win))
        self.win.edt_output.setText(str(self.base))
        self.assertEqual(self.win.current_output_dir(), str(self.base))
        self.assertEqual(self.win.options().output_dir, str(self.base))
        self._select_mode('ask')
        with mock.patch.object(QFileDialog, 'getExistingDirectory', return_value=str(self.base / 'asked')):
            self.assertEqual(self.win.ask_output_dir(), str(self.base / 'asked'))
        self.assertEqual(self.win.current_output_dir(), str(self.base / 'asked'))
        with mock.patch.object(QFileDialog, 'getExistingDirectory', return_value=''):
            self.assertIsNone(self.win.ask_output_dir())

    def test_save_results_to_copies_files(self):
        self._select_mode('source')
        self.win.add_paths([str(self.video)])
        self.assertEqual([p.name for p in self.win._result_files(0)], ['clip_자막_en.srt'])
        target = self.base / 'downloads'
        with mock.patch.object(QFileDialog, 'getExistingDirectory', return_value=str(target)), \
                mock.patch.object(QMessageBox, 'information', return_value=None):
            self.win.save_results_to()
        self.assertTrue((target / 'clip_자막_en.srt').exists())
        self.assertIn('1개', self.win.status_label.text())

    def test_save_results_without_files_warns(self):
        self.win.table.setRowCount(0)
        with mock.patch.object(QMessageBox, 'information', return_value=None) as info:
            self.win.save_results_to()
        self.assertEqual(info.call_count, 1)


class ViewerSaveAsTests(unittest.TestCase):
    def test_save_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            en, ko = base / 'c_자막_en.srt', base / 'c_자막_ko.srt'
            write_srt(en, [Cue(0, 1, 'Hello')])
            write_srt(ko, [Cue(0, 1, '안녕')])
            dlg = SrtViewerDialog([en, ko])
            dlg.cues[1][0].text = '안녕하세요'
            saved = dlg.save_copies(base / 'out')
            self.assertEqual([p.name for p in saved], ['c_자막_en.srt', 'c_자막_ko.srt'])
            self.assertEqual(read_srt(saved[1])[0].text, '안녕하세요')
            self.assertEqual(read_srt(ko)[0].text, '안녕')  # 원본은 그대로
            dlg.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
