"""Path creation."""

from pathlib import Path
from typing import Optional

from ASTRA import __version__


def build_filename(
    og_path: Path, filename: str, fmt: str, ASTRA_version: Optional[str] = None, skip_version: bool = False
) -> str:
    """Standardize the filenames of ASTRA outputs.

    Args:
        og_path (Path): Folder in which the file will be stored
        filename (str): stem of the filename
        fmt (str): format of the file
        ASTRA_version (Optional[str], optional): version of ASTRA. Defaults to None.

    Returns:
        str: Posix version of the file that want to store

    """
    ASTRA_version = ASTRA_version if ASTRA_version is not None else __version__
    if skip_version:
        return (og_path / f"{filename}_TM.{fmt}").as_posix()
    else:
        return (og_path / f"{filename}_TM_{ASTRA_version}.{fmt}").as_posix()
