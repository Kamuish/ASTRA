import datetime
from pathlib import Path
from typing import Any, Dict, NoReturn, Optional

import numpy as np
from astropy.coordinates import EarthLocation
from astropy.io import fits
from loguru import logger
from scipy.constants import convert_temperature
from scipy.ndimage import median_filter

from ASTRA.base_models.Frame import Frame
from ASTRA.data_objects import DataClass
from ASTRA.status.flags import FATAL_KW, KW_WARNING, MISSING_DATA, MISSING_SHAQ_RVS, QUAL_DATA, Flag
from ASTRA.status.Mask_class import Mask
from ASTRA.utils import custom_exceptions
from ASTRA.utils.parameter_validators import BooleanValue, NumericValue, PathValue
from ASTRA.utils.shift_spectra import SPEED_OF_LIGHT
from ASTRA.utils.units import kilometer_second, meter_second
from ASTRA.utils.UserConfigs import DefaultValues, UserParam


class CARMENES(Frame):
    """Interface to handle KOBE-CARMENES data (optical arm only).

    Using this class implies passing an input file (shaq_output_folder), from where we will load
    the following information:

    - Column 0 -> BJD
    - Column 5 -> CCF RV in km/s
    - Column 3 -> CCF RV Error in km/s
    - Column 10 -> BERV in km/s (used if we configure the override_BERV option)
    - Column 7 -> Instrumental drift in m/s
    - Column 8 -> Error in Instrumental drift in m/s
    - Column 9 -> QC flag on instrumental drift

    Any observation that can't be cross-matched to the BJD will be marked as invalid
    """

    _default_params = Frame._default_params + DefaultValues(
        shaq_output_folder=UserParam(None, constraint=PathValue, mandatory=True),
        override_BERV=UserParam(True, constraint=BooleanValue, mandatory=False),
        is_KOBE_data=UserParam(True, constraint=BooleanValue, mandatory=False),
        max_hours_to_calibration=UserParam(
            100,
            constraint=NumericValue,
            mandatory=False,
            description="Maximum number of hours between observation and calibration. If exceeded, frame is invalid",
        ),
        sigma_clip_flux=UserParam(
            -1,
            constraint=NumericValue,  # -1 means that it is disabled,
            mandatory=False,
            description="If positive, then sigma clip the flux",
        ),
    )
    _default_params.update("IS_SA_CORRECTED", UserParam(True, constraint=BooleanValue, mandatory=False))

    sub_instruments = {
        "CARMENES": datetime.datetime.max,
    }
    _name = "CARMENES"

    KW_map = {
        "OBJECT": "OBJECT",
        "BJD": "HIERARCH CARACAL BJD",
        "MJD": "MJD-OBS",
        "ISO-DATE": "DATE-OBS",  # TODO: to check this KW name
        "DRS-VERSION": "HIERARCH CARACAL FOX VERSION",
        "RA": "RA",
        "DEC": "DEC",
    }

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

        self._blaze_corrected = True

        super().__init__(
            inst_name=self._name,
            array_size={"S2D": [61, 4096]},
            file_path=file_path,
            frameID=frameID,
            KW_map=self.KW_map,
            available_indicators=("FWHM", "BIS SPAN"),
            user_configs=user_configs,
            reject_subInstruments=reject_subInstruments,
            need_external_data_load=True,
            quiet_user_params=quiet_user_params,
        )
        coverage = [500, 1750]
        self.instrument_properties["wavelength_coverage"] = coverage
        self.instrument_properties["is_drift_corrected"] = False

        # TODO: ensure that there are no problem when using the NIR arm of CARMENES!!!!!
        self.instrument_properties["resolution"] = 94600

        # lat/lon from: https://geohack.toolforge.org/geohack.php?pagename=Calar_Alto_Observatory&params=37_13_25_N_2_32_46_W_type:landmark_region:ES
        # height from: https://en.wikipedia.org/wiki/Calar_Alto_Observatory
        lat, lon = 37.223611, -2.546111
        self.instrument_properties["EarthLocation"] = EarthLocation.from_geodetic(lat=lat, lon=lon, height=2168)

        # from https://www.mide.com/air-pressure-at-altitude-calculator
        # and convert to Pa to mbar
        self.instrument_properties["site_pressure"] = 778.5095

        self.is_BERV_corrected = False

    def get_spectral_type(self):
        name_lowercase = self.file_path.stem
        if "vis_A" in name_lowercase:
            return "S2D"
        else:
            raise custom_exceptions.InternalError(
                f"{self.name} can't recognize the file that it received ( - {self.file_path.stem})!"
            )

    def load_instrument_specific_KWs(self, header):
        self.observation_info["airmass"] = header[f"AIRMASS"]

        # Load BERV info + previous RV
        self.observation_info["MAX_BERV"] = 30 * kilometer_second
        self.observation_info["BERV"] = header["HIERARCH CARACAL BERV "] * kilometer_second

        # TODO: check ambient temperature on CARMENES data TO SEE IF IT IS THE "REAL ONE"
        # Environmental KWs for telfit (also needs airmassm previously loaded)
        ambi_KWs = {
            "relative_humidity": "AMBI RHUM",
            "ambient_temperature": "AMBI TEMPERATURE",
        }

        for name, endKW in ambi_KWs.items():
            self.observation_info[name] = header[f"HIERARCH CAHA GEN {endKW}"]
            if "temperature" in name:  # store temperature in KELVIN for TELFIT
                self.observation_info[name] = convert_temperature(
                    self.observation_info[name], old_scale="Celsius", new_scale="Kelvin"
                )
        for order in range(self.N_orders):
            self.observation_info["orderwise_SNRs"].append(header[f"HIERARCH CARACAL FOX SNR {order}"])

        self.observation_info["MOON PHASE"] = header["HIERARCH CAHA INS SCHEDULER MOON PHASE"]
        self.observation_info["MOON DISTANCE"] = header["HIERARCH CAHA INS SCHEDULER MOON DISTANCE"]

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
        kill_messages = []

        try:
            drift_file = header["CARACAL DRIFT FP REF"]

            night_drift = drift_file.split("s-")[0].split("car-")[-1]
            night_drift = datetime.datetime.strptime(night_drift, r"%Y%m%dT%Hh%Mm%S")
            night_data = datetime.datetime.strptime(header["CARACAL DATE-OBS"], r"%Y-%m-%dT%H:%M:%S")
            msg = f"\tDistance between calibration (FP) and OB has surpassed the limit of {self._internal_configs['max_hours_to_calibration']}"
            if (
                abs(night_drift - night_data).total_seconds()
                > datetime.timedelta(hours=self._internal_configs["max_hours_to_calibration"]).total_seconds()
            ):
                kill_messages.append(msg)

        except KeyError:
            kill_messages.append("Observation missing the CARACAL DRIFT FP REF keyword")

        if self._internal_configs["is_KOBE_data"]:
            # we can have skysubs outside of KOBE
            for msg in kill_messages:
                logger.critical(msg)
                self.add_to_status(FATAL_KW(msg.replace("\t", "")))

    def load_S2D_data(self):
        if self.is_open:
            return
        super().load_S2D_data()

        with fits.open(self.file_path) as hdulist:
            s2d_data = hdulist["SPEC"].data * 100000  # spetra from all olders
            err_data = hdulist["SIG"].data * 100000
            wavelengths = hdulist["WAVE"].data  # vacuum wavelengths; no BERV correction

        self.wavelengths = wavelengths
        self.spectra = s2d_data
        self.uncertainties = err_data
        self.build_mask(bypass_QualCheck=True)
        return 1

    def finalize_data_load(self, bad_flag: Optional[Flag] = None):
        bad_flag = MISSING_SHAQ_RVS
        super().finalize_data_load(bad_flag)

        moon_sep = self.observation_info["MOON DISTANCE"]
        moon_illum = self.observation_info["MOON PHASE"]
        rv = self.observation_info["DRS_RV"]
        berv = self.observation_info["BERV"]
        fwhm = self.observation_info["FWHM"]
        conditions = (
            moon_sep > 80,
            (30 < moon_sep < 80) and moon_illum < 0.6,
            abs(rv - berv) > 5 * fwhm,
        )
        if not any(conditions):
            logger.warning("Target is close to the moon, setting warning flag")
            self.add_to_status(KW_WARNING("Target is close to moon"))

    def load_S1D_data(self) -> Mask:
        raise NotImplementedError

    def build_mask(self, bypass_QualCheck: bool = False):
        # We evaluate the bad orders all at once
        super().build_mask(bypass_QualCheck, assess_bad_orders=False)

        bpmap0 = np.zeros((61, 4096), dtype=np.uint64)
        bpmap0[14:38, [2453 - 3, 2453 - 2, 2453 - 1, 2453, 2453 + 1, 2453 + 2, 2453 + 3]] |= 1
        bpmap0[14:38, 1643] |= 1  # ghost of hotspot tail
        bpmap0[14:38, 2459] |= 1  # spikes of hotspot satellite (bug not correct due to bug in v2.00)
        bpmap0[15:41, 3374] |= 1  # displaced column; ignore by marking as nan
        bpmap0[28, 3395:3400] |= 1  # car-20160701T00h49m36s-sci-gtoc-vis.fits
        bpmap0[34, 838:850] |= 1  # car-20160803T22h46m41s-sci-gtoc-vis.fits
        bpmap0[34, 2035:2044] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[34, 3150:3161] |= 1  # car-20160803T22h46m41s-sci-gtoc-vis.fits
        bpmap0[35, 403:410] |= 1  # car-20160803T22h46m41s-sci-gtoc-vis
        bpmap0[35, 754:759] |= 1  # car-20170419T03h27m48s-sci-gtoc-vis
        bpmap0[35, 1083:1093] |= 1  # car-20160803T22h46m41s-sci-gtoc-vis
        bpmap0[35, 1944:1956] |= 1  # car-20160803T22h46m41s-sci-gtoc-vis
        bpmap0[35, 2710:2715] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[35, 3050:3070] |= 1  # car-20160803T22h46m41s-sci-gtoc-vis
        bpmap0[35, 3706:3717] |= 1  # car-20160803T22h46m41s-sci-gtoc-vis
        bpmap0[35, 3706:3717] |= 1  # car-20160803T22h46m41s-sci-gtoc-vis
        bpmap0[36, 303:308] |= 1  # car-20170419T03h27m48s-sci-gtoc-vis
        bpmap0[36, 312:317] |= 1  # car-20170419T03h27m48s-sci-gtoc-vis
        bpmap0[36, 1311:1315] |= 1  # car-20170419T03h27m48s-sci-gtoc-vis
        bpmap0[36, 1325:1329] |= 1  # car-20170419T03h27m48s-sci-gtoc-vis
        bpmap0[37, 1326:1343] |= 1  # car-20170419T03h27m48s-sci-gtoc-vis
        bpmap0[39, 1076:1082] |= 1  # car-20170626T02h00m17s-sci-gtoc-vis
        bpmap0[39, 1204:1212] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[39, 1236:1243] |= 1  # car-20170419T03h27m48s-sci-gtoc-vis
        bpmap0[39, 1463:1468] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[39, 2196:2203] |= 1  # car-20160520T03h10m13s-sci-gtoc-vis.fits
        bpmap0[39, 2493:2504] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[39, 3705:3717] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[40, 2765:2773] |= 1  # car-20170419T03h27m48s-sci-gtoc-vis
        bpmap0[40, 3146:3153] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[40, 3556:3564] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[41, 486:491] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[41, 495:501] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[41, 1305:1315] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[42, 480:490] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[42, 1316:1330] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[42, 2363:2368] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[42, 2375:2382] |= 1  # car-20170509T03h05m21s-sci-gtoc-vis
        bpmap0[44, 3355:3361] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[46, 311:321] |= 1  # car-20160701T00h49m36s-sci-gtoc-vis.fits
        bpmap0[46, 835:845] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[46, 1156:1171] |= 1  # car-20160701T00h49m36s-sci-gtoc-vis.fits
        bpmap0[46, 1895:1905] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[46, 2212:2232] |= 1  # car-20160701T00h49m36s-sci-gtoc-vis.fits
        bpmap0[47, 2127:2133] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[47, 2218:2223] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[47, 2260:2266] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[47, 2313:2319] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[47, 3111:3116] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[47, 3267:3272] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[47, 3316:3321] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[47, 3432:3438] |= 1  # car-20170509T03h05m21s-sci-gtoc-vis
        bpmap0[47, 3480:3488] |= 1  # car-20160714T00h18m29s-sci-gtoc-vis
        bpmap0[47, 3658:3665] |= 1  # car-20170509T03h05m21s-sci-gtoc-vis
        bpmap0[49, 1008:1017] |= 1  # car-20160701T00h49m36s-sci-gtoc-vis.fits
        bpmap0[49, 2532:2544] |= 1  # car-20160701T00h49m36s-sci-gtoc-vis.fits
        bpmap0[49, 3046:3056] |= 1  # car-20160701T00h49m36s-sci-gtoc-vis.fits
        bpmap0[49, 3574:3588] |= 1  # car-20160701T00h49m36s-sci-gtoc-vis.fits

        # Constructing the bad pixel map, as defined by SERVAL in here:
        # https://github.com/mzechmeister/serval/blob/c2f47b26f1102333dfe76f93c2a686807cda02ce/src/inst_CARM_VIS.py#L95

        bpmap0[25:41, 3606:3588] |= 1  # Our rejection

        if self._internal_configs["sigma_clip_flux"] > 0:
            sigma = self._internal_configs["sigma_clip_flux"]
            for order_number in range(self.N_orders):
                cont = median_filter(self.spectra[order_number], size=500)
                inds = np.where(self.spectra[order_number] >= cont + sigma * self.uncertainties[order_number])
                bpmap0[order_number, inds] |= 1
        self.spectral_mask.add_indexes_to_mask(np.where(bpmap0 != 0), QUAL_DATA)

        # remove extremely negative points!
        self.spectral_mask.add_indexes_to_mask(np.where(self.spectra < -3 * self.uncertainties), MISSING_DATA)
        self.spectral_mask.add_indexes_to_mask(np.where(self.uncertainties == 0), MISSING_DATA)

        self.assess_bad_orders()

    def close_arrays(self):
        super().close_arrays()
        self.is_BERV_corrected = False


def load_CARMENES_extra_information(self: DataClass) -> None:
    """CARMENES pipeline does not give RVs, we have to do an external load of the information

    Parameters
    ----------
    shaq_folder : str
        Path to the main folder of shaq-outputs. where all the KOBE-*** targets live
    """

    name_to_search = self.Target.true_name

    if self.observations[0]._internal_configs["is_KOBE_data"]:
        if "KOBE-" not in name_to_search:
            name_to_search = "KOBE-" + name_to_search  # temporary fix for naming problem!
    else:
        logger.info(f"Not loading KOBE data, searching for {name_to_search} dat file with Rvs")

    shaq_folder = Path(self.observations[0]._internal_configs["shaq_output_folder"])
    override_BERV = self.observations[0]._internal_configs["override_BERV"]

    if shaq_folder.name.endswith("dat"):
        logger.info("Received the previous RV file, not searching for outputs")
        shaqfile = shaq_folder
    else:
        logger.info("Searching for outputs of previous RV extraction")
        shaqfile = shaq_folder / name_to_search / f"{name_to_search}_RVs.dat"

    if shaqfile.exists():
        logger.info("Loading extra CARMENES data from {}", shaqfile)
    else:
        logger.critical(f"RV file does not exist on {shaqfile}")
        raise custom_exceptions.InvalidConfiguration("Missing RV file for data")

    number_loads = 0
    locs = []
    loaded_BJDs = [frame.get_KW_value("BJD") for frame in self.observations]
    with open(shaqfile) as file:
        for line in file:
            if "#" in line:  # header or other "BAD" files
                continue
            # TODO: implement a more thorough check in here, to mark the "bad" frames as invalid!
            ll = line.strip().split()
            if len(ll) == 0:
                logger.warning(f"shaq RV from {name_to_search} has empty line")
                continue
            bjd = round(float(ll[1]) - 2400000.0, 7)  # we have the full bjd date

            try:
                index = loaded_BJDs.index(bjd)  # to make sure that everything is loaded in the same order
                locs.append(index)
            except ValueError:
                logger.warning("RV shaq has entry that does not exist in the S2D files")
                continue

            self.observations[index].import_KW_from_outside("DRS_RV", float(ll[5]) * kilometer_second, optional=False)
            self.observations[index].import_KW_from_outside(
                "DRS_RV_ERR", float(ll[3]) * kilometer_second, optional=False
            )
            if override_BERV:
                self.observations[index].import_KW_from_outside(
                    "BERV", float(ll[10]) * kilometer_second, optional=False
                )
                berv_factor = 1 + ll[10] / SPEED_OF_LIGHT
                self.observations[index].import_KW_from_outside("BERV_FACTOR", berv_factor, optional=False)

            self.observations[index].import_KW_from_outside("FWHM", float(ll[11]), optional=True)
            self.observations[index].import_KW_from_outside("BIS SPAN", float(ll[13]), optional=True)

            drift_val = np.nan_to_num(float(ll[7])) * meter_second
            drift_err = np.nan_to_num(float(ll[8])) * meter_second
            drift_flag = float(ll[9])
            if drift_flag > 1:
                self.observations[index].add_to_status(KW_WARNING("Drift flag of KOBE is greater than 1"))

            self.observations[index].import_KW_from_outside("drift", drift_val, optional=False)
            self.observations[index].import_KW_from_outside("drift_ERR", drift_err, optional=False)

            number_loads += 1
            self.observations[index].finalized_external_data_load()

    if number_loads < len(self.observations):
        msg = f"RV shaq outputs does not have value for all S2D files of {name_to_search} ({number_loads}/{len(self.observations)})"

        logger.critical(msg)
