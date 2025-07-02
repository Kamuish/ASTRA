"""Handles the creation of the stellar models."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Optional

from loguru import logger

from ASTRA.base_models.TemplateFramework import TemplateFramework
from ASTRA.status.flags import INTERNAL_ERROR
from ASTRA.utils import custom_exceptions
from ASTRA.utils.ASTRAtypes import UI_DICT, UI_PATH
from ASTRA.utils.choices import STELLAR_CREATION_MODE
from ASTRA.utils.custom_exceptions import BadTemplateError, NoDataError
from ASTRA.utils.parameter_validators import (
    BooleanValue,
    ValueFromDtype,
    ValueFromIterable,
)
from ASTRA.utils.spectral_conditions import ConditionModel, Empty_condition
from ASTRA.utils.UserConfigs import (
    DefaultValues,
    UserParam,
)

from .stellar_templates.median_stellar import MedianStellar
from .stellar_templates.OBS_stellar import OBS_Stellar
from .stellar_templates.PHOENIX_STELLAR import PHOENIX
from .stellar_templates.Stellar_Template import StellarTemplate
from .stellar_templates.sum_stellar import SumStellar

if TYPE_CHECKING:
    from ASTRA.data_objects.DataClass import DataClass


class StellarModel(TemplateFramework):
    """The StellarModel is responsible for the creation of the stellar template for each sub-Instrument.

    It allows the user to apply :py:mod:`~ASTRAutils.spectral_conditions` to select the observations that will
    be in use for this process.

    This object supports the following user parameters:

    **Note:** Also check the **User parameters** of the parent classes for further customization options of SBART
    **Note:** All disk- and user-facing interactions are handled by the parent class

    """

    _object_type = "SpectralModel"
    _name = "Stellar"

    model_type = "Stellar"

    template_map: ClassVar[dict[STELLAR_CREATION_MODE, StellarTemplate]] = {
        STELLAR_CREATION_MODE.Sum: SumStellar,
        STELLAR_CREATION_MODE.OBSERVATION: OBS_Stellar,
        STELLAR_CREATION_MODE.Median: MedianStellar,
        STELLAR_CREATION_MODE.PHOENIX: PHOENIX,
    }

    _default_params = TemplateFramework._default_params + DefaultValues(
        CREATION_MODE=UserParam(STELLAR_CREATION_MODE.Sum, constraint=ValueFromIterable(STELLAR_CREATION_MODE)),
        ALIGNEMENT_RV_SOURCE=UserParam("DRS", constraint=ValueFromIterable(["DRS", "SBART"])),
        PREVIOUS_SBART_PATH=UserParam("", constraint=ValueFromDtype((str, Path))),
        USE_MERGED_RVS=UserParam(False, constraint=BooleanValue),
    )

    def __init__(self, root_folder_path: UI_PATH, user_configs: Optional[UI_DICT] = None):
        """Instantiate the object.

        Parameters
        ----------
        root_folder_path: Union [str, pathlib.Path]
            Path to the folder inside which SBART will store its outputs
        user_configs: Optional[Dict[str, Any]]
            Dictionary with the keys and values of the user parameters that have been described above

        """
        super().__init__(mode="", root_folder_path=root_folder_path, user_configs=user_configs)

        self._creation_conditions = Empty_condition()
        self.iteration_number = 0
        self.RV_source = None

    def Generate_Model(
        self,
        dataClass: DataClass,
        template_configs: Optional[UI_DICT] = None,
        conditions: Optional[ConditionModel] = None,
        force_computation: bool = False,
        store_templates: bool = True,
        previous_sbart_rv=None,
    ) -> None:
        """Apply the spectral conditions to decide which observations to use.

        Then, returns to the model generation as defined in the parent implementation.

        Parameters
        ----------
        dataClass : [type]
            DataClass with the observations
        template_configs : dict
            Dictionary with the parameters needed to control the creation of the template. Each one has its own
            set of requirements
        conditions: None, Condition
            Either None (to not select the OBS that will be used) or :py:mod:`~ASTRAutils.spectral_conditions` to
                restrict the observations in use.
        force_computation: bool
            If True, recompute the stellar templates, even if they exist on disk. By default False
        store_templates: bool
            If True [default], store the templates to disk
        previous_sbart_rv: SBART.data_objects.RV_outputs.RV_holder
            Object that s-BART loaded from disk, containing the RVs from a previous iteration

        Notes
        -----
        * The conditions that are passed to the StellarModel are **only** used for the creation of the stellar template.
         This will **not** reject observations from the RV extraction

        """
        if conditions is not None:
            logger.info("Applying conditions to creation of stellar template")
            self._creation_conditions = conditions

        self.RV_source = self._internal_configs["ALIGNEMENT_RV_SOURCE"]

        if self._internal_configs["ALIGNEMENT_RV_SOURCE"] == "SBART":
            logger.info(
                "{} using {} RVs as the source for stellar template creation",
                self.name,
                self._internal_configs["ALIGNEMENT_RV_SOURCE"],
            )
            if previous_sbart_rv is None:
                msg = "No previous SBART RVs were provided!"
                logger.critical(msg)
                raise custom_exceptions.InvalidConfiguration(msg)

            self.iteration_number = previous_sbart_rv.iteration_number + 1
            self.RV_source = previous_sbart_rv.RV_source

            dataClass.load_previous_SBART_results(
                previous_sbart_rv,
                use_merged_cube=self._internal_configs["USE_MERGED_RVS"],
            )

        else:
            logger.info("Using CCF RVs as the basis for the creation of the stellar models")

        self.add_relative_path("Stellar", f"Stellar/Iteration_{self.iteration_number}")

        super().Generate_Model(
            dataClass=dataClass,
            template_configs=template_configs,
            attempt_to_load=not force_computation,
            store_templates=False,
        )

        for subInst, temp in self.templates.items():
            temp.update_RV_source_info(
                iteration_number=self.iteration_number,
                RV_source=self.RV_source,
                merged_source=self._internal_configs["USE_MERGED_RVS"],
            )

        if store_templates:
            self.store_templates_to_disk()

    def initialize_modelling_interfaces(self, new_properties):
        for subInst, temp in self.templates.items():
            temp.initialize_modelling_interface()

    def get_interpol_modes(self) -> set[str]:
        return set(temp.interpol_mode for temp in self.templates.values())

    def _compute_template(self, data: DataClass, subInstrument: str, user_configs: dict) -> None:
        chosen_template = self.template_map[self._internal_configs["CREATION_MODE"]]
        key = "ALIGNEMENT_RV_SOURCE"
        if key in user_configs:
            logger.warning(f"Key <{key}> from Stellar Model over-riding the one from the template configs")
        user_configs[key] = self._internal_configs[key]
        stellar_template = chosen_template(subInst=subInstrument, user_configs=user_configs)

        try:
            stellar_template.create_stellar_template(dataClass=data, conditions=self._creation_conditions)
        except NoDataError:
            logger.info(
                "{} has no available data. The template will be created as an array of zeros",
                subInstrument,
            )

        return stellar_template

    def get_orders_to_skip(self, subInst: str) -> set[int]:
        """Compute orders to skip on a given subInstrument.

        GIven by the orders that the stellar template rejected.

        Args:
            subInst (str): sub-Instrument name

        Raises:
            BadTemplateError: No valid template for the subInstrument

        Returns:
            Set[int]: Set of bad orders.

        """
        if subInst == "all":
            bad_orders: set[int] = set()
            for temp in self.templates.values():
                if not temp.is_valid:
                    logger.critical("Invalid template <{}> does not have orders to skip", temp)
                    continue
                bad_orders.union(temp.bad_orders)
        else:
            if not self.templates[subInst].is_valid:
                raise BadTemplateError
            bad_orders = self.templates[subInst].bad_orders

        return bad_orders

    def load_templates_from_disk(self) -> None:
        """Load stellar templates from disk.

        Parameters
        ----------
        path : str
            [description]

        """
        super().load_templates_from_disk()

    @property
    def RV_keyword(self) -> str:
        """RV keyword to use when aligning observations."""
        if self._internal_configs["ALIGNEMENT_RV_SOURCE"] == "SBART":
            RV_KW_start = "previous_SBART_RV"
        else:
            RV_KW_start = "DRS_RV"

        return RV_KW_start
