"""Honor a course's release driver when using the shared command-line tools."""
import importlib.util
import json
from pathlib import Path
import sys

from release_policy import validate_source


def dispatch(root, args, action):
    config = json.loads((root / 'release.json').read_text())
    source = config.get('course_release_driver')
    if not source:
        return False
    path = validate_source(root, root / source)
    spec = importlib.util.spec_from_file_location('_course_release_driver', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = sys.argv
    forwarded = [str(path)]
    if action == 'build':
        if args.output:
            forwarded += ['--output', str(args.output)]
        if args.skip_build:
            forwarded.append('--skip-build')
        entry = module.build_main
    elif action == 'check':
        if args.site:
            forwarded += ['--site', str(args.site)]
        entry = module.check_main
    else:
        raise ValueError(f'Unknown release action: {action}')
    try:
        sys.argv = forwarded
        entry()
    finally:
        sys.argv = original
    return True
