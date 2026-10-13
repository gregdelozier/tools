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
