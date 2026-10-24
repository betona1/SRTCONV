"""핵심 로직 단위 테스트 (unittest). 실행: python -m unittest discover -s tests -v"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from srtconv import languages, translator  # noqa: E402
from srtconv.srt_utils import Cue, Word, timestamp, parse_timestamp, split_words, to_srt, write_srt, read_srt, reserve_output  # noqa: E402
from srtconv.pipeline import Options, process_file, is_media  # noqa: E402


class TimestampTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(timestamp(0), '00:00:00,000')
        self.assertEqual(timestamp(3661.5), '01:01:01,500')
        self.assertEqual(timestamp(-1), '00:00:00,000')

    def test_roundtrip(self):
        for value in (0.0, 1.234, 59.999, 3600.0, 7325.5):
            self.assertAlmostEqual(parse_timestamp(timestamp(value)), value, places=3)


class SplitTests(unittest.TestCase):
    def words(self, text, start=0.0, step=0.4):
        out = []
        t = start
        for token in text.split(' '):
            out.append(Word(t, t + step, ' ' + token))
            t += step
        return out

    def test_short_segment_untouched(self):
        cues = split_words(0, 2, 'Hello world.', self.words('Hello world.'))
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].text, 'Hello world.')

    def test_long_segment_split_by_chars(self):
        text = 'one two three four five six seven eight nine ten eleven twelve thirteen fourteen'
        cues = split_words(0, 20, text, self.words(text), max_duration=5.0, max_chars=30)
        self.assertGreater(len(cues), 1)
        for cue in cues:
            self.assertLessEqual(len(cue.text), 30 * 2)  # 짧은 조각 병합 허용치
            self.assertLess(cue.start, cue.end)
        self.assertEqual(' '.join(c.text for c in cues), text)

    def test_hyphen_not_split(self):
        words = [Word(0, 0.5, ' released'), Word(0.5, 1.0, ' on'), Word(1.0, 1.5, ' that'),
                 Word(1.5, 2.0, ' follow'), Word(2.0, 2.5, '-through'), Word(2.5, 3.0, ' today')]
        cues = split_words(0, 3, 'released on that follow-through today', words, max_duration=1.0, max_chars=18)
        joined = ' '.join(c.text for c in cues)
        self.assertIn('follow-through', joined)
        for cue in cues:
            self.assertFalse(cue.text.startswith('-'))

    def test_sentence_boundary(self):
        text = 'This is the first sentence. And here is the second one.'
        cues = split_words(0, 10, text, self.words(text), max_duration=20, max_chars=30)
        self.assertEqual(cues[0].text, 'This is the first sentence.')

    def test_empty(self):
        self.assertEqual(split_words(0, 1, '   ', []), [])


class SrtIoTests(unittest.TestCase):
    def test_write_read(self):
        cues = [Cue(0.0, 1.5, '안녕하세요'), Cue(1.5, 3.0, 'Hello\nWorld')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.srt'
            write_srt(path, cues)
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))  # UTF-8 BOM
            back = read_srt(path)
        self.assertEqual(len(back), 2)
        self.assertEqual(back[1].text, 'Hello\nWorld')
        self.assertAlmostEqual(back[1].end, 3.0)

    def test_to_srt_numbering(self):
        text = to_srt([Cue(0, 1, 'a'), Cue(1, 2, 'b')])
        self.assertIn('1\n00:00:00,000 --> 00:00:01,000\na\n', text)
        self.assertIn('2\n00:00:01,000 --> 00:00:02,000\nb\n', text)

    def test_reserve_output_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'video.mp4'
            src.write_bytes(b'')
            first = reserve_output(src, '자막_en')
            self.assertEqual(first.name, 'video_자막_en.srt')
            first.write_text('x')
            second = reserve_output(src, '자막_en')
            self.assertEqual(second.name, 'video_자막_en_2.srt')
            custom = reserve_output(src, '자막_ko', Path(tmp) / 'out')
            self.assertEqual(custom.parent.name, 'out')


class LanguageTests(unittest.TestCase):
    def test_lookup(self):
        self.assertEqual(languages.get('ko').nllb, 'kor_Hang')
        self.assertEqual(languages.get('zh-TW').google, 'zh-TW')
        self.assertEqual(languages.get('zh').whisper, 'zh')
        self.assertIsNone(languages.get('xx'))
        self.assertEqual(languages.display_name('auto'), '자동 감지')
        self.assertEqual(languages.display_name('ja'), '일본어')

    def test_required_languages_present(self):
        for code in ('en', 'ko', 'zh', 'ja', 'es'):
            self.assertIn(code, languages.BY_CODE)


class FakeEngine:
    name = 'fake'

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def translate(self, texts, source, target):
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError('boom')
        return [f'[{target}] {t}' for t in texts]


class TranslatorTests(unittest.TestCase):
    def test_chain_fallback(self):
        bad, good = FakeEngine(fail=True), FakeEngine()
        out = translator.translate_texts([bad, good], ['a', 'b'], 'en', 'ko')
        self.assertEqual(out, ['[ko] a', '[ko] b'])
        self.assertEqual(len(bad.calls), 1)

    def test_all_fail(self):
        with self.assertRaises(translator.TranslationError):
            translator.translate_texts([FakeEngine(fail=True)], ['a'], 'en', 'ko')

    def test_group_sentences(self):
        texts = ['Hello there,', 'how are you?', 'Fine.', 'a', 'b', 'c', 'd', 'e']
        groups = translator.group_sentences(texts, max_group=4)
        self.assertEqual(groups[0], (0, 2))
        self.assertEqual(groups[1], (2, 3))
        self.assertEqual(groups[2], (3, 7))
        self.assertEqual(groups[3], (7, 8))

    def test_distribute_words(self):
        pieces = translator.distribute('one two three four five six', [10, 20])
        self.assertEqual(len(pieces), 2)
        self.assertEqual(' '.join(pieces), 'one two three four five six')

    def test_distribute_cjk(self):
        pieces = translator.distribute('가나다라마바사아', [1, 1], no_space=True)
        self.assertEqual(pieces, ['가나다라', '마바사아'])

    def test_distribute_too_short(self):
        self.assertEqual(translator.distribute('x', [1, 1, 1]), ['x', '', ''])

    def test_translate_cues_length_preserved(self):
        engine = FakeEngine()
        texts = ['The quick brown', 'fox jumps over.', 'Lazy dog sleeps.']
        out = translator.translate_cues([engine], texts, 'en', 'es')
        self.assertEqual(len(out), 3)
        self.assertEqual(len(engine.calls[0]), 2)  # 문장 2개로 묶여 호출
        self.assertTrue(all(out))

    def test_offline_model_kind_and_tokens(self):
        self.assertEqual(translator._model_kind('x/m2m100_418M-ct2-int8'), 'm2m100')
        self.assertEqual(translator._model_kind('x/nllb-200-distilled-600M-ct2-int8'), 'nllb')
        fake = translator.CT2Translator.__new__(translator.CT2Translator)
        fake.kind = 'm2m100'
        self.assertEqual(fake._lang_token(languages.get('ko')), '__ko__')
        self.assertEqual(fake._lang_token(languages.get('zh-TW')), '__zh__')
        fake.kind = 'nllb'
        self.assertEqual(fake._lang_token(languages.get('zh-TW')), 'zho_Hant')
        self.assertEqual(translator.ENGINE_ALIASES.get('nllb'), 'offline')

    def test_translate_lines_batching(self):
        class Client:
            def __init__(self):
                self.calls = []

            def translate(self, text):
                self.calls.append(text)
                return '\n'.join('T:' + line for line in text.split('\n'))

        client = Client()
        out = translator._translate_lines(client, ['a', 'b', 'c'], limit=4)
        self.assertEqual(out, ['T:a', 'T:b', 'T:c'])
        self.assertGreaterEqual(len(client.calls), 2)


class _Seg:
    def __init__(self, start, end, text, words=None):
        self.start, self.end, self.text, self.words = start, end, text, words


class _Info:
    language = 'en'
    language_probability = 0.99
    duration = 10.0


class FakeModel:
    def transcribe(self, path, **kwargs):
        self.kwargs = kwargs
        segs = [_Seg(0.0, 2.0, ' Hello there.'), _Seg(2.0, 4.0, ' How are you?'), _Seg(4.0, 4.0, ' bad'), _Seg(5.0, 6.0, '   ')]
        return iter(segs), _Info()


class CudaFallbackTests(unittest.TestCase):
    def test_is_cuda_error(self):
        from srtconv import transcriber
        self.assertTrue(transcriber.is_cuda_error(RuntimeError('Library cublas64_12.dll is not found or cannot be loaded')))
        self.assertTrue(transcriber.is_cuda_error(RuntimeError('CUDA failed with error out of memory')))
        self.assertFalse(transcriber.is_cuda_error(FileNotFoundError('no such video')))

    def test_cuda_available_requires_runtime(self):
        from srtconv import transcriber
        from unittest import mock
        with mock.patch.object(transcriber, 'cuda_runtime_present', return_value=False):
            self.assertFalse(transcriber.cuda_available())
            self.assertEqual(transcriber.resolve_device('auto'), ('cpu', 'int8'))


class PipelineTests(unittest.TestCase):
    def test_is_media(self):
        self.assertTrue(is_media('a.MP4'))
        self.assertTrue(is_media('b.mp3'))
        self.assertFalse(is_media('c.txt'))

    def test_process_file_with_translation(self):
        engine = FakeEngine()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'clip.mp4'
            src.write_bytes(b'0')
            options = Options(translate=True, targets=['ko', 'en', 'ja'], source_language='auto')
            logs = []
            stages = []
            result = process_file(src, options, FakeModel(), [engine],
                                  progress=lambda s, f: stages.append((s, f)), log=logs.append)
            self.assertEqual(result.detected, 'en')
            self.assertEqual(result.cue_count, 2)
            self.assertTrue(result.original.exists())
            self.assertEqual(result.original.name, 'clip_자막_en.srt')
            self.assertEqual(set(result.translated), {'ko', 'ja'})  # en 은 원문과 같아 생략
            ko = read_srt(result.translated['ko'])
            self.assertEqual(len(ko), 2)
            self.assertTrue(ko[0].text.startswith('[ko]'))
            self.assertEqual(result.errors, [])
            self.assertIn(('transcribe', 1.0), stages)
            self.assertTrue(any('번역 생략' in line for line in logs))

    def test_process_file_forced_language(self):
        model = FakeModel()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'clip.mp4'
            src.write_bytes(b'0')
            process_file(src, Options(source_language='ko'), model)
            self.assertEqual(model.kwargs['language'], 'ko')
            process_file(src, Options(source_language='auto'), model)
            self.assertIsNone(model.kwargs['language'])

    def test_translation_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'clip.mp4'
            src.write_bytes(b'0')
            result = process_file(src, Options(translate=True, targets=['ko']), FakeModel(), [FakeEngine(fail=True)])
            self.assertTrue(result.original.exists())
            self.assertEqual(result.translated, {})
            self.assertEqual(len(result.errors), 1)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            process_file(Path('no_such_file.mp4'), Options(), FakeModel())


if __name__ == '__main__':
    unittest.main(verbosity=2)
