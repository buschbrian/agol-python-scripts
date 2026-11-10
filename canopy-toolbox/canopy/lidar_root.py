"""Where the lidar data disk is mounted on this machine. No ArcPy required.

The laptop and the office workstation mount the same disk under different drive letters, and run
manifests record absolute paths. Scripts take the root from here and translate recorded paths when
they read them back. With CANOPY_LIDAR_ROOT unset the root is the conventional H:\\lidar and every
path is left alone, so behaviour on the machine that made the runs is unchanged.
"""
import os
import re
from pathlib import Path

DEFAULT_ROOT = r"H:\lidar"
ENV = "CANOPY_LIDAR_ROOT"
_LIDAR_PREFIX = re.compile(r"^[A-Za-z]:[\\/]+lidar(?=[\\/]|$)", re.IGNORECASE)


def lidar_root():
    return Path(os.environ.get(ENV) or DEFAULT_ROOT)


def live(path):
    """The path on this machine for a path recorded on any machine.

    Only a path directly under a drive's lidar folder is rewritten, and only when CANOPY_LIDAR_ROOT is set.
    """
    text = str(path)
    root = os.environ.get(ENV)
    if root and _LIDAR_PREFIX.match(text):
        return Path(root) / Path(_LIDAR_PREFIX.sub("", text).lstrip("\\/"))
    return Path(text) if not isinstance(path, Path) else path
