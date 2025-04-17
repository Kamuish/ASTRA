"""Collect metadata from the loaded Frames."""

from __future__ import annotations

from pathlib import Path

import ujson as json
from loguru import logger

from ASTRA.utils import custom_exceptions
from ASTRA.utils.json_ready_converter import json_ready_converter
from ASTRA.utils.paths_tools.build_filename import build_filename


class MetaData:
    """Class to hold metadata information of the processed data.

    The Frames, when loading data from disk will collect information to work as MetaData, which will be used to
    provide an  option of avoiding the repeated computation of exactly the same dataset. This class provides an
    easy interface to hold such data, write and load it to disk, and compare equality between two MetaData objects.

    The data stored inside this object is divided by subInstruments, with each having a unique set of values, that
    is not shared with other subInstruments. Comparisons of equality are supported at the subInstrument level.

    """

    def __init__(self, data_to_hold: dict | None = None) -> None:  # noqa: D107
        self.information = {} if data_to_hold is None else data_to_hold

    def subInstrument_comparison(self, other: MetaData, subInstrument: str) -> bool:
        """Compare the Metadata of a given subInstrument.

        Checks that must pass for equality:

        * The same keys are present in the two objects
        * A given key has the same value in the two objects

        Parameters
        ----------
        other:
            Other MetaData object
        subInstrument: str
            SubInstrument to compare

        Returns
        -------
        comparison_result: bool
            True if the MetaData matchess

        """
        equal = True

        try:
            for key, subInst_value in self.information[subInstrument].items():
                if subInst_value != other.information[subInstrument][key]:
                    equal = False
                    break
        except KeyError:
            equal = False

        return equal

    def store_json(self, path: Path) -> None:
        """Store the class as a json files.

        Args:
            path (Path):Path in which this object will be stored

        """
        logger.debug("Storing Metadata to {}", path)

        storage_path = build_filename(path, "MetaData", fmt="json", skip_version=True)

        info_to_store = {}
        for key, value in self.information.items():
            value = json_ready_converter(value)
            info_to_store[key] = value

        with open(storage_path, mode="w") as handle:
            json.dump(info_to_store, handle, indent=4)

    def add_info(self, key: str, info: str | tuple | list, subInstrument: str) -> None:
        """Add a new metric to be tracked, with the values being collected over all available frames.

        Parameters
        ----------
        key: str
            Name of the metric
        info: Union[str, Iterable]
            data to be stored
        subInstrument: str
            subInstrument to which the info belongs to


        Raises
        ------
        TypeError
            If the info is not a list nor an iterable

        """
        if not isinstance(info, (str, tuple, list)):
            raise TypeError("info must be  str or list object")
        if subInstrument not in self.information:
            self.information[subInstrument] = {}

        # remove duplicates, but keep as a list (to avoid problems when storing to json)!
        self.information[subInstrument][key] = list(set(info))

    @classmethod
    def load_from_json(cls, path: Path) -> MetaData:
        """Load from a json file."""
        storage_path = build_filename(
            path,
            "MetaData",
            fmt="json",
            ASTRA_version=None,
            skip_version=True,  # we don't want a version
        )
        try:
            with open(storage_path) as handle:
                information = json.load(handle)
        except FileNotFoundError:
            msg = f"Failed to find metadata file in {storage_path}"
            logger.warning(msg)
            raise custom_exceptions.StopComputationError(msg)

        return MetaData(information)
