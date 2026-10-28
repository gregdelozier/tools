#!/usr/bin/env python3
"""Select a chapter (with all code), or add one lecture to its release."""
import argparse
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_course_release import chapter_sort_key


def chapter_folder(root, number):
    matches = [p for p in root.glob('chapter-*') if p.is_dir() and re.fullmatch(r'chapter-\d+[A-Za-z]*-.+', p.name) and chapter_sort_key(p.name.split('-')[1]) == chapter_sort_key(number)]
    if len(matches) != 1:
        raise ValueError(f'Expected one chapter {number}, found {len(matches)}')
    return matches[0]


def change(root, kind, number, lecture=None):
    path = root / 'release.json'
    config = json.loads(path.read_text())
    folder = chapter_folder(root, number)
    chapter = next((c for c in config['chapters'] if chapter_sort_key(c['number']) == chapter_sort_key(number)), None)
    if kind == 'chapter':
        source = folder / (folder.name + '.md')
        if not source.exists():
            raise ValueError(f'No chapter manuscript: {source}')
        if chapter is None:
            n, slug = folder.name.split('-', 2)[1:]
            title = source.read_text().splitlines()[0].lstrip('# ').split(':', 1)[-1].strip()
            chapter = dict(number=n, slug=slug, title=title, description=title,
                           chapter=dict(source=str(source.with_suffix('.pdf').relative_to(root)),
                                        filename=source.with_suffix('.pdf').name,
                                        build=f'{folder.name}/build_pdf.sh'), lectures=[])
            if not (folder / 'build_pdf.sh').exists(): chapter['chapter'].pop('build')
            config['chapters'].append(chapter)
        if (folder / 'code').is_dir():
            chapter['code'] = {'source': f'{folder.name}/code'}
    else:
        if chapter is None:
            raise ValueError('Publish the chapter before adding its lectures')
        # Prefer a standalone lecture directory. Existing flat lectures/ also work.
        dirs = [p for parent in [folder, folder / 'lectures'] for p in parent.glob('lecture-*')
                if p.is_dir() and len(p.name.split('-', 2)) == 3 and p.name.split('-')[1].isdigit()
                and int(p.name.split('-')[1]) == lecture]
        if len(dirs) > 1:
            raise ValueError(f'Ambiguous lecture directory: {lecture}')
        directory = dirs[0] if dirs else folder / 'lectures'
        if dirs:
            decks = [p for p in directory.glob('*.md') if 'speaker-notes' not in p.name and 'instructor-notes' not in p.name and p.name != 'README.md']
            preferred = directory / (directory.name + '.md')
            if preferred.exists(): decks = [preferred]
        else:
            decks = [p for p in directory.glob('lecture-*.md') if len(p.name.split('-', 2)) == 3 and p.name.split('-')[1].isdigit() and int(p.name.split('-')[1]) == lecture and not p.stem.endswith('speaker-notes')]
        if len(decks) != 1:
            raise ValueError(f'Expected one slide deck for lecture {lecture}, found {len(decks)}')
        source = decks[0].with_suffix('.html')
        builder = directory / 'build_slides.py'
        if not builder.exists() and lecture != 0: builder = directory / 'build_deep_dive.py'
        if not source.exists() and source.with_suffix('.pdf').exists() and not builder.exists(): source = source.with_suffix('.pdf')
        slides = dict(source=str(source.relative_to(root)), filename=source.name, pdf=source.suffix != '.pdf')
        if (directory / 'slide-assets').is_dir(): slides['assets'] = str((directory / 'slide-assets').relative_to(root))
        if builder.exists(): slides['build'] = str(builder.relative_to(root))
        entries = chapter.setdefault('lectures', [])
        entries[:] = [entry for entry in entries if int(entry['number']) != lecture]
        entries.append(dict(number=lecture, title=decks[0].read_text().splitlines()[0].lstrip('# '), slides=slides, directory=str(directory.relative_to(folder))))
        entries.sort(key=lambda entry: int(entry['number']))
    config['chapters'].sort(key=lambda c: chapter_sort_key(c['number']))
    path.write_text(json.dumps(config, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course', type=Path, default=Path.cwd(), help='Working course repository')
    sub = parser.add_subparsers(dest='kind', required=True)
    chapter = sub.add_parser('chapter'); chapter.add_argument('number')
    lecture = sub.add_parser('lecture'); lecture.add_argument('number'); lecture.add_argument('lecture', type=int)
    args = parser.parse_args()
    change(args.course.resolve(), args.kind, args.number, getattr(args, 'lecture', None))
    print('Release selection saved. Build and check with build_course_release.py and check_course_release.py.')


if __name__ == '__main__':
    main()
