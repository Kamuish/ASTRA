"""Base class for ASTRA objects.

Presents a common set of routines  for all objects, mainly controlling:

1) internal link to disk paths
2) general options, such as the SAVE_DISK_SPACE and WORKING_MODE

Raises:
    custom_exceptions.InvalidConfiguration: _description_
    custom_exceptions.InvalidConfiguration: _description_

"""

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Dict, Optional

from ASTRA.status.flags import Flag
from ASTRA.status.Status import Status
from ASTRA.utils import custom_exceptions
from ASTRA.utils.ASTRAtypes import UI_DICT, UI_PATH
from ASTRA.utils.choices import DISK_SAVE_MODE, WORKING_MODE
from ASTRA.utils.parameter_validators import ValueFromIterable
from ASTRA.utils.paths_tools.PathsHandler import Paths
from ASTRA.utils.UserConfigs import DefaultValues, InternalParameters, UserParam


class BASE:
    """Base class, for almost all of SBART objects.

    Inheriting from this class brings a common interface for SBART's User parameters and handling of disk paths.

    """

    _object_type = ""
    _name = ""

    _default_params = DefaultValues(
        SAVE_DISK_SPACE=UserParam(
            DISK_SAVE_MODE.DISABLED,
            constraint=ValueFromIterable(DISK_SAVE_MODE),
            description="Save disk space in the outputs if different than None",
        ),
        WORKING_MODE=UserParam(
            default_value=WORKING_MODE.ONE_SHOT,
            constraint=ValueFromIterable(WORKING_MODE),
            description="How to store the output files. If one-shot, overwrites all files, otherwise updates products",
        ),
    )

    def __init__(
        self,
        user_configs: Optional[UI_DICT] = None,
        root_level_path: Optional[UI_PATH] = None,
        needed_folders: Optional[Dict[str, str]] = None,
        start_with_valid_status: bool = True,
        quiet_user_params: bool = False,
    ):
        """Instantiate a new object.

        Args:
            user_configs (Optional[UI_DICT], optional): User-provided dictionary with configurations.
                Defaults to None, which is interpreted as empty list.
            root_level_path (Optional[UI_PATH], optional): Main storage folder for this object. Defaults to None.
            needed_folders (Optional[Dict[str, str]], optional): dictionary of internal path names
                and relative (to root_level_path) paths. Defaults to None.
            start_with_valid_status (bool, optional): The object is instantiated with a valid status. Defaults to True.
            quiet_user_params (bool, optional): Avoid logging at run-time. Defaults to False.

        """
        self._internal_configs = InternalParameters(
            self.name,
            self._default_params,
            no_logs=quiet_user_params,
        )

        if user_configs is None:
            user_configs = {}

        self._internalPaths: Paths = Paths(root_level_path=root_level_path, preconfigured_paths=needed_folders)

        self._internal_configs.receive_user_inputs(user_configs)
        self._needed_folders = needed_folders
        self._status = Status(assume_valid=start_with_valid_status)  # BY DEFAULT IT IS A VALID ONE!

    def update_user_configs(self, new_configs: dict[str, Any]) -> None:
        """Update the current configurations with new values."""
        self._internal_configs.update_configs_with_values(new_configs)

    @property
    def disk_save_level(self) -> DISK_SAVE_MODE:
        """Return the current disk save level for this object."""
        return self._internal_configs["SAVE_DISK_SPACE"]

    @property
    def work_mode(self) -> WORKING_MODE:
        """Return the current working mode for this object."""
        return self._internal_configs["WORKING_MODE"]

    def update_work_mode_level(self, level: WORKING_MODE) -> None:
        """Update the disk save level."""
        if self.disk_save_level != level:
            self._internal_configs.update_configs_with_values({"WORKING_MODE": level})

    def update_disk_saving_level(self, level: DISK_SAVE_MODE) -> None:
        """Update the work level of the current object."""
        if self.disk_save_level != level:
            self._internal_configs.update_configs_with_values({"SAVE_DISK_SPACE": level})

    ###
    #   Data storage
    ###

    def trigger_data_storage(self, *args: Any, **kwargs: Any) -> None:
        """To be implemented by child classes."""
        ...

    def json_ready(self) -> Dict[str, Any]:
        """Convert current class into a json entry.

        Returns:
            Dict[str, Any]: json-compatible dictionary

        """
        return {}

    def generate_root_path(self, storage_path: Path, no_logs: bool = True) -> None:
        """Generate root storage folder in memory."""
        if not isinstance(storage_path, (str, Path)):
            raise custom_exceptions.InvalidConfiguration(
                f"The root path must be a string or Path object, instead of {storage_path}",
            )

        if not isinstance(storage_path, Path):
            storage_path = Path(storage_path)

        self._internalPaths.add_root_path(storage_path)

    def add_relative_path(self, path_name: str, relative_structure: str) -> None:
        """Add a new relative path to internal structure.

        Args:
            path_name (str): Keyword that will be used to specify the new path
            relative_structure (str): relative path in relation to the root one

        """
        self._internalPaths.add_relative_path(path_name, relative_structure)

    ###
    #   Handling the status of the sBART objects
    ###

    def add_to_status(self, new_flag: Flag) -> None:
        """Add a new flag to the status of this object.

        Args:
            new_flag (Flag): New flag to be added into the status

        """
        self._status.store_flag(new_flag=new_flag)

    def _data_access_checks(self) -> None:
        """Ensure that the status of the ASTRA object is valid.

        This is a very broad check of validity that is overloaded
        in multiple places in the code

        Raises
        ------
            InvalidConfiguration: If the object is not valid

        """
        if not self.is_valid:
            raise custom_exceptions.InvalidConfiguration(
                "Attempting to access data from sBART object that is not "
                f"valid. Check previous log messages for further information: {self._status}",
            )

    def load_from_file(self, root_path: Path, loading_path: str) -> None:
        """Load from file, to be overriden."""
        self.generate_root_path(root_path)

    ###
    #  Properties
    ###
    def is_object_type(self, type_to_check: str) -> bool:
        """Check if this object is of a given 'type'."""
        return self._object_type == type_to_check

    @property
    def is_valid(self) -> bool:
        """Check if object only has 'good' flags."""
        return self._status.is_valid

    @property
    def name(self) -> str:
        """Representation name."""
        return f"{self.__class__._object_type} - {self.__class__._name}"

    @property
    def storage_name(self) -> str:
        """Storage name of object."""
        return self.__class__._name

    @property
    def disk_save_enabled(self) -> bool:
        """True if there is any sort of disk savings active."""
        return self.disk_save_level != DISK_SAVE_MODE.DISABLED

    @classmethod
    def config_help(cls) -> None:
        """Print terminal all possible configurations and their constraints."""
        print(cls._default_params)

    @classmethod
    def control_parameters(cls) -> Iterable[str]:
        """Retrieve all default parameters of object."""
        return cls._default_params.keys()
