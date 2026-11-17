#!/usr/bin/env bash
# Regenerate the compiled ProPresenter format modules.
# Only needed if a future ProPresenter version changes the .pro format.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$HERE/src/propresenter_lyrics/proto"
VERSION="${1:-autogen-proto}"  # folder inside the greyshirtguy repo (autogen-proto = latest ProPresenter)

TMP="$(mktemp -d)"
echo "Cloning proto definitions into $TMP ..."
git clone --depth 1 https://github.com/greyshirtguy/ProPresenter7-Proto.git "$TMP/repo"

pip install "protobuf>=6.33,<7" "grpcio-tools==1.76.0" >/dev/null  # stamps 6.31.1: works with protobuf 6.33+

echo "Compiling '$VERSION' -> $OUT"
rm -f "$OUT"/*_pb2.py
cp -r "$TMP/repo/$VERSION" "$TMP/protos"
( cd "$TMP/protos" && python -m grpc_tools.protoc -I. --python_out="$OUT" *.proto )
: > "$OUT/__init__.py"

echo "Done. $(ls "$OUT"/*_pb2.py | wc -l) modules written."
rm -rf "$TMP"
