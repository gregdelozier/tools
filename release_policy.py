"""Non-overridable exclusions for student-facing course files."""

from pathlib import Path
import re


PRIVATE_SUFFIXES = {".md", ".markdown", ".mmd", ".pyc"}


def private_name(name: str) -> bool:
    lower = name.lower()
    crossword_key = ("crossword" in lower and
                     bool(set(re.split(r"[^a-z]+", lower)) & {"key", "keys", "answer", "answers", "solution", "solutions"}))
    return (crossword_key or lower.startswith(".private")
            or lower in {"assignments", "instructor-notes", "speaker-notes",
                         ".git", "node_modules", "__pycache__"}
            or "speaker-notes" in lower or "instructor-notes" in lower
            or lower == "notes.js"
            or Path(lower).suffix in PRIVATE_SUFFIXES)


def private_path(path: Path) -> bool:
    return any(private_name(part) for part in path.parts)


def validate_source(root: Path, path: Path, *, authoring: bool = False) -> Path:
    """Reject traversal and links below the trusted course root, before reading."""
    root = root.absolute()
    if not path.is_absolute():
        path = root / path
    if ".." in path.parts:
        raise ValueError(f"Source traversal is not allowed: {path}")
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Publication source must not be a symlink: {current}")
    policy_path = relative
    if authoring and relative.suffix.lower() in {".md", ".markdown", ".mmd"}:
        policy_path = relative.with_suffix("")
    if private_path(policy_path):
        raise ValueError(f"Refusing private publication source: {path}")
    return path
