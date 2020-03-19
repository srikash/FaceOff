# FaceOff

![](https://gitlab.com/skash/images-and-gifs/-/raw/master/face-off/faceoff.gif)

**An ANTs-based commandline utility to deface whole-head anatomical MRI images.**

***

A sub-set of the OASIS ANTs template files are used. The complete ANTs OASIS Template and Priors can be found here:\
[1] Source: [https://ndownloader.figshare.com/files/3133832](https://ndownloader.figshare.com/files/3133832)\
[2] Mirror: [https://gitlab.com/skash/antstemplatesmirror/-/blob/master/ANTs_OASIS_Template_and_Priors.zip](https://gitlab.com/skash/antstemplatesmirror/-/blob/master/ANTs_OASIS_Template_and_Priors.zip)

If you use this template, please cite:\
Avants, Brian; Tustison, Nick (2018): ANTs/ANTsR Brain Templates. figshare. Dataset. https://doi.org/10.6084/m9.figshare.915436.v2

***

## Example use

`FaceOff -i sub-01-mp2rage-t1w.nii.gz -n 12`

#### Face-ON
![face_on](https://gitlab.com/skash/images-and-gifs/-/raw/master/face-off/0_face_on.png)

#### Face-OFF
![face_off](https://gitlab.com/skash/images-and-gifs/-/raw/master/face-off/1_face_off.png)