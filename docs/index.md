# Welcome to ASTRA 

This is the documentation of Astrophysical Spectral Tools for Retrieval & Analysis (ASTRA), with a standard implementation of:

- Access to stellar spectra from multiple state-of-the-art spectrographs
- Construction of telluric masks, based on the observations with the worst atmospheric conditions
- Construction of high-SNR stellar templates from the available observations

ASTRA is now working as the low-level data-interface of the [s-BART](https://github.com/iastro-pt/sBART) pipeline for RV extraction and it also allows for:

- Built-in normalization of stellar spectra
- Built-in interpolation of stellar spectra to new wavelength grids
- Smoothing of stellar spectra

ASTRA supports the 2D stellar spectra format for all supported instruments (S2D_A, S2D_BLAZE_A, S2D_TELL_CORR_A,S2D_TELL_CORR_BLAZE_A for the ESO-based pipelines) and in some cases the S1D format.

## Installation

ASTRA is currently available in python 3.11 and python 3.12, and it can be installed either through Pypi or github:


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

## Troubleshooting

### Installation of TelFit

Depending on the python version that is in use, the installation of TelFit might not be straightforward. For the currently ASTRA_supported python versions, one can apply the following steps to install Telfit:

1. Download TelFit from github
    ``` sh
    git clone https://github.com/kgullikson88/Telluric-Fitter
    cd Telluric-Fitter
    ```
2. Ensure that the "develop" libraries for the selected python version are installated. For Fedora, this would be
    ``` sh
    dnf install python3.11-devel
    ```
3. Install necessary python libraries for TelFit installation
    ``` sh
    pip install cython requests numpy pysynphot lockfile fortranformat
    ```
5. Install Telfit through
    ``` sh
    python setup.py install
    ```


## Changelog

### V1.2.7 (current)

1) Added HARPS-N support 
2) Updated plotting capabilities of DataClass


### V1.2.6


1. Added preliminary support for PoET data
2. Updated spawn method of multiprocessing pools
3. Improved frame-rejection tools


### V1.2.4

1. Update init of ESO based pipelines


### V1.2.3 (5th December 2025)

1. Addition of new routines to oversample the stellar template
2. Sanity check of the input observations, ensuring that they match the expected format

### V1.1.0 (2nd July 2025)

1. Addition of new interpolation algorithms
2. Inclusion of interface to SPIROU simulated data
3. Added BERV_factor to ESO pipelines
4. Improvement of data interface to iterate over template construction

### V1.0.0 (5th of May 2025)

- Original commit, as transposed from sBART internals
- Addition of CARMENES and MAROON-X as valid instruments for analysis
