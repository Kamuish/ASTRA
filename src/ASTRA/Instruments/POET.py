import datetime
from typing import Any, Dict, Iterable, Optional, TYPE_CHECKING
from pathlib import Path
import pandas as pd
import numpy as np
from astropy.coordinates import EarthLocation
import astropy.units as u
from astropy.io import fits

from scipy.constants import convert_temperature
from collections import defaultdict
from ASTRA import astra_logger as logger
from ASTRA.status.flags import ERROR_THRESHOLD, KW_WARNING, FATAL_KW
from ASTRA.utils.definitions import DETECTOR_DEFINITION
from ASTRA.utils.units import kilometer_second
from ASTRA.utils.compute_berv_and_herv_poet import compute_berv_and_herv_POET
from ASTRA.Instruments.ESPRESSO import ESPRESSO
from ASTRA.utils.UserConfigs import DefaultValues, UserParam
from ASTRA.utils.parameter_validators import BooleanValue, PathValue

if TYPE_CHECKING:
    from ASTRA.data_objects import DataClass


class POET(ESPRESSO):
    """Interface to handle POET-ESPRESSO observations (S2D and S1D)."""

    _default_params = ESPRESSO._default_params + DefaultValues(
        DEFER_BERV_UPDATE=UserParam(
            False,
            constraint=BooleanValue,
            description="If True, only updated berv and rv when opening the data",
        ),
        SOLYARIS_PATH=UserParam(
            None,
            description="Path to the solyaris file to use for BERV/HERV computation",
        ),
        AUX_FILE_FOLDER=UserParam(
            None,
            description="Path to the folder in which the auxiliary files are stored. If None, the default folder will be used.",
        ),
    )

    _name = "PoET"

    def __init__(
        self,
        file_path,
        user_configs: Optional[Dict[str, Any]] = None,
        reject_subInstruments: Optional[Iterable[str]] = None,
        frameID: Optional[int] = None,
        quiet_user_params: bool = True,
    ):
        """ESPRESSO interface.

        Parameters
        ----------
        file_path
            Path to the S2D (or S1D) file.
        user_configs
            Dictionary whose keys are the configurable options of ESPRESSO (check above)
        reject_subInstruments
            Iterable of subInstruments to fully reject
        frameID
            ID for this observation. Only used for organization purposes by :class:`~SBART.data_objects.DataClass`

        """
        # Wavelength coverage

        coverage = (350, 900)
        self.is_solar = True
        self.is_resolved_observation = "_B" in file_path.as_posix()
        self._updated_drs_rv = False

        super().__init__(
            file_path=file_path,
            frameID=frameID,
            user_configs=user_configs,
            reject_subInstruments=reject_subInstruments,
            quiet_user_params=quiet_user_params,
        )

    def _load_ESO_DRS_KWs(self, header):
        super()._load_ESO_DRS_KWs(header)

        self.is_poet_data = header.get("ESO INS POET MODE", False)
        if not self.is_poet_data:
            raise custom_exceptions.FrameError(f"{self.name} is not PoET file")

        logger.info("Detected PoET frame")
        self.UT_number = 5
        self.observation_info["POET_APERTURE"] = header.get("ESO POET APER", "UNKNOWN")

        if self.observation_info["POET_APERTURE"] == "UNKNOWN":
            logger.critical("Could not load aperture from %s", self.file_path)

        if not self._internal_configs["DEFER_BERV_UPDATE"]:
            self._update_drs_rv()

    def _update_drs_rv(self) -> None:
        if self._updated_drs_rv:
            return
        logger.debug(f"Updating BERV solution for {self.fname}")

        self._updated_drs_rv = True
        self.wrong_berv = self.observation_info["BERV"]
        try:
            true_bary, true_herv = compute_berv_and_herv_POET(self._header)
        except Exception as e:
            logger.critical(f"Failed to compute BERV and HERV due to {e}")
            true_bary, true_herv = 0 * kilometer_second, 0 * kilometer_second
            self.add_to_status(FATAL_KW("Failed BERV and HERV correction"))

        true_berv = true_bary + true_herv

        new_rv = self.observation_info["DRS_RV"] - self.wrong_berv + true_berv
        self.observation_info["DRS_RV"] = new_rv
        self.observation_info["BERV"] = true_berv
        self.observation_info["HERV"] = true_herv

        self.observation_info["BERV_FACTOR"] = None  # Avoid re-write later on
        self.observation_info["MAX_BERV"] = 2.5 * kilometer_second

    def load_telemetry_info(self, header):
        # Find the UT number and load the airmass
        super().load_telemetry_info(header)

        if "ESO TEL5 AMBI FWHM START" not in header:
            # Backup since some files had the wrong keyword
            logger.critical("seeing KW not in header, falling back to old KW")
            logger.warning(header["*AMBI FWHM"])
            self.observation_info["seeing"] = float(
                header[f"HIERARCH ESO TEL{self.UT_number} AMBI FWHM"]
            )

    def load_S1D_data(self) -> None:
        # Store the open status before calling parent classes
        is_open = self.is_open
        super().load_S1D_data()
        if not is_open:
            self.apply_poet_data_corrections()

    def load_S2D_data(self) -> None:
        # Store the open status before calling parent classes
        is_open = self.is_open
        super().load_S2D_data()
        if not is_open:
            self.apply_poet_data_corrections()

    def apply_poet_data_corrections(self) -> None:
        # Correct spectra
        if self._internal_configs["DEFER_BERV_UPDATE"]:
            self._update_drs_rv()

        self.remove_BERV_correction(self.wrong_berv)
        self.apply_BERV_correction(self.observation_info["BERV"])

    def trigger_data_storage(self, *args, **kwargs):
        super().trigger_data_storage(*args, **kwargs)


def load_POET_extra_information(self: "DataClass") -> None:

    poet_ob_names, frameIDs = self.collect_KW_observations(
        KW="OBS NAME",
        subInstruments=self.get_subInstruments_with_valid_frames(),
        include_invalid=True,
        return_frameIDs=True,
    )

    poet_iso_dates, frameIDs = self.collect_KW_observations(
        KW="ISO-DATE",
        subInstruments=self.get_subInstruments_with_valid_frames(),
        include_invalid=True,
        return_frameIDs=True,
    )

    map_of_days: dict[str, list[int]] = defaultdict(list)
    for name, fID in zip(poet_iso_dates, frameIDs):
        map_of_days[name.split("T")[0]].append(fID)

    sol_path: Path = self.observations[0]._internal_configs["SOLYARIS_PATH"]
    aux_path: Path = self.observations[0]._internal_configs["AUX_FILE_FOLDER"]

    sol_data = None
    # Apply extra corrections to Sun as a Star data (differential atmospheric extinction)
    if sol_path is not None:
        sol_path = Path(sol_path)
        print(sol_data, sol_path)
        if not sol_path.exists():
            raise custom_exceptions.InternalError(
                f"SOLYARIS path ({sol_path}) does not exist"
            )
        for day, frameIDs in map_of_days.items():
            if sol_path.is_dir():
                local_sol_path = sol_path.glob(f"**/*{day}*csv")
                try:
                    sol_data = pd.read_csv(next(local_sol_path))
                except StopIteration:
                    logger.critical(
                        f"Couldn't find solyaris file for {day} in {sol_path}"
                    )
                    for fID in frameIDs:
                        frame = self.get_frame_by_ID(fID)
                        frame.add_to_status(FATAL_KW("No SOLYARIS info found"))
                    continue
            else:
                sol_data = pd.read_csv(sol_path)

            for frameID in frameIDs:
                frame = self.get_frame_by_ID(frameID)
                if frame.is_resolved_observation:
                    # No correction for fiber B data
                    continue

                raw_fname = frame.fname.replace("r.", "").split("_")[0] + ".fits"

                try:
                    row = sol_data[sol_data["file"] == raw_fname].iloc[0]
                except IndexError:
                    frame.add_to_status(f"No SOLYARIS info for {raw_fname}")
                    continue

                rv_corr = row["corr_extinction_tot"] * kilometer_second
                frame.import_KW_from_outside(
                    "DIFF_ATMOS_RV_CORR", rv_corr, optional=True
                )
                frame.observation_info["DRS_RV"] = (
                    frame.observation_info["DRS_RV"] + rv_corr
                )
                # Thresholds provided by Khaled Al Moulla
                qual_value = (
                    (row["quality_68"] > 0.95)
                    & (row["c0_hat_68"] < 0.1)
                    & (row["jit_68"] < 0.005)
                )
                if not qual_value:
                    frame.add_to_status(
                        FATAL_KW(f"Failed SOLYARIS QC checks for {frame.fname}")
                    )
                frame.finalized_external_data_load()

    else:
        logger.warning(
            "SOLYARIS path was not provided, skipping atmospheric extinction and QC checks"
        )
        for fID in frameIDs:
            frame = self.get_frame_by_ID(fID)
            if not frame.is_resolved_observation:
                frame.finalized_external_data_load()

    if aux_path is not None:
        aux_path = Path(aux_path)
        all_aux_files = aux_path.glob(f"**/POET.INT.{day}*fits")
        map_of_files: dict[str, list[int]] = defaultdict(list)
        for name, fID in zip(poet_ob_names, frameIDs):
            map_of_files[name].append(fID)

        poe_to_header_map = {}
        for aux_file in all_aux_files:
            aux_header = fits.getheader(aux_file, ext=1)
            aux_ob_name = aux_header["ESO OBS NAME"]
            if aux_ob_name not in map_of_files:
                logger.debug(
                    f"Could not find any frame for {aux_ob_name} in {aux_file}"
                )
                continue

            poe_to_header_map[aux_ob_name] = aux_header

        for poet_ob_name, frameIDs in map_of_files.items():

            head = poe_to_header_map.get(poet_ob_name)

            for frame in frameIDs:
                frame = self.get_frame_by_ID(frame)

                for int_kw, head_kwy in [
                    ("PROG ID", "ESO ST ID"),
                    ("TX", "ESO TEL5 TARG TX"),
                    ("TY", "ESO TEL5 TARG TY"),
                ]:
                    val = head[head_kwy]

                    if val in ["TX", "TY"]:
                        val = float(val) * u.arcsec

                    frame.import_KW_from_outside(KW=int_kw, value=val, optional=True)

    else:
        logger.warning("AUXILLIARY path was not provided, skipping loading of metadata")
        for fID in frameIDs:
            frame = self.get_frame_by_ID(fID)
            if frame.is_resolved_observation:
                frame.finalized_external_data_load()
