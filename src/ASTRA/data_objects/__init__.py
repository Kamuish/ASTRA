from ASTRA.utils.concurrent_tools.proxyObjects import DataClassManager

from .DataClass import DataClass

DataClassManager.register("DataClass", DataClass)
