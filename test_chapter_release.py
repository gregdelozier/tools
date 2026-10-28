"""Chapter publication includes all code; lecture publication adds only slides."""
import json
from pathlib import Path
import tempfile
import unittest

from chapter_release import ReleaseBuilder, check
from activate_course import change


class PublicationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'working'; self.root.mkdir()
        self.site = Path(tmp.name) / 'site'
        from new_course import DEFAULT_THEME
        real = {'site': {'theme': DEFAULT_THEME, 'intro': 'Intro', 'code_description': 'Code', 'repository': {'url': 'https://example.org/repo', 'label': 'repo', 'clone_url': 'https://example.org/repo.git', 'codespaces_url': 'https://example.org'}}}
        self.config = dict(course_title='Test', chapters=[], site=real['site'] | {'pages': []})
        (self.root / 'release.json').write_text(json.dumps(self.config))
        self.write('chapter-11-functions/chapter-11-functions.md', '# Chapter 11: Functions\n')
        self.write('chapter-11-functions/chapter-11-functions.pdf', 'chapter')
        self.write('chapter-11-functions/code/runner.py', 'runner')
        self.write('chapter-11-functions/code/examples/example.v', 'example')
        self.write('chapter-11-functions/code/.private-secret', 'secret')
        self.write('chapter-11-functions/exercises/generated-crossword.pdf', 'puzzle')
        self.write('chapter-11-functions/exercises/generated-crossword-key.pdf', 'key')
        for n in [0, 1]:
            for suffix in ['md', 'html', 'pdf']:
                self.write(f'chapter-11-functions/lectures/lecture-{n}-functions.{suffix}', f'Lecture {n}')
        self.write('chapter-11-functions/lectures/slide-assets/style.css', 'css')
        self.write('chapter-11-functions/lectures/lecture-0-speaker-notes.md', 'notes')

    def write(self, name, content):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)

    def build(self):
        ReleaseBuilder(self.root, self.site, True).build()
        return self.site / 'chapter-11-functions'

    def test_chapter_includes_complete_code_without_lectures(self):
        change(self.root, 'chapter', 11); base = self.build()
        self.assertEqual('runner', (base / 'code/runner.py').read_text())
        self.assertEqual('example', (base / 'code/examples/example.v').read_text())
        self.assertTrue((base / 'chapter-11-functions.pdf').exists())
        self.assertTrue((base / 'exercises/generated-crossword.pdf').exists())
        self.assertFalse((base / 'lectures').exists())
        self.assertFalse((base / 'code/.private-secret').exists())
        self.assertFalse((base / 'exercises/generated-crossword-key.pdf').exists())
        self.assertEqual([], check(self.root, self.site))

    def test_lecture_adds_slides_without_splitting_code(self):
        change(self.root, 'chapter', 11); change(self.root, 'lecture', 11, 1)
        base = self.build()
        self.assertTrue((base / 'lectures/lecture-1-functions.html').exists())
        self.assertTrue((base / 'lectures/lecture-1-functions.pdf').exists())
        self.assertFalse((base / 'lectures/lecture-0-functions.html').exists())
        self.assertFalse((base / 'lectures/code').exists())
        self.assertTrue((base / 'code/runner.py').exists())
        self.assertEqual([], check(self.root, self.site))

    def test_both_lectures_share_assets_and_selection_is_idempotent(self):
        change(self.root, 'chapter', 11)
        for n in [1, 0, 0]: change(self.root, 'lecture', 11, n)
        config = json.loads((self.root / 'release.json').read_text())
        self.assertEqual([0, 1], [l['number'] for l in config['chapters'][0]['lectures']])
        base = self.build()
        self.assertEqual('css', (base / 'lectures/slide-assets/style.css').read_text())
        self.assertEqual([], check(self.root, self.site))

    def test_lecture_requires_published_chapter(self):
        with self.assertRaisesRegex(ValueError, 'chapter before'): change(self.root, 'lecture', 11, 0)
        self.assertEqual([], json.loads((self.root / 'release.json').read_text())['chapters'])

    def test_missing_lecture_does_not_change_selection(self):
        change(self.root, 'chapter', 11)
        before = (self.root / 'release.json').read_bytes()
        with self.assertRaises(ValueError): change(self.root, 'lecture', 11, 2)
        self.assertEqual(before, (self.root / 'release.json').read_bytes())

    def test_checker_detects_missing_changed_and_unselected_files(self):
        change(self.root, 'chapter', 11); base = self.build()
        (base / 'code/runner.py').unlink()
        (base / 'code/examples/example.v').write_text('changed')
        (base / 'unreleased.pdf').write_text('unexpected')
        errors = '\n'.join(check(self.root, self.site))
        for text in ['Missing release file', 'Release differs', 'Unexpected release file']:
            self.assertIn(text, errors)

    def test_legacy_slides_travel_with_chapter(self):
        self.write('chapter-11-functions/slides/chapter-slides.html', '<h1>Chapter slides</h1>')
        self.write('chapter-11-functions/slides/chapter-slides.pdf', 'slides pdf')
        self.write('chapter-11-functions/slides/slide-assets/style.css', 'css')
        change(self.root, 'chapter', 11); base = self.build()
        self.assertTrue((base / 'slides/chapter-slides.html').exists())
        self.assertTrue((base / 'slides/chapter-slides.pdf').exists())
        self.assertFalse((base / 'lectures').exists())
        self.assertEqual([], check(self.root, self.site))

    def test_named_lecture_directory_is_separate_and_preserved(self):
        for suffix in ['md', 'html', 'pdf']:
            self.write(f'chapter-11-functions/lecture-02-calls/lecture-02-calls.{suffix}', 'Calls')
        self.write('chapter-11-functions/lecture-02-calls/slide-assets/style.css', 'css')
        change(self.root, 'chapter', 11); base = self.build()
        self.assertFalse((base / 'lecture-02-calls').exists())
        change(self.root, 'lecture', 11, 2)
        import shutil
        shutil.rmtree(self.site); base = self.build()
        self.assertTrue((base / 'lecture-02-calls/lecture-02-calls.html').exists())
        self.assertTrue((base / 'lecture-02-calls/lecture-02-calls.pdf').exists())
        self.assertFalse((base / 'lecture-02-calls/lecture-02-calls.md').exists())
        self.assertEqual([], check(self.root, self.site))

    def test_existing_reading_destination_within_chapter(self):
        change(self.root, 'chapter', 11)
        config = json.loads((self.root / 'release.json').read_text())
        self.write('supplement.html', '<h1>Supplement</h1>')
        config['chapters'][0]['readings'] = [dict(source='supplement.html', filename='../slides/supplement.html', title='Supplement', description='Supplement')]
        (self.root / 'release.json').write_text(json.dumps(config))
        base = self.build()
        self.assertTrue((base / 'slides/supplement.html').exists())
        self.assertEqual([], check(self.root, self.site))

    def test_pdf_only_lecture(self):
        self.write('chapter-11-functions/lecture-03-review/lecture-03-review.md', '# Review')
        self.write('chapter-11-functions/lecture-03-review/lecture-03-review.pdf', 'review pdf')
        change(self.root, 'chapter', 11); change(self.root, 'lecture', 11, 3)
        base = self.build()
        self.assertEqual('review pdf', (base / 'lecture-03-review/lecture-03-review.pdf').read_text())
        self.assertEqual([], check(self.root, self.site))

    def test_suffixed_chapter_number(self):
        folder = self.root / 'chapter-11-functions'
        folder.rename(self.root / 'chapter-11a-functions')
        renamed = self.root / 'chapter-11a-functions'
        for suffix in ['md', 'pdf']:
            (renamed / f'chapter-11-functions.{suffix}').rename(renamed / f'chapter-11a-functions.{suffix}')
        change(self.root, 'chapter', '11a')
        base = self.build()
        self.assertTrue((self.site / 'chapter-11a-functions/chapter-11a-functions.pdf').exists())
        self.assertEqual([], check(self.root, self.site))

    def test_symlink_code_rejected(self):
        change(self.root, 'chapter', 11)
        (self.root / 'chapter-11-functions/code/link.py').symlink_to('/etc/hosts')
        with self.assertRaises(ValueError): self.build()


if __name__ == '__main__': unittest.main()
