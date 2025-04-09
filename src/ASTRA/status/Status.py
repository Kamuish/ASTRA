"""Class to represent the state of one observation or model.

The Status represents the overall state of a given piece of data. It will
contain the information from multiple *Flag*s that together will either make the
corresponding information usable or not.

It will store Flags (valid or fatal), as well as the warnings that are collected at runtime

Raises:
    RuntimeError: _description_
    NotImplementedError: _description_

"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from loguru import logger

from ASTRA.status.flags import SUCCESS, VALID, Flag


class Status:
    """Store the combined state for an object, which can be a combination of multiple flags."""

    def __init__(self, assume_valid: bool = True):
        """Instantiate a Status object.

        Args:
            assume_valid (bool, optional): If True, start the object with a valid state. Defaults to True.

        """
        self._stored_flags: set[Flag] = set()
        self._assume_valid = assume_valid
        if assume_valid:
            self.store_flag(VALID)

        self._warnings: set[Flag] = set()

    def store_flag(self, new_flag: Flag | Iterable[Flag]) -> None:
        """Store a new flag.

        Args:
            new_flag (Flag | Iterable[Flag]): New flag to store within the object.

        """
        if isinstance(new_flag, Iterable):
            for entry in new_flag:
                self._stored_flags.add(entry)
        else:
            self._stored_flags.add(new_flag)

    def has_flag(self, flag: Flag) -> bool:
        """Check if a given flag exists in the current Status."""
        return flag in self._stored_flags

    def check_if_warning_exists(self, flag: Flag) -> bool:
        """Check if a given warning exists in the current Status."""
        return flag in self._warnings

    def delete_flag(self, flag: Flag) -> None:
        """Remove a given flag exists in the current Status."""
        try:
            self._stored_flags.remove(flag)
        except KeyError:
            logger.warning("Trying to remove flag that doesn't exist (flag)")

    ###
    #   Adding new flags
    ###

    def store_warning(self, warning_flag: Flag) -> None:
        """Store a warning in the Status.

        Args:
            warning_flag (Flag): Warning to store

        Raises:
            RuntimeError: If the flag is not considered to be a warning

        """
        if not warning_flag.is_warning:
            raise RuntimeError("Trying to store an error as a warning")

        self._warnings.add(warning_flag)

    def __add__(self, other: Flag) -> Status:  # noqa: D105
        """Add a new flag to the status."""
        self.store_flag(other)
        return self

    def __radd__(self, other: Flag) -> Status:  # noqa: D105
        return self.__add__(other)

    def __eq__(self, other: Any) -> bool:  # noqa: D105
        if other == SUCCESS:
            return self.is_valid
        raise NotImplementedError("Can only compare a status with SUCCESS")

    def reset(self) -> None:
        """Fully reset a Status and clean all flags (keeps warnings).

        If the status was previously assumed to be assumed valid, it makes it so
        """
        self._stored_flags = set()
        if self._assume_valid:
            self.store_flag(VALID)

    ###
    #   Status properties
    ###

    @property
    def all_flags(self) -> set[Flag]:
        """Return a set of all flags in the Status."""
        return self._stored_flags

    @property
    def all_warnings(self) -> set[Flag]:
        """Return a set of all warnings in the Status."""
        return self._warnings

    @property
    def number_warnings(self) -> int:
        """Return the number of flags in the Status."""
        return len(self._warnings)

    @property
    def has_warnings(self) -> bool:
        """Return the number of warnings in the Status."""
        return len(self._warnings) != 0

    @property
    def is_valid(self) -> bool:
        """Check the validity of the Status.

        If we don't have any fatal flag, it will be valid
        If it has no flags at all (no VALID one) it also assumes it is not valid

        """
        valid = True

        for flag in self._stored_flags:
            if flag.is_fatal:
                valid = False
                break
        if len(self._stored_flags) == 0:
            valid = False
            logger.warning("Status has NO stored flags (i.e. no SUCCESS flag found)")
        return valid

    ###
    #   String representation of Status
    ###
    def get_rejection_reasons(self) -> str:
        """Construct a string with all flags that were used to reject this object."""
        rejection = ""
        for flag in self._stored_flags:
            if not flag.is_good_flag:
                rejection += flag.name + " "
        return rejection

    def description(self, indent_level: int = 0) -> tuple[list[str], dict]:
        """Create String to directly place on a txt file.

        Args:
            indent_level (int, optional): Number of tabs to place on each line. Defaults to 0.

        Returns:
            tuple[list[str], dict]: String ready to export to file.

        """
        skip_reasons: dict[str, dict[str, str | None]] = {"Warnings": {}, "Rejections": {}}

        indent_character = "\t"
        base_indent = indent_level * indent_character

        message = [base_indent + f"Current Status - valid = {self.is_valid}"]

        message.append("\n" + base_indent + indent_character + "Rejection Flags:")
        if not self.is_valid:
            for flag in self._stored_flags:
                if not flag.is_good_flag:
                    message.append("\n" + base_indent + 2 * indent_character + f"{flag.name} : {flag.extra_info}")

                    skip_reasons["Rejections"][flag.name] = flag.description
        else:
            message.append("\n" + base_indent + 2 * indent_character + "No Rejection")

        if self.has_warnings:
            message.append("\n" + base_indent + indent_character + "Warning Flags:")
            for flag in self._warnings:
                message.append("\n" + base_indent + 2 * indent_character + f"{flag.name} : {flag.extra_info}")

                skip_reasons["Warnings"][flag.name] = flag.description

        return message, skip_reasons

    def __str__(self) -> str:  # noqa: D105
        return f"Flags = {[i.name for i in self._stored_flags]}; valid = {self.is_valid}"

    def __repr__(self) -> str:  # noqa: D105
        return str(self)

    def to_json(self) -> dict[str, Any]:
        """Transform the Status into a json-compatible dict."""
        out = {}
        out["flags"] = [i.to_json() for i in self._stored_flags]
        out["warnings"] = [i.to_json() for i in self._warnings]
        return out
