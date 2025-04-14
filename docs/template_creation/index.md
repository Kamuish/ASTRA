# Template creation

In ASTRA, the interface to generate stellar and telluric templates is quite similar. Both support the same API functions, albeit to different goals. In short, they provide us with:

1) Internal storage and load from disk files (for re-utilization purposes)
   
2) Common interface to access wavelength and "fluxes"/masks of the templates 

Internally, they are constructed individually for each sub-Instrument that we have available to us