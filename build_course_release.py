#!/usr/bin/env python3
"""Build a student-facing course site from a working repository's release.json."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

# Course-local launchers use runpy, which does not add this directory to sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_extras import extra_files, crossword_files
from release_policy import private_name, private_path, validate_source


TOOLS = Path(__file__).resolve().parent


def chapter_sort_key(number):
    match = re.fullmatch(r"(\d+)([A-Za-z]*)", str(number))
    if not match:
        raise ValueError(f"Invalid chapter number: {number}")
    return int(match[1]), match[2].lower()


def chapter_label(number):
    numeric, suffix = chapter_sort_key(number)
    return f"{numeric}{suffix}"


class ReleaseBuilder:
    def __init__(self, root: Path, output: Path, skip_build: bool = False):
        self.root = root.absolute()
        self.output = output.absolute()
        self.skip_build = skip_build
        self.config = json.loads((root / "release.json").read_text())
        self.site = self.config["site"]

    def run_build(self, script: str) -> None:
        if self.skip_build:
            return
        path = validate_source(self.root, self.root / script)
        if not path.exists():
            raise FileNotFoundError(path)
        command = ["python3", str(path)] if path.suffix == ".py" else ["bash", str(path)] if path.suffix == ".sh" else [str(path)]
        subprocess.run(command, cwd=path.parent, check=True)

    def copy_file(self, source: str, dest: Path) -> None:
        src = validate_source(self.root, self.root / source)
        if private_path(src.relative_to(self.root)) or private_path(dest.relative_to(self.output)):
            raise ValueError(f"Refusing to publish private source: {source}")
        if not src.exists():
            raise FileNotFoundError(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    def slide_pdf(self, item: dict) -> Path:
        source = validate_source(self.root, self.root / item["source"])
        pdf = validate_source(self.root, source.with_suffix(".pdf"))
        if not self.skip_build:
            node = shutil.which("node", path="/opt/homebrew/bin:/usr/local/bin") or shutil.which("node")
            if not node:
                raise RuntimeError("Node.js is required to export slides")
            subprocess.run([node, str(TOOLS / "export_slides_pdf.mjs"), str(source), str(pdf)], check=True, timeout=180)
        if not pdf.exists():
            raise FileNotFoundError(f"Build the slide PDF before using --skip-build: {pdf}")
        return pdf

    def ignored(self, _directory: str, names: list[str]) -> set[str]:
        release = self.config.get("release", {})
        ignored_names = set(release.get("exclude_names", []))
        suffixes = tuple(release.get("exclude_suffixes", []))
        return ignored_names | {name for name in names if private_name(name) or (suffixes and name.endswith(suffixes))}

    def copy_tree(self, source: str, dest: Path) -> None:
        src = validate_source(self.root, self.root / source)
        if private_path(src.relative_to(self.root)) or private_path(dest.relative_to(self.output)):
            raise ValueError(f"Refusing to publish private source: {source}")
        if not src.exists():
            raise FileNotFoundError(src)
        # Preflight the whole included tree before copytree can follow any link.
        for directory, dirs, files in os.walk(src, followlinks=False):
            ignored = self.ignored(directory, dirs + files)
            dirs[:] = [name for name in dirs if name not in ignored]
            for name in dirs + [name for name in files if name not in ignored]:
                validate_source(self.root, Path(directory) / name)
        shutil.copytree(src, dest, ignore=self.ignored)

    def build_reading(self, reading: dict) -> Path:
        source = validate_source(self.root, self.root / reading["source"], authoring=True)
        if not source.exists():
            raise FileNotFoundError(source)
        result = validate_source(self.root, source.with_suffix(".pdf") if source.suffix == ".md" else source)
        if source.suffix == ".md" and not self.skip_build:
            converter = self.config.get("markdown_to_pdf", str(Path.home() / ".local/bin/md-to-pdf"))
            subprocess.run([converter, str(source)], cwd=source.parent, check=True)
        if not result.exists():
            raise FileNotFoundError(result)
        return result

    def chapter_dir(self, chapter: dict) -> Path:
        return self.output / f"chapter-{chapter['number']}-{chapter['slug']}"

    def relative(self, path: Path) -> str:
        return path.relative_to(self.output).as_posix()

    def write_code_index(self, dest: Path, chapter: dict) -> None:
        rows, panels = [], []
        for path in sorted(dest.rglob("*")):
            if not path.is_file() or path == dest / "index.html":
                continue
            href = path.relative_to(dest).as_posix()
            file_id = "file-" + href.encode().hex()
            label = html.escape(href)
            raw = path.read_bytes()
            try:
                source = raw.decode("utf-8")
                if b"\0" in raw:
                    raise UnicodeError
                content = f"<pre><code>{html.escape(source, quote=False)}</code></pre>"
            except UnicodeError:
                content = '<p class="binary">This is a binary data file. It is available in the repository linked below.</p>'
            rows.append(f'<li><a href="#{file_id}">{label}</a></li>')
            hidden = " hidden" if panels else ""
            panels.append(f'<section class="source-file" id="{file_id}" aria-labelledby="title-{file_id}"{hidden}><header class="file-header"><h2 id="title-{file_id}">{label}</h2></header>{content}</section>')
        repo = self.site["repository"]
        repo_path = repo.get("code_path", "chapter-{number}-{slug}/code").format(**chapter)
        page = (TOOLS / "code_viewer.html").read_text()
        values = {
            "{{TITLE}}": html.escape(chapter["title"]),
            "{{REPO_URL}}": f"{repo['url']}/tree/{repo.get('branch', 'main')}/{repo_path}",
            "{{FILES}}": "\n".join(rows),
            "{{PANELS}}": "\n".join(panels),
        }
        for marker, value in values.items():
            page = page.replace(marker, value)
        (dest / "index.html").write_text(page)

    def render_page(self, title: str, body: str) -> str:
        theme = self.site["theme"]
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
    <style>
        body {{ background: linear-gradient(135deg, {theme['background_start']} 0%, {theme['background_end']} 100%); min-height: 100vh; font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif; padding: 48px 24px; }}
        .container {{ background: white; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,.2); padding: 40px; max-width: 960px; width: 100%; }}
        h1 {{ color: {theme['primary']}; margin-bottom: 18px; font-weight: 700; font-size: 42px; line-height: 1.1; }}
        .intro {{ color: #444; font-size: 17px; line-height: 1.55; margin-bottom: 30px; max-width: 780px; }}
        .chapter-label {{ color: {theme['secondary']}; font-size: 18px; font-weight: 700; margin-bottom: 8px; }}
        .chapter-title {{ {theme.get('chapter_title_css', 'overflow-wrap: anywhere;')} }}
        .toc-section {{ margin-bottom: 30px; }}
        .toc-section h2 {{ color: {theme['secondary']}; font-size: 18px; font-weight: 600; margin-bottom: 15px; border-bottom: 2px solid {theme['primary']}; padding-bottom: 8px; }}
        .toc-link {{ display: block; padding: 12px 16px; margin-bottom: 8px; background: #f8f9fa; border-left: 4px solid {theme['primary']}; text-decoration: none; color: #333; border-radius: 4px; transition: all .2s ease; }}
        .toc-link:hover {{ background: {theme['hover']}; border-left-color: {theme['secondary']}; transform: translateX(4px); }}
        .description {{ color: #666; font-size: 14px; margin-top: 4px; }}
    </style>
</head>
<body>
    <div class="container">
{body}    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

    @staticmethod
    def card(href: str, title: str, description: str) -> str:
        return f'            <a href="{html.escape(href)}" class="toc-link">\n                {html.escape(title)}\n                <div class="description">{html.escape(description)}</div>\n            </a>\n'

    def render_extras_index(self, extras: dict[Path, Path]) -> str:
        cards = []
        for relative in sorted(extras):
            local = relative.relative_to("extras")
            if any(part in ("assets", "slide-assets") for part in local.parts[:-1]):
                continue
            if local.suffix.lower() in (".css", ".js", ".svg", ".png", ".jpg", ".woff", ".woff2"):
                continue
            cards.append(self.card(quote(local.as_posix()), local.as_posix(), ""))
        body = '<h1>Extras</h1>\n' + "".join(cards)
        body += '<p><a href="../index.html">Back to chapters</a></p>\n'
        return self.render_page(f"Extras: {self.config['course_title']}", body)

    def render_index(self, links: dict[str, dict[str, str]], has_extras: bool = False) -> str:
        cards = "".join(self.card(links[c["number"]]["index"], f"Chapter {chapter_label(c['number'])}: {c['title']}", c["description"]) for c in self.chapters())
        repo = self.site["repository"]
        details = f"        <p>{html.escape(self.site['details'])}</p>\n" if self.site.get("details") else ""
        pages = "".join(self.card(page["filename"], page["title"], page.get("description", "")) for page in self.site.get("pages", []))
        if has_extras:
            pages += self.card("extras/index.html", "Extras", "Supplemental slides and documents.")
        body = f"""        <h1>{html.escape(self.config['course_title'])}</h1>
{details}        <p class="intro">{html.escape(self.site['intro'])}</p>
{pages}
        <div class="toc-section">
            <h2>Chapters</h2>
{cards}        </div>
        <div class="toc-section">
            <h2>Repository</h2>
            <p class="intro">The course code is in the public GitHub repository at <a href="{repo['url']}">{html.escape(repo['label'])}</a>. You can fork it on GitHub, clone it with <code>git clone {html.escape(repo['clone_url'])}</code>, or open it in <a href="{repo['codespaces_url']}">GitHub Codespaces</a>.</p>
        </div>
"""
        return self.render_page(self.config["course_title"], body)

    def render_chapter_index(self, chapter: dict, links: dict[str, str]) -> str:
        cards = []
        if "chapter" in links:
            cards.append(self.card(links["chapter"], chapter["title"], f"Chapter {chapter_label(chapter['number'])} workbook."))
        if "slides" in links:
            cards.append(self.card(links["slides"], "Slides", "Slide deck for class discussion."))
        if "slides_pdf" in links:
            cards.append(self.card(links["slides_pdf"], "Slides (PDF)", "One slide per page, for reading or printing."))
        if "code" in links:
            cards.append(self.card(links["code"], "Code", chapter.get("code_description", self.site["code_description"])))
        cards.extend(self.card(f"readings/{r['filename']}", r["title"], r["description"]) for r in chapter.get("readings", []))
        cards.extend(self.card(url, "Crossword", "Printable concept review.")
                     for name, url in links.items() if name.startswith("crossword:"))
        body = f"""        <div class="chapter-label">Chapter {chapter_label(chapter['number'])}</div>
        <h1 class="chapter-title">{html.escape(chapter['title'])}</h1>
        <p class="intro">{html.escape(chapter['description'])}</p>
        <div class="toc-section">
            <h2>Contents</h2>
{"".join(cards)}        </div>
        <p><a href="../index.html">Back to chapters</a></p>
"""
        return self.render_page(f"Chapter {chapter_label(chapter['number'])}: {chapter['title']}", body)

    def chapters(self) -> list[dict]:
        return sorted(self.config["chapters"], key=lambda item: chapter_sort_key(item["number"]))

    @staticmethod
    def write_redirect(path: Path, target: str, preserve_fragment: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        script = f"<script>location.replace({json.dumps(target)} + location.hash);</script>" if preserve_fragment else ""
        path.write_text(f'<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={html.escape(target)}"><title>Moved</title></head><body><a href="{html.escape(target)}">Open page</a>{script}</body></html>')

    def write_legacy_urls(self) -> None:
        legacy = self.config.get("legacy_urls", {})
        for chapter in self.chapters():
            base = self.chapter_dir(chapter)
            if legacy.get("workbook") and chapter.get("chapter"):
                source = base / chapter["chapter"]["filename"]
                dest = self.output / "workbook" / source.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
            if legacy.get("slides") and chapter.get("slides"):
                target = f"../../{base.name}/slides/{chapter['slides']['filename']}"
                self.write_redirect(self.output / "slides" / base.name / f"topic-{chapter['number']}-slides.html", target, True)
            if legacy.get("topics") and chapter.get("code"):
                self.write_redirect(self.output / "topics" / f"topic-{chapter['number']}-{chapter['slug']}.html", f"../{base.name}/index.html")

    def build(self) -> None:
        extras = extra_files(self.root, self.config)
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / ".nojekyll").write_text("")
        links: dict[str, dict[str, str]] = {}
        for chapter in self.chapters():
            key, base = chapter["number"], self.chapter_dir(chapter)
            links[key] = {}
            for kind in ("chapter", "slides"):
                item = chapter.get(kind)
                if not item:
                    continue
                if item.get("build"):
                    self.run_build(item["build"])
                dest = base / ("slides" if kind == "slides" else "") / item["filename"]
                self.copy_file(item["source"], dest)
                if kind == "slides" and item.get("assets"):
                    self.copy_tree(item["assets"], base / "slides/slide-assets")
                links[key][kind] = self.relative(dest)
                if kind == "slides" and item.get("pdf", True):
                    pdf = self.slide_pdf(item)
                    pdf_dest = dest.with_suffix(".pdf")
                    self.copy_file(str(pdf), pdf_dest)
                    links[key]["slides_pdf"] = self.relative(pdf_dest)
            if chapter.get("code"):
                dest = base / "code"
                self.copy_tree(chapter["code"]["source"], dest)
                self.write_code_index(dest, chapter)
                links[key]["code"] = self.relative(dest / "index.html")
            for reading in chapter.get("readings", []):
                source = self.build_reading(reading)
                dest = base / "readings" / reading["filename"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.copy_file(str(source), dest)
            for relative, source in crossword_files(self.root, chapter, self.config).items():
                self.copy_file(str(source), self.output / relative)
                links[key]["crossword:" + source.name] = relative.as_posix()
            prefix = self.relative(base) + "/"
            local_links = {name: path.removeprefix(prefix) for name, path in links[key].items()}
            index = base / "index.html"
            index.parent.mkdir(parents=True, exist_ok=True)
            index.write_text(self.render_chapter_index(chapter, local_links))
            links[key]["index"] = self.relative(index)
        for page in self.site.get("pages", []):
            self.copy_file(page["source"], self.output / page["filename"])
        for relative, source in extras.items():
            self.copy_file(str(source), self.output / relative)
        if extras:
            (self.output / "extras/index.html").write_text(self.render_extras_index(extras))
        (self.output / "index.html").write_text(self.render_index(links, bool(extras)))
        self.write_legacy_urls()
        if self.config.get("release_readme"):
            (self.output / "README.md").write_text(self.config["release_readme"].rstrip() + "\n")


def replace_output(staged: Path, final: Path) -> None:
    previous = final.with_name(f".{final.name}-previous")
    if previous.exists():
        shutil.rmtree(previous)
    if final.exists():
        final.rename(previous)
    staged.rename(final)
    if previous.exists():
        shutil.rmtree(previous)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course", nargs="?", type=Path, default=Path.cwd(), help="Working course repository (default: current directory)")
    parser.add_argument("--output", type=Path, help="Output directory (default: COURSE/release)")
    parser.add_argument("--skip-build", action="store_true", help="Use existing PDF and slide build products")
    args = parser.parse_args()
    root = args.course.resolve()
    from course_driver import dispatch
    if dispatch(root, args, 'build'):
        return
    final = args.output.resolve() if args.output else root / "release"
    if root.is_relative_to(final) or (final.is_relative_to(root) and final != root / 'release') or final.is_relative_to(root.parent / 'active'):
        raise ValueError('Build to release/ or a preview directory, not the working or active checkout')
    final.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{final.name}-build-", dir=final.parent))
    try:
        from chapter_release import ReleaseBuilder as ChapterReleaseBuilder
        ChapterReleaseBuilder(root, staged, args.skip_build).build()
        replace_output(staged, final)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
