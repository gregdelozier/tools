#!/usr/bin/env python3
"""Check links, private-source exclusions, and copied code in a course release."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        for key in ("href", "src"):
            if values.get(key):
                self.links.append(values[key])


def check(root: Path, site: Path) -> list[str]:
    config = json.loads((root / "release.json").read_text())
    validation = config.get("validation", {})
    errors: list[str] = []
    allowed_markdown = {site / "README.md"} if config.get("release_readme") else set()
    private_suffixes = set(validation.get("private_suffixes", [".md", ".mmd", ".pyc"]))
    skip_link_parts = set(validation.get("skip_link_parts", ["templates"]))
    for path in site.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        if path.suffix in private_suffixes and path not in allowed_markdown:
            errors.append(f"Private source: {path.relative_to(site)}")
        if path.suffix != ".html":
            continue
        text = path.read_text(errors="replace")
        parser = Links()
        parser.feed(text)
        if '<aside class="notes">' in text or "RevealNotes" in text:
            errors.append(f"Speaker notes: {path.relative_to(site)}")
        if skip_link_parts.intersection(path.relative_to(site).parts):
            continue
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if target.is_dir():
                target /= "index.html"
            if not target.exists():
                errors.append(f"Broken link: {path.relative_to(site)} -> {link}")
            if not url.path and url.fragment and url.fragment not in parser.ids:
                errors.append(f"Missing anchor: {path.relative_to(site)} -> {link}")
    expected = {f"chapter-{c['number']}-{c['slug']}" for c in config["chapters"]}
    actual = {path.name for path in site.glob("chapter-*") if path.is_dir()}
    if actual != expected:
        errors.append(f"Chapter directories differ: expected {sorted(expected)}, found {sorted(actual)}")
    for chapter in config["chapters"]:
        if "code" not in chapter:
            continue
        source = root / chapter["code"]["source"]
        dest = site / f"chapter-{chapter['number']}-{chapter['slug']}" / "code"
        for path in dest.rglob("*"):
            if path.is_file() and path != dest / "index.html":
                original = source / path.relative_to(dest)
                if not original.exists() or original.read_bytes() != path.read_bytes():
                    errors.append(f"Code differs: {path.relative_to(site)}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course", nargs="?", type=Path, default=Path.cwd(), help="Working course repository")
    parser.add_argument("--site", type=Path, help="Release directory (default: COURSE/release)")
    args = parser.parse_args()
    root = args.course.resolve()
    site = args.site.resolve() if args.site else root / "release"
    errors = check(root, site)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: links, release scope, private-source exclusions, and unchanged code in {site}")


if __name__ == "__main__":
    main()
