"""Representation of the star, used to query SIMBAD."""

from pathlib import Path
from typing import Any, Dict

import numpy as np
from loguru import logger

from ASTRA.utils import custom_exceptions
from ASTRA.utils.ASTRAtypes import RV_measurement
from ASTRA.utils.secular_acceleration import secular_acceleration
from ASTRA.utils.units import meter_second


class Target:
    """Represents an observed object.

    This class provides an interface to handle data sanitization and simbad lookups
    for the targets that we load from the S2D files.


    TODO list:
    - [ ] Allow for the comparison of two different targets
    - [ ] Improve docs and interfaces of the class
    """

    def __init__(
        self,
        target_list: list[str],
        original_name: str | None = None,
        target_dictionary_path: None | str = None,
    ) -> None:
        """Create object and run sanity checks.

        Args:
            target_list (list[str]): List of target names that have been collected across all files that have been
                loaded from disk.
            original_name (str | None): If not None, name that we will use in the place of the one in the fits header.
            target_dictionary_path (dict[str, str] | None): If not None, path to a file that maps
              'encrypted names' to SIMBAD names, separated by ,

        """
        if len(target_list) == 0:
            msg = "No valid observations. Can't create a target name"
            logger.critical(msg)
            raise custom_exceptions.NoDataError(msg)

        self.to_replace = {
            "NAME": "",
            "star": "",
        }

        self.extra_KW = {
            "KOBE-": "",
            "HD-": "HD",
            " ": "",  # TODO: do we really want to replace empty spaces in the middle of the name?
        }

        self.KOBE_alias = {}

        if target_dictionary_path is not None and Path(target_dictionary_path).exists():
            complete_removal = {**self.to_replace, **self.extra_KW}
            with open(target_dictionary_path) as dicion:
                logger.debug("Found target dictionary; Loading keys")
                for entry in dicion:
                    combination = entry.split(",")
                    KOBE_key = combination[0]
                    for key, replace in complete_removal.items():
                        KOBE_key = KOBE_key.replace(key, replace)
                    simbad_resolvable = combination[1]
                    self.KOBE_alias[KOBE_key] = simbad_resolvable
        else:
            logger.warning(f"Target dictionary not found in <{target_dictionary_path}>")

        target_list = self.clean_targ_list(target_list)
        self.validate_target_list(target_list)

        # Name from the header!
        self._original_name: str = target_list[0].strip()

        # original_nam
        if original_name is None:
            self._overriden_name: str = self._original_name
        else:
            self._overriden_name = original_name

        if self._original_name != self._overriden_name:
            msg = f"Original target name '{self._overriden_name}' "
            msg += f"validated to '{self._original_name}'"
            logger.info(msg)
        else:
            logger.info(f"Validated target to be {self._original_name}")
        self._simbad_error = False
        self._SA = np.nan

    def clean_targ_list(self, target_list: list[str]) -> list[str]:
        """Process all names to generate clean ones."""
        logger.debug("Parsing through loaded OBJECTs")
        clean_list = []

        for targ in target_list:
            clean_name = targ
            for key, replacement in self.to_replace.items():
                clean_name = clean_name.replace(key, replacement)
            clean_list.append(clean_name.strip())
        return clean_list

    def validate_target_list(self, targets: list[str]) -> None:
        """Raise warning if we are using different targ names."""
        # ! maybe should assert np.all(np.array(targets) == targets[0])

        processed_targlist = [self.searchable_name(i) for i in targets]
        if not np.all(np.asarray(processed_targlist) == processed_targlist[0]):
            msg = f"Different targets in the input data: {np.unique(targets)}"
            logger.warning(msg)
            # raise Exception(msg)

    @property
    def secular_acceleration(self) -> RV_measurement:
        """Return the secular accelaration of the target star."""
        if self._simbad_error:
            logger.warning("\tWARNING: Failed connection to SIMBAD!!!!!! SA OF 0 BEING RETURNED")
            self._SA = 0 * meter_second

        if np.isnan(self._SA):
            try:
                logger.info(f"Querying simbad for {self.searchable_name(self.true_name)}")
                self._SA = secular_acceleration(self.searchable_name(self.true_name))
            except Exception:
                logger.opt(exception=True).critical(
                    "Could not compute the secular accelaration from {}",
                    self.true_name,
                )
                self._SA = 0 * meter_second
                self._simbad_error = True
        return self._SA

    def searchable_name(self, star: str) -> str:
        """Transform star name in one that is recognized by SIMBAD."""
        complete_removal = {**self.to_replace, **self.extra_KW}
        for key, replace in complete_removal.items():
            star = star.replace(key, replace)

        # alias list that is recognizable from SIMBAD
        alias_list = {
            "ProximaCentauri": "proxima",
            "VV645Cen": "proxima",
            "Barnards": "GJ 699",
            "VYZCet": "YZ Cet",
            "VV376Peg": " HD 209458",
            "tauCet": "tau Cet",
        }

        alias_list = {**alias_list, **self.KOBE_alias}
        return alias_list.get(star, star)

    @property
    def true_name(self) -> str:
        """Return the name of a target that is extracted from the header of the .fits files.

        This name can be overriden if the user provides a new name when instantiating this object

        """
        return self._overriden_name

    @property
    def original_name(self) -> str:
        """Name that was present in the header of the files.

        This will disregard any kind of user-provided name

        """
        return self._original_name

    @property
    def json_ready(self) -> Dict[str, Any]:
        """Data in json-compatible fmt."""
        out = {}
        out["raw_name"] = self.true_name
        return out
