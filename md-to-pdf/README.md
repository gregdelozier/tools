# Markdown to PDF

Install or rebuild the local dependencies and compatibility symlinks:

```bash
./install.sh
```

The installer requires Python 3, npm, Pandoc, and Google Chrome. WeasyPrint may
also require Homebrew libraries on macOS.

Run from any directory:

```bash
md-to-pdf path/to/chapter.md
md-to-pdf path/to/chapter.md -o path/to/output.pdf
md-to-pdf path/to/chapter.md --css custom_print.css
```

The default output sits beside the source, with the same name and a `.pdf` extension. A successful build replaces an existing output. A failed conversion leaves it intact.

The command uses Pandoc, Mermaid CLI with installed Google Chrome, and an isolated WeasyPrint environment. Mermaid fenced code blocks become vector diagrams. Markdown images resolve relative to the source file, including paths with spaces and reference-style images. Missing images stop the build.

The shared `print.css` controls Letter pages, margins, page numbers, typography, and pagination. Headings stay with following content. Figures and captions stay together. Code blocks and short tables stay together when they fit; long tables can split between rows and repeat their headers. Objects taller than a page may require editing or a custom stylesheet. Inspect the PDF after substantive changes.

For an explicit page break:

```markdown
::: {.page-break}
## New Section

Section content.
:::
```

For a group that should remain together:

```markdown
::: {.keep-together}
Related content.
:::
```

This is a text-and-image publishing pipeline, not a JavaScript website renderer. Mermaid is rendered separately; other embedded JavaScript is not executed. Remote image availability depends on the network. Standard Markdown images are preferred over custom HTML.

Source and installed dependencies live in `~/courses/tools/md-to-pdf`. The
executable is available through the `~/.local/bin/md-to-pdf` symlink. Node
dependencies are locked in `package-lock.json`, and Python versions are
recorded in `requirements.txt`.
