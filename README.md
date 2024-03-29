# FaceOff [![DOI](https://zenodo.org/badge/307797054.svg)](https://zenodo.org/badge/latestdoi/307797054)

ANTs-based commandline utility to deface anatomical MRI images and optionally, depad the images off dielectric pads (7 T specific).
***
A sub-set of the OASIS ANTs template files are used. The complete ANTs OASIS Template and Priors can be found here:\
Source: [https://ndownloader.figshare.com/files/3133832](https://ndownloader.figshare.com/files/3133832)\

If you use this template, please cite:\
Avants, Brian; Tustison, Nick (2018): ANTs/ANTsR Brain Templates. figshare. Dataset. https://doi.org/10.6084/m9.figshare.915436.v2

***

## How-To: 

### Make sure everything is findable
`echo "export PATH=$PATH:/path/to/faceoff" >> ~/.bashrc`

### Example use

`FaceOff -i sub-01-mp2rage-t1w.nii.gz -n 12`

#### Before
![face_on](https://gitlab.com/skash/images-and-gifs/-/raw/master/face-off/0_face_on.png)

#### After
![face_off](https://gitlab.com/skash/images-and-gifs/-/raw/master/face-off/1_face_off.png)

![](https://gitlab.com/skash/images-and-gifs/-/raw/master/face-off/faceoff.gif)
