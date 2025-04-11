"""Skeleton for the data storage units."""

from __future__ import annotations

from pathlib import Path

from ASTRA.utils import custom_exceptions
from ASTRA.utils.BASE import BASE


class UnitModel(BASE):
    """Base unit."""

    # The Units will store data in the RV_cube/_content_name folder
    _content_name = "BASE"
    _name = "StorageUnit::"

    def __init__(self, frameIDs: list[int], N_orders: int, needed_folders: dict[str, str] | None = None) -> None:
        """Create new instance.

        Args:
            frameIDs (int): List of frameIDs
            N_orders (int): Number of orders
            needed_folders (dict[str, str], optional): folders that will be needed. Defaults to None.

        """
        super().__init__(needed_folders=needed_folders)
        self.associated_frameIDs = frameIDs
        self.N_orders = N_orders

    def is_storage_type(self, store_type: str) -> bool:
        """Check if the unit is og a given type."""
        return store_type in self._name

    def find_index_of(self, frameID: int) -> int:
        """Get internal index of a given frameID."""
        return self.associated_frameIDs.index(frameID)

    @classmethod
    def load_from_disk(cls, root_path: Path) -> None:
        """Load unit from disk.

        Raises
        ------
        NoDataError: if no data exists on the provided path.

        """
        if not root_path.exists():
            raise custom_exceptions.NoDataError

    def merge_with(self, new_unit: UnitModel) -> None:
        """Merge two data units, to be implemented by children classes."""
        ...
