import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from course_driver import dispatch


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'release.json').write_text(json.dumps({'course_release_driver': 'driver.py'}))
        (self.root / 'driver.py').write_text('import sys\nfrom pathlib import Path\ndef build_main():\n    Path(__file__).with_suffix(".result").write_text("build " + " ".join(sys.argv[1:]))\ndef check_main():\n    Path(__file__).with_suffix(".result").write_text("check " + " ".join(sys.argv[1:]))\n')

    def test_forwards_build_flags_and_restores_argv(self):
        with patch('sys.argv', ['original']) as argv:
            self.assertTrue(dispatch(self.root, argparse.Namespace(output=Path('/tmp/preview'), skip_build=True), 'build'))
            self.assertEqual(argv, ['original'])
        self.assertEqual('build --output /tmp/preview --skip-build', (self.root / 'driver.result').read_text())

    def test_forwards_check_site(self):
        self.assertTrue(dispatch(self.root, argparse.Namespace(site=Path('/tmp/preview')), 'check'))
        self.assertEqual('check --site /tmp/preview', (self.root / 'driver.result').read_text())

    def test_other_courses_keep_standard_driver(self):
        (self.root / 'release.json').write_text('{}')
        self.assertFalse(dispatch(self.root, argparse.Namespace(), 'build'))

    def test_rejects_outside_driver(self):
        (self.root / 'release.json').write_text(json.dumps({'course_release_driver': '../driver.py'}))
        with self.assertRaises(ValueError): dispatch(self.root, argparse.Namespace(), 'build')


if __name__ == '__main__': unittest.main()
