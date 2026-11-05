#!/usr/bin/env bash
# Millcreek CFTree I/O adapter. Same CGAL algorithm, with Linux-local temporary files.
set -euo pipefail
if [[ $# -ne 4 ]]; then exit 2; fi
native="$(dirname -- "$0")/awrap_points.native"
scratch="$(mktemp -d /tmp/millcreek-cftree.XXXXXXXX)"
case "$scratch" in /tmp/millcreek-cftree.*) ;; *) exit 3 ;; esac
cleanup() {
  rm -f -- "$scratch/input.xyz" "$scratch/output.ply"
  rmdir -- "$scratch"
}
trap cleanup EXIT
cp -- "$1" "$scratch/input.xyz"
"$native" "$scratch/input.xyz" "$2" "$3" "$scratch/output.ply"
cp -- "$scratch/output.ply" "$4"
