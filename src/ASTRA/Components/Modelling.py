"""Provide interfaces to interpolate spectra.

This class will control the interpolation of stellar spectra (and templates) to a new wavelength grid,
allowing for possible RV shifts before doing so. This provides a unified framework to ensure
that we can consistently interpolate stellar spectra and stellar models.

It will also control the smoothing before/after interpolation, by properly configuring the different
modelling interfaces that we have available.

"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

import numpy as np
from loguru import logger

from ASTRA.spectral_modelling import ScipyInterpolSpecModel
from ASTRA.utils import custom_exceptions
from ASTRA.utils.BASE import BASE
from ASTRA.utils.choices import (
    FLUX_SMOOTH_CONFIGS,
    FLUX_SMOOTH_ORDER,
    INTERPOLATION_ERR_PROP,
    SPECTRA_INTERPOL_MODE,
    SPLINE_INTERPOL_MODE,
)
from ASTRA.utils.parameter_validators import Positive_Value_Constraint, ValueFromIterable
from ASTRA.utils.shift_spectra import apply_RVshift, remove_RVshift
from ASTRA.utils.UserConfigs import DefaultValues, UserParam

if TYPE_CHECKING:
    from ASTRA.spectral_modelling.modelling_base import ModellingBase


class Spectral_Modelling(BASE):
    """Introduces, in a given object, the functionality to model and interpolate the stellar orders.

    In order to inherit from this class, it must also be a children of
    :class:`ASTRAComponents.SpectrumComponent.Spectrum`

    **User parameters:**

    ============================ ================ ================ ======================== ================
    Parameter name                 Mandatory      Default Value    Valid Values                 Comment
    ============================ ================ ================ ======================== ================
    INTERPOL_MODE                   False           splines         splines / GP / NN           [1]
    ============================ ================ ================ ======================== ================

    .. note::
        This flag will select which algorithm we will use to interpolate the spectra. Depending on the selection,
        we might want to pass extra-parameters, which can be set by passing a dictionary with the parameters
        defined in:
            - splines: :class:`ASTRAComponents.scipy_interpol.ScipyInterpolSpecModel`
            - GP: :class:`ASTRAComponents.GPSectralmodel.GPSpecModel`

        Those configuration are passed in different ways, depending on if we are dealing with Frames or
        a StellarModel object. The easy way to change them both is to call the following functions:
            -   DataClass.update_interpol_properties_of_all_frames
            -   DataClass.update_interpol_properties_of_stellar_model

    *Note:* Also check the **User parameters** of the parent classes for further customization options of SBART

    """

    # TODO: confirm the kernels that we want to allow
    _default_params = BASE._default_params + DefaultValues(
        INTERPOL_MODE=UserParam(
            SPECTRA_INTERPOL_MODE.SPLINES,
            constraint=ValueFromIterable(SPECTRA_INTERPOL_MODE),
        ),
        # We have to add this here, so that the parameters are not rejected by the config validation
        SPLINE_TYPE=UserParam(
            SPLINE_INTERPOL_MODE.CUBIC_SPLINE,
            constraint=ValueFromIterable(SPLINE_INTERPOL_MODE),
        ),
        INTERPOLATION_ERR_PROP=UserParam(
            INTERPOLATION_ERR_PROP.interpolation,
            constraint=ValueFromIterable(INTERPOLATION_ERR_PROP),
        ),
        NUMBER_WORKERS=UserParam(1, constraint=Positive_Value_Constraint),
        FLUX_SMOOTH_CONFIGS=UserParam(
            default_value=FLUX_SMOOTH_CONFIGS.NONE,
            constraint=ValueFromIterable(FLUX_SMOOTH_CONFIGS),
            description="Configure a possible flux smoothing before template construction",
        ),
        FLUX_SMOOTH_WINDOW_SIZE=UserParam(
            default_value=15,
            constraint=Positive_Value_Constraint,
            description="Number of points that will be used for the filter to smooth the spectra",
        ),
        FLUX_SMOOTH_DEG=UserParam(
            default_value=2,
            constraint=Positive_Value_Constraint,
            description="Degree of the polynomial that will be used for the filter to smooth the spectra",
        ),
        FLUX_SMOOTH_ORDER=UserParam(
            default_value=FLUX_SMOOTH_ORDER.AFTER,
            constraint=ValueFromIterable(FLUX_SMOOTH_ORDER),
            description="Order in which we smooth the flux (before, after or both)",
        ),
    )

    def __init__(self, **kwargs: Any) -> None:  # noqa: D107
        self._default_params = self._default_params + Spectral_Modelling._default_params
        self.has_modelling_component = True
        super().__init__(**kwargs)

        if not self.has_spectrum_component:
            # TODO: ensure that it is safe to do this in here
            # TODO 1: won't this raise an Exception depending on the instantiation order???
            logger.critical("Can't add modelling component to class without a spectrum")
            raise Exception("Can't add modelling component to class without a spectrum")

        self.initialized_interface = False

        self._modelling_interfaces: Dict[SPECTRA_INTERPOL_MODE, ModellingBase] = {}

    def initialize_modelling_interface(self) -> None:
        """Initialize all modelling interfaces."""
        if self.initialized_interface:
            return
        interface_init = {
            "obj_info": self.spectrum_information,
            "user_configs": self._internal_configs.get_user_configs(),
        }
        self._modelling_interfaces[SPECTRA_INTERPOL_MODE.SPLINES] = ScipyInterpolSpecModel(**interface_init)
        # SPECTRA_INTERPOL_MODE.GP: GPSpecModel(**interface_init),

        if self._internalPaths.root_storage_path is None:
            logger.critical(
                "{self.name} launching modelling interface without a root path. Fallback to current directory",
            )
            self.generate_root_path(Path())

        for comp in self._modelling_interfaces.values():
            comp.generate_root_path(self._internalPaths.root_storage_path)

        self.initialized_interface = True

    @property
    def interpol_mode(self) -> SPECTRA_INTERPOL_MODE:
        """Current interpol mode."""
        return self._internal_configs["INTERPOL_MODE"]

    @property
    def interpolation_interface(self) -> ModellingBase:
        """Access the currently specified interpolatio interface."""
        self.initialize_modelling_interface()
        return self._modelling_interfaces[self.interpol_mode]

    def update_user_configs(self, new_configs: dict[str, Any]) -> None:
        """Propagates update of configs to the interpolation interface."""
        super().update_user_configs(new_configs)
        self.interpolation_interface.set_interpolation_properties(new_configs)

    def interpolate_spectrum_to_wavelength(
        self,
        order: int,
        new_wavelengths: np.ndarray,
        shift_RV_by: float,
        RV_shift_mode: str,
        include_invalid: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Shift and interpolate spectra to new wavelength grid.

        Args:
            order (int): Spectral order
            new_wavelengths (np.ndarray): New wavelength grid
            shift_RV_by (float): RV that will be used to shift the spectra before interpolation
            RV_shift_mode (str): apply/remove
            include_invalid (bool, optional): if False, raise Exception when accessing invalid frames.
              Defaults to False.

        Raises:
            custom_exceptions.InternalError: _description_
            custom_exceptions.InvalidConfiguration: _description_
            exc: _description_

        Returns:
            tuple[np.ndarray, np.ndarray]: New fluxes and associated uncertainties

        """
        self.initialize_modelling_interface()

        wavelength, flux, uncertainties, mask = self.get_data_from_spectral_order(order, include_invalid)
        desired_inds = ~mask

        og_lambda, og_spectra, og_errs = (
            wavelength[desired_inds],
            flux[desired_inds],
            uncertainties[desired_inds],
        )

        if RV_shift_mode == "apply":
            shift_function = apply_RVshift
        elif RV_shift_mode == "remove":
            shift_function = remove_RVshift
        else:
            raise custom_exceptions.InvalidConfiguration("Unknown mode")

        og_lambda = shift_function(wave=og_lambda, stellar_RV=shift_RV_by)

        try:
            (
                new_flux,
                new_errors,
            ) = self.interpolation_interface.interpolate_spectrum_to_wavelength(
                og_lambda=og_lambda,
                og_spectra=og_spectra,
                og_err=og_errs,
                new_wavelengths=new_wavelengths,
                order=order,
            )
        except custom_exceptions.StopComputationError as exc:
            logger.critical("Interpolation of {} has failed", self.name)
            raise exc

        return np.asarray(new_flux), np.asarray(new_errors)

    def trigger_data_storage(self, *args: Any, **kwargs: Any) -> None:  # noqa: D102
        super().trigger_data_storage(*args, **kwargs)
        for model_name, comp in self._modelling_interfaces.items():
            comp.trigger_data_storage()
