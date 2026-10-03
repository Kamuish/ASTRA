"""Interface to MAROON-X data."""

import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from astropy.coordinates import EarthLocation
from astropy.io import fits

from ASTRA.base_models.Frame import Frame
from ASTRA.status.flags import (
    MISSING_DATA,
)
from ASTRA.status.Mask_class import Mask
from ASTRA.utils import custom_exceptions
from ASTRA.utils.definitions import DETECTOR_DEFINITION
from ASTRA.utils.units import kilometer_second, meter_second
from astropy.time import Time


class SimulatedSpirou(Frame):
    """Interface to handle simulated data."""

    _default_params = Frame._default_params

    # Adding one more day than the official time, so that we ensure to include any observations
    # from the last day

    sub_instruments = {
        "SimulatedSpirou": datetime.datetime.max,
    }
    _name = "SimulatedSpirou"

    order_intervals: dict[DETECTOR_DEFINITION, slice] = {
        DETECTOR_DEFINITION.WHITE_LIGHT: list(range(48)),
    }
    KW_map = {}

    def __init__(
        self,
        file_path: Path,
        user_configs: Optional[Dict[str, Any]] = None,
        reject_subInstruments=None,
        frameID=None,
        quiet_user_params: bool = True,
    ):
        """Construct MAROON-X object.

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
        self._blaze_corrected = True

        super().__init__(
            inst_name=self._name,
            array_size={"S2D": [48, 4088]},
            file_path=file_path,
            frameID=frameID,
            KW_map=self.KW_map,
            available_indicators=[],
            user_configs=user_configs,
            reject_subInstruments=reject_subInstruments,
            need_external_data_load=False,
            quiet_user_params=quiet_user_params,
        )
        coverage = [955, 2438]
        self.instrument_properties["wavelength_coverage"] = coverage
        self.instrument_properties["is_drift_corrected"] = True

        self.instrument_properties["resolution"] = 100_000

        # lat/lon from: https://geohack.toolforge.org/geohack.php?params=19_49_25_N_155_28_9_W
        lat, lon = 19.820667, -155.468056
        self.instrument_properties["EarthLocation"] = EarthLocation.from_geodetic(lat=lat, lon=lon, height=4214)

        # from https://www.mide.com/air-pressure-at-altitude-calculator
        # and convert from Pa to mbar
        self.instrument_properties["site_pressure"] = 599.4049

        self.is_BERV_corrected = True

    def get_spectral_type(self):
        return "S2D"

    def load_instrument_specific_KWs(self, header):
        # Load BERV info + previous RV
        self.observation_info["MAX_BERV"] = 30 * kilometer_second
        self.observation_info["BERV"] = header["BERV"] * meter_second

        self.observation_info["DRS_RV"] = header["DRS_RV"] * meter_second
        self.observation_info["DRS_RV_ERR"] = header["DRS_RV_ERR"] * meter_second
        self.observation_info["BJD"] = header["BJD"]

        t = Time(header["BJD"], format="jd", scale="tdb")
        iso_string = t.iso
        self.observation_info["ISO-DATE"] = "T".join(iso_string.split(" "))

        for order in range(self.N_orders):
            self.observation_info["orderwise_SNRs"].append(header[f"SNR {order}"])

    def check_header_QC(self, header: fits.Header):
        """Header QC checks for CARMENES.

        1) Drift calibration was done (CARACAL DRIFT FP REF exists)
        2) Time between observation and calibration is smaller than "max_hours_to_calibration"

        Can add the following status:

        - KW_WARNING("Drift flag of KOBE is greater than 1")
            If th drift value is greater than one. This is actually set in the DataClass.load_CARMENES_extra_information()

        Args:
            header (fits.Header): _description_
        """
        ...

    def load_S2D_data(self):
        if self.is_open:
            return
        super().load_S2D_data()

        with fits.open(self.file_path) as hdulist:
            s2d_data = hdulist["SPEC"].data * 100000  # spetra from all olders
            err_data = hdulist["SIG"].data * 100000
            wavelengths = hdulist["WAVE"].data

        self.wavelengths = wavelengths
        self.spectra = s2d_data
        self.uncertainties = err_data
        self.build_mask(bypass_QualCheck=True)
        return 1

    def load_S1D_data(self) -> Mask:
        raise NotImplementedError

    def build_mask(self, bypass_QualCheck: bool = False):
        # We evaluate the bad orders all at once
        super().build_mask(bypass_QualCheck, assess_bad_orders=False)

        # remove extremely negative points!
        self.spectral_mask.add_indexes_to_mask(np.where(self.spectra < -3 * self.uncertainties), MISSING_DATA)
        self.spectral_mask.add_indexes_to_mask(np.where(self.uncertainties == 0), MISSING_DATA)

        self.assess_bad_orders()

    def close_arrays(self):
        super().close_arrays()
