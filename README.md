# ASTRA
[![status](https://joss.theoj.org/papers/d60b535393334128194448349206de6e/status.svg)](https://joss.theoj.org/papers/d60b535393334128194448349206de6e)


Welcome to the repository of ASTRA (Astrophysical Spectral Tools for Retrieval &amp; Analysis). 

The main goal of this project is to standardize the handling of stellar spectra for both RV extraction tools and spectral analysis tools. In order to do so, ASTRA provides:

1) Common interface to interact with stellar spectra of different state-of-the-art instruments
2) Framework to construct stellar templates from data, following best practices
3) Framework to mask telluric features from stellar spectra
4) Implement utility methods to interpolate, normalize and smooth stellar spectra

For information on installation, usage, and contribution check the official [documentation](https://kamuish.github.io/ASTRA/)


## Installation

ASTRA is currently available in python 3.11 and python 3.12, and it can be installed either through

1) Pypi
``` bash
pip install ASTRA-spectra
```

2) Github

``` sh
git clone git@github.com:Kamuish/ASTRA.git
cd ASTRA
pip install . 
```
By default, ASTRA does not install Telfit as it will only be needed for the masking of the telluric features. If this is the goal, it must be installed manually.

## Contribution guidelines


Management of any issues to the code, as well as external contribution is done through the *github* repository
