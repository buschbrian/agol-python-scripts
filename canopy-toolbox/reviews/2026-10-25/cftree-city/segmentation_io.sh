#!/usr/bin/env bash
# Millcreek CFTree I/O adapter. Unmodified algorithm; bulk copies across the Windows/WSL boundary.
set -euo pipefail
if [[ $# -ne 5 ]]; then
  printf 'Expected input, output, radius, vertical resolution, minimum points\n' >&2
  exit 2
fi
native="$(dirname -- "$0")/segmentation.native"
scratch="$(mktemp -d /tmp/millcreek-cftree.XXXXXXXX)"
case "$scratch" in /tmp/millcreek-cftree.*) ;; *) exit 3 ;; esac
cleanup() {
  rm -f -- "$scratch/input.xyz" "$scratch/output.xyz"
  rmdir -- "$scratch"
}
trap cleanup EXIT
cp -- "$1" "$scratch/input.xyz"
"$native" "$scratch/input.xyz" "$scratch/output.xyz" "$3" "$4" "$5"
cp -- "$scratch/output.xyz" "$2"
