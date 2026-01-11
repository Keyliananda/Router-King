#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/build_app.sh --dmg /path/to/FreeCAD.dmg [--out dist] [--name RouterKing.app] [--dmg-out dist/RouterKing.dmg] [--unquarantine]
  ./scripts/build_app.sh --url https://example.com/FreeCAD.dmg [--out dist] [--name RouterKing.app] [--dmg-out dist/RouterKing.dmg] [--unquarantine]

Builds a macOS RouterKing.app by bundling FreeCAD with the RouterKing workbench
and produces a distributable DMG.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script is macOS-only." >&2
  exit 1
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

dmg=""
url=""
out_dir="$repo_dir/dist"
app_name="RouterKing.app"
dmg_out=""
unquarantine=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dmg)
      dmg="$2"
      shift 2
      ;;
    --url)
      url="$2"
      shift 2
      ;;
    --out)
      out_dir="$2"
      shift 2
      ;;
    --name)
      app_name="$2"
      shift 2
      ;;
    --dmg-out)
      dmg_out="$2"
      shift 2
      ;;
    --unquarantine)
      unquarantine=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -n "$url" && -n "$dmg" ]]; then
  echo "Use either --dmg or --url, not both." >&2
  exit 1
fi

if [[ -z "$url" && -z "$dmg" ]]; then
  usage
  exit 1
fi

tmp_dir=""
if [[ -n "$url" ]]; then
  tmp_dir="$(mktemp -d)"
  dmg="$tmp_dir/FreeCAD.dmg"
  curl -L -o "$dmg" "$url"
fi

if [[ ! -f "$dmg" ]]; then
  echo "DMG not found: $dmg" >&2
  exit 1
fi

mount_point="$(hdiutil attach -nobrowse -readonly "$dmg" | awk '/\/Volumes\// {for(i=3;i<=NF;i++){printf $i; if(i<NF) printf " "}; print ""; exit}')"
if [[ -z "$mount_point" ]]; then
  echo "Failed to mount DMG." >&2
  exit 1
fi

cleanup() {
  hdiutil detach "$mount_point" >/dev/null 2>&1 || true
  if [[ -n "$tmp_dir" ]]; then
    rm -rf "$tmp_dir"
  fi
}
trap cleanup EXIT

src_app="$(find "$mount_point" -maxdepth 1 -name "*.app" -print -quit)"
if [[ -z "$src_app" ]]; then
  echo "No .app found in DMG." >&2
  exit 1
fi

mkdir -p "$out_dir"
dest_app="$out_dir/$app_name"
rm -rf "$dest_app"
cp -R "$src_app" "$dest_app"

mod_dir="$dest_app/Contents/Resources/Mod/RouterKing"
mkdir -p "$mod_dir"
rsync -a --delete "$repo_dir/RouterKing/" "$mod_dir/"
cp "$repo_dir/package.xml" "$mod_dir/package.xml"
cp "$repo_dir/README.md" "$mod_dir/README.md"
cp "$repo_dir/THIRD_PARTY.md" "$mod_dir/THIRD_PARTY.md"
cp "$repo_dir/LICENSE" "$mod_dir/LICENSE"

# Remove signing artifacts and non-essential files that confuse Gatekeeper.
rm -rf "$dest_app/Contents/_CodeSignature"
rm -f "$dest_app/Contents/packages.txt"

# Clear extended attributes that can trigger Gatekeeper warnings.
xattr -cr "$dest_app" || true

# Ad-hoc sign to keep macOS from flagging the bundle as modified.
codesign --force --deep --sign - "$dest_app"

if [[ $unquarantine -eq 1 ]]; then
  xattr -dr com.apple.quarantine "$dest_app" || true
fi

app_base="${app_name%.app}"
if [[ -z "$dmg_out" ]]; then
  dmg_out="$out_dir/${app_base}.dmg"
fi
mkdir -p "$(dirname "$dmg_out")"
hdiutil create -volname "$app_base" -srcfolder "$dest_app" -ov -format UDZO "$dmg_out"

echo "Built: $dest_app"
echo "DMG: $dmg_out"
