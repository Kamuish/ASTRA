"""Handle the interface with disk paths.

Store and generate paths from relative locations, after a given *root path* is set.
It allows to define tags to relative path on disk, ensuring that ASTRA objects are
agnostic to the storage path.

Raises:
    custom_exceptions.MissingRootPath: If accessing disk paths without setting the root one.

"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

from ASTRA.utils import custom_exceptions


class Paths:
    """ASTRA internal class to store disk paths for storage."""

    def __init__(
        self,
        root_level_path: Optional[Union[str, Path]] = None,
        preconfigured_paths: Optional[Dict[str, str]] = None,
    ):
        """Instantiate object.

        Args:
            root_level_path (Optional[Union[str, Path]], optional): If not None, sets the
                root path. Defaults to None.
            preconfigured_paths (Optional[Dict[str, str]], optional): Original mapping of
                tags and paths. Defaults to None.

        """
        self._folder_mappings = preconfigured_paths if preconfigured_paths is not None else {}

        if isinstance(root_level_path, str):
            root_level_path = Path(root_level_path)

        self._root_path: Optional[Path] = root_level_path if root_level_path is not None else None

        # For lazy creation of the folders and to avoid multiple creation attempts
        self._constructed_folders: set[str] = set()

    def add_relative_path(self, folder_KW: str, rel_path: str) -> None:
        """Add relative (to self._root_path) folder, associated with a given Keyword.

        Args:
            folder_KW (str): keyword that will be associated with the relative path
            rel_path (str): relative (to root path) path

        """
        self._folder_mappings[folder_KW] = rel_path

    def get_path_to(self, folder_tag: str, absolute: bool = True, as_posix: bool = True) -> Union[str, Path]:
        """Get the path from a relative "tag".

        Args:
            folder_tag (str): Internal path name
            absolute (bool, optional): returns absolute path. Defaults to True.
            as_posix (bool, optional): return string if True. Defaults to True.

        Raises:
            custom_exceptions.MissingRootPath: If the root path was not previously set

        Returns:
            Union[str, Path]: Path

        """
        if self._root_path is None:
            raise custom_exceptions.MissingRootPath("Must provide the root level path before asking for other paths")

        if folder_tag == "ROOT":
            out_path = self._root_path.absolute()
        else:
            out_path = self._folder_mappings[folder_tag]

            if absolute:
                out_path = self._root_path / out_path

        if folder_tag not in self._constructed_folders:
            out_path.mkdir(parents=True, exist_ok=True)
            self._constructed_folders.add(folder_tag)

        if as_posix:
            out_path = out_path.as_posix()

        return out_path

    def add_root_path(self, path: Union[str, Path], current_folder_name: Optional[str] = None) -> None:
        """Set the current root path."""
        if isinstance(path, str):
            path = Path(path)

        if current_folder_name is not None:
            path = path / current_folder_name

        # ensure that the folder exists
        path.mkdir(exist_ok=True, parents=True)

        self._root_path = path

    @property
    def root_storage_path(self) -> Path:
        """Retrieve the root storage path."""
        return self._root_path
