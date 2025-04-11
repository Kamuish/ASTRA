"""Validators for the configuration options.

We can combine multiple validation conditions by summing them, thus creating a AND condition

Raises:
    InvalidConfiguration: If passed value does not meet its imposed conditions
    InternalError: Passing unknown configuration of the methods

"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from ASTRA.utils.custom_exceptions import InternalError, InvalidConfiguration


class Constraint:
    """Base class to define a constraint on possible values that a parameter can take.

    Serves as parent class, allows the "sum" of two constraints to make "AND" operations

    Attributes:
        constraint_text: String that describes the constraint

    Raises:
        InvalidConfiguration: If the constraint on the parameter value is not met

    """

    def __init__(self, const_text: str):  # noqa: D107
        self._constraint_list = [self._evaluate]
        self.constraint_text = const_text

    def __add__(self, other: Constraint) -> Constraint:
        """Create AND condition of current and other."""
        new_const = Constraint(self.constraint_text)
        # ensure that we don't propagate changes to all existing constraints
        new_const._constraint_list = deepcopy(self._constraint_list)
        new_const._constraint_list.append(other._evaluate)
        new_const.constraint_text += " and " + other.constraint_text

        return new_const

    def __radd__(self, other: Constraint) -> Constraint:  # noqa: D105
        return self.__add__(other)

    def _evaluate(self, value: Any) -> None:
        del value

    def check_if_value_meets_constraint(self, value: Any) -> None:
        """Compare the provided value against all constraint.

        Args:
            value (Any): Value to be compared

        Raises:
            InvalidConfiguration: If the value is not met

        """
        for evaluator in self._constraint_list:
            evaluator(value)

    def __str__(self) -> str:  # noqa: D105
        return self.constraint_text

    def __repr__(self) -> str:  # noqa: D105
        return self.constraint_text

    def __call__(self, value: Any) -> None:
        """Call the self.check_if_value_meets_constraint."""
        self.check_if_value_meets_constraint(value)


class ValueInInterval(Constraint):
    """Constraint that imposes the provided value to be inside a given interval."""

    def __init__(self, interval: tuple[Any, Any], include_edges: bool = False):
        """Instantiate the ValueInInterval class.

        Args:
            interval (Tuple): Tuple of the two edges of the interval
            include_edges (bool, optional): Include the edge in the comparison.
                Defaults to False.

        """
        super().__init__(
            const_text=f"Value inside interval <{interval}>; Edges: {include_edges}",
        )
        self._interval = interval
        self._include_edges = include_edges

    def _evaluate(self, value: Any) -> None:
        good_value = False
        try:
            if self._include_edges:
                if self._interval[0] <= value <= self._interval[1]:
                    good_value = True
            elif self._interval[0] < value < self._interval[1]:
                good_value = True
        except TypeError as exc:
            msg = f"Config value can't be compared with the the interval: {value} ({type(value)}) vs {self._interval}"
            raise InvalidConfiguration(msg) from exc

        if not good_value:
            msg = f"Config value is not inside the interval: {value} vs {self._interval}"
            raise InvalidConfiguration(msg)


class ValueFromDtype(Constraint):
    """Constraint that limits the datatype of the input."""

    def __init__(self, dtype_list: tuple[type, ...]) -> None:
        """Constraint that limits the datatype of the input.

        Args:
            dtype_list (List[type]): Valid data types

        """
        super().__init__(const_text=f"Value from dtype <{dtype_list}>")
        self.valid_dtypes = dtype_list

        if not isinstance(dtype_list, tuple):
            msg = "Dtype list must be a tuple"
            raise InternalError(msg)

    def _evaluate(self, value: Any) -> None:
        if not isinstance(value, self.valid_dtypes):
            msg = f"Config value ({value}) not from" f"the valid dtypes: {type(value)} vs {self.valid_dtypes}"
            raise InvalidConfiguration(
                msg,
            )


class ValueFromIterable(Constraint):
    """Limits the possible values to be inside a list."""

    def __init__(self, available_options: Iterable[Any]) -> None:
        """Limits the possible values that the input can take.

        Args:
            available_options (Tuple[Any]): Tuple with the allowed values for this input

        """
        super().__init__(const_text=f"Value from list <{available_options}>")
        self.available_options = available_options
        if not isinstance(available_options, Iterable):
            msg = "The available options must be an iterable"
            raise InternalError(msg)

    def _evaluate(self, value: Any) -> None:
        bad_value = False
        if isinstance(value, (list, tuple)):
            for element in value:
                if element not in self.available_options:
                    bad_value = True
                    break
        elif isinstance(self.available_options, type) and not isinstance(
            value,
            self.available_options,
        ):
            # The value in Enum does not work properly before python3.12
            bad_value = True
        elif value not in self.available_options:
            bad_value = True

        if bad_value:
            msg = f"Config value not one of the valid ones: {value} vs {self.available_options}"
            raise InvalidConfiguration(
                msg,
            )


class IterableMustHave(Constraint):
    """Imposes that certain values must be inside a given iterable."""

    def __init__(self, available_options: tuple[Any, ...], mode: str = "all") -> None:
        """Imposes that certain values must be inside the passed iterable object.

        Args:
            available_options (Tuple[Any]): Tuple with values that must be present in the iterable
            mode (str, optional): "all" if we want all values present in the iterable,
            "any" if we want at least one of them. Defaults to "all".

        """
        super().__init__(const_text=f"Must have value from list <{available_options}>")
        self.available_options = available_options
        self.mode = mode

        if mode not in ["all", "any"]:
            msg = "Using the wrong mode"
            raise InternalError(msg)

    def _evaluate(self, value: Any) -> None:
        if not isinstance(value, Iterable):
            msg = "Constraint needs a iterable object"
            raise InvalidConfiguration(msg)

        evaluation = [i in value for i in self.available_options]

        good_value = False

        if self.mode == "all":
            good_value = all(evaluation)
        elif self.mode == "any":
            good_value = any(evaluation)

        if not good_value:
            raise InvalidConfiguration(
                f"Config value {value} does not" " have {self.mode} of {self.available_options}",
            )


class PathExists(Constraint):
    """Imposes that a given path must exist."""

    def __init__(self) -> None:
        """Imposes that a given path exists."""
        super().__init__(const_text="The path must exist")

    def _evaluate(self, value: Any) -> None:
        if not Path(value).exists():
            raise InvalidConfiguration(f"Path {value} does not exist")


constraint_map = {
    "ValueInInterval": ValueInInterval,
    "ValueFromDtype": ValueFromDtype,
    "IterableMustHave": IterableMustHave,
    "ValueFromList": ValueFromIterable,
}

Positive_Value_Constraint = ValueInInterval((0, np.inf), include_edges=True)
StringValue = ValueFromDtype((str,))
PathValue = ValueFromDtype((str, Path)) + PathExists()
NumericValue = ValueFromDtype((int, float))
IntegerValue = ValueFromDtype((int,))
BooleanValue = ValueFromDtype((bool,))


predefined_constraints = {
    "Positive_Value_Constraint": Positive_Value_Constraint,
    "StringValue": StringValue,
    "PathValue": PathValue,
    "NumericValue": NumericValue,
    "IntegerValue": IntegerValue,
    "BooleanValue": BooleanValue,
}
