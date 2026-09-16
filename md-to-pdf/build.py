import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent

def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True, capture_output=True, **kwargs).stdout

def main():
    parser = argparse.ArgumentParser(prog="md-to-pdf", description='Build a paginated PDF from Markdown, local images, and Mermaid diagrams.')
    parser.add_argument('source', type=Path)
    parser.add_argument('-o', '--output', type=Path, help='Default: beside the Markdown, with .pdf extension')
    parser.add_argument('--css', type=Path, help='Additional print stylesheet')
    args = parser.parse_args()
    source = args.source.expanduser().resolve(strict=True)
    output = (args.output or source.with_suffix('.pdf')).expanduser().resolve()
    if output == source:
        parser.error('Output must differ from the Markdown source.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='md-to-pdf-') as scratch:
        tmp = Path(scratch)
        doc = json.loads(run(['/opt/homebrew/bin/pandoc', source, '-f', 'markdown', '-t', 'json'], cwd=source.parent))
        count = 0
        def walk(obj):
            nonlocal count
            if isinstance(obj, list):
                return [walk(item) for item in obj]
            if not isinstance(obj, dict):
                return obj
            if obj.get('t') == 'CodeBlock' and 'mermaid' in obj['c'][0][1]:
                count += 1
                mmd = tmp / f'diagram-{count}.mmd'
                svg = mmd.with_suffix('.svg')
                mmd.write_text(obj['c'][1])
                run(['/opt/homebrew/bin/node', ROOT / 'node_modules/@mermaid-js/mermaid-cli/src/cli.js',
                     '-i', mmd, '-o', svg, '-c', ROOT / 'mermaid.json', '-p', ROOT / 'puppeteer.json', '-b', 'transparent'])
                return {'t': 'Para', 'c': [{'t': 'Image', 'c': [['', ['mermaid-diagram'], []], [], [svg.as_uri(), '']]}]}
            if obj.get('t') == 'Table':
                rows = sum(len(body[2]) + len(body[3]) for body in obj['c'][4])
                if rows > 18:
                    obj['c'][0][1].append('long-table')
            if obj.get('t') == 'Image':
                target = obj['c'][2][0]
                parsed = urlparse(target)
                if not parsed.scheme:
                    image = (source.parent / unquote(parsed.path)).resolve()
                    if not image.is_file():
                        raise ValueError(f'Image not found: {image}')
                    obj['c'][2][0] = image.as_uri()
            return {key: walk(value) for key, value in obj.items()}
        doc = walk(doc)
        html = run(['/opt/homebrew/bin/pandoc', '-f', 'json', '-t', 'html5', '--standalone',
                    '--metadata', f'title={source.stem}', '--template', ROOT / 'template.html'], input=json.dumps(doc))
        from weasyprint import HTML, CSS
        errors = []
        class ErrorCollector(logging.Handler):
            def emit(self, record):
                if record.levelno >= logging.ERROR:
                    errors.append(record.getMessage())
        logging.getLogger('weasyprint').addHandler(ErrorCollector())
        styles = [CSS(filename=str(ROOT / 'print.css'))]
        if args.css:
            styles.append(CSS(filename=str(args.css.expanduser().resolve(strict=True))))
        result = HTML(string=html, base_url=str(source.parent) + '/').write_pdf(stylesheets=styles)
        if errors:
            raise ValueError('PDF rendering failed: ' + '; '.join(errors))
        # Replace output only after a complete successful render.
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix='.pdf', delete=False) as staged:
            staged.write(result)
            staged_path = Path(staged.name)
        os.replace(staged_path, output)
        print(f'{output} ({count} Mermaid diagrams)')

if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError) as exc:
        print(f'md-to-pdf: {exc}', file=sys.stderr)
        sys.exit(1)
