"""Non-overridable exclusions for student-facing course files."""

from pathlib import Path


PRIVATE_SUFFIXES = {".md", ".markdown", ".mmd", ".pyc"}


def private_name(name: str) -> bool:
    lower = name.lower()
    return (lower.startswith(".private")
            or lower in {"assignments", "instructor-notes", "speaker-notes",
                         ".git", "node_modules", "__pycache__"}
            or "speaker-notes" in lower or "instructor-notes" in lower
            or lower == "notes.js"
            or Path(lower).suffix in PRIVATE_SUFFIXES)


def private_path(path: Path) -> bool:
    return any(private_name(part) for part in path.parts)
