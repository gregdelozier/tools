"""Find explicitly publishable files in the course-root extras directory."""

import os
from pathlib import Path
from release_policy import private_name


def extra_files(root: Path, config: dict) -> dict[Path, Path]:
    """Map public extras to sources, excluding authoring and private files."""
    excluded = {".git", ".DS_Store", "__pycache__", "assignments", "instructor-notes",
                "speaker-notes.md", "notes.js"}
    excluded.update(config.get("release", {}).get("exclude_names", []))
    result = {}
    base = root / "extras"
    if base.is_symlink():
        raise ValueError(f"Extras source must not be a symlink: {base}")
    if not base.is_dir():
        return result
    for directory, dirs, files in os.walk(base, followlinks=False):
        parent = Path(directory)
        relative = parent.relative_to(root)
        for name in list(dirs):
            path = parent / name
            if name in excluded or private_name(name):
                dirs.remove(name)
            elif path.is_symlink():
                raise ValueError(f"Extras source must not be a symlink: {path}")
        for name in files:
            if parent == base and name == "index.html":
                continue  # The release builder owns the extras contents page.
            suffixes = tuple(config.get("release", {}).get("exclude_suffixes", []))
            if name in excluded or private_name(name) or (suffixes and name.endswith(suffixes)):
                continue
            path = parent / name
            if path.is_symlink():
                raise ValueError(f"Extras source must not be a symlink: {path}")
            result[relative / name] = path
    return result


def crossword_files(root: Path, chapter: dict, config: dict) -> dict[Path, Path]:
    """Discover finished crossword PDFs only for a selected chapter."""
    from release_policy import validate_source
    relative = Path(f"chapter-{chapter['number']}-{chapter['slug']}") / "exercises"
    base = validate_source(root, root / relative)
    if not base.is_dir():
        return {}
    release = config.get("release", {})
    excluded = set(release.get("exclude_names", []))
    suffixes = tuple(release.get("exclude_suffixes", []))
    result = {}
    for path in sorted(base.glob("*")):
        if "crossword" not in path.stem.lower() or path.suffix.lower() != ".pdf":
            continue
        if private_name(path.name) or path.name in excluded or (suffixes and path.name.endswith(suffixes)):
            continue
        validate_source(root, path)
        if path.is_file():
            result[relative / path.name] = path
    return result
