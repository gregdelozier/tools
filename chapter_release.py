"""Chapter publication and separate lecture publication for student course releases."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile

SHARED = Path(__file__).resolve().parent
sys.path.insert(0, str(SHARED))
from build_course_release import ReleaseBuilder as BaseBuilder, replace_output
from release_extras import extra_files
from release_policy import private_path, validate_source


def answer_key(path):
    for part in Path(path).parts:
        words = set(re.split(r'[^a-z]+', part.lower()))
        if 'crossword' in part.lower() and words & {'key', 'keys', 'answer', 'answers', 'solution', 'solutions'}:
            return True
    return False


def crossword_files(root, chapter, config):
    relative = Path(f"chapter-{chapter['number']}-{chapter['slug']}") / 'exercises'
    folder = validate_source(root, root / relative)
    excluded = config.get('release', {})
    result = {}
    for path in sorted(folder.glob('*')):
        if path.suffix.lower() != '.pdf' or 'crossword' not in path.stem.lower() or answer_key(path.name) or private_path(path.relative_to(root)):
            continue
        if path.name in excluded.get('exclude_names', []) or any(path.name.endswith(s) for s in excluded.get('exclude_suffixes', [])):
            continue
        validate_source(root, path)
        if path.is_file():
            result[relative / path.name] = path
    return result


def relative_name(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value:
        raise ValueError(f'Invalid release path: {value}')
    return Path(value)


def chapter_slides(root, chapter):
    """Existing chapter slides travel with the chapter, never lecture folders."""
    result = [chapter['slides']] if chapter.get('slides') else []
    folder = root / f"chapter-{chapter['number']}-{chapter['slug']}" / 'slides'
    seen = {str(Path(item['source']).resolve()) if Path(item['source']).is_absolute() else str((root / item['source']).resolve()) for item in result}
    for source in sorted(folder.glob('*')):
        if source.suffix not in {'.html', '.pdf'} or 'speaker-notes' in source.name or 'instructor-notes' in source.name or answer_key(source.name):
            continue
        if str(source.resolve()) in seen or (source.suffix == '.pdf' and source.with_suffix('.html').exists()):
            continue
        item = dict(source=str(source.relative_to(root)), filename=source.name, pdf=source.suffix == '.html')
        if (folder / 'slide-assets').is_dir(): item['assets'] = str((folder / 'slide-assets').relative_to(root))
        builder = folder / 'build_slides.py'
        if builder.exists(): item['build'] = str(builder.relative_to(root))
        result.append(item)
    return result


class ReleaseBuilder(BaseBuilder):
    def ignored(self, directory, names):
        return super().ignored(directory, names) | {'.pytest_cache', '.mypy_cache', '.ruff_cache', '.venv', '.coverage', 'htmlcov'} | {name for name in names if answer_key(name)}

    def copy_file(self, source, dest):
        if answer_key(source) or answer_key(dest.relative_to(self.output)):
            raise ValueError(f'Refusing crossword answer-key publication: {source}')
        super().copy_file(source, dest)

    def materials(self, chapter):
        item = chapter['chapter']
        yield 'chapter', 'chapter', item, relative_name(item['filename'])
        folder = self.root / self.chapter_dir(chapter).name
        code = {'source': str((folder / 'code').relative_to(self.root))} if (folder / 'code').is_dir() else chapter.get('code')
        if code:
            yield 'code', 'code', code, Path('code')
        slide_items = chapter_slides(self.root, chapter)
        for index, slide in enumerate(slide_items):
            key = 'slides' if index == 0 else f'slides:{index}'
            yield key, 'slides', slide, Path('slides') / relative_name(slide['filename'])
        for lecture in chapter.get('lectures', []):
            item = lecture['slides']
            yield f"lecture:{lecture['number']}:slides", 'slides', item, relative_name(lecture.get('directory', 'lectures')) / relative_name(item['filename'])

    def copy_code(self, item, dest, chapter):
        self.copy_tree(item['source'], dest)
        self.write_code_index(dest, chapter)

    def render_chapter_index(self, chapter, links):
        groups = []
        base_links = {key: value for key, value in links.items() if not key.startswith('lecture:')}
        # Reuse the established chapter-page appearance and URLs.
        visible = chapter
        page = super().render_chapter_index(visible, base_links)
        for lecture in chapter.get('lectures', []):
            number = str(lecture['number'])
            prefix = f'lecture:{number}:'
            cards = []
            for kind, title, description in [('slides', 'Slides', 'Lecture slides.'), ('slides_pdf', 'Slides (PDF)', 'Printable lecture slides.')]:
                if prefix + kind in links:
                    cards.append(self.card(links[prefix + kind], title, description))
            if cards:
                title = html.escape(lecture.get('title', f'Lecture {int(number)}'))
                groups.append(f'<section class="toc-section"><h2>Lecture {int(number)}: {title}</h2>\n' + ''.join(cards) + '</section>\n')
        for key, path in links.items():
            if key.startswith('slides:'):
                groups.append(self.card(path, 'Slides (PDF)' if key.endswith('_pdf') else 'Slides', 'Chapter slides.'))
        return page.replace('        <p><a href="../index.html">Back to chapters</a></p>', ''.join(groups) + '        <p><a href="../index.html">Back to chapters</a></p>')

    def write_legacy_urls(self):
        legacy = self.config.get('legacy_urls', {})
        for chapter in self.chapters():
            base = self.chapter_dir(chapter)
            active = {key: (kind, item) for key, kind, item, _ in self.materials(chapter)}
            if legacy.get('workbook') and 'chapter' in active:
                source = base / chapter['chapter']['filename']
                dest = self.output / 'workbook' / source.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
            if legacy.get('slides') and ('slides' in active or chapter.get('lectures')):
                if 'slides' in active:
                    target = f"../../{base.name}/slides/{active['slides'][1]['filename']}"
                else:
                    lecture = chapter['lectures'][0]
                    target = f"../../{base.name}/{lecture.get('directory', 'lectures')}/{lecture['slides']['filename']}"
                self.write_redirect(self.output / 'slides' / base.name / f"topic-{chapter['number']}-slides.html", target, True)
            if legacy.get('topics') and 'code' in active:
                self.write_redirect(self.output / 'topics' / f"topic-{chapter['number']}-{chapter['slug']}.html", f'../{base.name}/index.html')

    def build(self):
        extras = extra_files(self.root, self.config)
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / '.nojekyll').write_text('')
        links = {}
        for chapter in self.chapters():
            key, base = chapter['number'], self.chapter_dir(chapter)
            links[key] = {}
            for link, kind, item, relative in self.materials(chapter):
                dest = base / relative
                if kind == 'code':
                    self.copy_code(item, dest, chapter)
                    links[key][link] = self.relative(dest / 'index.html')
                    continue
                self.run_build(item.get('build', '')) if item.get('build') else None
                self.copy_file(item['source'], dest)
                if kind == 'slides' and item.get('assets'):
                    assets = dest.parent / 'slide-assets'
                    if not assets.exists():
                        self.copy_tree(item['assets'], assets)
                links[key][link] = self.relative(dest)
                if kind == 'slides' and item.get('pdf', True):
                    self.copy_file(str(self.slide_pdf(item)), dest.with_suffix('.pdf'))
                    links[key][link + '_pdf'] = self.relative(dest.with_suffix('.pdf'))
            for reading in chapter.get('readings', []):
                source = self.build_reading(reading)
                dest = Path(os.path.normpath(base / 'readings' / reading['filename']))
                dest.relative_to(base)
                self.copy_file(str(source), dest)
            if chapter.get('crosswords', True):
                for relative, source in crossword_files(self.root, chapter, self.config).items():
                    self.copy_file(str(source), self.output / relative)
                    links[key]['crossword:' + source.name] = relative.as_posix()
            prefix = self.relative(base) + '/'
            local = {name: path.removeprefix(prefix) for name, path in links[key].items()}
            base.mkdir(parents=True, exist_ok=True)
            (base / 'index.html').write_text(self.render_chapter_index(chapter, local))
            links[key]['index'] = self.relative(base / 'index.html')
        for page in self.site.get('pages', []):
            self.copy_file(page['source'], self.output / relative_name(page['filename']))
        for relative, source in extras.items():
            self.copy_file(str(source), self.output / relative)
        if extras:
            (self.output / 'extras/index.html').write_text(self.render_extras_index(extras))
        (self.output / 'index.html').write_text(self.render_index(links, bool(extras)))
        self.write_legacy_urls()
        if self.config.get('release_readme'):
            (self.output / 'README.md').write_text(self.config['release_readme'].rstrip() + '\n')


def check(root, site, config=None):
    """Compare the release with selected chapters and lectures."""
    from check_course_release import Links
    from urllib.parse import unquote, urlsplit
    errors = []
    with tempfile.TemporaryDirectory(prefix='course-release-check-') as tmp:
        expected = Path(tmp) / 'expected'
        builder = ReleaseBuilder(root, expected, True)
        if config is not None:
            builder.config = config
            builder.site = config['site']
        builder.build()
        wanted = {p.relative_to(expected): p for p in expected.rglob('*') if p.is_file()}
        actual = {}
        for directory, dirs, files in os.walk(site, followlinks=False):
            dirs[:] = [d for d in dirs if d != '.git']
            for name in dirs + files:
                path = Path(directory) / name
                if path.is_symlink():
                    errors.append(f'Symlink in release: {path.relative_to(site)}')
            for name in files:
                path = Path(directory) / name
                if not path.is_symlink():
                    actual[path.relative_to(site)] = path
        for relative, source in wanted.items():
            if relative not in actual:
                errors.append(f'Missing release file: {relative}')
            elif source.read_bytes() != actual[relative].read_bytes():
                errors.append(f'Release differs: {relative}')
        for relative in actual.keys() - wanted.keys():
            if relative == Path('.gitignore') and (root / relative).is_file() and actual[relative].read_bytes() == (root / relative).read_bytes():
                continue
            errors.append(f'Unexpected release file: {relative}')
        for relative, path in actual.items():
            if path.suffix != '.html':
                continue
            parser = Links(); parser.feed(path.read_text(errors='replace'))
            if '<aside class="notes">' in path.read_text(errors='replace'):
                errors.append(f'Speaker notes in release: {relative}')
            if set(builder.config.get('validation', {}).get('skip_link_parts', ['templates'])).intersection(relative.parts):
                continue
            for link in parser.links:
                url = urlsplit(link)
                if url.scheme or url.netloc:
                    continue
                target = (path.parent / unquote(url.path)).resolve() if url.path else path
                if target.is_dir():
                    target /= 'index.html'
                if not target.exists():
                    errors.append(f'Broken link: {relative} -> {link}')
                if not url.path and url.fragment and url.fragment not in parser.ids:
                    errors.append(f'Missing anchor: {relative} -> {link}')
    return errors


def build_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('course', nargs='?', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--skip-build', action='store_true')
    args = parser.parse_args()
    root = args.course.resolve()
    final = (args.output or root / 'release').resolve()
    if root.is_relative_to(final) or (final.is_relative_to(root) and final != root / 'release') or final.is_relative_to(root.parent / 'active'):
        raise ValueError('Build to release/ or a preview directory, not the working or active checkout')
    final.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f'.{final.name}-build-', dir=final.parent))
    try:
        ReleaseBuilder(root, staged, args.skip_build).build()
        replace_output(staged, final)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise


def check_main():
    parser = argparse.ArgumentParser(description='Check selected chapters and lecture material')
    parser.add_argument('course', nargs='?', type=Path, default=Path.cwd())
    parser.add_argument('--site', type=Path)
    args = parser.parse_args()
    root = args.course.resolve()
    errors = check(root, (args.site or root / 'release').resolve())
    if errors:
        raise SystemExit('\n'.join(errors))
    print('PASS: chapters with all code, selected lectures, links, and exact source contents')
