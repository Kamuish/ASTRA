"""Order-wise state for different operations.

Implements a more detailed control of state for order-wise operations, extending the Status interface.
This will allow us to:

1) Keep track of the state of each order of any individual observation
2) If needed, centralize the state of all orders of all observations and compute the common set of bad orders.

Raises:
    custom_exceptions.InvalidConfiguration
    RuntimeError
    RuntimeError
    RuntimeError
    RuntimeError
    custom_exceptions.InvalidConfiguration
    custom_exceptions.InvalidConfiguration
    custom_exceptions.InvalidConfiguration

"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import ujson as json
from loguru import logger

from ASTRA.status.flags import SUCCESS, VALID, Flag
from ASTRA.status.Status import Status
from ASTRA.utils import custom_exceptions
from ASTRA.utils.ASTRAtypes import UI_PATH


class OrderStatus:
    """Store state for a collection of spectral orders.

    The state will be stored in two different ways:

    1) Assuming that we are referring to a single observation (work in the 'line' mode)
    2) Assuming that we are dealing with a cube of N observations, each with M orders (work in the 'matrix' mode)
    """

    def __init__(self, N_orders: int, frameIDs: None | list[int] = None):
        """Instantiate a new object.

        Args:
            N_orders (int): Number of spectral orders
            frameIDs (Optional[List[int]], optional): if not None, list of all frame IDs
            (and see the working mode to 'matrix'). Otherwise, it will assume 'line' mode. Defaults to None.

        Raises:
            custom_exceptions.InvalidConfiguration: If we have repeated frameIDs

        """
        N_epochs = len(frameIDs) if frameIDs is not None else frameIDs

        if frameIDs is not None and len(set(frameIDs)) != len(frameIDs):
            msg = "Using a repeated set of FrameIDs"
            raise custom_exceptions.InvalidConfiguration(msg)

        # we might have invalid frames -> frameIDs are not (necessarily) continuous
        self._stored_frameIDs = frameIDs if frameIDs is not None else [None]
        if N_epochs is not None:
            self._internal_mode = "matrix"
        else:
            self._internal_mode = "line"
        self._OrderStatus: np.ndarray[Status]
        self._generate_status_array(N_orders, N_epochs)

        # TODO: do we want to init to VALID ??
        self._OrderStatus += VALID

    def get_index_of_frameID(self, frameID: int) -> int:
        """Get the internal ID of a frameID."""
        return self._stored_frameIDs.index(frameID)

    def mimic_status(self, frameID: int, other_status: OrderStatus) -> None:
        """Mimic the OrderStatus from a different frame.

        This will copy the flags that are present on the OrderStatus
        of the other frame
        This will NOT copy the warnings


        Args:
            frameID (int): FrameID
            other_status (OrderStatus): OrderStatus of corresponding frame

        """
        order_wise_stats = other_status.get_status_from_order(all_orders=True)
        if not other_status.from_frame:
            msg = "We can only mimic the status of a single frame at a time!"
            raise RuntimeError(msg)

        for order, order_status in enumerate(order_wise_stats):
            for flag in order_status.all_flags:
                self.add_flag_to_order(frameID=frameID, order=order, order_flag=flag)

    def add_flag_to_order(
        self,
        order: Union[List[int], int],
        order_flag: Flag,
        frameID: Optional[int] = None,
        all_frames: bool = False,
    ) -> None:
        """Add a new Flag to a given order, associated witha  frameID.

        Args:
            order (Union[List[int], int]): zero-indexed order number
            order_flag (Flag): New flag
            frameID (Optional[int], optional): If in matrix mode, used to link to a given frameID. Defaults to None.
            all_frames (bool, optional): Update the order of all frames, only in matrix mode. Defaults to False.

        """
        if self._internal_mode == "line":
            self._OrderStatus[0, order] += order_flag
        elif self._internal_mode == "matrix":
            if frameID is None:
                raise custom_exceptions.InvalidConfiguration("None frameID on matrix mode")
            if all_frames:
                self._OrderStatus[:, order] = self._OrderStatus[:, order] + order_flag
            else:
                frame_index = self.get_index_of_frameID(frameID)
                self._OrderStatus[frame_index, order] = self._OrderStatus[frame_index, order] + order_flag

    def worst_rejection_flag_from_frameID(self, frameID: Optional[int] = None, ignore_flags=()) -> Tuple[str, int]:
        """Compute the worst rejection flag across all orders of a frame.

        Args:
            frameID (Optional[int], optional): _description_. Defaults to None.
            ignore_flags (tuple, optional): _description_. Defaults to ().

        Returns:
            Tuple[str, int]: Name of the flag, Number of appearences

        """
        flag_count = {}
        for order, status in enumerate(self.get_status_from_order(frameID=frameID, all_orders=True)):
            for flag in status.all_flags:
                if flag in ignore_flags or flag.is_good_flag:
                    continue
                if flag not in flag_count:
                    flag_count[flag] = 0
                flag_count[flag] += 1

        max_count = 0
        max_flag = VALID
        for flag, counts in flag_count.items():
            if counts > max_count:
                max_count = counts
                max_flag = flag

        return max_flag.name, max_count

    def get_status_from_order(
        self,
        order: Optional[int] = None,
        frameID: Optional[int] = None,
        all_orders: bool = False,
    ) -> Status:
        """Return the status from a given set of orders for one frame.

        Parameters
        ----------
        order: Optional[int]
            If None, return all orders when the all_orders flag is set to True
        frameID: Optional[int]
            If None, return all orders when the all_orders flag is set to True. Optional when this is used inside the
            from instances of Frame obects
        all_orders: bool
            if True, return the status for all orders of this frame. Default is False


        """
        if self._internal_mode == "line":
            if all_orders:
                return self._OrderStatus[0]
            return self._OrderStatus[0, order]

        # For the matrix mode
        if frameID is None:
            msg = "When we have multiple observations we need a frameID"
            raise RuntimeError(msg)

        epoch = self.get_index_of_frameID(frameID)
        if all_orders:
            return self._OrderStatus[epoch, :]
        return self._OrderStatus[epoch, order]

    @property
    def from_frame(self) -> bool:
        """True if the OrderStatus corresponds to a single Frame."""
        return self._internal_mode == "line"

    @property
    def bad_orders(self) -> set[int]:
        """Get all rejected orders for a frame."""
        if self._internal_mode == "matrix":
            raise RuntimeError("bad_orders is only defined at the Frame level. Use the common_bad_orders property")
        bad_orders = set()
        for order, order_stat in enumerate(self._OrderStatus[0]):
            if not order_stat.is_valid:
                bad_orders.add(order)
        return bad_orders

    @property
    def common_bad_orders(self) -> set[int]:
        """Find the common set of spectral orders that is rejected in all epochs."""
        return np.unique(np.where(self._OrderStatus != SUCCESS)[1])

    def as_boolean(self) -> np.ndarray[bool]:
        """Return boolean matrix of good entries."""
        return np.where(self._OrderStatus == SUCCESS, True, False)

    def _generate_status_array(self, N_orders: int, N_epochs: int) -> None:
        if self._internal_mode == "line":
            self._OrderStatus = np.empty((1, N_orders), dtype=Status)
        elif self._internal_mode == "matrix":
            self._OrderStatus = np.empty((N_epochs, N_orders), dtype=Status)
        else:
            raise RuntimeError("Internal mode not recognized")
        if N_epochs is None:
            N_epochs = 1

        for epoch in range(N_epochs):
            for order in range(N_orders):
                self._OrderStatus[epoch][order] = Status()

    def reset_state_of_frameIDs(self, frameIDs: list[int]) -> None:  # noqa: N802, N803
        """Fully reset the flags of one frame, used in ROLL mode."""
        for frame_id in frameIDs:
            index = self.get_index_of_frameID(frame_id)
            new_row = [Status() for _ in range(self._OrderStatus.shape[1])]
            self._OrderStatus[index] = new_row

    def add_new_epochs(self, N_epochs: int, frameIDs: list[int]) -> None:  # noqa: N803
        """Add a new epoch in the status.

        Args:
            N_epochs (int): Number of epochs to be added, must be > 0
            frameIDs (list[int]): FrameID of the provided observations

        Raises:
            custom_exceptions.InvalidConfiguration: If N_epochs < 0
            custom_exceptions.InvalidConfiguration: If number of epochs is not the same as the one of frmaeIDs
            custom_exceptions.InvalidConfiguration: If one of the frameIDs already exists

        """
        if N_epochs <= 0:
            msg = "Can't add negative rows"
            logger.critical(msg)
            raise custom_exceptions.InvalidConfiguration(msg)
        if len(frameIDs) != N_epochs:
            msg = "Number of frameIDs doesn't match the provided number of epochs"
            logger.critical(msg)
            raise custom_exceptions.InvalidConfiguration(msg)

        for entry in frameIDs:
            if entry in self._stored_frameIDs:
                msg = "Adding a repeat of the same frameID"
                raise custom_exceptions.InvalidConfiguration(msg)

        n_orders = self._OrderStatus.shape[1]
        for _ in range(N_epochs):
            new_line = [Status() for _ in range(n_orders)]
            self._OrderStatus = np.vstack([self._OrderStatus, new_line])
        self._stored_frameIDs.extend(frameIDs)

    ###
    #   Status string representation
    ###

    def description(
        self,
        indent_level: int = 0,
        frameID: Optional[int] = None,
        include_header: bool = True,
        include_footer: bool = True,
    ) -> Tuple[List[str], Dict]:
        """Return string that represents the OrderStatus.

        Args:
            indent_level (int, optional): Amount of tabs to add in each line. Defaults to 0.
            frameID (Optional[int], optional): Specify frameID. Defaults to None.
            include_header (bool, optional): Include header in the output. Defaults to True.
            include_footer (bool, optional): Include footer in output. Defaults to True.

        Returns:
            Tuple[List[str], Dict]: Final textual output; specification of warnings and rejections

        """
        skip_reasons: dict[str, dict[str, str]] = {"Warnings": {}, "Rejections": {}}

        indent_character = "\t"
        base_indent = indent_level * indent_character
        message = []

        if frameID is not None:
            ID_to_process = [frameID]
        else:
            ID_to_process = self._stored_frameIDs

        for frameID in ID_to_process:
            fatal_flag_dict: dict[str, list[str]] = {}
            warning_flag_dict: dict[str, list[str]] = {}

            if include_header:
                message.append(f"\n{base_indent}FrameID:{frameID}")

            for order_number, status in enumerate(self.get_status_from_order(frameID=frameID, all_orders=True)):
                for flag in status.all_flags:
                    if not flag.is_good_flag:
                        if flag.name not in fatal_flag_dict:
                            fatal_flag_dict[flag.name] = []
                        fatal_flag_dict[flag.name].append(order_number)
                        skip_reasons["Rejections"][flag.name] = flag.description

                for flag in status.all_warnings:
                    if flag.name not in warning_flag_dict:
                        warning_flag_dict[flag.name] = []
                    warning_flag_dict[flag.name].append(order_number)
                    skip_reasons["Warnings"][flag.name] = flag.description

            message.append(
                "\n"
                + base_indent
                + indent_character
                + "Order Rejections (Worst - {} -> N = {}):".format(*self.worst_rejection_flag_from_frameID(frameID)),
            )

            for key, orders in fatal_flag_dict.items():
                message.append("\n" + base_indent + 2 * indent_character + f"{key} (N = {len(orders)}): {orders}")

            if len(warning_flag_dict) != 0:
                message.append("\n" + base_indent + indent_character + "Order Warnings:")
                for key, orders in warning_flag_dict.items():
                    message.append("\n" + base_indent + 2 * indent_character + f"{key}: {orders}")
            message.append("\n")

        if include_footer:
            message.append("\n\n" + base_indent + "Rejection reasons:")
            for key, descr in skip_reasons["Rejections"].items():
                message.append("\n" + base_indent + indent_character + f"{key}: {descr}")

            if len(skip_reasons["Warnings"]) != 0:
                message.append("\n" + base_indent + "Warnings:")
                for key, descr in skip_reasons["Warnings"].items():
                    message.append("\n" + base_indent + indent_character + f"{key}: {descr}")
        return message, skip_reasons

    def __str__(self) -> str:  # noqa: D105
        return str(self._OrderStatus)

    def store_as_json(self, storage_path: UI_PATH) -> None:
        """Directly stores to a single file all information inside this class."""
        with open(storage_path, mode="w") as file:
            json.dump(self.to_json(), file, indent=4)

    def to_json(self) -> dict[str | int, Any]:
        """Convert the object to disk-file products."""
        out = {
            "general_confs": {
                "frameIDs": self._stored_frameIDs if self._internal_mode == "matrix" else None,
                "N_orders": self._OrderStatus.shape[1],
            },
        }

        for epoch in range(self._OrderStatus.shape[0]):
            epoch_key = f"frameID::{self._stored_frameIDs[epoch]}"
            out[epoch_key] = {}
            for order in range(self._OrderStatus.shape[1]):
                out[epoch_key][order] = self._OrderStatus[epoch, order].to_json()
        return out

    @classmethod
    def load_from_json(cls, storage_path: UI_PATH) -> None:
        """Load the order status from a disk file."""
        with open(storage_path) as file:
            json_info = json.load(file)

        N_orders = json_info["general_confs"]["N_orders"]
        frameIDs = json_info["general_confs"]["frameIDs"]
        new_stats = OrderStatus(N_orders, frameIDs)

        for frameID_string, values in json_info.items():
            if frameID_string in ["general_confs"]:
                continue

            frameID = frameID_string.split("::")[1]
            for order in range(N_orders):
                for flag_dict in values[str(order)]["flags"]:
                    loaded_frameID = None if frameIDs is None else int(frameID)
                    new_stats.add_flag_to_order(
                        order_flag=Flag.create_from_json(flag_dict),
                        order=order,
                        frameID=loaded_frameID,
                    )
                for flag_dict in values[str(order)]["warnings"]:
                    new_stats.add_flag_to_order(
                        order_flag=Flag.create_from_json(flag_dict),
                        order=order,
                        frameID=int(frameID),
                    )
        return new_stats
