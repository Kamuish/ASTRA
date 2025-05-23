"""Allow to normalize stellar spectra through different methods.

Thhis allows to normalize stellar spectra using three different algorithms:

1) SNT - in-house implementation of alpha-shape algorithms (only S1D)
2) RASSINE (only S1D)
3) First degree polynomial fit (S1D and S2D files)

In all cases, ASTRA stores on disk the relevant parameters, so that subsquent
normalization of a given Frame will be cached and avoid recomputation of continuum
models.

Currently, SNT and RASSINE can only be applied to the S1D frames.

"""

from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from ASTRA.DataUnits.SpecNormUnit import SpecNorm_Unit
from ASTRA.spectral_normalization import available_normalization_interfaces
from ASTRA.spectral_normalization.normalization_base import NormalizationBase
from ASTRA.utils import custom_exceptions
from ASTRA.utils.BASE import BASE
from ASTRA.utils.choices import NORMALIZATION_SOURCES
from ASTRA.utils.parameter_validators import (
    BooleanValue,
    PathValue,
    ValueFromIterable,
)
from ASTRA.utils.UserConfigs import (
    DefaultValues,
    UserParam,
)


class Spectral_Normalization(BASE):
    """Introduces, in a given object, the functionality to normalize the continuum level.

    In order to inherit from this class, it must also be a children of
     :class:`ASTRAComponents.SpectrumComponent.Spectrum`

    **User parameters:**

    ============================ ================ ================ ======================== ================
    Parameter name                 Mandatory      Default Value    Valid Values                 Comment
    ============================ ================ ================ ======================== ================
    NORMALIZATION_MODE               False          RASSINE                                    [1]
    ============================ ================ ================ ======================== ================

    Notes:
        [1] Name of the spectral normalizers, that are described in :mod:`ASTRA.spectral_normalization`

    *Note:* Also check the **User parameters** of the parent classes for further customization options of SBART

    """

    # TODO: confirm the kernels that we want to allow
    _default_params = BASE._default_params + DefaultValues(
        NORMALIZE_SPECTRA=UserParam(
            False,
            constraint=BooleanValue,
            description=(
                "If True, enable the normalization interface" "If False, a call to normalize_spectra does nothing"
            ),
        ),
        NORMALIZATION_MODE=UserParam(
            NORMALIZATION_SOURCES.SNT,
            constraint=ValueFromIterable(NORMALIZATION_SOURCES),
            description="Normalization method to use, as defined in the enum provided in ASTRA.utils.choices",
        ),
        S1D_folder=UserParam(
            mandatory=False,
            constraint=PathValue,
            default_value="",
            description="Not used for now",
        ),
        RASSINE_path=UserParam(
            mandatory=False,
            constraint=PathValue,
            default_value="",
            description=(
                "Path to a local clone of the modified RASSINE"
                "(git@github.com:Kamuish/Rassine_modified.git)"
                ". Only used if we are using RASSINE as the normalization tool"
            ),
        ),
    )

    def __init__(self, **kwargs: Any) -> None:  # noqa: D107
        self._default_params = self._default_params + Spectral_Normalization._default_params
        self.has_normalization_component = True
        super().__init__(**kwargs)

        if not self.has_spectrum_component:
            msg = "Can't add modelling component to class without a spectrum"
            logger.critical(msg)
            raise Exception(msg)

        self._already_normalized_data = False
        self._normalization_interfaces: Dict[NORMALIZATION_SOURCES, NormalizationBase] = {}
        self._normalization_information: Optional[SpecNorm_Unit] = None

    def initialize_normalization_interface(self) -> None:
        """Initialize the normalization interface for the currently selected model."""
        key = self._internal_configs["NORMALIZATION_MODE"]

        if key in self._normalization_interfaces:
            return

        interface_init = {
            "obj_info": self.spectrum_information,
            "user_configs": self._internal_configs.get_user_configs(),
        }

        interface_init["obj_info"]["S1D_name"] = self.get_S1D_name()
        interface_init["obj_info"]["frame_path"] = self.file_path
        interface_init["obj_info"]["Frame_instance"] = type(self)
        interface_init["obj_info"]["FWHM"] = self.get_KW_value("FWHM")

        interface = available_normalization_interfaces[key]

        self._normalization_interfaces[key] = interface(**interface_init)

        if self._internalPaths.root_storage_path is None:
            logger.critical(
                f"{self.name} launching normalization interface without a root path. Fallback to current directory",
            )
            self.generate_root_path(Path())

        self._normalization_interfaces[key].generate_root_path(self._internalPaths.root_storage_path)

        current_frame_name = self.fname.split(".fits")[0]
        try:  # Generate class to store the normalization parameters
            self._normalization_information = SpecNorm_Unit.load_from_disk(
                self._internalPaths.root_storage_path,
                filename=current_frame_name,
                algo_name=self._internal_configs["NORMALIZATION_MODE"].name,
            )
        except custom_exceptions.NoDataError:
            logger.warning("Can't find previous normalization parameters on disk!")
            self._normalization_information = SpecNorm_Unit(
                frame_name=current_frame_name,
                algo_name=self._internal_configs["NORMALIZATION_MODE"].name,
            )
            self._normalization_information.generate_root_path(self._internalPaths.root_storage_path)

    def normalize_spectra(self):
        """Launch the normalization of the spectra, using the selected algorithm."""
        if not self._internal_configs["NORMALIZE_SPECTRA"]:
            logger.warning("<NORMALIZE_SPECTRA> option has been disabled by the user")
            return
        if self._already_normalized_data:
            logger.warning("{} is already normalized; Doing nothing!", self.name)
            return
        self.initialize_normalization_interface()

        norm_interface = self._normalization_interfaces[self._internal_configs["NORMALIZATION_MODE"]]
        if norm_interface.orderwise_application:
            self.trigger_orderwise_method(norm_interface)
        else:
            self.trigger_epochwise_method(norm_interface)

    def trigger_epochwise_method(self, norm_interface) -> None:
        """Normalize the spectra using an epoch-wise method."""
        name = "S1D"
        loaded_info = self._normalization_information.get_norm_info_from_order(name)

        wavelengths, flux, uncerts, mask = self.get_data_from_full_spectrum()

        (
            new_waves,
            new_flux,
            new_uncert,
            norm_keys,
        ) = norm_interface.launch_epochwise_normalization(
            wavelengths=wavelengths,
            flux=flux,
            uncertainties=uncerts,
            mask=mask,
            loaded_info=loaded_info,
        )
        self.wavelengths = new_waves.reshape(wavelengths.shape)
        self.spectra = new_flux.reshape(wavelengths.shape)
        self.uncertainties = new_uncert.reshape(wavelengths.shape)
        logger.warning("Epoch wise normalization is overriding the minimum SNR!")
        self._internal_configs["minimum_order_SNR"] = 0
        self.regenerate_order_status()
        self._normalization_information.store_norm_info(name, norm_keys)

        self._already_normalized_data = True
        # Trigger a new check of the data integrity, as we have just overloaded the entire
        # S2D spectrum. However, this ignores any kind of quality check!

    def trigger_orderwise_method(self, norm_interface) -> None:
        """Normalize the spectra using an order-wise method."""
        # TODO: see if we want to parallelize this!
        for order in range(self.N_orders):
            wavelengths, flux, uncerts, mask = self.get_data_from_spectral_order(order, include_invalid=True)

            mask_to_use = ~mask
            loaded_info = self._normalization_information.get_norm_info_from_order(order)

            (
                new_flux,
                new_uncerts,
                norm_keys,
            ) = norm_interface.launch_orderwise_normalization(
                wavelengths=wavelengths[mask_to_use],
                flux=flux[mask_to_use],
                uncertainties=uncerts[mask_to_use],
                mask=mask,
                loaded_info=loaded_info,
            )
            self.spectra[order][mask_to_use] = new_flux
            self.uncertainties[order][mask_to_use] = new_uncerts

            self._normalization_information.store_norm_info(order, norm_keys)

        self._already_normalized_data = True

    def trigger_data_storage(self, *args, **kwargs) -> None:  # noqa: D102
        super().trigger_data_storage(*args, **kwargs)
        if self._normalization_information is not None:
            self._normalization_information.trigger_data_storage()
