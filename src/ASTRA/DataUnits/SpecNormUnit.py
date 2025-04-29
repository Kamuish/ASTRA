"""Data unit to store information from spectral normalization."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import ujson as json
from loguru import logger

from ASTRA.base_models.UnitModel import UnitModel
from ASTRA.utils import custom_exceptions
from ASTRA.utils.json_ready_converter import json_ready_converter
from ASTRA.utils.paths_tools.build_filename import build_filename


class SpecNorm_Unit(UnitModel):
    """Data unit to store information from the order-wise normaization."""

    _content_name = "SpecNorm"
    _name = UnitModel._name + _content_name

    def __init__(self, frame_name, algo_name: str):
        """Create new object."""
        super().__init__(0, 0)
        self.frame_name = frame_name
        self.algorithm_name = algo_name
        self.stored_info: Dict[int, dict] = {}

    def generate_root_path(self, storage_path: Path) -> None:  # noqa: D102
        storage = storage_path / "_Storage" / self._content_name / self.algorithm_name
        super().generate_root_path(storage)

    def store_norm_info(self, order: int, keys: Dict[str, Any]) -> None:
        """Store information from normalization."""
        self.stored_info[order] = keys

    def get_norm_info_from_order(self, order: int) -> Dict[str, Any]:
        """Get normalization info from specific order."""
        return self.stored_info.get(order, {})

    ###
    # Disk IO operations
    ###
    def get_storage_filename(self) -> str:
        """Get filename for storage."""
        return build_filename(
            og_path=self._internalPaths.root_storage_path,
            filename=f"{self.frame_name}_normalization_params",
            fmt="json",
        )

    def trigger_data_storage(self) -> None:  # noqa: D102
        data = {}
        for key, values in self.stored_info.items():
            data[key] = {}
            for key_1, order_values in values.items():
                data[key][key_1] = json_ready_converter(order_values)

        with open(self.get_storage_filename(), mode="w") as handle:
            json.dump(data, handle, indent=4)

    @classmethod
    def load_from_disk(cls, rv_cube_fpath: Path, filename, algo_name) -> SpecNorm_Unit:
        """Load result from disk.

        Parameters
        ----------
        rv_cube_fpath: path to the RV cube folder. Internally append the folder name from the corresponding data unit

        """
        super().load_from_disk(rv_cube_fpath)

        new_unit = SpecNorm_Unit(frame_name=filename, algo_name=algo_name)

        new_unit.generate_root_path(rv_cube_fpath)
        unit_path = Path(new_unit.get_storage_filename())
        if not unit_path.exists():
            raise custom_exceptions.NoDataError

        with open(unit_path) as handle:
            norm_info = json.load(handle)
            profile = {}
            for str_key, info in norm_info.items():
                try:
                    profile[int(str_key)] = {j: float(k) for j, k in info.items()}
                except ValueError:
                    profile[str_key] = info
            new_unit.stored_info = profile
        logger.info("Loaded previous normalization parameters from disk")
        return new_unit
