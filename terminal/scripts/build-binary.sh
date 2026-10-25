#!/usr/bin/env bash
# Build a standalone lector executable with PyInstaller.
#
# The result is a single file that carries its own Python, so users do not
# need any Python installation to run the terminal client.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(awk -F'"' '/^version = /{print $2; exit}' "${ROOT}/pyproject.toml")"
OUT_DIR="${1:-${ROOT}/dist}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lector-build.XXXXXX")"
VENV="${WORK_DIR}/venv"
BUILD_INFO="${ROOT}/lector_tui/_build_info.py"

cleanup() {
  rm -f "${BUILD_INFO}"
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

echo "==> 构建 lector ${VERSION}（独立二进制）"
uv venv --python 3.12 "${VENV}"
uv pip install --python "${VENV}/bin/python" "pyinstaller>=6.10" "${ROOT}"

# The bundle has no installed distribution metadata, so the version is baked
# into the package before the analysis runs.
printf 'VERSION = "%s"\n' "${VERSION}" > "${BUILD_INFO}"

mkdir -p "${OUT_DIR}"
"${VENV}/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --distpath "${OUT_DIR}" \
  --workpath "${WORK_DIR}/build" \
  "${ROOT}/packaging/lector.spec"

BINARY="${OUT_DIR}/lector"
if [ "$(uname -s)" = "Darwin" ]; then
  # Ad-hoc signature: keeps Gatekeeper from refusing the unsigned binary.
  codesign --force --sign - "${BINARY}"
fi
chmod +x "${BINARY}"

echo "==> 完成：${BINARY}"
"${BINARY}" --version
