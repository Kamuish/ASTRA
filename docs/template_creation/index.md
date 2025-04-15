# Template creation

In ASTRA, the interface to generate stellar and telluric templates is quite similar. Both support the same API functions, albeit to different goals. In short, they provide us with:

1) Internal storage and load from disk files (for re-utilization purposes)
   
2) Common interface to access wavelength and "fluxes"/masks of the templates 

Internally, they are constructed individually for each sub-Instrument that we have available to us.

The templates will be constructed and automatically saved to disk, under the specified disk path. If ASTRA finds a pre-existing template in that storage path, it will instead load the previous template to memory (unless it is forced to construct a new one). 