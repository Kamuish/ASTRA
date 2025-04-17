import datetime
from pathlib import Path
from typing import Any, Dict, NoReturn, Optional

import numpy as np
import pandas as pd
from astropy.coordinates import EarthLocation
from astropy.io import fits
from loguru import logger
from scipy.constants import convert_temperature
from scipy.ndimage import median_filter

from ASTRA.base_models.Frame import Frame
from ASTRA.data_objects import DataClass
from ASTRA.status.flags import (
    MISSING_DATA,
    QUAL_DATA,
)
from ASTRA.status.Mask_class import Mask
from ASTRA.utils import custom_exceptions, meter_second
from ASTRA.utils.definitions import DETECTOR_DEFINITION
from ASTRA.utils.units import kilometer_second
from ASTRA.utils.UserConfigs import (
    DefaultValues,
    UserParam,
)


class MAROONX(Frame):
    """Interface to handle MAROONX data."""

    _default_params = Frame._default_params

    # Adding one more day than the official time, so that we ensure to include any observations
    # from the last day

    sub_instruments = {
        "MAROON1": datetime.datetime.strptime("10/14/2020", r"%Y-%m-%d"),
        "MAROON2": datetime.datetime.strptime("13/01/2020", r"%Y-%m-%d"),
        "MAROON3": datetime.datetime.strptime("04/03/2021", r"%Y-%m-%d"),
        "MAROON4": datetime.datetime.strptime("05/29/2021", r"%Y-%m-%d"),
        "MAROON5": datetime.datetime.strptime("07/03/2021", r"%Y-%m-%d"),
        "MAROON6": datetime.datetime.strptime("09/22/2021", r"%Y-%m-%d"),
        "MAROON7": datetime.datetime.strptime("12/22/2021", r"%Y-%m-%d"),
        "MAROON8": datetime.datetime.strptime("05/26/2022", r"%Y-%m-%d"),
        "MAROON9": datetime.datetime.strptime("07/02/2022", r"%Y-%m-%d"),
        "MAROON10": datetime.datetime.strptime("09/14/2022", r"%Y-%m-%d"),
        "MAROON11": datetime.datetime.strptime("08/10/2023", r"%Y-%m-%d"),
        "MAROON12": datetime.datetime.strptime("11/27/2023", r"%Y-%m-%d"),
        "MAROON13": datetime.datetime.strptime("12/28/2023", r"%Y-%m-%d"),
        "MAROON14": datetime.datetime.strptime("02/02/2024", r"%Y-%m-%d"),
        "MAROON15": datetime.datetime.strptime("05/23/2024", r"%Y-%m-%d"),
        "MAROON16": datetime.datetime.strptime("07/12/2024", r"%Y-%m-%d"),
        "MAROON17": datetime.datetime.strptime("08/17/2024", r"%Y-%m-%d"),
        "MAROON18": datetime.datetime.strptime("09/19/2024", r"%Y-%m-%d"),
        "MAROON19": datetime.datetime.strptime("11/14/2024", r"%Y-%m-%d"),
        "MAROON20": datetime.datetime.strptime("02/08/2025", r"%Y-%m-%d"),
        "MAROON21": datetime.datetime.strptime("03/03/2025", r"%Y-%m-%d"),
        "MAROON22": datetime.datetime.max,
    }
    _name = "MAROONX"

    order_intervals: dict[DETECTOR_DEFINITION, slice] = {
        DETECTOR_DEFINITION.WHITE_LIGHT: list(range(62)),
        DETECTOR_DEFINITION.RED_DET: list(range(34, 62)),
        DETECTOR_DEFINITION.BLUE_DET: list(range(0, 34)),
    }
    KW_map = {}

    def __init__(
        self,
        file_path,
        user_configs: Optional[Dict[str, Any]] = None,
        reject_subInstruments=None,
        frameID=None,
        quiet_user_params: bool = True,
    ):
        """

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

        # TODO:
        # - [ ] Fix header access
        # - [ ] Open frames
        # - [ ] Divide into subInstruments
        self._blaze_corrected = True

        super().__init__(
            inst_name=self._name,
            array_size={"S2D": [62, 4036]},
            file_path=file_path,
            frameID=frameID,
            KW_map=self.KW_map,
            available_indicators=("FWHM", "BIS SPAN"),
            user_configs=user_configs,
            reject_subInstruments=reject_subInstruments,
            need_external_data_load=False,
            quiet_user_params=quiet_user_params,
        )
        coverage = [500, 920]
        self.instrument_properties["wavelength_coverage"] = coverage
        self.instrument_properties["is_drift_corrected"] = False

        self.instrument_properties["resolution"] = 86_000

        # lat/lon from: https://geohack.toolforge.org/geohack.php?params=19_49_25_N_155_28_9_W
        lat, lon = 19.820667, -155.468056
        self.instrument_properties["EarthLocation"] = EarthLocation.from_geodetic(lat=lat, lon=lon, height=4214)

        # from https://www.mide.com/air-pressure-at-altitude-calculator
        # and convert from Pa to mbar
        self.instrument_properties["site_pressure"] = 599.4049

        self.is_BERV_corrected = False

    def get_spectral_type(self):
        name_lowercase = self.file_path.stem
        if "vis_A" in name_lowercase:
            return "S2D"
        else:
            raise custom_exceptions.InternalError(
                f"{self.name} can't recognize the file that it received ( - {self.file_path.stem})!"
            )

    def load_instrument_specific_KWs(self, header): ...

    def load_header_info(self):
        store = pd.HDFStore(self.file_path, "r+")
        header_blue = store["header_blue"]
        store.close()

        for name, kw in [
            ("airmass", "MAROONX TELESCOPE AIRMASS"),
            ("relative_humidity", "MAROONX TELESCOPE HUMIDITY"),
            ("ISO-DATE", "MAROONX TELESCOPE TIME"),
            ("ambient_temperature", "MAROONX WEATHER TEMPERATURE"),  # TODO: check units
            ("BERV", "BERV_FLUXWEIGHTED_FRD"),
            ("JD", "JD_UTC_FLUXWEIGHTED_FRD"),
            ("EXPTIME", "EXPTIME"),
        ]:
            self.observation_info[name] = float(header_blue[kw])

        self.observation_info["BERV"] = self.observation_info["BERV"] * meter_second
        self.find_instrument_type()
        self.assess_bad_orders()

    def load_S2D_data(self):
        if self.is_open:
            return
        super().load_S2D_data()
        store = pd.HDFStore(self.file_path, "r+")
        spec_red = store["spec_red"]
        spec_blue = store["spec_blue"]
        store.close()

        red_pix = spec_red["wavelengths"].values[0].shape[0]
        blue_pix = spec_blue["wavelengths"].values[0].shape[0]
        blue_pad = red_pix - blue_pix

        blue_det_flux = np.vstack(spec_blue["optimal_extraction"][6])
        p_blue_det_flux = np.pad(blue_det_flux, ((0, 0), (0, blue_pad)), mode="constant")
        blue_det_wave = np.vstack(spec_blue["wavelengths"])
        p_blue_det_wave = np.pad(blue_det_wave, ((0, 0), (0, blue_pad)), mode="constant")
        blue_det_err = np.vstack(spec_blue["optimal_var"][6])
        p_blue_det_err = np.pad(blue_det_err, ((0, 0), (0, blue_pad)), mode="constant")

        red_det_flux = np.vstack(spec_red["optimal_extraction"][6])
        red_det_wave = np.vstack(spec_red["wavelengths"])
        red_det_err = np.vstack(spec_red["optimal_var"][6])

        self.wavelengths = np.vstack((p_blue_det_wave, red_det_wave))
        self.spectra = np.vstack((p_blue_det_flux, red_det_flux))
        self.uncertainties = np.vstack((p_blue_det_err, red_det_err))
        self.build_mask(bypass_QualCheck=True)
        return 1

    def load_S1D_data(self) -> Mask:
        raise NotImplementedError

    def build_mask(self, bypass_QualCheck: bool = False):
        # We evaluate the bad orders all at once
        super().build_mask(bypass_QualCheck, assess_bad_orders=False)

        bpmap0 = np.zeros((62, 4036), dtype=np.uint64)
        # Remove the first blue order
        bpmap0[0, :] = 1

        if self._internal_configs["sigma_clip_flux"] > 0:
            sigma = self._internal_configs["sigma_clip_flux"]
            for order_number in range(self.N_orders):
                cont = median_filter(self.spectra[order_number], size=500)
                inds = np.where(self.spectra[order_number] >= cont + sigma * self.uncertainties[order_number])
                bpmap0[order_number, inds] |= 1
        self.spectral_mask.add_indexes_to_mask(np.where(bpmap0 != 0), QUAL_DATA)

        # remove extremely negative points!
        self.spectral_mask.add_indexes_to_mask(np.where(self.spectra < -3 * self.uncertainties), MISSING_DATA)

        self.assess_bad_orders()

    def close_arrays(self):
        super().close_arrays()
        self.is_BERV_corrected = False
