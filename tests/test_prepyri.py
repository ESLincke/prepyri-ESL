import contextlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from script import prepyri
from script.layouts import Text, detect_layout, reconstruct, segment_texts

FIXTURES = Path(__file__).parent / 'fixtures'
MON = 'PMonEpiph_170-172_2026-11-17.txt'
RYL = 'PRylCopt_320-329_2026-01-09.txt'


def texts(name):
    return segment_texts((FIXTURES / name).read_text(), name)[0]


def body(text, layout='auto'):
    return [r for r in reconstruct(text, layout)[0] if r.kind == 'text']


class RegressionTests(unittest.TestCase):
    def test_eof_with_and_without_newline_or_blank(self):
        for suffix in ('', '\n', '\n\n'):
            source = '170\nⲁ\n\n171\nⲃ' + suffix
            self.assertIn('ⲃ', ''.join(sum(prepyri.split_lines(source.splitlines(True)), [])))
            out, _ = prepyri.process_text(source, MON)
            self.assertTrue(out.rstrip().endswith('1. ⲃ'))
        self.assertEqual(prepyri.split_lines([]), [])

    def test_mon_segmentation_layout_and_counts(self):
        items = texts(MON)
        self.assertEqual([t.number for t in items], ['170', '171', '172'])
        self.assertEqual([detect_layout(t.lines) for t in items], ['wysiwyg'] * 3)
        self.assertEqual([len(body(t)) for t in items], [9, 36, 22])
        for text in items:
            self.assertEqual([r.number for r in body(text)], list(range(1, len(body(text)) + 1)))
        out, warnings = prepyri.process_text((FIXTURES / MON).read_text(), MON)
        self.assertIn('Conflicting line marker 10; reconstructed line 15', warnings)
        self.assertIn('Verso (palimpsest)', out)
        self.assertIn('2.- ⲛⲁⲁⲡⲟⲗⲟⲅⲓⲍⲉ', out)
        self.assertIn('22. ⲕ̣ⲁ̣ⲁ̣ϥ̣', out)

    def test_rylands_all_ten_texts_and_layouts(self):
        items = texts(RYL)
        self.assertEqual([t.number for t in items], list(map(str, range(320, 330))))
        self.assertEqual([detect_layout(t.lines) for t in items], ['pipe', 'numbered'] + ['pipe'] * 8)
        self.assertEqual([len(body(t)) for t in items], [41, 10, 15, 12, 10, 7, 12, 8, 10, 9])
        for text in items:
            self.assertEqual([r.number for r in body(text)], list(range(1, len(body(text)) + 1)))

    def test_rylands_320_boundaries_anchors_and_ocr_hyphens(self):
        rows = body(texts(RYL)[0])
        self.assertTrue(rows[2].text.endswith('ⲁⲓⲁⲛⲁⲕⲁ'))
        self.assertTrue(rows[3].text.startswith('ⲍⲉ'))
        self.assertIn('ϣⲁⲣⲉⲡⲕⲱⲙⲏⲕⲁⲑⲏⲕⲏⲥ', rows[10].text)
        self.assertEqual([r.anchor for r in rows if r.anchor], list(range(5, 41, 5)))
        self.assertTrue(rows[29].text.startswith('-ⲙⲉ'))
        self.assertIn('¹⁰', rows[25].text)
        self.assertIn('[ϫⲉⲛⲁⲩ above]', rows[21].text)

    def test_rylands_321_numbered_wraps_and_notes(self):
        rows = body(texts(RYL)[1])
        self.assertTrue(rows[0].text.endswith('ⲧⲁⲣⲉⲧⲉⲕⲙⲛⲧϫⲟⲉⲓⲥ'))
        self.assertIn('ⲛⲡⲉⲛϣⲧⲁⲗⲟⲟⲩ', rows[4].text)
        self.assertIn('[rest illegible]', rows[7].text)
        self.assertIn('[all illegible till end,]', rows[8].text)
        self.assertIn('φαρμονθ', rows[9].text)

    def test_rylands_323_cross_page_same_line(self):
        rows = body(texts(RYL)[3])
        self.assertTrue(rows[1].text.startswith('ⲁϥ̣ⲉⲓ ⲉⲃⲟⲗ'))
        self.assertTrue(rows[1].text.endswith('ⲁ̣ϥ̣ⲥⲙⲛ'))
        self.assertEqual(len(rows), 12)

    def test_paratext_and_footnotes_preserved(self):
        source = (FIXTURES / RYL).read_text()
        out, _ = prepyri.process_text(source, RYL)
        for note in ('Above l. 1,\nⲭⲙⲅ.\n1.', '(verso)\n28.',
                     'Verso: the address in one line, illegible.',
                     '(in ⲟtⲠⲉr direⲥtion\n12.', 'ⲟf an Arabic letter'):
            self.assertIn(note, out)
        self.assertEqual(re.findall('[⁰¹²³⁴⁵⁶⁷⁸⁹]+', source), re.findall('[⁰¹²³⁴⁵⁶⁷⁸⁹]+', out))
        self.assertNotIn('Element', out)
        self.assertNotIn('|', out)
        self.assertNotIn('P.Mon.Epiph.', out)

    def test_296_301_missing_heading_not_invented(self):
        name = 'PRylCopt_296-301_2026-11-18.txt'
        self.assertEqual([t.number for t in texts(name)], ['296', '297', '299', '300', '301'])
        out, _ = prepyri.process_text((FIXTURES / name).read_text(), name)
        self.assertIn('¹⁰', out)
        self.assertIn('[space]', out)
        self.assertNotIn('P.Ryl.Copt. 298', out)


class StructureTests(unittest.TestCase):
    def test_pages_and_blank_lines_not_boundaries(self):
        source = '170\nⲁ\n\nElement 1 (page.png)\nⲃ\n171\nⲅ'
        items, _ = segment_texts(source)
        self.assertEqual([t.number for t in items], ['170', '171'])
        self.assertEqual([r.text for r in body(items[0])], ['ⲁ', 'ⲃ'])

    def test_high_line_counters_not_titles(self):
        source = '320.\n' + '\n'.join(f'{i}.\nⲁ¹' for i in range(98, 103)) + '\n321.\nⲃ|ⲅ'
        items, _ = segment_texts(source)
        self.assertEqual([t.number for t in items], ['320', '321'])
        self.assertEqual([r.number for r in body(items[0])], list(range(98, 103)))

    def test_footnote_numbers_not_titles_or_inline_markers(self):
        items, _ = segment_texts('320.\nⲁ¹⁰|ⲃ11 ⲅ\n1. Footnote\n321.\nⲇ')
        self.assertEqual([t.number for t in items], ['320', '321'])
        self.assertEqual([r.text for r in body(items[0])], ['ⲁ¹⁰', 'ⲃ11 ⲅ'])

    def test_blank_pipe_lines_preserved_and_normalization_safe(self):
        out, _ = prepyri.process_text('320.\nⲁ-| |ⲃ|', 'PRylCopt.txt')
        self.assertIn('1. ⲁ\n2.- [.?]\n3. ⲃ', out)

    def test_nonconsecutive_editions_from_filename(self):
        items, _ = segment_texts('113\nⲁ\n114\nⲃ\n123\nⲅ\n127\nⲇ',
                                 'PMonEpiph_113-114+123+127_2024-12-20.txt')
        self.assertEqual([t.number for t in items], ['113', '114', '123', '127'])

    def test_numbered_across_page_and_blank(self):
        items, _ = segment_texts('321.\n1.\nⲁ-\n\nElement 2 (x)\nⲃ\n2.\nⲅ')
        self.assertEqual([r.text for r in body(items[0])], ['ⲁⲃ', 'ⲅ'])

    def test_editorial_rules_unchanged_after_reconstruction(self):
        out, _ = prepyri.process_text('170\n⳨ ⲁ[\n5\nⲃ/ ... + · ⳿ ⲓ̈ :', MON)
        self.assertIn('4. *rho-cross* ⲁ[.?]', out)
        self.assertIn('5. (ⲃ( )) .3 *stauros* *middot* *word-sep-apostrophe*', out)
        self.assertIn('ⲓ(¨) *dipunct*', out)

    def test_file_text_overrides_and_small_edition_numbers(self):
        config = {'files': {'sample.txt': {'layout': 'pipe', 'edition': 'Example',
                   'edition_numbers': [1, 2], 'texts': {'2': {'layout': 'wysiwyg', 'start_line': 7}}}}}
        out, log = prepyri.process_text('1\nⲁ\nⲃ|ⲅ\n2\nⲇ\nⲉ', 'sample.txt', config)
        self.assertIn('Example 1\n1. ⲁ ⲃ\n2. ⲅ', out)
        self.assertIn('Example 2\n7. ⲇ\n8. ⲉ', out)
        self.assertIn('layout=wysiwyg', log)

    def test_invalid_configuration_fails_before_processing(self):
        for config in ({'files': []}, {'files': {'x': {'layout': 'typo'}}},
                       {'files': {'x': {'texts': {'1': {'start_line': 0}}}}}):
            with self.assertRaises(ValueError):
                prepyri.process_text('ⲁ', 'x', config)

    def test_input_output_archive_log_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'in').mkdir()
            (root / 'in' / MON).write_text((FIXTURES / MON).read_text())
            (root / 'in' / 'README.md').write_text('keep')
            (root / 'prepyri.json').write_text(json.dumps({'files': {MON: {'layout': 'wysiwyg'}}}))
            with contextlib.redirect_stdout(io.StringIO()):
                prepyri.main(root)
            self.assertFalse((root / 'in' / MON).exists())
            self.assertTrue((root / 'in' / 'README.md').exists())
            self.assertEqual((root / 'archive' / MON).read_bytes(), (FIXTURES / MON).read_bytes())
            self.assertIn('22. ⲕ̣ⲁ̣ⲁ̣ϥ̣', (root / 'out' / f'out_{MON}').read_text())
            self.assertIn('layout=wysiwyg', next((root / 'log').glob('*.txt')).read_text())

    def test_direct_cli_import(self):
        result = subprocess.run([sys.executable, 'prepyri.py', '--help'], cwd=Path(prepyri.__file__).parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--config', result.stdout)


if __name__ == '__main__':
    unittest.main()
