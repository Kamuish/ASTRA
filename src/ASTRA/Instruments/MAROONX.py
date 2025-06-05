"""Interface to MAROON-X data."""

import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from astropy.coordinates import EarthLocation
from scipy.constants import convert_temperature
from scipy.ndimage import median_filter

from ASTRA.base_models.Frame import Frame
from ASTRA.status.flags import (
    MISSING_DATA,
    QUAL_DATA,
)
from ASTRA.status.Mask_class import Mask
from ASTRA.utils import custom_exceptions
from ASTRA.utils.definitions import DETECTOR_DEFINITION
from ASTRA.utils.shift_spectra import SPEED_OF_LIGHT
from ASTRA.utils.units import kilometer_second, meter_second


class MAROONX(Frame):
    """Interface to handle MAROONX data."""

    _default_params = Frame._default_params

    # Adding one more day than the official time, so that we ensure to include any observations
    # from the last day

    sub_instruments = {
        "MAROON1": datetime.datetime.strptime("09-15-2020", r"%m-%d-%Y"),
        "MAROON2": datetime.datetime.strptime("12-02-2020", r"%m-%d-%Y"),
        "MAROON3": datetime.datetime.strptime("03-04-2021", r"%m-%d-%Y"),
        "MAROON4": datetime.datetime.strptime("04-30-2021", r"%m-%d-%Y"),
        "MAROON5": datetime.datetime.strptime("06-04-2021", r"%m-%d-%Y"),
        "MAROON6": datetime.datetime.strptime("08-23-2021", r"%m-%d-%Y"),
        "MAROON7": datetime.datetime.strptime("11-23-2021", r"%m-%d-%Y"),
        "MAROON8": datetime.datetime.strptime("04-27-2022", r"%m-%d-%Y"),
        "MAROON9": datetime.datetime.strptime("06-03-2022", r"%m-%d-%Y"),
        "MAROON10": datetime.datetime.strptime("08-15-2022", r"%m-%d-%Y"),
        "MAROON11": datetime.datetime.strptime("07-11-2023", r"%m-%d-%Y"),
        "MAROON12": datetime.datetime.strptime("10-28-2023", r"%m-%d-%Y"),
        "MAROON13": datetime.datetime.strptime("11-29-2023", r"%m-%d-%Y"),
        "MAROON14": datetime.datetime.strptime("01-03-2024", r"%m-%d-%Y"),
        "MAROON15": datetime.datetime.strptime("04-24-2024", r"%m-%d-%Y"),
        "MAROON16": datetime.datetime.strptime("06-13-2024", r"%m-%d-%Y"),
        "MAROON17": datetime.datetime.strptime("07-18-2024", r"%m-%d-%Y"),
        "MAROON18": datetime.datetime.strptime("08-20-2024", r"%m-%d-%Y"),
        "MAROON19": datetime.datetime.strptime("10-15-2024", r"%m-%d-%Y"),
        "MAROON20": datetime.datetime.strptime("01-09-2025", r"%m-%d-%Y"),
        "MAROON21": datetime.datetime.strptime("02-04-2025", r"%m-%d-%Y"),
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

    def get_spectral_type(self) -> str:
        """Get the spectral type from the filename."""
        if not self.file_path.name.endswith("hd5"):
            raise custom_exceptions.InternalError("MAROON-X interface only recognizes hd5 files")
        return "S2D"

    def load_instrument_specific_KWs(self, header) -> None:
        """Override parent class, does nothing."""
        ...

    def load_header_info(self) -> None:
        """Load information from the header."""
        store = pd.HDFStore(self.file_path, "r+")
        header_blue = store["header_blue"]
        header_red = store["header_red"]

        orders_blue = store["spec_blue"].index.levels[1]
        orders_red = store["spec_red"].index.levels[1]
        store.close()

        for order_set, header_det in [
            (orders_blue, header_blue),
            (orders_red, header_red),
        ]:
            for order in order_set:
                self.observation_info["orderwise_SNRs"].append(float(header_det[f"SNR_{order}"]))
        for name, kw in [
            ("ISO-DATE", "MAROONX TELESCOPE TIME"),
            ("OBJECT", "MAROONX TELESCOPE TARGETNAME"),
        ]:
            self.observation_info[name] = header_blue[kw]

        for name, kw in [
            ("airmass", "MAROONX TELESCOPE AIRMASS"),
            ("relative_humidity", "MAROONX TELESCOPE HUMIDITY"),
            ("ambient_temperature", "MAROONX WEATHER TEMPERATURE"),  # TODO: check units
            ("BERV", "BERV_FLUXWEIGHTED_FRD"),
            ("JD", "JD_UTC_FLUXWEIGHTED_FRD"),
            ("EXPTIME", "EXPTIME"),
        ]:
            self.observation_info[name] = float(header_blue[kw])

        self.observation_info["BERV"] = self.observation_info["BERV"] * meter_second
        self.observation_info["BERV_FACTOR"] = (
            1 + self.observation_info["BERV"].to(kilometer_second).value / SPEED_OF_LIGHT
        )
        # Convert ambient temperature to Kelvin
        self.observation_info["ambient_temperature"] = convert_temperature(
            self.observation_info["ambient_temperature"],
            old_scale="Celsius",
            new_scale="Kelvin",
        )

        # Note: we don't have DRS values for MAROON-X
        self.observation_info["DRS_RV"] = 0 * meter_second
        self.observation_info["DRS_RV_ERR"] = 0 * meter_second

        self.find_instrument_type()
        self.assess_bad_orders()

    def load_S2D_data(self) -> None:
        """Load the S2D data from the HD5 files."""
        if self.is_open:
            return
        super().load_S2D_data()
        store = pd.HDFStore(self.file_path, "r+")
        spec_red = store["spec_red"]
        spec_blue = store["spec_blue"]
        store.close()

        red_pix = spec_red["wavelengths"][6].values[0].shape[0]
        blue_pix = spec_blue["wavelengths"][6].values[0].shape[0]
        blue_pad = red_pix - blue_pix

        blue_det_flux = np.vstack(spec_blue["optimal_extraction"][6])
        p_blue_det_flux = np.pad(blue_det_flux, ((0, 0), (0, blue_pad)), mode="constant")
        blue_det_wave = np.vstack(spec_blue["wavelengths"][6])
        p_blue_det_wave = np.pad(blue_det_wave, ((0, 0), (0, blue_pad)), mode="constant")
        blue_det_err = np.vstack(spec_blue["optimal_var"][6])
        p_blue_det_err = np.pad(blue_det_err, ((0, 0), (0, blue_pad)), mode="constant")

        red_det_flux = np.vstack(spec_red["optimal_extraction"][6])
        red_det_wave = np.vstack(spec_red["wavelengths"][6])
        red_det_err = np.vstack(spec_red["optimal_var"][6])

        self.wavelengths = np.vstack((p_blue_det_wave, red_det_wave))
        self.spectra = np.vstack((p_blue_det_flux, red_det_flux))
        self.uncertainties = np.vstack((p_blue_det_err, red_det_err))
        self.build_mask(bypass_QualCheck=True)

    def load_S1D_data(self) -> Mask:
        """Load S1D data, currently not implemented."""
        raise NotImplementedError

    def build_mask(self, bypass_QualCheck: bool = False) -> None:
        """Construct the pixel-wise mask."""
        # We evaluate the bad orders all at once
        super().build_mask(bypass_QualCheck, assess_bad_orders=False)

        bpmap0 = np.zeros((62, 4036), dtype=np.uint64)
        # Remove the first blue order
        bpmap0[0, :] = 1

        if self._internal_configs["SIGMA_CLIP_FLUX_VALUES"] > 0:
            sigma = self._internal_configs["SIGMA_CLIP_FLUX_VALUES"]
            for order_number in range(self.N_orders):
                cont = median_filter(self.spectra[order_number], size=500)
                inds = np.where(self.spectra[order_number] >= cont + sigma * self.uncertainties[order_number])
                bpmap0[order_number, inds] |= 1
        self.spectral_mask.add_indexes_to_mask(np.where(bpmap0 != 0), QUAL_DATA)

        # remove extremely negative points!
        self.spectral_mask.add_indexes_to_mask(np.where(self.spectra < -3 * self.uncertainties), MISSING_DATA)

        self.assess_bad_orders()

    def close_arrays(self) -> None:
        """Close arrays in memory."""
        super().close_arrays()
        self.is_BERV_corrected = False
