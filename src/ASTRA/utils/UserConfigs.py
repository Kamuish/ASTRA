"""ASTRA configurations.

This defines the main configuration scheme of ASTRA:

1) Userparam, which defines the individual configurations
2) InternalParameters, which are used by ASTRA objects
3) DefaultValues, which agregates all possible configurations that are
available to the users
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict, NoReturn, Optional

from loguru import logger

from ASTRA.utils.custom_exceptions import InternalError, InvalidConfiguration
from ASTRA.utils.parameter_validators import Constraint


class UserParam:
    """Define an individual configuration that the user can specify."""

    __slots__ = (
        "_valueConstraint",
        "_default_value",
        "_mandatory",
        "quiet",
        "description",
    )

    def __init__(
        self,
        default_value: Optional[Any] = None,
        constraint: Optional[Constraint] = None,
        mandatory: bool = False,
        quiet: bool = False,
        description: Optional[str] = None,
    ) -> None:
        """Instantiate a user parameter and assoctied constraints and values.

        Args:
            default_value (Optional[Any], optional): Default value of the parameter. Defaults to None.
            constraint (Optional[Constraint], optional): Constraint that is used to
                validate the user input. Defaults to None.
            mandatory (bool, optional): If True, the configuration must always be provided by the
                user. Defaults to False.
            quiet (bool, optional): Avoid logs. Defaults to False.
            description (Optional[str], optional): Description of the parameter, to be printed
                to terminal when requested. Defaults to None.

        """
        self._valueConstraint = constraint if constraint is not None else Constraint("")
        self._default_value = default_value
        self._mandatory = mandatory
        self.quiet = quiet
        self.description = description

    def apply_constraints_to_value(self, param_name: str, value: Any) -> None:
        """Apply the constraints of this parameter to a given value.

        Args:
            param_name (str): Name of the parameter, used in the logs
            value (Any): Value that the user provided

        """
        self._valueConstraint.check_if_value_meets_constraint(value)

    @property
    def existing_constraints(self) -> Constraint:
        """Retrieve existing constraints of parameter."""
        return self._valueConstraint

    @property
    def is_mandatory(self) -> bool:
        """True if the parameter is mandatory."""
        return self._mandatory

    @property
    def quiet_output(self) -> bool:
        """True if the parameter should not log to terminal."""
        return self.quiet

    @property
    def default_value(self) -> Any:
        """Return the default value of the parameter.

        Raises
        ------
        InvalidConfiguration: if the parameter is mandatory, there is no default

        """
        if self.is_mandatory:
            raise InvalidConfiguration("Trying to use default value of a mandatory parameter")

        self.apply_constraints_to_value("default_value", self._default_value)
        return self._default_value

    def __repr__(self) -> str:  # noqa: D105
        return (
            "\n".join(
                (
                    f" Mandatory Flag: {self._mandatory}",
                    f"Default Value: {self._default_value}",
                    f"Constraints: {self._valueConstraint}",
                )
            )
            + "\n"
        )

    def get_terminal_output(self, indent_level: int = 1) -> str:
        """Generate terminal-formatted text from this UserParam.

        Args:
            indent_level (int, optional): How many tabs to add at the start of each line. Defaults to 1.

        Returns:
            str: Formatted message with the Description, mandatory status, default value and constraints

        """
        offset = indent_level * "\t"
        message = ""
        for name, value in [
            ("Description", self.description),
            ("Mandatory", self._mandatory),
            ("Default value", self._default_value),
            ("Constraints", self._valueConstraint),
        ]:
            message += offset + f"{name}:: {value}\n"
        return message


class InternalParameters:
    """Contain all configurations from a given ASTRA object.

    This class will store all configurations (*UserParam*) from a given ASTRA object, as well as
    their current value. When updating a given parameter, the QC checks that are imposed
    by the UserParam object.
    """

    __slots__ = ("_default_params", "_user_configs", "_name_of_parent", "no_logs")

    def __init__(
        self,
        name_of_parent: str,
        default_params: DefaultValues,
        no_logs: bool = False,
    ):
        """Create new object.

        Args:
            name_of_parent (str): Name of the config
            default_params (Dict[str, UserParam]): Dict with text name of parameters
                and a UserParam object that describes it.
            no_logs (bool, optional): Avoid terminal logs. Defaults to False.

        """
        self._default_params = default_params
        self._user_configs: dict[str, Any] = {}
        self._name_of_parent = name_of_parent
        self.no_logs = no_logs

    def update_configs_with_values(self, user_configs: dict[str, Any]) -> None:
        """Update the parameters with a configuration dictionary.

        Args:
            user_configs (dict[str, Any]): Dictionary with user parameters.

        Raises:
            InternalError: If the provided value does not meet the imposed restrictions.

        """
        for key, value in user_configs.items():
            try:
                parameter_def_information = self._default_params[key]
            except KeyError:
                if not self.no_logs:
                    # The only object that will have this enabled are the Frames
                    # And we shall call one of the Frames with the User-Param logs enabled!
                    logger.warning(
                        "{} received a configuration flag that is not recognized: {}",
                        self._name_of_parent,
                        key,
                    )
                continue

            try:
                parameter_def_information.apply_constraints_to_value(key, value)
            except InvalidConfiguration as exc:
                logger.critical("User-given parameter {} does not meet the constraints", key)
                raise InternalError from exc

            self._user_configs[key] = value

            if not self.no_logs:
                if not self._default_params[key].quiet_output:
                    logger.debug("Configuration <{}> taking the value: {}", key, value)
                else:
                    logger.debug("Configuration <{}> was updated")

    def receive_user_inputs(self, user_configs: dict[str, Any] = None) -> None:
        """Parse the config dictionary from the user.

        Args:
            user_configs (Optional[Dict[str, Any]], optional): Dictionary where the keys are the parameter names, and
                the values are the new values of that parameter. The values will be checked by the validation
                layer defined in the corresponding UserParam. Defaults to None.

        Raises:
            InvalidConfiguration: If a given parameter is mandatory and it was not provided by the user
            InternalError: If the validation layer does not agree with the provided value.

        """
        if not self.no_logs:
            logger.debug("Generating internal configs of {}", self._name_of_parent)

        self.update_configs_with_values(user_configs)

        if not self.no_logs:
            logger.info("Checking for any parameter that will take default value")
        for key, default_param in self._default_params.items():
            if key not in self._user_configs:
                if default_param.is_mandatory:
                    raise InvalidConfiguration(f"SBART parameter <{key}> is mandatory.")

                if not self.no_logs:
                    logger.debug(
                        "Configuration <{}> using the default value: {}",
                        key,
                        default_param.default_value,
                    )
                try:
                    self._user_configs[key] = default_param.default_value
                except Exception as e:
                    logger.critical("Error in the generation of parameter: {}", key)
                    raise InternalError from e

    def text_pretty_description(self, indent_level: int) -> str:
        """Generate textual description of internal parameters."""
        file_offset = indent_level * "\t"
        to_write = ""

        to_write += f"\n{file_offset}Parameters in use:"
        for key, value in self._user_configs.items():
            to_write += f"\n{file_offset}\t{key} -> {value}"
        return to_write

    def __setitem__(self, key: str, value: Any) -> None:  # noqa: D105
        logger.warning(f"Internal configs are being updated in real time ({key=})")
        try:
            parameter_def_information = self._default_params[key]
        except KeyError:
            if not self.no_logs:
                # The only object that will have this enabled are the Frames
                # And we shall call one of the Frames with the User-Param logs enabled!
                logger.warning(
                    "{} received a configuration flag that is not recognized: {}",
                    self._name_of_parent,
                    key,
                )
        try:
            parameter_def_information.apply_constraints_to_value(key, value)
        except InvalidConfiguration as exc:
            logger.critical("User-given parameter {} does not meet the constraints", key)
            raise InternalError from exc
        self._user_configs[key] = value

    def __getitem__(self, item: str):  # noqa: D105
        try:
            return self._user_configs[item]
        except KeyError:
            msg = f"<{item}> is not a valid parameter of {self._name_of_parent}"
            logger.critical(msg)
            raise Exception(msg)

    def get_user_configs(self) -> Dict[str, Any]:
        """Get all user configs."""
        return self._user_configs

    def items(self):
        """Get the values."""
        return self._user_configs.items()


class DefaultValues:
    """Defines all of the user parameters that SBART has available for any given object.

    We can sum two DefaultValues objects to expand the possible configurable parameters
    of the ASTRA object.
    """

    def __init__(self, **kwargs: UserParam) -> None:
        """Map of str to UserParam to describe configurations."""
        self.default_mapping: dict[str, UserParam] = kwargs

    def update(self, item: str, new_value: UserParam) -> None:
        """Update the default value of a stored parameter, if it exists.

        Args:
            item (str): Param name
            new_value (UserParam): New configuration

        Raises:
            Exception: If the parameter that we want to update does not exist

        """
        if item not in self.default_mapping:
            raise Exception
        self.default_mapping[item] = new_value

    def __add__(self, other: DefaultValues) -> DefaultValues:  # noqa: D105
        new_default_mapping = {**self.default_mapping, **other.default_mapping}
        return DefaultValues(**new_default_mapping)

    def __radd__(self, other: DefaultValues) -> DefaultValues:  # noqa: D105
        return self.__add__(other)

    def __getitem__(self, item: str) -> Any:  # noqa: D105
        return self.default_mapping[item]

    def __str__(self) -> str:  # noqa: D105
        return self.__repr__()

    def __repr__(self) -> str:  # noqa: D105
        representation = "Configurations:\n\n"

        for key, value in self.default_mapping.items():
            representation += f"Name:: {key}\n{value.get_terminal_output()} \n"

        return representation

    ### Map the inside dict properties to the outside!
    def items(self):  # noqa: D102
        return self.default_mapping.items()

    def keys(self) -> Iterable[str]:  # noqa: D102
        return self.default_mapping.keys()

    def values(self) -> Iterable[UserParam]:  # noqa: D102
        return self.default_mapping.values()

    def __iter__(self) -> NoReturn:  # noqa: D105
        raise TypeError("no!")
