"""SRT 보기 창 테스트 (오프스크린). 실행: QT_QPA_PLATFORM=offscreen python -m unittest tests.test_viewer -v"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from srtconv.srt_utils import Cue, write_srt, read_srt  # noqa: E402
from srtconv.viewer import SrtViewerDialog, column_title, FIXED_COLUMNS  # noqa: E402

app = QApplication.instance() or QApplication([])


class ColumnTitleTests(unittest.TestCase):
    def test_language_suffix(self):
        self.assertEqual(column_title('clip_자막_en.srt'), '영어')
        self.assertEqual(column_title('clip_자막_zh-TW_2.srt'), '중국어(번체)')
        self.assertEqual(column_title('clip_자막_xx.srt'), 'xx')
        self.assertEqual(column_title('other.srt'), 'other')


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.en = base / 'clip_자막_en.srt'
        self.ko = base / 'clip_자막_ko.srt'
        write_srt(self.en, [Cue(0, 1, 'Hello'), Cue(1, 2, 'World'), Cue(2, 3, 'Third')])
        write_srt(self.ko, [Cue(0, 1, '안녕'), Cue(1, 2, '세계')])

    def tearDown(self):
        self.tmp.cleanup()

    def test_side_by_side(self):
        dlg = SrtViewerDialog([self.en, self.ko])
        self.assertEqual(dlg.table.columnCount(), FIXED_COLUMNS + 2)
        self.assertEqual(dlg.table.rowCount(), 3)
        self.assertEqual(dlg.table.horizontalHeaderItem(2).text(), '영어')
        self.assertEqual(dlg.table.horizontalHeaderItem(3).text(), '한국어')
        self.assertEqual(dlg.table.item(0, 1).text(), '00:00:00,000 → 00:00:01,000')
        self.assertEqual(dlg.table.item(1, 3).text(), '세계')
        self.assertEqual(dlg.table.item(2, 3).text(), '')   # 짧은 파일은 빈 칸
        self.assertFalse(dlg.btn_save.isEnabled())
        dlg.close()

    def test_edit_and_save(self):
        dlg = SrtViewerDialog([self.en, self.ko])
        dlg.table.item(0, 3).setText('안녕하세요')
        dlg.table.item(2, 3).setText('셋째')
        self.assertTrue(dlg.btn_save.isEnabled())
        self.assertEqual(dlg.modified, {1})
        dlg.save()
        back = read_srt(self.ko)
        self.assertEqual([c.text for c in back], ['안녕하세요', '세계', '셋째'])
        self.assertAlmostEqual(back[2].start, 2.0)
        self.assertEqual(read_srt(self.en)[0].text, 'Hello')   # 수정 안 한 파일은 그대로
        self.assertFalse(dlg.btn_save.isEnabled())
        dlg.close()

    def test_filter(self):
        dlg = SrtViewerDialog([self.en, self.ko])
        dlg.search.setText('world')
        hidden = [dlg.table.isRowHidden(r) for r in range(3)]
        self.assertEqual(hidden, [True, False, True])
        dlg.search.setText('')
        self.assertFalse(any(dlg.table.isRowHidden(r) for r in range(3)))
        dlg.close()

    def test_add_file_and_duplicates(self):
        dlg = SrtViewerDialog([self.en])
        dlg.add_file(self.ko)
        dlg.add_file(self.ko)
        self.assertEqual(len(dlg.files), 2)
        self.assertEqual(dlg.table.columnCount(), FIXED_COLUMNS + 2)
        dlg.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
