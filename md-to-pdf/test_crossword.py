import tempfile
import unittest
from pathlib import Path
from crossword import ensure_crossword

class CrosswordTests(unittest.TestCase):
    def test_nonchapter_and_outline_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p=root/'notes.md';p.write_text('Text '*300)
            ensure_crossword(p)
            self.assertFalse((root/'exercises').exists())
            d=root/'chapter-01-example';d.mkdir()
            p=d/'chapter-01-example.md';p.write_text('# Outline\n')
            ensure_crossword(p)
            self.assertFalse((d/'exercises').exists())

    def test_existing_puzzle_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'chapter-01-example';d.mkdir()
            p=d/'chapter-01-example.md';p.write_text('# Example\n'+'Text '*300)
            e=d/'exercises';e.mkdir();pdf=e/'my-crossword.pdf';pdf.write_bytes(b'existing')
            ensure_crossword(p)
            self.assertEqual(b'existing',pdf.read_bytes())
            self.assertEqual([pdf],list(e.iterdir()))

if __name__=='__main__':unittest.main()
