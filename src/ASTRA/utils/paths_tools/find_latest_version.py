"""Search for latest version in file products."""

import os
from pathlib import Path

from loguru import logger

from ASTRA import __version__, __version_info__
from ASTRA.utils.custom_exceptions import NoDataError


def find_latest_version(path: Path, enable_logs: bool = True) -> str:
    """Search, inside a directory, for all files with SBART versions. Returns the latest version found on disk."""
    available_cubes = []
    versions_full = []
    version_sum = []

    for filename in os.listdir(path):
        if os.path.isdir(os.path.join(path, filename)) or "_" not in filename or filename.startswith("."):
            continue

        available_cubes.append(filename)
        cube_ver = filename.split("_")[-1].split(".")[0]
        versions_full.append(cube_ver)
        version_sum.append(sum([i * j for i, j in zip([100, 10, 1], map(int, cube_ver.split("-")))]))
    try:
        highest_ver = max(version_sum)
    except ValueError as exc:  # no version number in the list
        raise NoDataError(f"There are no SBART outputs in {path}") from exc

    if highest_ver != sum([i * j for i, j in zip([100, 10, 1], __version_info__)]) and enable_logs:
        logger.warning(
            (
                f"\tRV cube is not the most recently installed version ({__version__})."
                f"Using data from {versions_full[version_sum.index(highest_ver)]}"
            )
        )

    return versions_full[version_sum.index(highest_ver)]
