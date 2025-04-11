"""Skeleton for the unified interpolation framework."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
from loguru import logger
from scipy.signal import savgol_filter

from ASTRA.ModelParameters import Model, ModelComponent
from ASTRA.utils import custom_exceptions
from ASTRA.utils.BASE import BASE
from ASTRA.utils.choices import FLUX_SMOOTH_CONFIGS, FLUX_SMOOTH_ORDER
from ASTRA.utils.parameter_validators import BooleanValue, IntegerValue, Positive_Value_Constraint, ValueFromIterable
from ASTRA.utils.UserConfigs import (
    DefaultValues,
    UserParam,
)


class ModellingBase(BASE):
    """Presents a unified framework for spectral interpolation/prediction.

    This ensures that we can apply different methods for spectral interpolation
    (e.g., through splines) or prediction (through GPs)
    """

    _name = "SpecModelBase"

    # The _default parameters that we define, must be added as configurations in the Modelling class
    # Otherwise, the user values will never reach here!
    _default_params = BASE._default_params + DefaultValues(
        FORCE_MODEL_GENERATION=UserParam(False, constraint=BooleanValue),
        NUMBER_WORKERS=UserParam(2, constraint=Positive_Value_Constraint + IntegerValue),
        FLUX_SMOOTH_CONFIGS=UserParam(
            default_value=FLUX_SMOOTH_CONFIGS.NONE,
            constraint=ValueFromIterable(FLUX_SMOOTH_CONFIGS),
            description="Configure a possible flux smoothing before template construction",
            mandatory=True,
        ),
        FLUX_SMOOTH_WINDOW_SIZE=UserParam(
            default_value=15,
            constraint=Positive_Value_Constraint,
            mandatory=True,
            description="Number of points that will be used for the filter to smooth the spectra",
        ),
        FLUX_SMOOTH_DEG=UserParam(
            default_value=2,
            constraint=Positive_Value_Constraint,
            mandatory=True,
            description="Degree of the polynomial that will be used for the filter to smooth the spectra",
        ),
        FLUX_SMOOTH_ORDER=UserParam(
            default_value=FLUX_SMOOTH_ORDER.AFTER,
            constraint=ValueFromIterable(FLUX_SMOOTH_ORDER),
            mandatory=True,
            description="Order in which we smooth the flux (before, after or both)",
        ),
    )

    def __init__(self, obj_info: Dict[str, Any], user_configs, needed_folders=None):
        """Instantiate object."""
        super().__init__(
            user_configs=user_configs,
            needed_folders=needed_folders,
            quiet_user_params=True,
        )

        # Avoid multiple loads of disk information
        self._loaded_disk_model: bool = False

        # Avoid multiple calls to disk loading if the file does not exist
        self._attempted_to_load_disk_model: bool = False

        self._modelling_parameters = Model(params_of_model=[])
        self.object_info = obj_info
        self._init_model()

    def _init_model(self) -> None:
        for order in range(self.object_info["N_orders"]):
            self._modelling_parameters.generate_prior_from_frameID(order)

    def generate_model_from_order(self, order: int) -> None:
        """Pre-compute model parameters for modelling (if needed).

        Args:
            order (int): Order number

        Raises:
            custom_exceptions.AlreadyLoaded: If the pre-computed model was already loaded from disk.

        """
        if not self._internal_configs["FORCE_MODEL_GENERATION"]:
            try:
                if not self._attempted_to_load_disk_model:
                    self.load_previous_model_results_from_disk(model_component_in_use=ModelComponent)
            except custom_exceptions.NoDataError:
                logger.warning("No information found on disk from previous modelling.")
        else:
            logger.info("Forcing model generation. Skipping disk-searches of previous outputs")

        if self._modelling_parameters.has_valid_identifier_results(order):
            # logger.info(f"Parameters of order {order} already exist on memory. Not fitting a new model")
            raise custom_exceptions.AlreadyLoaded

    def interpolate_spectrum_to_wavelength(
        self,
        og_lambda: np.ndarray,
        og_spectra: np.ndarray,
        og_err: np.ndarray,
        new_wavelengths: np.ndarray,
        order: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Interpolation of spectra to a given wavelength.

        It supports the smoothing of stellar spectra before and/or after interpolation, using the predefined
        configurations.

        Args:
            og_lambda (np.ndarray): Original wavelength
            og_spectra (np.ndarray): Original spectra
            og_err (np.ndarray): Original flux uncertainties
            new_wavelengths (np.ndarray): New wavelength solution
            order (int): Spectral order, might be needed for compatibility purposes

        Returns:
            tuple[np.ndarray, np.ndarray]: New flux and new uncertainties

        """
        if self._internal_configs["FLUX_SMOOTH_ORDER"] in [FLUX_SMOOTH_ORDER.BEFORE, FLUX_SMOOTH_ORDER.BOTH]:
            if self._internal_configs["FLUX_SMOOTH_CONFIGS"] == FLUX_SMOOTH_CONFIGS.SAVGOL:
                og_spectra = savgol_filter(
                    og_spectra,
                    window_length=self._internal_configs["FLUX_SMOOTH_WINDOW_SIZE"],
                    polyorder=self._internal_configs["FLUX_SMOOTH_DEG"],
                )
            elif self._internal_configs["FLUX_SMOOTH_CONFIGS"] != FLUX_SMOOTH_CONFIGS.NONE:
                raise custom_exceptions.InternalError("Can't recognize smoothing filter name")

        interpol_spectra, interpol_errors = self._internal_interpolation(
            og_lambda=og_lambda,
            og_spectra=og_spectra,
            og_err=og_err,
            new_wavelengths=new_wavelengths,
            order=order,
        )

        if self._internal_configs["FLUX_SMOOTH_ORDER"] in [FLUX_SMOOTH_ORDER.AFTER, FLUX_SMOOTH_ORDER.BOTH]:
            if self._internal_configs["FLUX_SMOOTH_CONFIGS"] == FLUX_SMOOTH_CONFIGS.SAVGOL:
                interpol_spectra = savgol_filter(
                    interpol_spectra,
                    window_length=self._internal_configs["FLUX_SMOOTH_WINDOW_SIZE"],
                    polyorder=self._internal_configs["FLUX_SMOOTH_DEG"],
                )
            elif self._internal_configs["FLUX_SMOOTH_CONFIGS"] != FLUX_SMOOTH_CONFIGS.NONE:
                raise custom_exceptions.InternalError("Can't recognize smoothing filter name")

        return interpol_spectra, interpol_errors

    def _internal_interpolation(
        self,
        og_lambda: np.ndarray,
        og_spectra: np.ndarray,
        og_err: np.ndarray,
        new_wavelengths: np.ndarray,
        order: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """To be implemented by child classes."""
        raise NotImplementedError("Must be implemented by child classes")

    def set_interpolation_properties(self, new_properties: dict[str, Any]) -> None:
        """Update interpolation properties, through the InternalParameters interface."""
        self._internal_configs.update_configs_with_values(new_properties)

    def load_previous_model_results_from_disk(self, model_component_in_use: str) -> None:
        """Load a previous disk-stored (precomputed) model parameters.

        Args:
            model_component_in_use (_type_): _description_

        Raises:
            custom_exceptions.AlreadyLoaded: Data was already loaded
            custom_exceptions.NoDataError: No disk-stored data

        """
        if self._loaded_disk_model or self._attempted_to_load_disk_model:
            raise custom_exceptions.AlreadyLoaded

        self._attempted_to_load_disk_model = True

        logger.debug(f"Searching for previous model on disk: {self._get_model_storage_filename()}")

        try:
            storage_name = self._get_model_storage_filename()
        except custom_exceptions.MissingRootPath:
            logger.debug("Missing Root path information. Giving up on loading data")
            raise custom_exceptions.NoDataError

        try:
            loaded_model = Model.load_from_json(storage_name, component_to_use=model_component_in_use)
            self._loaded_disk_model = True
            self._modelling_parameters = loaded_model
        except FileNotFoundError:
            self._loaded_disk_model = False
            logger.debug("Failed to find disk model")
            raise custom_exceptions.NoDataError

    def _store_model_to_disk(self) -> None:
        """Store the fit parameters to disk, to avoid multiple computations in the future."""
        if not self._modelling_parameters.has_results_stored:
            return

        full_fname = self._get_model_storage_filename()

        self._modelling_parameters.save_to_json_file(full_fname)

    def trigger_data_storage(self, *args, **kwargs) -> None:  # noqa: D102
        super().trigger_data_storage(args, kwargs)
        self._store_model_to_disk()

    def _get_model_storage_filename(self) -> str:
        """Compute storage filename for this object."""
        obj_type = self.object_info["object_type"]
        if obj_type == "Frame":
            filename_start = self.object_info["filename"]
        elif obj_type == "Template":
            filename_start = f"Template_{self.object_info['subInstrument']}"
        else:
            raise custom_exceptions.InvalidConfiguration(
                "Spectral modelling can't save results for {}",
                self._object_type,
            )

        return filename_start
