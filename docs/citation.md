# Citation

If you use FaceOff, please cite FaceOff, the MNI ICBM152 template, and ANTs. Each reference below has an APA 7 line and a BibTeX entry to copy. Details were checked against the publishers' records (PubMed, Crossref, Zenodo) on 2026-11-06.

## Text for your methods section

> Scans were defaced with FaceOff (version 1.9.7; Kashyap, 2026a), which registers each scan to a modified MNI ICBM152 template (Kashyap, 2026b) using the ANTs registration tools (Avants et al., 2011; Tustison et al., 2021).

Change the version number to the one you used, and list the references below in your bibliography (the "a" and "b" tell the two 2026 entries by the same author apart, as APA requires).

You can also cite FaceOff from the `CITATION.cff` file in this repository, or from the Zenodo badge at the top of the README.

## FaceOff

The all-versions DOI always resolves to the latest release. If you want to cite the exact release you used, take its version DOI from the [Zenodo page](https://doi.org/10.5281/zenodo.4626832) and use the matching version number.

APA:

> Kashyap, S. (2026a). *FaceOff* (Version 1.9.7) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.4626832

BibTeX:

```bibtex
@software{kashyap_faceoff,
  author    = {Kashyap, Sriranga},
  title     = {{FaceOff}},
  version   = {1.9.7},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.4626832},
  url       = {https://doi.org/10.5281/zenodo.4626832},
}
```

## The template files

FaceOff registers to a modified version of the MNI ICBM152 2020 template. The modified files are archived on Zenodo. Cite them together with the original template papers in the next section.

APA:

> Kashyap, S. (2026b). *FaceOff Resources* [Data set]. Zenodo. https://doi.org/10.5281/zenodo.23328835

BibTeX:

```bibtex
@dataset{kashyap_faceoff_resources,
  author    = {Kashyap, Sriranga},
  title     = {{FaceOff Resources}},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.23328835},
  url       = {https://doi.org/10.5281/zenodo.23328835},
}
```

## The MNI ICBM152 template

APA:

> Fonov, V., Evans, A. C., Botteron, K., Almli, C. R., McKinstry, R. C., Collins, D. L., & Brain Development Cooperative Group. (2011). Unbiased average age-appropriate atlases for pediatric studies. *NeuroImage, 54*(1), 313–327. https://doi.org/10.1016/j.neuroimage.2010.07.033

> Fonov, V. S., Evans, A. C., McKinstry, R. C., Almli, C. R., & Collins, D. L. (2009). Unbiased nonlinear average age-appropriate brain templates from birth to adulthood. *NeuroImage, 47*(Suppl. 1), S102. https://doi.org/10.1016/S1053-8119(09)70884-5

BibTeX:

```bibtex
@article{fonov2011unbiased,
  author  = {Fonov, Vladimir and Evans, Alan C. and Botteron, Kelly and Almli, C. Robert and McKinstry, Robert C. and Collins, D. Louis and {Brain Development Cooperative Group}},
  title   = {Unbiased average age-appropriate atlases for pediatric studies},
  journal = {NeuroImage},
  year    = {2011},
  volume  = {54},
  number  = {1},
  pages   = {313--327},
  doi     = {10.1016/j.neuroimage.2010.07.033},
}

@article{fonov2009unbiased,
  author  = {Fonov, V. S. and Evans, A. C. and McKinstry, R. C. and Almli, C. R. and Collins, D. L.},
  title   = {Unbiased nonlinear average age-appropriate brain templates from birth to adulthood},
  journal = {NeuroImage},
  year    = {2009},
  volume  = {47},
  number  = {Suppl. 1},
  pages   = {S102},
  doi     = {10.1016/S1053-8119(09)70884-5},
}
```

## ANTs

Please cite both of these. The first is for the toolbox; the second is for the registration algorithm FaceOff uses (the affine and SyN registration with mutual information and cross-correlation).

**The toolbox**

APA:

> Tustison, N. J., Cook, P. A., Holbrook, A. J., Johnson, H. J., Muschelli, J., Devenyi, G. A., Duda, J. T., Das, S. R., Cullen, N. C., Gillen, D. L., Yassa, M. A., Stone, J. R., Gee, J. C., & Avants, B. B. (2021). The ANTsX ecosystem for quantitative biological and medical imaging. *Scientific Reports, 11*, Article 9068. https://doi.org/10.1038/s41598-021-87564-6

BibTeX:

```bibtex
@article{tustison2021antsx,
  author  = {Tustison, Nicholas J. and Cook, Philip A. and Holbrook, Andrew J. and Johnson, Hans J. and Muschelli, John and Devenyi, Gabriel A. and Duda, Jeffrey T. and Das, Sandhitsu R. and Cullen, Nicholas C. and Gillen, Daniel L. and Yassa, Michael A. and Stone, James R. and Gee, James C. and Avants, Brian B.},
  title   = {The {ANTsX} ecosystem for quantitative biological and medical imaging},
  journal = {Scientific Reports},
  year    = {2021},
  volume  = {11},
  pages   = {9068},
  doi     = {10.1038/s41598-021-87564-6},
}
```

**The registration algorithm**

APA:

> Avants, B. B., Tustison, N. J., Song, G., Cook, P. A., Klein, A., & Gee, J. C. (2011). A reproducible evaluation of ANTs similarity metric performance in brain image registration. *NeuroImage, 54*(3), 2033–2044. https://doi.org/10.1016/j.neuroimage.2010.09.025

BibTeX:

```bibtex
@article{avants2011reproducible,
  author  = {Avants, Brian B. and Tustison, Nicholas J. and Song, Gang and Cook, Philip A. and Klein, Arno and Gee, James C.},
  title   = {A reproducible evaluation of {ANTs} similarity metric performance in brain image registration},
  journal = {NeuroImage},
  year    = {2011},
  volume  = {54},
  number  = {3},
  pages   = {2033--2044},
  doi     = {10.1016/j.neuroimage.2010.09.025},
}
```

[Back to the README](../README.md)
