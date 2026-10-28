"""Root-level extras publishing tests, without document builders or network."""

import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from build_course_release import ReleaseBuilder
from check_course_release import check


class ExtrasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "working"
        self.root.mkdir()
        self.site = Path(self.temp.name) / "release"
        config = {
            "course_title": "Test", "chapters": [],
            "site": {"intro": "Test", "theme": dict.fromkeys(
                ["background_start", "background_end", "primary", "secondary", "hover"], "#ffffff"),
                "repository": dict.fromkeys(["url", "label", "clone_url", "codespaces_url"], "https://example.org")},
            "release": {"exclude_names": ["private.txt"], "exclude_suffixes": [".md", ".mmd"]},
        }
        self.write("release.json", json.dumps(config).encode())

    def write(self, name, contents=b"example"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def build(self):
        ReleaseBuilder(self.root, self.site, skip_build=True).build()

    def test_crosswords_selected_only_and_byte_identical(self):
        config = json.loads((self.root / "release.json").read_text())
        config["chapters"] = [{"number": "06", "slug": "ci", "title": "CI", "description": "Test"}]
        self.write("release.json", json.dumps(config).encode())
        name = "chapter-06-ci/exercises/ci-crossword.pdf"
        self.write(name, b"Crossword PDF fixture")
        for other in ["chapter-06-ci/exercises/build_crossword.py",
                      "chapter-06-ci/exercises/crossword-data.json",
                      "chapter-06-ci/exercises/.private-crossword.pdf",
                      "chapter-06-ci/exercises/ci-crossword-key.pdf",
                      "chapter-06-ci/exercises/crossword_answers.pdf",
                      "chapter-06-ci/exercises/.venv/crossword.pdf",
                      "chapter-07-later/exercises/crossword.pdf"]:
            self.write(other)
        self.build()
        self.assertEqual(b"Crossword PDF fixture", (self.site / name).read_bytes())
        self.assertEqual(["ci-crossword.pdf"], [f.name for f in (self.site / "chapter-06-ci/exercises").rglob("*")])
        self.assertIn('href="exercises/ci-crossword.pdf"', (self.site / "chapter-06-ci/index.html").read_text())
        self.assertEqual([], check(self.root, self.site))
        (self.site / name).write_bytes(b"changed")
        self.assertIn("Crossword differs: " + name, check(self.root, self.site))
        (self.site / name).unlink()
        self.assertIn("Missing crossword: " + name, check(self.root, self.site))

    def test_absent_extras(self):
        self.build()
        self.assertFalse((self.site / "extras").exists())
        self.assertNotIn('href="extras/index.html"', (self.site / "index.html").read_text())
        self.assertEqual([], check(self.root, self.site))

    def test_runpy_course_launchers(self):
        self.write("extras/guide.pdf", b"Student guide")
        tools = Path(__file__).resolve().parent
        for script, args in [
            ("build_course_release.py", [str(self.root), "--output", str(self.site), "--skip-build"]),
            ("check_course_release.py", [str(self.root), "--site", str(self.site)]),
        ]:
            result = subprocess.run(
                [sys.executable, "-c", "import runpy,sys; runpy.run_path(sys.argv.pop(1), run_name='__main__')",
                 str(tools / script), *args], cwd=self.root, capture_output=True, text=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_nested_public_files_copied_byte_for_byte(self):
        files = {"extras/guide.pdf": b"Student guide\n",
                 "extras/data/sample.bin": bytes(range(256)),
                 "extras/lesson.html": b'<a href="guide.pdf">Guide</a>'}
        for name, content in files.items():
            self.write(name, content)
        self.build()
        for name, content in files.items():
            self.assertEqual(content, (self.site / name).read_bytes())
        self.assertEqual([], check(self.root, self.site))

    def test_chapter_and_archive_extras_not_discovered(self):
        self.write("chapter-09-unreleased/extras/no.txt")
        self.write("archive/extras/no.txt")
        self.write("release/extras/no.txt")
        self.build()
        self.assertFalse((self.site / "extras").exists())
        self.assertFalse((self.site / "chapter-09-unreleased").exists())

    def test_private_names_stay_excluded(self):
        for name in ["assignments/quiz.json", "instructor-notes/lecture.txt",
                     "speaker-notes.md", ".git/config", "__pycache__/x.pyc",
                     ".DS_Store", "notes.js", "private.txt"]:
            self.write("extras/" + name)
        self.write("extras/keep.txt")
        self.build()
        self.assertEqual(["index.html", "keep.txt"], sorted(p.name for p in (self.site / "extras").rglob("*") if p.is_file()))

    def test_authoring_and_private_prefixes_are_never_published(self):
        for name in [".private-test.json", "nested/.private-data/token.txt",
                     "deck.md", "diagram.mmd", "guide.MD", "guide.markdown",
                     "deep-dive-speaker-notes.md", "instructor-notes.txt",
                     "nested/speaker-notes/lecture.html"]:
            self.write("extras/" + name, b"Synthetic test data")
        self.write("extras/deck.html", b"<h1>Public deck</h1>")
        self.build()
        self.assertEqual(["deck.html", "index.html"], sorted(
            p.name for p in (self.site / "extras").rglob("*") if p.is_file()))
        self.assertEqual([], check(self.root, self.site))

    def test_checker_rejects_private_files_outside_extras_too(self):
        config = json.loads((self.root / "release.json").read_text())
        config["validation"] = {"private_suffixes": []}
        self.write("release.json", json.dumps(config).encode())
        self.build()
        for name in [".private-test.json", "nested/.private-dir/token.txt",
                     "deck.md", "deep-dive-speaker-notes.txt"]:
            path = self.site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Synthetic test data")
        errors = check(self.root, self.site)
        for name in [".private-test.json", "nested/.private-dir/token.txt",
                     "deck.md", "deep-dive-speaker-notes.txt"]:
            self.assertIn("Private source: " + name, errors)

    def test_generated_readme_is_allowed_but_extras_readme_is_not(self):
        config = json.loads((self.root / "release.json").read_text())
        config["release_readme"] = "# Student materials"
        self.write("release.json", json.dumps(config).encode())
        self.write("extras/README.md")
        self.build()
        self.assertTrue((self.site / "README.md").exists())
        self.assertFalse((self.site / "extras/README.md").exists())
        self.assertEqual([], check(self.root, self.site))

    def test_tree_copy_filters_private_names_and_direct_copy_rejects_them(self):
        self.write("code/.private-test.json")
        self.write("code/nested/.private-dir/token.txt")
        self.write("code/deep-dive-speaker-notes.md")
        self.write("code/runner.py", b"print(1)")
        builder = ReleaseBuilder(self.root, self.site, skip_build=True)
        builder.copy_tree("code", self.site / "code")
        self.assertEqual(["runner.py"], [p.name for p in (self.site / "code").rglob("*") if p.is_file()])
        with self.assertRaises(ValueError):
            builder.copy_file("code/.private-test.json", self.site / "public.json")
        with self.assertRaises(ValueError):
            builder.copy_file("code/runner.py", self.site / ".private-output")

    def test_authoring_only_extras_omitted(self):
        self.write("extras/deck.md")
        self.build()
        self.assertFalse((self.site / "extras").exists())
        self.assertNotIn('href="extras/index.html"', (self.site / "index.html").read_text())

    def test_public_symlinks_cannot_disguise_private_sources(self):
        secret = self.write(".private-fixture/token.txt", b"Synthetic secret")
        self.write("assets/keep.txt")
        (self.root / "assets/public.txt").symlink_to(secret)
        builder = ReleaseBuilder(self.root, self.site, True)
        with self.assertRaises(ValueError):
            builder.copy_file("assets/public.txt", self.site / "public.txt")
        with self.assertRaises(ValueError):
            builder.copy_tree("assets", self.site / "assets")
        self.assertFalse(self.site.exists())

    def test_tree_roots_nested_directories_and_ancestors_cannot_be_links(self):
        self.write("original/sub/file.txt")
        (self.root / "alias").symlink_to(self.root / "original")
        builder = ReleaseBuilder(self.root, self.site, True)
        for source in ["alias", "alias/sub"]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                builder.copy_tree(source, self.site / "tree")
        with self.assertRaises(ValueError):
            builder.copy_file("alias/sub/file.txt", self.site / "file.txt")
        self.write("tree/keep.txt")
        (self.root / "tree/nested").symlink_to(self.root / "original")
        with self.assertRaises(ValueError):
            builder.copy_tree("tree", self.site / "tree")

    def test_render_inputs_and_outputs_reject_links_before_subprocess(self):
        original = self.write("original.md", b"# Synthetic")
        builder = ReleaseBuilder(self.root, self.site, False)
        with patch("build_course_release.subprocess.run") as run:
            for source in ["reading.md", "slides.html"]:
                path = self.root / source
                path.symlink_to(original)
                with self.subTest(source=source), self.assertRaises(ValueError):
                    if source.endswith(".md"):
                        builder.build_reading({"source": source})
                    else:
                        builder.slide_pdf({"source": source})
            self.write("safe.md")
            self.write("safe.html")
            (self.root / "safe.pdf").symlink_to(original)
            with self.assertRaises(ValueError):
                builder.build_reading({"source": "safe.md"})
            with self.assertRaises(ValueError):
                builder.slide_pdf({"source": "safe.html"})
            run.assert_not_called()

    def test_traversal_and_dangling_links_are_rejected(self):
        builder = ReleaseBuilder(self.root, self.site, True)
        (self.root / "dangling.txt").symlink_to(self.root / "absent")
        for source in ["dangling.txt", "../outside.txt"]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                builder.copy_file(source, self.site / "file.txt")

    def test_checker_rejects_output_symlinks(self):
        self.build()
        original = self.write("original.txt")
        (self.site / "link.txt").symlink_to(original)
        (self.site / "linked-dir").symlink_to(self.root)
        errors = check(self.root, self.site)
        self.assertIn("Symlink in release: link.txt", errors)
        self.assertIn("Symlink in release: linked-dir", errors)

    def test_decks_pdfs_assets_and_generated_index(self):
        self.write("extras/deep-dive/deck.html", b'<script src="slide-assets/deck.js"></script>')
        self.write("extras/deep-dive/deck.pdf", b"PDF fixture")
        self.write("extras/deep-dive/slide-assets/deck.js", b"// fixture")
        self.write("extras/index.html", b"outdated index")
        self.build()
        index = (self.site / "extras/index.html").read_text()
        self.assertIn('href="deep-dive/deck.html"', index)
        self.assertIn('href="deep-dive/deck.pdf"', index)
        self.assertNotIn('href="deep-dive/slide-assets/deck.js"', index)
        self.assertIn('href="extras/index.html"', (self.site / "index.html").read_text())
        self.assertEqual([], check(self.root, self.site))

    def test_empty_extras_omitted(self):
        (self.root / "extras").mkdir()
        self.build()
        self.assertFalse((self.site / "extras").exists())
        self.assertNotIn('href="extras/index.html"', (self.site / "index.html").read_text())

    def test_missing_extras_index_is_reported(self):
        self.write("extras/handout.pdf")
        self.build()
        (self.site / "extras/index.html").unlink()
        self.assertIn("Missing extras index: extras/index.html", check(self.root, self.site))

    def test_checker_detects_missing_changed_and_unexpected_extras(self):
        self.write("extras/a.txt")
        self.write("extras/b.txt")
        self.build()
        (self.site / "extras/a.txt").unlink()
        (self.site / "extras/b.txt").write_text("changed")
        (self.site / "extras/leaked.md").write_text("private")
        errors = check(self.root, self.site)
        self.assertIn("Missing extras file: extras/a.txt", errors)
        self.assertIn("Extras differs: extras/b.txt", errors)
        self.assertIn("Unexpected extras file: extras/leaked.md", errors)
        self.assertIn("Private source: extras/leaked.md", errors)

    def test_symlink_file_or_directory_is_rejected(self):
        original = self.write("private.txt")
        extras = self.root / "extras"
        extras.mkdir()
        for target in [original, self.root]:
            with self.subTest(target=target):
                link = extras / "link"
                link.symlink_to(target)
                with self.assertRaises(ValueError):
                    self.build()
                link.unlink()

    def test_symlink_root_is_rejected(self):
        (self.root / "extras").symlink_to(self.root)
        with self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()
