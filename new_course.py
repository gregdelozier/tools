#!/usr/bin/env python3
"""Create working and active repositories for a new course."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
DEFAULT_THEME = {
    "background_start": "#1f2937",
    "background_end": "#0f766e",
    "primary": "#0f766e",
    "secondary": "#155e75",
    "hover": "#e6f4f1",
}


def slug_value(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise argparse.ArgumentTypeError("use lowercase letters, numbers, and single hyphens")
    return value


def write(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if executable:
        path.chmod(0o755)


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def ensure_available(course_root: Path) -> None:
    if course_root.exists() and any(course_root.iterdir()):
        raise SystemExit(f"Refusing to replace nonempty directory: {course_root}")


def launcher(tool: str, shared: str) -> str:
    return f'''#!/usr/bin/env python3
"""Run the shared {tool} tool for this course."""

import runpy
import sys
from pathlib import Path


COURSE = Path(__file__).resolve().parents[1]
TOOL = Path.home() / "courses/tools/{shared}"
sys.argv[1:1] = [str(COURSE)]
runpy.run_path(str(TOOL), run_name="__main__")
'''


def initialize_git(path: Path, message: str) -> None:
    run(["git", "init", "-b", "main"], path)
    run(["git", "add", "."], path)
    run(["git", "commit", "-m", message], path)


def create_github_repo(owner: str, name: str, source: Path, visibility: str) -> None:
    run(
        ["gh", "repo", "create", f"{owner}/{name}", f"--{visibility}", "--source", str(source), "--remote", "origin", "--push"],
        source,
    )


def enable_github_pages(owner: str, name: str, source: Path) -> None:
    run(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{owner}/{name}/pages",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2026-03-10",
            "-f",
            "build_type=legacy",
            "-f",
            "source[branch]=main",
            "-f",
            "source[path]=/",
        ],
        source,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", type=slug_value, help="Directory and repository name, such as operating-systems")
    parser.add_argument("--title", required=True, help="Student-facing course title")
    parser.add_argument("--description", required=True, help="Short course description for the site index")
    parser.add_argument("--details", help="Optional term, instructor, and meeting line")
    parser.add_argument("--base", type=Path, default=Path.home() / "courses", help="Parent directory for the course")
    parser.add_argument("--working-owner", default="gregdelozier", help="GitHub owner for the working repository")
    parser.add_argument("--active-owner", default="kentcs", help="GitHub owner for the student repository")
    parser.add_argument("--no-git", action="store_true", help="Do not initialize local Git repositories")
    parser.add_argument("--github", action="store_true", help="Create and push the GitHub repositories")
    args = parser.parse_args()

    if args.github and args.no_git:
        parser.error("--github cannot be combined with --no-git")

    course_root = args.base.expanduser().resolve() / args.slug
    ensure_available(course_root)
    working = course_root / "working"
    active = course_root / "active"

    chapter = working / "chapter-00-introduction"
    for directory in (chapter / "slides", chapter / "code", chapter / "readings", working / "archive"):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".gitkeep").write_text("")
    write(chapter / "chapter-00-introduction.md", "# Introduction\n\n::: {.author}\nGregory S. DeLozier, PhD\n:::\n\n")
    write(chapter / "slides/slides-00-introduction.md", '# Introduction\n\nCourse introduction\n\n<hr style="border:0;border-top:1px solid #c3cbd0;margin:32px 0 18px">\n\n<p class="slide-author" style="font-size:22px">Gregory S. DeLozier, PhD</p>\n\nNote:\n\n')
    write(chapter / "slides/speaker-notes.md", "# Introduction: Speaker Notes\n\n")
    write(chapter / "build_pdf.sh", '''#!/usr/bin/env bash
set -euo pipefail
chapter_dir="$(cd "$(dirname "$0")" && pwd)"
"$HOME/.local/bin/md-to-pdf" "$chapter_dir/chapter-00-introduction.md"
''', True)

    public_url = f"https://github.com/{args.active_owner}/{args.slug}"
    site = {
        "intro": args.description,
        "code_description": "Examples and supporting files for this chapter.",
        "repository": {
            "label": f"{args.active_owner}/{args.slug}",
            "url": public_url,
            "clone_url": f"{public_url}.git",
            "codespaces_url": public_url,
        },
        "theme": DEFAULT_THEME,
    }
    if args.details:
        site["details"] = args.details

    config = {
        "layout": "chapter-first",
        "course_title": args.title,
        "release_readme": f"# {args.title}\n\nStudent materials: {public_url}\n",
        "site": site,
        "release": {
            "exclude_names": [".DS_Store", ".gitkeep", ".git", "node_modules", "__pycache__", "notes.js", ".pytest_cache", ".venv"],
            "exclude_suffixes": [".md", ".mmd", ".pyc", "-wal", "-shm"],
        },
        "chapters": [],
    }
    write(working / "release.json", json.dumps(config, indent=2) + "\n")
    write(working / ".gitignore", ".DS_Store\n__pycache__/\n*.pyc\n.venv/\nnode_modules/\n.private*\n")
    write(
        working / "README.md",
        f"# {args.title}\n\n"
        "Working course repository. Each `chapter-NN-title/` contains the chapter Markdown\n"
        "and PDF, with `slides/`, `code/`, and `readings/` beside them. Speaker notes stay\n"
        "in `slides/speaker-notes.md` and must not be embedded in public slide HTML.\n\n"
        "The introduction is an unpublished scaffold. Rename it as needed and add content.\n"
        "Nothing is released until explicitly added to the `chapters` list in `release.json`.\n"
        "The shared tools README contains a chapter configuration example.\n\n"
        "Build with `python3 tools/build_release.py`, then check with\n"
        "`python3 tools/check_release.py`. Preview `release/index.html` locally before\n"
        "copying that release to active. Never copy an entire working chapter to active.\n",
    )
    write(working / "tools/build_release.py", launcher("release builder", "build_course_release.py"), True)
    write(working / "tools/check_release.py", launcher("release checker", "check_course_release.py"), True)

    run([str(TOOLS / "build_course_release.py"), str(working)], working)
    shutil.copytree(working / "release", active)

    if not args.no_git:
        initialize_git(working, "Create course working repository")
        initialize_git(active, "Create student course repository")
    if args.github:
        create_github_repo(args.working_owner, args.slug, working, "private")
        create_github_repo(args.active_owner, args.slug, active, "public")
        enable_github_pages(args.active_owner, args.slug, active)

    print(f"Working course: {working}")
    print(f"Active course:  {active}")
    if not args.github:
        print("GitHub repositories were not created. Use --github when that external step is intended.")
    else:
        print(f"GitHub Pages:   https://{args.active_owner}.github.io/{args.slug}/")


if __name__ == "__main__":
    main()
