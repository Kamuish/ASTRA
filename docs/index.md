# Welcome to ASTRA 

This is the documentation of Astrophysical Spectral Tools for Retrieval & Analysis (ASTRA), with a standard implementation of:

- Access to stellar spectra from multiple state-of-the-art spectrographs
- Construction of telluric masks, based on the observations with the worst atmospheric conditions
- Construction of high-SNR stellar templates from the available observations

ASTRA is now working as the low-level data-interface of the [s-BART](https://github.com/iastro-pt/sBART) pipeline for RV extraction and it also allows for:

- Built-in normalization of stellar spectra
- Built-in interpolation of stellar spectra to new wavelength grids
- Smoothing of stellar spectra


## Installation

Installation of ASTRA can be made either through Pypi or through github:


=== "Pypi"

    ``` bash
    pip install ASTRA-spectra
    ```

=== "github"

    ``` sh
    git clone git@github.com:Kamuish/ASTRA.git
    cd ASTRA
    pip install . 
    ```

By default, ASTRA does not install Telfit as it will only be needed for the masking of the telluric features. If this is the goal, it must be installed manually.

## Issues and contribution

Management of any issues to the code, as well as external contribution is done through the *github* repository
