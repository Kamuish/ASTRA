"""Define a base Frame object to interface with the observations.

This ensures that ASTRA is fully agnostic to the instrument that we are using, as long as
our data is properly loaded in the children classes of the Frame object.

It will also provide a common set of names for commonly used header values.
"""

from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np
from astropy.io import fits
from loguru import logger
from matplotlib import pyplot as plt

from ASTRA.Components.Modelling import Spectral_Modelling
from ASTRA.Components.Spectral_Normalization import Spectral_Normalization
from ASTRA.Components.SpectrumComponent import Spectrum
from ASTRA.status.flags import (
    HIGH_CONTAMINATION,
    LOADING_EXTERNAL_DATA,
    LOW_SNR,
    MISSING_DATA,
    MISSING_EXTERNAL_DATA,
    MISSING_FILE,
    NO_VALID_ORDERS,
    NON_COMMON_WAVELENGTH,
    QUAL_DATA,
    Flag,
)
from ASTRA.status.Mask_class import Mask
from ASTRA.status.Status import Status
from ASTRA.utils import custom_exceptions
from ASTRA.utils.ASTRAtypes import RV_measurement
from ASTRA.utils.custom_exceptions import FrameError
from ASTRA.utils.definitions import DETECTOR_DEFINITION
from ASTRA.utils.parameter_validators import (
    BooleanValue,
    NumericValue,
    Positive_Value_Constraint,
    ValueFromIterable,
    ValueInInterval,
)
from ASTRA.utils.ranges import ranges
from ASTRA.utils.telluric_utilities.compute_overlaps_blocks import check_if_overlap
from ASTRA.utils.units import kilometer_second
from ASTRA.utils.UserConfigs import DefaultValues, UserParam


class Frame(Spectrum, Spectral_Modelling, Spectral_Normalization):
    """Base Class for the different instruments.

    Providing a shared interface to spectral data and header information.

    This class defines a set of Keywords, consistent for all ASTRA supported Instruments, which can be accessed
    through the proper methods. The internal keywords are initialized to a default value, which the Frame will use
    if the instrument does  not provide that metric/value. Furthermore, all RV-related metrics are returned as
    astropy.Quantity objects (or lists of such objects). For such cases, one can use
    :func:`~ASTRAutils.units.convert_data` to convert data to different units and/or to floats


    The supported list of keywords, and the default initialization values is:


    Internal KW name     |  Default intialization
    ------------ | -------------
        BERV| np.nan * kilometer_second
    previous_SBART_RV| np.nan * kilometer_second
    previous_SBART_RV_ERR| np.nan * kilometer_second
    DRS_CCF_MASK| ""
    DRS_FLUX_CORRECTION_TEMPLATE| ""
    DRS_RV| np.nan * kilometer_second
    DRS_RV_ERR| np.nan * kilometer_second
    drift| np.nan * kilometer_second
    drift_ERR| np.nan * kilometer_second
    relative_humidity| np.nan,  # for telfi
    ambient_temperature| np.nan [Kelvin],  # for telfi
    airmass| np.nan
    orderwise_SNRs| []
    OBJECT| None
    MAX_BERV| np.nan * kilometer_second
    BJD| None
    MJD| None
    DRS-VERSION| None
    MD5-CHECK| None
    ISO-DATE| None
    CONTRAST| 0
    CONTRAST_ERR| 0
    FWHM| 0,  # Store this as km/
    FWHM_ERR| 0,  # Store this as km/
    BIS SPAN| 0,  # Store this as km/
    BIS SPAN_ERR| 0,  # Store this as km/
    EXPTIME| 0
    RA| None
    DEC| None
    SPEC_TYPE "None",  # This keyword is simply loading the CCF mask..
    DET_BINX| None
    DET_BINY| None
    seeing| None
    MOON PHASE| 0
    MOON DISTANCE| 0
    INS MODE| "None"
    INS NAME| "None"
    PROG ID| "None"
    DATE_NIGHT| "None"

    """

    _object_type = "Frame"
    _name = ""

    sub_instruments: dict[str, datetime.datetime] = {}
    # Dict of options and default values for them. Specific for each instrument

    _default_params = DefaultValues(
        bypass_QualCheck=UserParam(False, constraint=BooleanValue),
        open_without_BervCorr=UserParam(
            False,
            constraint=BooleanValue,
            description=(
                "Ensure that the Frame is not BERV corrected, independently "
                "of correction being applied or not in the official pipeline"
            ),
        ),
        apply_FluxCorr=UserParam(False, constraint=ValueFromIterable((False,))),
        use_air_wavelengths=UserParam(
            False,
            constraint=BooleanValue,
            description="Use air wavelengths, instead of the vacuum ones",
        ),
        apply_FluxBalance_Norm=UserParam(False, constraint=ValueFromIterable((False,))),
        reject_order_percentage=UserParam(0.25, constraint=ValueInInterval((0, 1), include_edges=True)),
        # If the SNR is smaller, discard the order:
        minimum_order_SNR=UserParam(
            5,
            constraint=Positive_Value_Constraint,
            description="SNR threshold under which the spectral order is rejected",
        ),
        MAX_ORDER_REJECTION=UserParam(
            50,
            constraint=ValueInInterval((0, 100)),
            description="Maximum percentage of orders that a Frame can reject before being considered invalid",
        ),
        bypass_ST_designation=UserParam(default_value=None, constraint=ValueFromIterable((None, "S2D", "S1D"))),
        IS_SA_CORRECTED=UserParam(
            False,
            constraint=BooleanValue,
            description=(
                "Indicates if the SA correction is already accounted in the BERV."
                " By default False, as the majority of instruments do not have it included in their BERV calculation"
            ),
        ),
        REJECT_NEGATIVE_FLUXES=UserParam(
            True,
            constraint=BooleanValue,
            description="Reject any flux value that falls below zero. Default: True",
        ),
        SIGMA_CLIP_FLUX_VALUES=UserParam(
            -1,
            constraint=NumericValue,
            description="Sigma clip the flux values. Disabled if the value is -1 (the default),"
            " as it is scarcely needed and we have outlier detection on the RV extraction",
        ),
        USE_APPROX_BERV_CORRECTION=UserParam(
            False,
            constraint=BooleanValue,
            description="Use the approximated BERV correction",
        ),
    )

    order_intervals: dict[DETECTOR_DEFINITION, list[int]] = {
        DETECTOR_DEFINITION.WHITE_LIGHT: [],
        DETECTOR_DEFINITION.RED_DET: [],
        DETECTOR_DEFINITION.BLUE_DET: [],
    }

    def __init__(
        self,
        inst_name: str,
        array_size: Dict[str, tuple],
        file_path: Path,
        frameID: int,
        KW_map: Dict[str, str],
        available_indicators: tuple,
        user_configs: Optional[Dict[str, Any]] = None,
        reject_subInstruments: Optional[Iterable[str]] = None,
        need_external_data_load: bool = False,
        init_log: bool = True,
        quiet_user_params: bool = True,
    ):
        """Init for all instruments.

        The Frame object is initialized with the following set of Keywords:

        Parameters
        ----------
        inst_name
            Name of the instrument
        array_size
            Size of the data that will be loaded from disk. Follow the format [Number order, Number pixels]
        file_path
            Path to the file that is going to be opened
        frameID
            Numerical value that represents the frame's ID inside the :class:`~ASTRAdata_objects.DataClass.DataClass`
        KW_map
            Dictionary where the keys are names of internal Keywords and the values represent the keyword name on the
            header of the .fits files
        available_indicators
            Names of available activity indicators for the instrument
        user_configs
            User configs information to be loaded in the parent class
        reject_subInstruments
            List of subInstruments to completely reject
        need_external_data_load
            True if the instrument must load data from a file that is not the one specified on the "file_path" argument
        use_approximated_BERV_correction
            If True, uses the approximated berv_factor
        init_log
            If True create a log entry with the filename
        quiet_user_params
            If True, there are no logs for the generation of the user parameters of each Frame

        """
        user_configs: dict = {} if user_configs is None else user_configs
        self.instrument_properties = {
            "name": inst_name,
            "array_sizes": array_size,
            "array_size": None,
            "wavelength_coverage": (),
            "resolution": None,
            "EarthLocation": None,
            "site_pressure": None,  # pressure in hPa
            "is_drift_corrected": None,  # True if the S2D files are already corrected from the drift
        }

        self.frameID = frameID
        self._status = Status()  # BY DEFAULT IT IS A VALID ONE!

        if not isinstance(file_path, (str, Path)):
            raise custom_exceptions.InvalidConfiguration("Invalid path!")

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        self.file_path: Path = file_path
        if init_log:
            logger.info(f"Creating frame from: {self.file_path}")
        self.inst_name = inst_name

        self.sub_instrument = None

        self.available_indicators = available_indicators

        self._KW_map = KW_map
        if "UseMolecfit" in user_configs:
            self.spectral_format = "S1D"
        elif "bypass_ST_designation" in user_configs:
            self.spectral_format = user_configs["bypass_ST_designation"]
        else:
            self.spectral_format = self.get_spectral_type()
        self.instrument_properties["array_size"] = self.instrument_properties["array_sizes"][self.spectral_format]
        self.array_size = self.instrument_properties["array_size"]
        super().__init__(user_configs=user_configs, quiet_user_params=quiet_user_params)

        self.use_approximated_BERV_correction = self._internal_configs["USE_APPROX_BERV_CORRECTION"]

        # stores the information loaded from the header of the S2D files. THis dict will be the default values in case
        # the instrument does not support them!
        # orderwise SNRs OR values with units -> should not be passed inside the KW_map!!!
        self.observation_info = {
            "BERV": np.nan * kilometer_second,
            # THE BERV value on the ESPRESSO pipeline is not fully correct on BERV, so we need to propagate
            # the BERV factor. As such, it will be a common property to all frames. Default value of None, so
            # that we can ensure that it is properly computed when used
            "BERV_FACTOR": None,
            "previous_SBART_RV": np.nan * kilometer_second,
            "previous_SBART_RV_ERR": np.nan * kilometer_second,
            "DRS_CCF_MASK": "",
            "DRS_FLUX_CORRECTION_TEMPLATE": "",
            "DRS_RV": np.nan * kilometer_second,
            "DRS_RV_ERR": np.nan * kilometer_second,
            "drift": np.nan * kilometer_second,
            "drift_ERR": np.nan * kilometer_second,
            "relative_humidity": np.nan,  # for telfit
            "ambient_temperature": np.nan,  # for telfit
            "airmass": np.nan,
            "orderwise_SNRs": [],
            "OBJECT": None,
            "MAX_BERV": 35 * kilometer_second,
            "BJD": None,
            "MJD": None,
            "DRS-VERSION": None,
            "MD5-CHECK": None,
            "ISO-DATE": None,
            "CONTRAST": 0,
            "CONTRAST_ERR": 0,
            "FWHM": 0,  # Store this as km/s
            "FWHM_ERR": 0,  # Store this as km/s
            "BIS SPAN": 0,  # Store this as km/s
            "BIS SPAN_ERR": 0,  # Store this as km/s
            "EXPTIME": 0,
            "RA": None,
            "DEC": None,
            "SPEC_TYPE": "None",  # This keyword is simply loading the CCF mask...
            "DET_BINX": None,
            "DET_BINY": None,
            "seeing": None,
            "MOON PHASE": 0,
            "MOON DISTANCE": 0,
            "INS MODE": "None",
            "INS NAME": "None",
            "PROG ID": "None",
            "DATE_NIGHT": "None",
        }

        # Used to allow to reject a wavelength region from one order and keep any overlap that might exist on others
        self._orderwise_wavelength_rejection: Optional[Dict[int, List]] = None

        self.load_header_info()
        # list of lists Each entry will be a pair of Reason: list<[<start, end>]> wavelenghts. When the S2D array is
        # opened, these elements will be used to mask spectral regions

        # TODO: understand why the typing error goes away when we use dict() instead of {}
        self.wavelengths_to_remove: Dict[Flag, List[List[int]]] = {}

        # Store here the wavelength limits for each order (if we want to impose them)!
        self.wavelengths_to_keep = None

        if reject_subInstruments is not None:
            for bad_subInst in reject_subInstruments:
                if self.is_SubInstrument(bad_subInst):
                    self.add_to_status(MISSING_DATA("Rejected entire subInstrument"))
                    logger.warning("Rejecting subInstruments")

        if need_external_data_load:
            self.add_to_status(LOADING_EXTERNAL_DATA)

        self._header: Optional[fits.Header] = None
        if "skysub" in self.file_path.stem:
            self.is_skysub = True

    def get_spectral_type(self) -> str:
        """Check the filename to see if we are using an S1D or S2D file.

        Raises:
            custom_exceptions.InternalError: If it is not possible to recognize the filename

        Returns:
            str: S1D or S2D

        """
        name_lowercase = self.file_path.stem.lower()
        if "s2d" in name_lowercase or "e2ds" in name_lowercase:
            return "S2D"
        if "s1d" in name_lowercase:
            return "S1D"
        raise custom_exceptions.InternalError(f"{self.name} can't recognize the file that it received!")

    def copy_into_S2D(self, new_S2D_size: Optional[Tuple[int, int]] = None) -> Frame:
        """Return a new object which contains the S1D that that has been converted into a S2D.

        Args:
            new_S2D_size (Optional[Tuple[int, int]], optional): Size of the new S2D size, should be a tuple with two
            elements: (number orders, pixel in order). If it is None, then uses the standard size of S2D files of this
            instrument. Defaults to None.

        Raises:
            custom_exceptions.InvalidConfiguration: If it is already in S2D format

        Returns:
            Frame: new Frame

        """
        if self.is_S2D:
            raise custom_exceptions.InvalidConfiguration("Can't transform S2D file into S2D file")
        logger.warning("Creating a copy of a S1D Frame for transformation into S2D")

        og_shape = self.instrument_properties["array_sizes"]["S2D"] if new_S2D_size is None else new_S2D_size

        reconstructed_S2D = np.zeros(og_shape)
        reconstructed_wavelengths = np.zeros(og_shape)
        reconstructed_uncertainties = np.zeros(og_shape)

        order_number = 0
        order_size = reconstructed_wavelengths[0].size
        to_break = False
        wavelengths, flux, uncertainties, _ = self.get_data_from_full_spectrum()
        wavelengths = wavelengths[0]
        flux = flux[0]
        uncertainties = uncertainties[0]

        while not to_break:
            start_order = order_size * order_number
            end_order = start_order + order_size
            if end_order >= wavelengths.size:
                to_break = True
                end_order = wavelengths.size

            slice_size = end_order - start_order
            reconstructed_wavelengths[order_number] = np.pad(
                wavelengths[start_order:end_order],
                (0, order_size - slice_size),
                constant_values=0,
            )
            reconstructed_S2D[order_number] = np.pad(
                flux[start_order:end_order],
                (0, order_size - slice_size),
                constant_values=0,
            )
            reconstructed_uncertainties[order_number] = np.pad(
                uncertainties[start_order:end_order],
                (0, order_size - slice_size),
                constant_values=0,
            )
            order_number += 1

        # The "new" orders that don't have any information will have a flux of zero. Thus, they will be deemed to
        # be invalid during the mask creation process (that is re-launched after this routine is done)

        # Ensure that we don't lose information due to the SNR cut
        user_configs = self._internal_configs._user_configs
        user_configs["minimum_order_SNR"] = 0

        inst_properties = self.instrument_properties["array_sizes"]
        if new_S2D_size is not None:
            inst_properties["S2D"] = new_S2D_size

        new_frame = Frame(
            inst_name=self.inst_name,
            array_size=inst_properties,
            file_path=self.file_path,
            frameID=self.frameID,
            KW_map=self._KW_map,
            available_indicators=self.available_indicators,
            user_configs=self._internal_configs._user_configs,
        )
        new_frame.wavelengths = reconstructed_wavelengths
        new_frame.spectra = reconstructed_S2D
        new_frame.uncertainties = reconstructed_uncertainties
        for key in ["observation_info", "instrument_properties"]:
            setattr(new_frame, key, getattr(self, key))

        new_frame._spectrum_has_data_on_memory = True  # to avoid new data loads!
        new_frame._never_close = True  # ensure that we don't lose the transformation
        new_frame.spectral_format = "S2D"
        new_frame.instrument_properties["array_size"] = new_S2D_size
        new_frame.array_size = new_S2D_size
        new_frame.sub_instrument = self.sub_instrument
        new_frame.is_blaze_corrected = self.is_blaze_corrected
        new_frame.observation_info["orderwise_SNRs"] = [1 for _ in range(new_S2D_size[0])]
        new_frame.regenerate_order_status()
        return new_frame

    def import_KW_from_outside(self, KW: str, value: Any, optional: bool) -> None:
        """Allow to manually override header parameters (in memory) from the outside.

        This can be used if an instrument has data stored in multiple files. This allows a post-setup
        update of header values (for the keywords stored in observation_info)

        Args:
            KW (str): keyword name, as defined by the Frame interface
            value (Any): New value
            optional (bool): if it is optional, it can be a non-finite value

        Raises:
            FrameError: If we attempt to load a optional=False keyword that has a non-finite value

        """
        if KW not in self.observation_info:
            logger.critical(
                "Keyword <{}> is not supported by the Frames. Couldn't load it from the outside",
                KW,
            )

        if not np.isfinite(value):
            if not optional:
                logger.critical(
                    "Loaded mandatory keyword <{}> with a non-finite value for frame {}",
                    KW,
                    self.fname,
                )
                raise FrameError
            logger.critical(
                "Loaded keyword <{}> has a non-finite value for frame {}",
                KW,
                self.fname,
            )
        self.observation_info[KW] = value

    def reject_wavelength_region_from_order(self, order: int, region: list[tuple[int, int]]) -> None:
        """Flag a wavelength region from specific order to be marked as invalid during the creation of the stellar mask.

        This will not account for order overlaps.

        Args:
            order (_type_): _description_
            region (_type_): _description_

        Raises:
            custom_exceptions.InvalidConfiguration:

        """
        if not isinstance(region, (Iterable,)):
            raise custom_exceptions.InvalidConfiguration("The rejection region must be a list of lists")

        if self._orderwise_wavelength_rejection is None:
            self._orderwise_wavelength_rejection = {}
        self._orderwise_wavelength_rejection[order] = region

    def mark_wavelength_region(self, reason: Flag, wavelength_blocks: list[tuple[int, int]]) -> None:
        """Add wavelength regions to be removed whenever the S2D file is opened.

        When rejecting wavelengths through this function, we only have to specify wavelength intervels, allowing
        to account for possible order overlap. When loading the Frame, we search through all orders to find any
        occurence of this wavelength blocks.

        Parameters
        ----------
        reason : Flag
            Flag for the removal type
        wavelength_blocks : list[tuple[int, int]]
            List with lists of wavelength limits. [[lambda_0, lambda_1], [lambda_2, lambda_3]] to reject.z\

        """
        self.wavelengths_to_remove[reason] = wavelength_blocks

    def select_wavelength_region(self, order: int, wavelength_blocks: list[tuple[int, int]]) -> None:
        """Reject all wavelengths that are not part of the provided intervals.

        Args:
            order (int): Spectral order
            wavelength_blocks (list[list[int]]): List of tuples, each containing wavelength of start and end
            of each "good" interval

        """
        if self.wavelengths_to_keep is None:
            self.wavelengths_to_keep = {}
        self.wavelengths_to_keep[order] = wavelength_blocks

    def finalize_data_load(self, bad_flag: Optional[Flag] = None) -> None:
        """Run for all Instruments, even those that do not need an external data load.

        Checks if the non-fatal Flag "LOADING_EXTERNAL_DATA" exists in the Status.
        If so, add the fatal Flag "MISSING_EXTERNAL_DATA". Otherwise, does nothing

        """
        if self._status.has_flag(LOADING_EXTERNAL_DATA):
            logger.critical(f"Frame {self.name} did not load the external data that it needed!")

            self._status.delete_flag(LOADING_EXTERNAL_DATA)
            if bad_flag is None:
                self.add_to_status(MISSING_EXTERNAL_DATA)
            else:
                self.add_to_status(bad_flag)

    def finalized_external_data_load(self) -> None:
        """Mark frame after everything is loaded into memory.

        The frames that need external data will have a Flag of "LOADING_EXTERNAL_DATA" that will translate into a
        rejection of the Frame (if it is not removed).

        This call will remove that flag from Status and sinalizes that this Frame managed to load everything that
        it needed
        """
        if not self.is_valid:
            logger.warning("Finalizing external data loading for Frame that was already rejected.")
        else:
            self._status.delete_flag(LOADING_EXTERNAL_DATA)

    def add_to_status(self, new_flag: Flag) -> None:
        """Add a new Flag to the Status of this Frame."""
        logger.debug("Updating Frame ({}) status to {}", self.fname, new_flag)

        super().add_to_status(new_flag=new_flag)

        if not self.is_valid:
            self.close_arrays()

    def _data_access_checks(self) -> None:
        super()._data_access_checks()
        if not self.is_open:
            self.load_data()

    @property
    def status(self) -> Status:
        """Return the Status of the entire Frame."""
        return self._status

    @property
    def is_SA_corrected(self) -> bool:
        """Check if the frame was corrected from secular acceleration."""
        return self._internal_configs["IS_SA_CORRECTED"]

    ###################################
    #          Cleaning data          #
    ###################################

    def build_mask(self, bypass_QualCheck: bool = False, assess_bad_orders: bool = True) -> None:
        """Build a pixel-wise mask for rejection purposes.

        Args:
            bypass_QualCheck (bool, optional): If True, Bypass using the QUAL_DATA from the DRS. Defaults to False.
            assess_bad_orders (bool, optional): if True, reject entire spectral orders based on the assess_bad_orders()
                This can be used if we want to run more pixel-rejection methods before we evaluate bad orders.
            Defaults to True.

        """
        self.spectral_mask = Mask(initial_mask=np.zeros(self.instrument_properties["array_size"], dtype=np.uint16))
        if not bypass_QualCheck:
            zero_indexes = np.where(self.qual_data != 0)
            self.spectral_mask.add_indexes_to_mask(zero_indexes, QUAL_DATA)

        self.spectral_mask.add_indexes_to_mask(np.where(~np.isfinite(self.spectra)), MISSING_DATA)
        self.spectral_mask.add_indexes_to_mask(np.where(self.spectra == 0), MISSING_DATA)

        if self._internal_configs["REJECT_NEGATIVE_FLUXES"]:
            self.spectral_mask.add_indexes_to_mask(np.where(self.spectra < 0), MISSING_DATA)

        self.spectral_mask.add_indexes_to_mask(np.where(self.uncertainties == 0), MISSING_DATA)
        self.spectral_mask.add_indexes_to_mask(np.where(~np.isfinite(self.uncertainties)), MISSING_DATA)

        order_map = {i: (np.min(self.wavelengths[i]), np.max(self.wavelengths[i])) for i in range(self.N_orders)}
        removal_reasons = [i.name for i in self.wavelengths_to_remove.keys()]
        N_point_removed = []
        time_took = []

        logger.debug(f"Cleaning wavelength regions from {removal_reasons}")

        for removal_reason, wavelengths in self.wavelengths_to_remove.items():
            start_time = time.time()
            nrem = len(wavelengths)

            N_point_removed.append(nrem)
            for wave_pair in wavelengths:
                for order in range(self.N_orders):
                    if check_if_overlap(wave_pair, order_map[order]):
                        indexes = np.where(
                            np.logical_and(
                                self.wavelengths[order] >= wave_pair[0],
                                self.wavelengths[order] <= wave_pair[1],
                            ),
                        )
                        self.spectral_mask.add_indexes_to_mask_order(order, indexes, removal_reason)
            time_took.append(time.time() - start_time)
        logger.debug(
            "Removed {} regions ({})",
            sum(N_point_removed),
            " + ".join(map(str, N_point_removed)),
        )

        if self._internal_configs["SIGMA_CLIP_FLUX_VALUES"] > 0:
            logger.info("Sigma-clipping on flux is activated. Running rejection procedure")
            median_level = np.median(self.spectra, axis=1)
            threshold = (
                self._internal_configs["SIGMA_CLIP_FLUX_VALUES"] * self.uncertainties + median_level[:, np.newaxis]
            )
            self.spectral_mask.add_indexes_to_mask(np.where(self.spectra > threshold), MISSING_DATA)

        if self._orderwise_wavelength_rejection is not None:
            logger.info("Rejecting spectral chunks from individual orders")
            for order, region in self._orderwise_wavelength_rejection.items():
                for subregion in region:
                    indexes = np.where(
                        np.logical_and(
                            self.wavelengths[order] >= subregion[0],
                            self.wavelengths[order] <= subregion[1],
                        ),
                    )
                    self.spectral_mask.add_indexes_to_mask_order(order, indexes, NON_COMMON_WAVELENGTH)

        logger.debug("Ensuring that we have increasing wavelengths")

        diffs = np.where(np.diff(self.wavelengths, axis=1) < 0)
        if diffs[0].size > 0:
            logger.warning("Found non-increasing wavelengths on {}", self.name)
            self.spectral_mask.add_indexes_to_mask(diffs, QUAL_DATA("Non-increasing wavelengths"))
        logger.debug("Took {} seconds ({})", sum(time_took), " + ".join(map(str, time_took)))

        if assess_bad_orders:
            self.assess_bad_orders()

        if self.wavelengths_to_keep is not None:
            logger.info("Provided desired wavelength region. Rejecting regions outside it")
            for order in range(self.N_orders):
                good_regions = self.wavelengths_to_keep[order]
                if len(good_regions) == 0:  # TODO: ensure that the order is also rejected
                    continue

                inds = np.zeros(self.wavelengths[order].size, dtype=bool)
                for region in good_regions:
                    wavelengths_to_keep = np.where(
                        np.logical_and(
                            self.wavelengths[order] >= region[0],
                            self.wavelengths[order] <= region[1],
                        ),
                    )
                    inds[wavelengths_to_keep] = True
                self.spectral_mask.add_indexes_to_mask_order(order, np.where(~inds), NON_COMMON_WAVELENGTH)

    def assess_bad_orders(self) -> None:
        """Evaluate the orders and Frames that can be fully rejected.

        Goals:
        1) Check if any order rejects more than *reject_order_percentage* % of the pixels. If so, rejects it
        2) Apply SNR cut of *minimum_order_SNR*
        3) if a Frame rejects more than *MAX_ORDER_REJECTION * % of all orders, it is rejected from the analysis.

        """
        # True in the points to mask
        logger.debug("Rejecting spectral orders")

        if self.spectral_mask is not None:
            entire_mask = self.spectral_mask.get_custom_mask()

            for order, value in enumerate(entire_mask):
                # See if the total amounf of rejected points is larger than
                # 1 - reject_order-percentage of the entire order
                perc = self._internal_configs["reject_order_percentage"]
                if np.sum(value) > (1 - perc) * self.pixels_per_order:
                    self._OrderStatus.add_flag_to_order(order, HIGH_CONTAMINATION("Rejection threshold met in order"))

        if len(self.bad_orders) > 0:
            logger.debug(
                "Frame {} rejected {} orders due for having less than {} valid pixels: {}",
                self.frameID,
                len(self.bad_orders),
                self._internal_configs["reject_order_percentage"],
                ranges(list(self.bad_orders)),
            )

        if self.is_S2D:  # we don't have the SNR for the S1D file!
            bad_SNR = []
            SNRS = self.get_KW_value("orderwise_SNRs")
            for order in range(self.N_orders):
                if SNRS[order] < self._internal_configs["minimum_order_SNR"]:
                    self._OrderStatus.add_flag_to_order(order, LOW_SNR("Minimum SNR not met in order"))
                    bad_SNR.append(order)

            if len(bad_SNR) > 0:
                logger.info(
                    "Frame {} rejected {} orders for having SNR smaller than {}: {}",
                    self.frameID,
                    len(bad_SNR),
                    self._internal_configs["minimum_order_SNR"],
                    ranges(bad_SNR),
                )

        if len(self.bad_orders) >= self._internal_configs["MAX_ORDER_REJECTION"] * self.N_orders / 100:
            logger.warning(
                "Frame {} is rejecting more than {} % of the spectral orders",
                self,
                self._internal_configs["MAX_ORDER_REJECTION"],
            )
            self.add_to_status(
                NO_VALID_ORDERS(
                    f" Rejected more than {self._internal_configs['MAX_ORDER_REJECTION']} % of spectral orders",
                ),
            )

    ####################################
    #      Sanity Checks               #
    ####################################
    def check_header_QC(self, header: fits.header.Header) -> None:
        """Check if the header keywords are in accordance with their default value.

        Each instrument should do this check on its own

        This function will check for two things:
        1. Fatal keywords - will mark the Frame as invalid
        2. Warning Keywords - the frame is still valid, but it has a warning issued in the logs

        If any of those conditions is met, make sure that the flags meet the following naming conditions
        (so that we can filter by them later on):

        For fatal flags
        ```
        msg = f"QC flag {flag} has taken the bad value of {bad_value}"
        self.add_to_status(FATAL_KW(msg))
        ```

        For warnings:
        ```
        msg = f"QC flag {flag} meets the bad value"
        self._status.store_warning(KW_WARNING(msg))
        ```
        """

    def find_instrument_type(self) -> None:
        """Compare the date of observation with pre-defined sub-Instruments to see where it fits."""
        obs_date = self.get_KW_value("ISO-DATE")
        obs_date = "-".join(obs_date.split("T")).split(":")[0]
        obs_date = datetime.datetime.strptime(obs_date, r"%Y-%m-%d-%H")

        for key, threshold in self.__class__.sub_instruments.items():
            # If it is not higher tha  the threshold, then it beleongs in this "interval"
            if not obs_date > threshold:
                self.sub_instrument = key
                break
        else:
            raise custom_exceptions.InternalError("no sub-instrument found for observation")

    #####################################
    #      Handle data management      #
    ####################################
    def get_S1D_name(self) -> str:
        """Build the S1D name that should be associated with this Frame.

        If it is already a S1D, returns the actual name.
        If it is not, remove "blaze" from the filename and replaces "S2D" with "S1D"

        """
        # TODO: this will not work for non-ESPRESSO files

        if self.is_S1D:
            return self.fname
        name = self.fname
        return name.replace("BLAZE_", "").replace("S2D", "S1D")

    def load_data(self) -> None:
        """Abstraction to load all data of this Frame.

        If the Frame is already open, it does nothing.
        Calls the S1D or S2D version of the data load, depending on file type
        Can remove BERV correction at run time, if properly configured to do so.

        Raises:
            custom_exceptions.InternalError: If it is neither S2D or S1D
            FrameError: If the frame is no longer valid after loading

        """
        if self.is_open:
            return

        if self.is_S1D:
            self.load_S1D_data()
        elif self.is_S2D:
            self.load_S2D_data()
        else:
            raise custom_exceptions.InternalError("something went wrong on this frame")

        if not self.is_valid:
            raise FrameError("Frame is no longer valid")

        BERV_value = self.get_KW_value("BERV")

        if not self._internal_configs["open_without_BervCorr"]:
            self.apply_BERV_correction(BERV_value)
        else:
            logger.warning(f"Opening {self.name} without the BERV correction")
            self.remove_BERV_correction(BERV_value)

    def load_S1D_data(self) -> None:
        """To be overriden by the children classes."""
        logger.debug("Opening the S1D arrays from {}", self.fname)
        if not self.is_valid:
            raise FrameError
        self._spectrum_has_data_on_memory = True

    def load_S2D_data(self) -> None:
        """To be overriden by the children classes."""
        logger.debug("Opening the S2D arrays from {}", self.fname)
        if not self.is_valid:
            raise FrameError
        self._spectrum_has_data_on_memory = True

    def load_instrument_specific_KWs(self, header: Mapping[str, Any]) -> None:
        """Load instrument-specific KW values that can't be loaded in a general fashion.

        To be overriden by the different instruments

        Args:
            header (Mapping[str, Any]): header unit of this observation

        """

    def load_header_info(self) -> None:
        """Open the header of the fits file and load the necessary keywords.

        Does the following operations:
        1) Load header assuming fits file
        2) Parse through the _KW_map to load header keywords
        3) Call self.load_instrument_specific_KWs
        4) Call check_header_QC(hdu)
        5) Call find_instrument_type()
        6) Call assess_bad_orders()

        """
        try:
            hdu = fits.getheader(self.file_path)
        except FileNotFoundError:
            msg = f"File <{self.file_path}> does not exist"
            self.add_to_status(MISSING_FILE(msg))
            logger.critical(msg)
            return

        for internal_KW, S2D_KW in self._KW_map.items():
            self.observation_info[internal_KW] = hdu[S2D_KW]

        self.load_instrument_specific_KWs(hdu)
        self.check_header_QC(hdu)
        self.find_instrument_type()
        self.assess_bad_orders()

    ####################################
    #       Access data
    ####################################

    def get_KW_value(self, KW: str) -> Any:
        """Get a given KW value that is defined in the common framework."""
        return self.observation_info[KW]

    def get_header_value(self, kw: str) -> Any:
        """Directly retrieves a KW from the header.

        After this is called, the frame will keep the header stored in memory until the object is deleted

        Args:
            kw (str): Keyword name, present in the fits header

        Returns:
            Any: Header value

        """
        if self._header is None:
            self._header = fits.getheader(self.file_path)
        return self._header[kw]

    ####################################
    #       properties of the Frames
    ####################################

    @property
    def is_S1D(self) -> bool:
        """Check if Frame is of S1D format."""
        return self.spectral_format == "S1D"

    @property
    def is_S2D(self) -> bool:
        """Check if Frame is of S2D format."""
        return self.spectral_format == "S2D"

    @property
    def has_warnings(self) -> bool:
        """Check if Frame has any warnings."""
        return self._status.has_warnings

    def is_Instrument(self, Instrument: str) -> bool:
        """Check if Frame is from a given instrument."""
        return self.inst_name == Instrument

    def is_SubInstrument(self, sub_instrument: str) -> bool:
        """Check if the current instrument is from the given time_block (e.g ESPRESSO18/ESPRESSO19).

        Parameters
        ----------
        sub_instrument : str
            Name of the time block that is going to be checked

        Returns
        -------
        [bool]
            Results from the comparison

        """
        return self.sub_instrument == sub_instrument

    @property
    def previous_RV_measurements(self) -> tuple[RV_measurement, RV_measurement]:
        """Get previous DRS RV and uncertainty."""
        return self.get_KW_value("DRS_RV"), self.get_KW_value("DRS_RV_ERR")

    @property
    def bare_fname(self) -> str:
        """Returns the file name without the _S2D (and similar) parts.

        The children classes must overload this property. Otherwise, returns the full filename
        """
        return self.fname

    @property
    def fname(self) -> str:
        """Get filename."""
        return self.file_path.name

    @property
    def min_pixel_in_order(self) -> int:
        """Minimum number of pixels in order to be a valid one."""
        return self._internal_configs["reject_order_percentage"] * self.pixels_per_order

    @property
    def spectrum_information(self) -> dict[str, Any]:
        """Get general instrument and spectra information."""
        return {
            "subInstrument": self.sub_instrument,
            "filename": self.bare_fname,
            "is_S2D": self.is_S2D,
            "is_S1D": self.is_S1D,
            **super().spectrum_information,
        }

    def __repr__(self) -> str:  # noqa: D105
        return self.__str__()

    def __str__(self) -> str:  # noqa: D105
        return (
            f"Frame of {self.inst_name} : {self.sub_instrument}"
            f" data ({self.get_KW_value('ISO-DATE')}; ID = {self.frameID})"
        )

    def plot_spectra(
        self,
        which_orders: None | DETECTOR_DEFINITION | list[int] = None,
        axis=None,
    ):
        """Plot the spectra.

        Args:
            which_orders (None | DETECTOR_DEFINITION | list[int], optional): Either a pre-configured
            detector definition, a list of orders, or None (plots all orders). Defaults to None.
            axis (_type_, optional): if None, create a new figure. Otherwise, use this one. Defaults to None.

        """
        fig = None
        if axis is None:
            fig, axis = plt.subplots()
        wf, ff, ef, mf = self.get_data_from_full_spectrum()

        if which_orders is None:
            which_orders = DETECTOR_DEFINITION.WHITE_LIGHT

        if isinstance(which_orders, (list, tuple)):
            orders_to_plot = which_orders
        else:
            orders_to_plot = self.order_intervals[which_orders]

        for sl in orders_to_plot:
            w, f, e, m = wf[sl], ff[sl], ef[sl], mf[sl]
            axis.errorbar(w[~m], f[~m], e[~m], ls="", marker="x")

        return fig, axis

    def trigger_data_storage(self, *args, **kwargs):
        super().trigger_data_storage(*args, **kwargs)
