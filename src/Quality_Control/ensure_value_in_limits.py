"""Ensure that a value is inside its correct bounds."""

from loguru import logger

from ASTRA.utils import custom_exceptions


def ensure_value_in_window(tentative_value: float, desired_interval: tuple[float, float]) -> None:
    """Ensure that a given radial velocity is inside the effective RV limits.

    (defined by the window centered in the previous RV estimate)

    Args:
        tentative_value (float): Current RV
        desired_interval (tuple[float, float]): Tuple with the RV limits

    Raises:
        InvalidConfiguration: If the RV is outside the window, raises error

    """
    if not desired_interval[0] <= tentative_value <= desired_interval[1]:
        msg = f"Using value outside the effective limit: {tentative_value} / {desired_interval}"
        logger.critical(msg)
        raise custom_exceptions.InvalidConfiguration(msg)
