import pickle
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import NoReturn

import matplotlib.pyplot as plt
import numpy as np
from loguru import logger
from scipy.interpolate import CubicSpline

from ASTRA.spectral_normalization.normalization_base import NormalizationBase
from ASTRA.utils import custom_exceptions
from ASTRA.utils.parameter_validators import PathValue
from ASTRA.utils.UserConfigs import DefaultValues, UserParam

try:
    from SNT import normalize_spectra

    SNT_AVAILABLE = True
except ImportError:
    SNT_AVAILABLE = False


class SNT_normalization(NormalizationBase):
    """Uses SNT to normalize the stellar spectra.

    **Description:**

    Works with either S1D or S2D spectra, with a different behaviour on both cases:

    1) With S1D data:
        - Simple division of the stellar spectra with the continuum model. The continuum is interpolated (cubic spline)
    2) With S2D data:
        - Loads the S1D file from disk, applying the process from 1). Then, it divides the S1D spectra in
         chunks of "N_{order}" pixels to recreate a S2D spectra. This will re-trigger all the order masking
         procedures and remove all previous rejections

    **Name of the normalizer**: SNT

    **User parameters:**

    ====================== ================ ================ ======================== ================
    Parameter name             Mandatory      Default Value    Valid Values                Comment
    ====================== ================ ================ ======================== ================
        S1D_folder          False               ---             str, Path               [1]
    ====================== ================ ================ ======================== ================


    Notes:
        [1] Folder in which the S1D files will be stored (if the input is a S2D spectra)

        [2] Also check the **User parameters** of the parent classes for further customization options of SBART


    """

    _default_params = NormalizationBase._default_params + DefaultValues(
        S1D_folder=UserParam(mandatory=False, constraint=PathValue, default_value=""),
    )

    _name = "SNT"

    orderwise_application = False

    def __init__(self, obj_info, user_configs):
        super().__init__(
            obj_info=obj_info,
            user_configs=user_configs,
            needed_folders={
                "SNT_OUT": "_Storage/SpecNorm/SNT/outputs",
            },
        )
        if obj_info["is_S2D"]:
            raise custom_exceptions.InvalidConfiguration("S2D normalization not supported for now")
            # raise custom_exceptions.InvalidConfiguration("Must provide the S1D folder when using S2D files")

    def _get_S1D_data(self, wavelengths, flux, uncertainties):
        if self._spec_info["is_S2D"]:
            S1D_path = self._internal_configs["S1D_folder"] / self._spec_info["S1D_name"]
            temp_configs = deepcopy(self._internal_configs.get_user_configs())
            temp_configs["spectra_format"] = "S1D"
            # open a temporary frame to retrieve the S1D data!
            new_frame = self._spec_info["Frame_instance"](
                file_path=S1D_path,
                user_configs=temp_configs,
            )
            (
                wavelengths,
                flux,
                uncertainties,
                _,
            ) = new_frame.get_data_from_full_spectrum()

        return (
            wavelengths[0],
            flux[0],
            uncertainties[0],
        )  # the S1D file is considered to be a very "large" order

    def run_SNT(self, wavelengths, flux, uncertainties, output_path, fname):
        if not SNT_AVAILABLE:
            raise custom_exceptions.InternalError("SNT is not installed")

        logger.info("Launching SNT")
        continuum = normalize_spectra(
            wavelengths=wavelengths,
            spectra=flux,
            header={},
            FWHM_override=self._spec_info["FWHM"],
            output_path=output_path,
            user_config={"parallel_orders": False, "Ncores": 1, "run_plot_generation": False},
            fname=fname,
        )
        logger.info("SNT has finished running")

    def _fit_epochwise_normalization(self, wavelengths, flux, uncertainties):
        super()._fit_epochwise_normalization(wavelengths, flux, uncertainties)

        filename = self._spec_info["S1D_name"].replace(".fits", "")
        output_path = self._internalPaths.get_path_to("SNT_OUT", as_posix=False)

        self.run_SNT(wavelengths, flux, uncertainties, output_path=output_path, fname=filename)

        # TODO: missing the parameters that will be cached!
        params_to_store = {"SNT_OUT_FOLDER": output_path.as_posix()}

        return (
            *self._apply_epoch_normalization(wavelengths, flux, uncertainties, **params_to_store),
            params_to_store,
        )

    def _apply_epoch_normalization(self, wavelengths, flux, uncertainties, **kwargs):
        super()._apply_epoch_normalization(wavelengths, flux, uncertainties, **kwargs)
        logger.info("Applying normalization to epoch!")

        wavelengths, flux, uncertainties = self._get_S1D_data(wavelengths, flux, uncertainties)

        # TODO: think about SNR problems that might arise within SBART if this goes through without adding an offset
        filename = self._spec_info["S1D_name"].replace(".fits", "")
        SNT_out_path = Path(kwargs["SNT_OUT_FOLDER"]) / "SNT_data" / f"{filename}_continuum.txt"
        snt_prod = np.loadtxt(SNT_out_path, delimiter=",")

        good_inds = np.where(np.isfinite(snt_prod[:, 1]))
        CSplineInterpolator = CubicSpline(snt_prod[:, 0][good_inds], snt_prod[:, 1][good_inds])
        cont_solution = CSplineInterpolator(wavelengths)

        # Ensure that we are not interpolating outside the grid!
        # In principle, this should not be a problem, as the grid **should** be large enough to
        # contain the entire wavelength solution
        cont_solution[
            np.logical_or(
                wavelengths < snt_prod[:, 0],
                wavelengths > snt_prod[:, 0],
            )
        ] = np.nan

        flux /= cont_solution
        uncertainties /= cont_solution

        return wavelengths, flux, uncertainties

    def _normalization_sanity_checks(self):
        # TODO: check this, maybe we will be limited to BLAZE-corrected spectra!
        logger.debug("{} does not apply any sanity check on the data!")
        if self._spec_info["is_S2D"]:
            raise custom_exceptions.InvalidConfiguration("Can't normalize S2D spectra")
