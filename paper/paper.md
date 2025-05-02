---
title: 'Astra: A Python Package for Cross-Instrument Stellar and Telluric Template Construction'
tags:
  - Python
  - astronomy
authors:
  - name: André M. Silva
    orcid: 0000-0003-4920-738X
    affiliation: "1, 2" 
  - name: J. P. Faria
    orcid:  0000-0002-6728-244X
    affiliation: 3 
  - name: Nuno C. Santos
    orcid:  0000-0003-4422-2919
    affiliation: "1, 2" 
  - name: Sérgio G. Sousa
    orcid:  0000-0000-0000-000
    affiliation: 1 
  - name: Pedro T. P. Viana
    orcid:  0000-0000-0000-000
    affiliation: "1, 2" 
  - name: J. H. C. Martins
    orcid:  0000-0002-1532-9082
    affiliation: 1 

affiliations:
 - name: Instituto de Astrofísica e Ciências do Espaço, CAUP, Universidade do Porto, Rua das Estrelas, 4150-762 Porto, Portugal
   index: 1
 - name: Departamento de Física e Astronomia, Faculdade de Ciências, Universidade do Porto, Rua do Campo Alegre, 4169-007 Porto, Portugal
   index: 2
 - name: Département d’astronomie de l’Université de Genève, Chemin Pegasi 51, 1290 Versoix, Switzerland 
   index: 3
date: 23 April 2025
bibliography: paper.bib
---

# Summary

*ASTRA* is Python package that provides a modular, instrument-independent interface for working with high-resolution stellar spectra. Designed to support data from multiple spectrographs — including ESPRESSO [@pepeESPRESSOVLTOnsky2021], HARPS [@2003MsngrHARPS; @pepe_harps_2002], MAROON-X [@maroonx_paper], and CARMENES [@carmenes_paper] — *ASTRA* offers a unified abstraction over their data formats, enabling consistent access to fluxes, wavelengths, uncertainties, and metadata across instruments. Furthermore, it applies the necessary wavelength and flux calibrations that are needed, as described by the official pipelines of each instrument.

In addition to a common interface, *ASTRA* provides internal quality control checks of the observations, automatically divides them into the different sub-datasets that are commonly used by each spectrograph, and provides avenues to dynamically reject observation based on different properties. Furthermore, it also provides routines to mask the spectral imprint of Earth's atmosphere (in the form of telluric lines) and construct high-SNR, data-driven, stellar templates.

This package serves as the backend of the SBART pipeline [@silvaNovelFrameworkSemiBayesian2022] and is designed to be extensible and suitable for integration into larger spectral analysis workflows, enabling the construction of pipelines without having to tailor them to individual instruments. It is implemented in such a way that the user can select to only open in memory a small number of observations, such that it can seamleslly handle datasets with thousands of observations. Furthermore, it makes use of *python*'s autoproxy objects, ensuring a smooth integration with codes that use the *multiprocessing* library to leverage concurrent processing for faster computations. 


# Statement of need

In recent years, multiple ultra-stable, high-resolution spectrographs capable of meter-per-second (or better) radial velocity precision have become central to exoplanet and stellar astrophysics, e.g. HARPS, CARMENES, MAROON-X, and ESPRESSO. While each spectrograph provides high-quality observations, they also use distinct data formats and apply different corrections to the stellar spectra. This hinders the development of generalized analysis pipelines, and often leads to analysis pipelines that are focused on a single instrument. To the best of our knowledge, there is no library that provides a similar interface to access stellar spectra of multiple state-of-the-art spectrographs. 

*ASTRA* was built with the intention of not only providing a common API to access stellar spectra, but also provides:

1. Management of observations -- *ASTRA*  provides a high-level interface for accessing stellar spectra and metadata, built on a memory-efficient design that only loads a minimal number of spectra at a time. This ensures that ASTRA stays responsive, even when dealing with datasets with thousands of observations, at the cost of computational speed when interfacing with the data. This is done through the *autoproxy* interface, ensuring full compatibility with any *multiprocessing*-based application. 
2. Masking of atmospheric features -- When dealing with ground-based spectroscopy, it is important to account for the spectral imprint of our atmosphere (in the form of telluric lines), as well as its yearly variation. *ASTRA* can automatically run *Telfit* [@gulliksonCorrectingTelluricAbsorption2014] to generate a syntethic transmittance model and create a binary mask to reject the position of telluric lines;
3. Construction of high-SNR stellar models -- The construction of high-SNR stellar templates from observations is pivotal for the extraction of precise radial velocities [@zechmeisterSpectrumRadialVelocity2018; @silvaNovelFrameworkSemiBayesian2022; @artigau_linebyline2022], determination of stellar parameters [@SousaSweetCat; @GomesSilvaStellarChar], and characterization of exoplanetary atmospheres [@azevedo_silva_detection_2022; @Stangret2024 ; @Damasceno2024];
4. Dynamically group the observations into different sub-datasets -- Over the lifetime of most state-of-the-art spectrographs they are subjected to instrumental interventions, leading to changes in the instrumental profile and offsets in radial velocities. As a consequence, it is often necessary to divide our data in the time-periods before and after such interventions, to construct individual templates in each. *ASTRA* is pre-configured with the dates of such instruments for all supported spectrographs, divides the observations in each dataset (or sub-Instrument) and creates individual stellar and telluric templates for each;
5. Filtering of observations -- When analysing data, we often reject observations based on metadata information (weather conditions, airmass, among others). Within *ASTRA* the user can dynamically set filters on different properties, with the goal of either fully rejecting the observation, or rejecting it from a specific operation. This means that it is possible to reject an observation for the construction of the stellar template, but not reject it from any subsquent analysis.
6. Masking of wavelength regions -- When dealing with stellar spectra we often need to reject wavelength regions due to different contaminating effects. *ASTRA* creates an internal binary mask for all pixels and allows the rejection of i) Telluric-contaminated regions; ii) Activity-sensitive regions; iii) user-provided wavelength intervals.

As the backend of the SBART pipeline[^1], it is already in use for scientific production, and is well-positioned to support the broader astrophysical community working with high-resolution spectroscopy.

[^1]: Publicly available at https://github.com/iastro-pt/sBART

# Acknowledgements

This work was funded by the European Union (ERC, FIERCE, 101052347). Views and opinions expressed are however those of the author(s) only and do not necessarily reflect those of the European Union or the European Research Council. Neither the European Union nor the granting authority can be held responsible for them. This work was also supported by FCT - Fundação para a Ciência e a Tecnologia through national funds by these grants: UIDB/04434/2020 DOI: 10.54499/UIDB/04434/2020, UIDP/04434/2020 DOI: 10.54499/UIDP/04434/2020, PTDC/FIS-AST/4862/2020, UID/04434/2025.  JPF acknowledges the financial support of the Swiss National Science Foundation (SNSF), supported since May 2022 over the grant 200020_20501.

# References 
