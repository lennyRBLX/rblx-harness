#!/bin/sh
# Fetch the pinned toolchain into tools/bin/ (macOS authoring side).
# Windows: setup_windows.bat fetches lute.exe under the windows pin below and
# checks luau-lsp on PATH; it never runs this script.
#
# Pins. Upgrades are deliberate: bump a URL + sha256 here, re-run the verify
# suite (tools/tests/) as the canary before committing.
set -eu

LUTE_VERSION="v1.0.0"
LUTE_MAC_ASSET="lute-macos-aarch64.zip"
LUTE_MAC_SHA256="6d120b5d2804e62ab2453565e755d022bd6902307cabcd0fedb4cdcbd4251e84"
# recorded for setup_windows.bat (lute-windows-x86_64.zip):
LUTE_WIN_SHA256="4f5de7cb1844d0df4e5796ad08d485ce7b6c35f7ba8d54046c7e7a12e7c28d92"

LSP_VERSION="1.68.1"
LSP_MAC_ASSET="luau-lsp-macos.zip"
LSP_MAC_SHA256="e32a71823ee47471d931a03e4186ced2b4c43bb785c8fe05de901fe54c6ebe21"
# recorded for a Windows developer fetching by hand (luau-lsp-win64.zip):
LSP_WIN_SHA256="15f2add7c70191c5cd636b047968760f0056893b63be10294453c75430bcb339"

# vendored beside this script; luau-lsp analyze resolves Roblox globals from it
GLOBALTYPES_SHA256="a0027362f872d231c1c4bbea6b2d5d561b0a4ea7e82458ea8a5f862cef8938aa"

HERE="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HERE}/bin"
mkdir -p "$BIN_DIR"

fetch() { # url sha dest_zip
	curl -sfL "$1" -o "$3"
	echo "$2  $3" | shasum -a 256 -c - >/dev/null
}

if [ ! -x "${BIN_DIR}/lute" ]; then
	echo "Fetching lute ${LUTE_VERSION} (${LUTE_MAC_ASSET})..."
	TMP="$(mktemp -t lute.zip)"
	fetch "https://github.com/luau-lang/lute/releases/download/${LUTE_VERSION}/${LUTE_MAC_ASSET}" "$LUTE_MAC_SHA256" "$TMP"
	unzip -o -q "$TMP" -d "$BIN_DIR"
	chmod +x "${BIN_DIR}/lute"
	rm -f "$TMP"
fi
"${BIN_DIR}/lute" --version

if [ ! -x "${BIN_DIR}/luau-lsp" ]; then
	echo "Fetching luau-lsp ${LSP_VERSION} (${LSP_MAC_ASSET})..."
	TMP="$(mktemp -t luau-lsp.zip)"
	fetch "https://github.com/JohnnyMorganz/luau-lsp/releases/download/${LSP_VERSION}/${LSP_MAC_ASSET}" "$LSP_MAC_SHA256" "$TMP"
	unzip -o -q "$TMP" -d "$BIN_DIR"
	chmod +x "${BIN_DIR}/luau-lsp"
	rm -f "$TMP"
fi
"${BIN_DIR}/luau-lsp" --version

echo "${GLOBALTYPES_SHA256}  ${HERE}/globalTypes.d.luau" | shasum -a 256 -c - >/dev/null
echo "globalTypes.d.luau: pin verified"
echo "Toolchain ready in ${BIN_DIR}/"
