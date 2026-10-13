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

The working course starts with an unpublished `chapter-00-introduction/` scaffold:

```text
chapter-00-introduction/
  chapter-00-introduction.md
  build_pdf.sh
  code/
  readings/
  slides/
    slides-00-introduction.md
    speaker-notes.md
```

Rename the introduction and write the material before adding it to `release.json`.
The slide files are authoring placeholders, not a finished deck or a slide builder.
Keep each chapter's PDF beside its Markdown. Student indexes are generated in
`release/`, not maintained as a second set of source pages.

## Migrate an existing course

```sh
~/courses/tools/migrate_course_layout.py ~/courses/advanced-database/working
~/courses/tools/migrate_course_layout.py ~/courses/advanced-database/working --apply
```

The default is a read-only preview. Applying makes a complete backup outside the
working repository, including uncommitted files and Git history. `--backup PATH`
chooses a new backup directory. A JSON migration report sits beside the backup.

The script brings matching `chapters/NN-title`, `slides/NN-title`, and
`code/NN-title` together under `chapter-NN-title/`. It updates configured source
paths, local documentation references, and slide-builder filenames. Slide files
become `slides-NN-title.md` and `.html`, with separate `speaker-notes.md`.
Reading ownership comes from `release.json`. Matching lecture notes move into
their chapter's `instructor-notes/`. Course-wide material remains at course level.

Conflicting chapter numbers stop the migration. After reviewing old code that
belongs to a previous sequence, `--archive-conflicting-code` preserves it in
`archive/legacy-code/` instead of assigning it to an unrelated chapter.
Existing destination files and symlinks also stop the migration for review.
Running the migration again after completion makes no changes.

The tool does not release additional material, alter active, commit, or push.
Build and check afterward. If an apply is interrupted, retain the partial tree
and restore the complete backup before trying again; do not merge it blindly.

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

Each configured slide deck also produces a matching PDF in its `slides/`
directory. The chapter contents page links both formats. Export uses the existing
Mermaid browser runtime and Reveal.js print layout: one slide per page, without
speaker notes. A deck can opt out with `"pdf": false` in its `slides` settings.
With `--skip-build`, enabled slide PDFs must already exist.

To export an unpublished deck without adding it to the release:

```sh
node ~/courses/tools/export_slides_pdf.mjs path/to/slides.html path/to/slides.pdf
```

The course templates include `Gregory S. DeLozier, PhD` beneath the title in
slide Markdown and chapter Markdown. Keep the `.slide-author` paragraph in decks
and the `.author` block in chapters when adapting the templates.

## Extras

Put supplemental student files in `working/extras/` at the course root.
Publishing copies those files to `extras/` in the release and active site,
unchanged to the same relative paths, including nested directories. No
per-file manifest entries are needed. This automatic copy only discovers
the root-level extras folder, not extras folders within chapters or archives.

Extras publishes rendered content and supporting assets, not authoring files.
Markdown and Mermaid source, instructor and speaker notes, assignments, Git
metadata, and dependency/cache directories are excluded. Files and directories
whose names start with `.private` are always excluded at every depth.
Configured name and suffix exclusions also apply. These safety exclusions
cannot be disabled by course configuration. Symlinks in extras are rejected
instead of following them into other material. The release checker verifies
that every published extras file matches its working source.

All publication copy paths reject symlink files, directories, and ancestors
below the course root, including public-looking links to private content.
Reading conversion and slide export validate their input and PDF output paths
before starting a subprocess. The checker also rejects symlinks in the release.
The course root is the trusted boundary; these checks do not sandbox build
scripts or inspect arbitrary dependencies read by those scripts.

The builder maintains `extras/index.html` and links it from the course main
page only when extras contain publishable files. The index links documents
and slide HTML/PDF files; supporting asset directories are copied without
listing each asset. A source `extras/index.html` is ignored because this
page is generated. Courses without extras have no Extras link or directory.

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

For example, a finished chapter can be added to `chapters` with:

```json
{
  "number": "00",
  "slug": "introduction",
  "title": "Introduction",
  "description": "Course introduction.",
  "chapter": {
    "build": "chapter-00-introduction/build_pdf.sh",
    "source": "chapter-00-introduction/chapter-00-introduction.pdf",
    "filename": "chapter-00-introduction.pdf"
  },
  "code": {"source": "chapter-00-introduction/code"}
}
```

Only include components that are ready. For slides, specify `source`, `filename`,
and optionally `build` and `assets` inside a `slides` object. Copy only rendered
HTML and assets; source Markdown and instructor notes stay in working.

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
