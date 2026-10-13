#!/usr/bin/env python3
"""Preview or apply a chapter-first working-course layout. Never touches active."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil


COLLECTIONS = {"chapters": "", "slides": "slides", "code": "code"}
CHAPTER = re.compile(r"\d{2,}-[a-z0-9]+(?:-[a-z0-9]+)*")


def mapped(path: str, moves: dict[str, str]) -> str:
    for old in sorted(moves, key=len, reverse=True):
        if path == old or path.startswith(old + "/"):
            return moves[old] + path[len(old):]
    return path


def plan(root: Path, archive_conflicts: bool = False) -> dict[str, str]:
    config = json.loads((root / "release.json").read_text())
    names = {f"{c['number']}-{c['slug']}" for c in config["chapters"]}
    names.update(p.name for p in (root / "chapters").glob("*") if p.is_dir())
    names.update(p.name.removeprefix("chapter-") for p in root.glob("chapter-*") if p.is_dir())
    moves = {}
    for collection, child in COLLECTIONS.items():
        for source in sorted((root / collection).glob("*")):
            if source.name in {".gitkeep", ".DS_Store"}:
                continue
            if not source.is_dir() or not CHAPTER.fullmatch(source.name):
                raise ValueError(f"Unrecognized course directory: {source}")
            number = source.name.split("-", 1)[0]
            conflicts = {name for name in names if name.split("-", 1)[0] == number and name != source.name}
            if conflicts:
                if collection != "code" or not archive_conflicts:
                    raise ValueError(f"Conflicting chapter number: {source.name} versus {sorted(conflicts)}. "
                                     "Review the mapping; --archive-conflicting-code preserves older code separately.")
                destination = f"archive/legacy-code/{source.name}"
            else:
                names.add(source.name)
                destination = f"chapter-{source.name}" + (f"/{child}" if child else "")
            moves[source.relative_to(root).as_posix()] = destination

    # Reading ownership comes from the release manifest, never a guessed number.
    for chapter in config["chapters"]:
        for reading in chapter.get("readings", []):
            source = reading["source"]
            if source.startswith("chapter-"):
                continue
            target = f"chapter-{chapter['number']}-{chapter['slug']}/readings/{Path(source).name}"
            if source in moves and moves[source] != target:
                raise ValueError(f"Shared reading needs an explicit owner: {source}")
            moves[source] = target
            if Path(source).suffix == ".md" and (root / source).with_suffix(".pdf").exists():
                moves[str(Path(source).with_suffix('.pdf'))] = str(Path(target).with_suffix('.pdf'))

    for source in sorted((root / "lecture-notes").glob("lecture-*.md")):
        name = source.stem.removeprefix("lecture-")
        if name in names:
            moves[source.relative_to(root).as_posix()] = f"chapter-{name}/instructor-notes/{source.name}"
    return moves


def file_moves(root: Path, moves: dict[str, str]) -> dict[str, str]:
    files = {}
    for old, new in moves.items():
        if any(Path(p).is_absolute() or ".." in Path(p).parts for p in (old, new)):
            raise ValueError(f"Migration paths must stay inside the course: {old} -> {new}")
        source = root / old
        if source.is_symlink():
            raise ValueError(f"Review symlink before migration: {source}")
        if not source.exists():
            raise FileNotFoundError(source)
        paths = source.rglob("*") if source.is_dir() else [source]
        for path in paths:
            if path.is_symlink():
                raise ValueError(f"Review symlink before migration: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            destination = new + relative[len(old):]
            if old.startswith("slides/"):
                chapter = old.split("/", 1)[1]
                number = chapter.split("-", 1)[0]
                filename = Path(destination).name
                if filename in {f"topic-{number}-slides.md", f"topic-{number}-slides.html", f"topic-{number}-slides.pdf"}:
                    destination = str(Path(destination).with_name(f"slides-{chapter}{Path(filename).suffix}"))
                elif filename == f"topic-{number}-speaker-notes.md":
                    destination = str(Path(destination).with_name("speaker-notes.md"))
            files[relative] = destination
    destinations = list(files.values())
    if len(destinations) != len(set(destinations)):
        raise ValueError("Two source files have the same destination")
    for dest in destinations:
        if (root / dest).exists():
            raise FileExistsError(f"Refusing to overwrite {root / dest}")
    return files


def rewrite_text(text: str, old_path: str, new_path: str, moves: dict[str, str]) -> str:
    replacements = dict(moves)
    for old, new in moves.items():
        # Relative paths in links, notes, and build scripts need the new depth.
        relative = os.path.relpath(old, Path(old_path).parent)
        target = os.path.relpath(new, Path(new_path).parent)
        if relative != ".":
            replacements[relative] = target
    if not replacements:
        return text
    # Only replace complete known path prefixes, not URLs or parts of identifiers.
    pattern = r"(?<![\w/.-])(?:" + "|".join(re.escape(p) for p in sorted(replacements, key=len, reverse=True)) + r")(?=$|[/\s`\"'<>),:;\]]|\.(?:\s|$))"
    return re.sub(pattern, lambda match: replacements[match.group()], text)


def migrate(root: Path, backup: Path, archive_conflicts: bool = False) -> dict:
    root = root.resolve()
    moves = plan(root, archive_conflicts)
    files = file_moves(root, moves)
    if not moves:
        return {"moves": {}, "message": "Already chapter-first; no changes."}
    backup = backup.resolve()
    if backup == root or root in backup.parents:
        raise ValueError("Backup must be outside the working repository")
    if backup.exists():
        raise FileExistsError(f"Backup already exists: {backup}")
    mapping = {**moves, **files}
    config = json.loads((root / "release.json").read_text())
    for chapter in config["chapters"]:
        for kind in ("chapter", "slides", "code"):
            for key in ("source", "build", "assets"):
                if key in chapter.get(kind, {}):
                    chapter[kind][key] = mapped(chapter[kind][key], mapping)
        for reading in chapter.get("readings", []):
            reading["source"] = mapped(reading["source"], mapping)
    config["layout"] = "chapter-first"
    edits = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if set(relative.parts) & {".git", "release", "archive", "node_modules", ".venv", "venv", "__pycache__"}:
            continue
        # Preserve runnable code byte for byte; only documentation and builders change.
        if path.name == "AGENTS.md" or path.suffix not in {".md", ".py", ".sh"}:
            continue
        if "code" in relative.parts and path.suffix != ".md":
            continue
        old = relative.as_posix()
        text = path.read_text()
        updated = rewrite_text(text, old, files.get(old, old), mapping)
        if updated != text:
            edits[files.get(old, old)] = updated
    # The complete backup includes uncommitted and untracked work, plus Git history.
    shutil.copytree(root, backup, symlinks=True)
    report = {"moves": moves, "files": files, "rewritten": sorted(edits), "backup": str(backup)}
    (backup.parent / (backup.name + "-migration.json")).write_text(json.dumps(report, indent=2) + "\n")
    for old, new in moves.items():
        if (root / old).is_dir():
            (root / new).mkdir(parents=True, exist_ok=True)
            for directory in (root / old).rglob("*"):
                if directory.is_dir():
                    (root / new / directory.relative_to(root / old)).mkdir(parents=True, exist_ok=True)
    for old, new in files.items():
        destination = root / new
        destination.parent.mkdir(parents=True, exist_ok=True)
        (root / old).rename(destination)
    for path, content in edits.items():
        (root / path).write_text(content)
    (root / "release.json").write_text(json.dumps(config, indent=2) + "\n")
    for collection in (*COLLECTIONS, "notes", "lecture-notes"):
        directory = root / collection
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.name == ".gitkeep":
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        if not any(directory.iterdir()):
            directory.rmdir()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course", type=Path)
    parser.add_argument("--apply", action="store_true", help="Apply after making a complete backup")
    parser.add_argument("--backup", type=Path, help="New backup directory outside the course")
    parser.add_argument("--archive-conflicting-code", action="store_true", help="Preserve mismatched older code under archive/legacy-code")
    args = parser.parse_args()
    root = args.course.expanduser().resolve()
    try:
        moves = plan(root, args.archive_conflicting_code)
        files = file_moves(root, moves)
        for old, new in moves.items():
            print(f"{old} -> {new}")
        print(f"{len(files)} files; release selection and active repository stay unchanged.")
        if args.apply:
            backup = args.backup or root.parent / f"working-backup-{datetime.now():%Y%m%d-%H%M%S}"
            report = migrate(root, backup, args.archive_conflicting_code)
            print(report.get("message", f"Backup: {backup}"))
        else:
            print("Preview only. Use --apply to migrate.")
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
