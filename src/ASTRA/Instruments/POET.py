import datetime
from typing import Any, Dict, Iterable, Optional

import numpy as np
from astropy.coordinates import EarthLocation
from scipy.constants import convert_temperature

from ASTRA import astra_logger as logger
from ASTRA.status.flags import ERROR_THRESHOLD, KW_WARNING
from ASTRA.utils.definitions import DETECTOR_DEFINITION
from ASTRA.utils.units import kilometer_second
from ASTRA.utils.compute_berv_and_herv_poet import compute_berv_and_herv_POET
from ASTRA.Instruments.ESPRESSO import ESPRESSO
from ASTRA.utils.UserConfigs import DefaultValues, UserParam
from ASTRA.utils.parameter_validators import BooleanValue


class POET(ESPRESSO):
    """Interface to handle POET-ESPRESSO observations (S2D and S1D)."""

    _default_params = ESPRESSO._default_params + DefaultValues(
        DEFER_BERV_UPDATE=UserParam(
            False,
            constraint=BooleanValue,
            description="If True, only updated berv and rv when opening the data",
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

        super().__init__(
            file_path=file_path,
            frameID=frameID,
            user_configs=user_configs,
            reject_subInstruments=reject_subInstruments,
            quiet_user_params=quiet_user_params,
        )
        self._updated_drs_rv = False

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

        self._updated_drs_rv = True
        self.wrong_berv = self.observation_info["BERV"]
        true_bary, true_herv = compute_berv_and_herv_POET(header)
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
            self.observation_info["seeomg"] = float(
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
