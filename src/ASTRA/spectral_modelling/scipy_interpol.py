"""Interpolate stellar spectra with scipy splines."""

from __future__ import annotations

from typing import NoReturn

import numpy as np
from scipy.interpolate import (
    CubicSpline,
    PchipInterpolator,
    RBFInterpolator,
    interp1d,
    Akima1DInterpolator,
    FloaterHormannInterpolator,
)

from ASTRA.spectral_modelling.modelling_base import ModellingBase
from ASTRA.utils import custom_exceptions
from ASTRA.utils.choices import INTERPOLATION_ERR_PROP, SPLINE_INTERPOL_MODE
from ASTRA.utils.Cubic_spline import CustomCubicSpline
from ASTRA.utils.parameter_validators import ValueFromIterable
from ASTRA.utils.UserConfigs import (
    DefaultValues,
    UserParam,
)


class ScipyInterpolSpecModel(ModellingBase):
    """Interpolate stellar spectra using scipy splines.

    **User parameters:**

    ============================ ================ ================ ======================== ================
    Parameter name                 Mandatory      Default Value    Valid Values                 Comment
    ============================ ================ ================ ======================== ================
    SPLINE_TYPE                     False           cubic            cubic/quadratic/pchip       Which spline
    INTERPOLATION_ERR_PROP          False           interpolation     [1]                       [2]
    NUMBER_WORKERS                  False           1                   Interger >= 0           [3]
    ============================ ================ ================ ======================== ================

    - [1] : One of interpolation / none / propagation
    - [2] - How the uncertainties are propagated through the spline interpolation
    - [3] - Number of workers to launch (this will happen for each core if [1] is propagation)
    *Note:* Also check the **User parameters** of the parent classes for further customization options of SBART

    """

    # TODO: confirm the kernels that we want to allow
    _default_params = ModellingBase._default_params + DefaultValues(
        SPLINE_TYPE=UserParam(
            SPLINE_INTERPOL_MODE.CUBIC_SPLINE,
            constraint=ValueFromIterable(SPLINE_INTERPOL_MODE),
        ),
        INTERPOLATION_ERR_PROP=UserParam(
            INTERPOLATION_ERR_PROP.interpolation,
            constraint=ValueFromIterable(INTERPOLATION_ERR_PROP),
        ),
    )

    def __init__(self, obj_info, user_configs):  # noqa: D107
        super().__init__(
            obj_info=obj_info,
            user_configs=user_configs,
        )

    def generate_model_from_order(self, order: int) -> None:
        """Override the parent implementation to make sure that nothing is done.

        (as there is no need to generate a pre-computed model)
        """
        return

    def _store_model_to_disk(self) -> None:
        """There is nothing to be stored.

        Overriding parent implementation to avoid issues
        """
        return

    def _internal_interpolation(
        self,
        og_lambda: np.ndarray,
        og_spectra: np.ndarray,
        og_err: np.ndarray,
        new_wavelengths: np.ndarray,
        order: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Interpolate the order of this spectrum to a given wavelength, using a spline.

        Args:
            og_lambda (np.ndarray): Original wavelength
            og_spectra (np.ndarray): Original spectra
            og_err (np.ndarray): Original flux uncertainties
            new_wavelengths (np.ndarray): New wavelength solution
            order (int): Not used, for compatibility purposes
            smooth_order (FLUX_SMOOTH_ORDER | None, optional): Control the order of operations between
                smoothing and interpolation
            apply_smooth (FLUX_SMOOTH_CONFIGS | None, optional): Not used, for compatibility purposes. Defaults to None.

        Raises:
            custom_exceptions.InvalidConfiguration: Can't recognize the provided configurations
            custom_exceptions.InvalidConfiguration: Trying to compute uncertainty propagation with non-cubic splines

        Returns:
            tuple[np.ndarray, np.ndarray]: New flux and new uncertainties

        """
        propagate_interpol_errors = self._internal_configs["INTERPOLATION_ERR_PROP"]

        interpolator_map = {
            SPLINE_INTERPOL_MODE.CUBIC_SPLINE: CubicSpline,
            SPLINE_INTERPOL_MODE.PCHIP: PchipInterpolator,
            SPLINE_INTERPOL_MODE.QUADRATIC_SPLINE: lambda x, y: interp1d(x, y, kind="quadratic"),
            SPLINE_INTERPOL_MODE.NEAREST: lambda x, y: interp1d(x, y, kind="nearest"),
            SPLINE_INTERPOL_MODE.RBF: lambda x, y: RBFInterpolator(x, y, kernel="cubic"),
            SPLINE_INTERPOL_MODE.AKIMA: Akima1DInterpolator,
            SPLINE_INTERPOL_MODE.BARYCENTRIC_INTERPOL: FloaterHormannInterpolator,
        }

        if propagate_interpol_errors == INTERPOLATION_ERR_PROP.propagation:
            # Custom Cubic spline routine!
            if self._internal_configs["SPLINE_TYPE"] != SPLINE_INTERPOL_MODE.CUBIC_SPLINE:
                raise custom_exceptions.InvalidConfiguration("Can't use non cubic-splines with propagation")
            CSplineInterpolator = CustomCubicSpline(
                og_lambda,
                og_spectra,
                og_err,
                n_threads=self._internal_configs["NUMBER_WORKERS"],
            )
            new_data, new_errors = CSplineInterpolator.interpolate(new_wavelengths)

        elif propagate_interpol_errors in [
            INTERPOLATION_ERR_PROP.interpolation,
            INTERPOLATION_ERR_PROP.none,
        ]:
            if self._internal_configs["SPLINE_TYPE"] == SPLINE_INTERPOL_MODE.CUBIC_SPLINE:
                extra = {"bc_type": "natural"}
            else:
                extra = {}

            if self._internal_configs["SPLINE_TYPE"] == SPLINE_INTERPOL_MODE.RBF:
                # RBF interpolation needs 2d arrays
                og_lambda = og_lambda[:, np.newaxis]
                og_spectra = og_spectra[:, np.newaxis]
                og_err = og_err[:, np.newaxis]
                new_wavelengths = new_wavelengths[:, np.newaxis]

            CSplineInterpolator = interpolator_map[self._internal_configs["SPLINE_TYPE"]](
                og_lambda,
                og_spectra,
                **extra,
            )
            new_data = CSplineInterpolator(new_wavelengths)

            if propagate_interpol_errors == INTERPOLATION_ERR_PROP.none:
                new_errors = np.zeros(new_data.shape)
            else:
                CSplineInterpolator = interpolator_map[self._internal_configs["SPLINE_TYPE"]](
                    og_lambda,
                    og_err,
                    **extra,
                )
                new_errors = CSplineInterpolator(new_wavelengths)
        else:
            raise custom_exceptions.InvalidConfiguration(f"How did we get {propagate_interpol_errors=}?")
        if self._internal_configs["SPLINE_TYPE"] == SPLINE_INTERPOL_MODE.RBF:
            new_data = new_data[:, 0]
            new_errors = new_errors[:, 0]
        return new_data, new_errors
