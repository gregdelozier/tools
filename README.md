# Course Release Tools

These tools build and check student-facing course sites from a working course repository.
Course-specific settings and the list of released chapters live in the course's
`release.json` file.

## Start a new course

```sh
~/courses/tools/new_course.py operating-systems \
    --title "Operating Systems" \
    --description "Processes, memory, files, concurrency, and operating-system design."
```

This creates `~/courses/operating-systems/working` and
`~/courses/operating-systems/active`, initializes both as local Git repositories,
and builds the initial student site. Add `--github` only when the corresponding
private working repository and public student repository should also be created
and pushed. The same option enables GitHub Pages for the active repository from
the root of its `main` branch.

## Build a release

```sh
~/courses/tools/build_course_release.py ~/courses/structures/working
```

The default output is the course's `release/` directory. The build happens in a
temporary sibling directory and replaces `release/` only after a successful build.

Build elsewhere for preview or testing:

```sh
~/courses/tools/build_course_release.py ~/courses/structures/working \
    --output /tmp/structures-release --skip-build
```

`--skip-build` uses existing PDFs and slide HTML instead of rebuilding source
documents.

## Check a release

```sh
~/courses/tools/check_course_release.py ~/courses/structures/working
```

To check a preview build:

```sh
~/courses/tools/check_course_release.py ~/courses/structures/working \
    --site /tmp/structures-release
```

The checker verifies local links, chapter scope, private-source exclusions,
speaker-note exclusions, and exact copies of released code files.

## Configuration

Each working course repository owns a `release.json`. It contains:

- `course_title` and `site`: course text, repository links, and colors
- `release`: file names and suffixes excluded from student code copies
- `chapters`: the ordered chapter, slide, code, and reading sources to release
- `legacy_urls`: optional redirects for previously published paths
- `release_readme`: optional Markdown allowed at the release root

The course-specific `tools/build_release.py` and `tools/check_release.py` files
may be small launchers for these shared commands. This keeps existing course
commands working without duplicating the implementation.

## Markdown to PDF

The repository also contains the Markdown publishing toolchain used to build
course chapters and readings. Its source is in `md-to-pdf/`; installed Python
and Node dependencies stay local and are excluded from Git. The normal command
remains `~/.local/bin/md-to-pdf`.

See `COURSE_RELEASE_TOOLS.md` for the design, release model, configuration,
and normal operating procedure for the complete toolset.
