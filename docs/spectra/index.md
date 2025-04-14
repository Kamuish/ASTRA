# Accessing stellar spectra

ASTRA provides an unyfying framework to interact with the stellar spectra of multiple state-of-the-art instruments. Its usage will ensure that our methods will be fully agnostic to the spectropgrah that we use, as they will all comply with the same API.


``` py
from ASTRA.data_objects.DataClass import DataClass
from ASTRA.Instruments import ESPRESSO
```

The *instruments* sub-package provides with a mapping between a text-based name and ASTRA's class:

``` py
from ASTRA.Instruments import instrument_dict
# instrument_dict = {
#     "ESPRESSO": ESPRESSO,
#     "HARPS": HARPS,
# }
```

Internally, the entire ASTRA pipeline is built in such a way that it can process data from multiple "time divisions" of the same instrument individually. For example, it can recognize data from ESPRESSO18 and ESPRESSO19, creating individual stellar templates for each.