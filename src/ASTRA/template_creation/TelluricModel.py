"""Handle Telluric models."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar, Type

from loguru import logger

from ASTRA.base_models.Template_Model import BaseTemplate
from ASTRA.base_models.TemplateFramework import TemplateFramework
from ASTRA.utils.ASTRAtypes import UI_DICT, UI_PATH
from ASTRA.utils.choices import (
    TELLURIC_APPLICATION_MODE,
    TELLURIC_CREATION_MODE,
    TELLURIC_EXTENSION,
    WORKING_MODE,
)
from ASTRA.utils.custom_exceptions import InvalidConfiguration, TemplateNotExistsError
from ASTRA.utils.parameter_validators import ValueFromIterable
from ASTRA.utils.UserConfigs import DefaultValues, UserParam

from .telluric_templates.telluric_from_OHemission import OHemissionTelluric
from .telluric_templates.telluric_from_telfit import TelfitTelluric
from .telluric_templates.Telluric_Template import TelluricTemplate

if TYPE_CHECKING:
    from ASTRA.data_objects.DataClass import DataClass


class TelluricModel(TemplateFramework):
    # noinspection LongLine
    """The TelluricModel is responsible for the creation of the telluric template for each sub-Instrument.

    This object supports the following user parameters:

    **User parameters:**

    ================================ ================ ================
    Parameter name                      Mandatory      Default Value
    ================================ ================ ================
    CREATION_MODE                       True            ----
    APPLICATION_MODE                    False           removal
    EXTENSION_MODE                      False           lines
    ================================ ================ ================


    *Note:* Also check the **User parameters** of the parent classes for further customization options of SBART

    """

    model_type = "Telluric"

    template_map: ClassVar[dict[TELLURIC_CREATION_MODE, TelluricTemplate]] = {
        TELLURIC_CREATION_MODE.telfit: TelfitTelluric,
        TELLURIC_CREATION_MODE.OHemission: OHemissionTelluric,
    }

    _default_params = TemplateFramework._default_params + DefaultValues(
        CREATION_MODE=UserParam(
            TELLURIC_CREATION_MODE.telfit,
            constraint=ValueFromIterable(TELLURIC_CREATION_MODE),
            mandatory=False,
        ),
        APPLICATION_MODE=UserParam(
            TELLURIC_APPLICATION_MODE.removal,
            constraint=ValueFromIterable(TELLURIC_APPLICATION_MODE),
        ),
        EXTENSION_MODE=UserParam(
            TELLURIC_EXTENSION.LINES,
            constraint=ValueFromIterable(TELLURIC_EXTENSION),
        ),
    )

    def __init__(self, usage_mode: str, root_folder_path: UI_PATH, user_configs: UI_DICT) -> None:
        """Instantiate of the object.

        Parameters
        ----------
        usage_mode : str
            How to telluric templates will be applied to the data. If 'individual' -> template applied to its own
            subInstrument. If 'merged', we use a template built from merging the templates from all subInstruments
        root_folder_path: Union [str, pathlib.Path]
            Path to the folder inside which SBART will store its outputs
        user_configs: Optional[Dict[str, Any]]
            Dictionary with the keys and values of the user parameters that have been described above

        """
        super().__init__(mode="", root_folder_path=root_folder_path, user_configs=user_configs)

        logger.info("Starting Telluric Model")

        # can be 'individual' -> template applied to its own subInstrument
        # or  'merged' and we use a template built from merging the templates from all subInstruments
        self._usage_mode = usage_mode

    def load_templates_from_disk(self) -> None:  # noqa: D102
        super().load_templates_from_disk()
        for value in self.templates.values():
            value.update_extension_mode(self._internal_configs["EXTENSION_MODE"])

    def request_template(self, subInstrument: str) -> Type[BaseTemplate]:
        """Return the template for a given sub-Instrument.

        Parameters
        ----------
        subInstrument: str
            "name" of the subInstrument

        Returns
        -------
            Requested telluric Template

        """
        logger.debug("Serving {} template to subInstrument {}", self._usage_mode, subInstrument)
        if self._usage_mode == "":
            return self.templates["merged"]
        if self._usage_mode == "individual":
            return self.templates[subInstrument]
        raise InvalidConfiguration()

    def Generate_Model(
        self,
        dataClass: DataClass,
        telluric_configs: dict,
        force_computation: bool = False,
        store_templates: bool = True,
    ) -> None:
        """Generate a telluric model for all subInstruments with data, as defined in the parent implementation.

        Afterwards, allow to combine the telluric model of all sub-Instruments into a single telluric binary
         model which will then be used for all available observations.

        [**Warning**: the combination is yet to be implemented]

        Parameters
        ----------
        dataClass : :class:`~ASTRAdata_objects.DataClass`
            DataClass with the observations
        telluric_configs : dict
            Dictionary with the parameters needed to control the creation of the telluric template, following the
            specifications of the templates.
        force_computation : bool
            If False, it will attempt to lead the telluric template from disk before trying to compute them. If True,
            always compute telluric template, even if it exists
        store_templates: bool
            If True (default) store to disk

        """
        super().Generate_Model(
            dataClass=dataClass,
            template_configs=telluric_configs,
            attempt_to_load=not force_computation,
            store_templates=False,
        )

        if self._usage_mode == "merged":
            logger.info("Telluric model merging the templates from all epochs")
            self.merge_templates()

        if store_templates:
            self.store_templates_to_disk()

    def merge_templates(self) -> None:
        """Merge the telluric template of all sub-Instruments to create a master telluric binary template.

        Raises
        ------
        NotImplementedError
            The method is yet to be implemented

        """
        logger.info("Merging templates to create a global one")
        raise NotImplementedError

    # Internal Usage:

    def _find_templates_from_disk(self, which: TELLURIC_CREATION_MODE) -> list[str]:
        loading_path = self._internalPaths.get_path_to(self.__class__.model_type)
        logger.info("Loading {} template from disk inside directory", self.__class__.model_type)
        logger.info("\t" + loading_path)

        available_templates = []

        if not os.path.exists(loading_path):
            logger.warning(f"Could not find template to load in {loading_path}")
            raise TemplateNotExistsError()

        for fname in os.listdir(loading_path):
            if which.value in fname and fname.endswith("fits"):
                available_templates.append(fname)
        logger.info(
            "Found {} available templates: {} of type {}",
            len(available_templates),
            available_templates,
            which,
        )
        if len(available_templates) == 0:
            logger.critical("Could not find templates to load!")
            raise TemplateNotExistsError()
        return [os.path.join(loading_path, i) for i in available_templates]

    def _compute_template(self, data, subInstrument: str, user_configs: dict) -> TelluricTemplate:
        creation_mode = self._internal_configs["CREATION_MODE"]
        logger.info("Using template of type: {}", creation_mode)

        if creation_mode == "none":
            pass
        elif creation_mode == TELLURIC_CREATION_MODE.telfit:
            chosen_template = TelfitTelluric
        elif creation_mode == TELLURIC_CREATION_MODE.tapas:
            chosen_template = TapasTelluric
        elif creation_mode == TELLURIC_CREATION_MODE.OHemission:
            chosen_template = OHemissionTelluric
        else:
            raise InvalidConfiguration()

        if self.work_mode == WORKING_MODE.ONE_SHOT or self.templates[subInstrument] is None:
            tell_template = chosen_template(
                subInst=subInstrument,
                user_configs=user_configs,
                extension_mode=self._internal_configs["EXTENSION_MODE"],
                application_mode=self._internal_configs["APPLICATION_MODE"],
            )

            tell_template.load_information_from_DataClass(data)

            if self.is_for_removal:
                tell_template.create_telluric_template(dataClass=data)
            else:
                logger.debug("Telluric template in removal mode. Fitting from inside dataClass")

        else:
            # If this is a rolling mode, we just need to add the new information
            tell_template = self.templates[subInstrument]
            tell_template.ingest_new_rolling_observations(dataClass=data)

            if not self.is_for_removal:
                msg = "The rolling template can only be used to remove features, not correct "
                raise InvalidConfiguration(msg)

        return tell_template

    @property
    def is_for_removal(self) -> bool:
        """True if the template will be used to remove telluric features."""
        return self._internal_configs["APPLICATION_MODE"] == TELLURIC_APPLICATION_MODE.removal

    @property
    def is_for_correction(self) -> bool:
        """True if the template will be used to correct telluric features."""
        return self._internal_configs["APPLICATION_MODE"] == TELLURIC_APPLICATION_MODE.correction
