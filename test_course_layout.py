"""Migration and scaffold regression tests; no network or document tools needed."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from build_course_release import ReleaseBuilder, chapter_sort_key, chapter_label
from check_course_release import check
from migrate_course_layout import file_moves, migrate, plan
from new_course import DEFAULT_THEME


class LayoutTests(unittest.TestCase):
    def test_chapter_suffix_numbering(self):
        self.assertEqual(sorted(["10", "01", "00a", "00", "00b"], key=chapter_sort_key),
                         ["00", "00a", "00b", "01", "10"])
        self.assertEqual(chapter_label("00a"), "0a")
        self.assertEqual(chapter_label("01"), "1")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "working"
        self.root.mkdir()
        self.config = {
            "course_title": "Test Course",
            "site": {"intro": "Intro", "code_description": "Code", "theme": DEFAULT_THEME,
                     "repository": {"url": "https://example.org/repo", "label": "repo",
                                    "clone_url": "https://example.org/repo.git", "codespaces_url": "https://example.org"}},
            "release": {"exclude_names": ["__pycache__"], "exclude_suffixes": [".md", ".mmd"]},
            "chapters": [{"number": "00", "slug": "intro", "title": "Intro", "description": "Intro",
                          "chapter": {"source": "chapters/00-intro/chapter.pdf", "filename": "chapter.pdf"},
                          "slides": {"source": "slides/00-intro/topic-00-slides.html", "filename": "slides-00-intro.html", "pdf": False,
                                     "build": "slides/00-intro/build_slides.py"},
                          "code": {"source": "code/00-intro"},
                          "readings": [{"source": "notes/reading.md", "filename": "reading.pdf", "title": "Reading", "description": "Read"}]}]}
        self.write("release.json", json.dumps(self.config))
        self.write("chapters/00-intro/chapter.pdf", "fixture PDF")
        self.write("chapters/00-intro/chapter.md", "See `code/00-intro`.\n")
        self.write("slides/00-intro/topic-00-slides.html", "<!doctype html><h1>Intro</h1>")
        self.write("slides/00-intro/topic-00-slides.md", "# Intro\nSource: ../../code/00-intro/example.py\n")
        self.write("slides/00-intro/build_slides.py", "source = 'topic-00-slides.md'\n")
        self.write("code/00-intro/example.py", "print('unchanged')\n")
        self.write("notes/reading.md", "# Reading\n")
        self.write("notes/reading.pdf", "fixture reading")
        self.write("README.md", "[Chapter](chapters/00-intro/chapter.md)\n")

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)

    @staticmethod
    def snapshot(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_migration_preserves_release_and_backup(self):
        before = self.snapshot(self.root)
        moves = plan(self.root)
        file_moves(self.root, moves)
        self.assertEqual(before, self.snapshot(self.root))
        ReleaseBuilder(self.root, self.base / 'before', True).build()
        migrate(self.root, self.base / 'backup')
        self.assertEqual(before, self.snapshot(self.base / 'backup'))
        ReleaseBuilder(self.root, self.base / 'after', True).build()
        self.assertEqual(self.snapshot(self.base / 'before'), self.snapshot(self.base / 'after'))
        self.assertEqual([], check(self.root, self.base / 'after'))
        self.assertEqual("source = 'slides-00-intro.md'\n", (self.root / 'chapter-00-intro/slides/build_slides.py').read_text())
        self.assertIn('../code/example.py', (self.root / 'chapter-00-intro/slides/slides-00-intro.md').read_text())
        self.assertIn('chapter-00-intro/code', (self.root / 'chapter-00-intro/chapter.md').read_text())
        self.assertIn('(chapter-00-intro/chapter.md)', (self.root / 'README.md').read_text())
        self.assertEqual({}, plan(self.root))
        migrate(self.root, self.base / 'unused-backup')
        self.assertFalse((self.base / 'unused-backup').exists())

    def test_conflicting_code_requires_explicit_flag(self):
        self.write('code/00-older/example.py', 'old\n')
        with self.assertRaises(ValueError):
            plan(self.root)
        migrate(self.root, self.base / 'backup', True)
        self.assertEqual('old\n', (self.root / 'archive/legacy-code/00-older/example.py').read_text())

    def test_slide_pdf_is_copied_and_linked(self):
        del self.config['chapters'][0]['slides']['pdf']
        self.write('release.json', json.dumps(self.config))
        self.write('slides/00-intro/topic-00-slides.pdf', 'fixture slide PDF')
        output = self.base / 'release'
        ReleaseBuilder(self.root, output, True).build()
        pdf = output / 'chapter-00-intro/slides/slides-00-intro.pdf'
        self.assertEqual(b'fixture slide PDF', pdf.read_bytes())
        self.assertIn('slides/slides-00-intro.pdf', (output / 'chapter-00-intro/index.html').read_text())
        self.assertEqual([], check(self.root, output))

    def test_skip_build_requires_slide_pdf(self):
        del self.config['chapters'][0]['slides']['pdf']
        self.write('release.json', json.dumps(self.config))
        with self.assertRaises(FileNotFoundError):
            ReleaseBuilder(self.root, self.base / 'release', True).build()

    def test_destination_collision_leaves_source_alone(self):
        self.write('chapter-00-intro/chapter.pdf', 'existing\n')
        before = self.snapshot(self.root)
        with self.assertRaises(FileExistsError):
            migrate(self.root, self.base / 'backup')
        self.assertEqual(before, self.snapshot(self.root))
        self.assertFalse((self.base / 'backup').exists())

    def test_symlink_rejected(self):
        (self.root / 'code/00-intro/link').symlink_to(self.root / 'README.md')
        with self.assertRaises(ValueError):
            file_moves(self.root, plan(self.root))

    def test_backup_must_be_new_and_outside_course(self):
        with self.assertRaises(ValueError):
            migrate(self.root, self.root / 'backup')
        (self.base / 'backup').mkdir()
        with self.assertRaises(FileExistsError):
            migrate(self.root, self.base / 'backup')

    def test_new_course_is_chapter_first_and_unreleased(self):
        subprocess.run([sys.executable, str(Path(__file__).with_name('new_course.py')), 'test-course',
                        '--title', 'Test', '--description', 'Test', '--base', str(self.base), '--no-git'], check=True, capture_output=True)
        working = self.base / 'test-course/working'
        active = self.base / 'test-course/active'
        self.assertTrue((working / 'chapter-00-introduction/slides/slides-00-introduction.md').is_file())
        self.assertFalse((working / 'chapters').exists())
        self.assertEqual([], json.loads((working / 'release.json').read_text())['chapters'])
        self.assertEqual(self.snapshot(working / 'release'), self.snapshot(active))
        self.assertEqual([], check(working, active))


if __name__ == '__main__':
    unittest.main()
