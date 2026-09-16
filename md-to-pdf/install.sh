#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

command -v python3 >/dev/null
command -v npm >/dev/null
command -v pandoc >/dev/null

python3 -m venv "$ROOT/venv"
"$ROOT/venv/bin/python" -m pip install --upgrade pip
"$ROOT/venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
npm ci --prefix "$ROOT"

mkdir -p "$HOME/.local/bin" "$HOME/.local/share"

for link in "$HOME/.local/bin/md-to-pdf" "$HOME/.local/share/md-to-pdf"; do
    if [ -e "$link" ] && [ ! -L "$link" ]; then
        echo "Refusing to replace non-symlink: $link" >&2
        exit 1
    fi
done

ln -sfn "$ROOT/md-to-pdf" "$HOME/.local/bin/md-to-pdf"
ln -sfn "$ROOT" "$HOME/.local/share/md-to-pdf"

echo "Installed md-to-pdf from $ROOT"
