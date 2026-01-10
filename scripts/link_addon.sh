#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$(uname -s)" in
  Darwin)
    mod_dir="$HOME/Library/Application Support/FreeCAD/Mod"
    ;;
  Linux)
    mod_dir="$HOME/.local/share/FreeCAD/Mod"
    ;;
  *)
    echo "Unsupported OS. Please link manually to your FreeCAD Mod directory." >&2
    exit 1
    ;;
esac

mkdir -p "$mod_dir"
ln -sfn "$repo_dir/RouterKing" "$mod_dir/RouterKing"

echo "Linked RouterKing workbench to: $mod_dir/RouterKing"
