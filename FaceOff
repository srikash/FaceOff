#!/bin/bash

################################################################################
#
# PREPARATIONS
#
################################################################################

if [[ ${#ANTSPATH} -le 3 ]]; then
    setPath >&2
fi

ANTS=${ANTSPATH}/antsRegistration

if [[ ! -s ${ANTS} ]]; then
    echo "antsRegistration can't be found. Please (re)define $ANTSPATH in your environment."
    exit
fi

SCRIPT_LOCATION=$(which FaceOff)
SCRIPT_DIR=$(dirname "${SCRIPT_LOCATION}")
TEMPLATE_DIR="${SCRIPT_DIR}/tempData"

################################################################################
# Simple formatting

bold=$(tput bold)
normal=$(tput sgr0)

################################################################################
# Define help message
function usage {
    echo "Usage: $(basename $0) [-h] -i <input_file> [-n <n_threads>] [-s <force_syn>] [-d]"
    echo " "
    echo "Options:"
    echo "  -h                           Show this help message and exit."
    echo "  -i <input_file>              Specify the input file for processing. (required)"
    echo "  -n <n_threads>               Specify the number of threads for processing. Default: 1."
    echo "  -s <force_syn>               Specify whether to force the SyN step of ANTS registration. Default: 0."
    echo "  -d <depad>                   Specify whether dielectric pads need to be stripped off. Default: 0."
    echo ""
    echo ""
    echo -e "Script was created by: Sriranga Kashyap (03-2020)\n"
    echo -e "Requires ANTs to be installed and \$ANTSPATH defined in your environment\n"
    echo -e "ANTs can be downloaded here: https://github.com/ANTsX/ANTs\n"
    echo "Cite: "
    echo "(1) http://www.ncbi.nlm.nih.gov/pubmed/20851191"
    echo "(2) http://www.frontiersin.org/Journal/10.3389/fninf.2013.00039/abstract"
}

################################################################################
function reportParameters() {
    echo "--------------------------------------------------------------------------------"
    echo "  ${bold} 0. Initialised with $n_threads threads ${normal}"
    echo "--------------------------------------------------------------------------------"
    echo "  ANTs installation found :   ${bold} $ANTSPATH ${normal}"
    echo "  FaceOff location        :   ${bold} $SCRIPT_DIR ${normal}"
    echo " "
    echo "  Using SyN?              :   ${bold} $issyn ${normal}"
    echo "  Depadding?              :   ${bold} $isdepad ${normal}"
    echo " "
    echo "  Input data              :   ${bold} $input_file ${normal}"
    echo "  Deface mask (output)    :   ${bold} $OUTPUT_MASK_NAME ${normal}"
    echo "  Defaced data (output)   :   ${bold} $OUTPUT_NAME ${normal}"
    echo "--------------------------------------------------------------------------------"
}

################################################################################
#
# PARSE INPUT ARGUMENTS
#
################################################################################
# Parse command-line arguments
while getopts "h:i:n:s:d:" opt; do
    case $opt in
    h)
        usage
        exit 0
        ;;
    i)
        input_file=$OPTARG
        ;;
    n)
        n_threads=$OPTARG
        ;;
    s)
        force_syn=$OPTARG
        ;;
    d)
        depad=$OPTARG
        ;;
    \?)
        echo "Invalid option: -$OPTARG" >&2
        usage
        exit 1
        ;;
    esac
done

# Check if any arguments were provided
if [ $# -eq 0 ]; then
    echo "Please specify at least input argument."
    usage
    exit 1
fi

################################################################################
#
# SET NUMBER OF THREADS
#
################################################################################
if [ -n "$ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS" ]; then
    n_threads=$ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS
else
    n_threads=12
    ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=$n_threads
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS
fi

################################################################################
#
# FUNCTIONS
#
################################################################################
if [[ ! "$input_file" == *\/* ]]; then
    input_file="$PWD/${input_file}"
fi

function remove_extension() {
    filename=$1

    if [[ "$filename" == *.nii.gz ]]; then
        new_filename="${filename%.nii.gz}"
    elif [[ "$filename" == *.nii ]]; then
        new_filename="${filename%.nii}"
    else
        echo "Error: invalid filename extension"
        return 1
    fi

    echo $new_filename
}

OUTPUT_PREFIX=$(remove_extension $input_file)
OUTPUT_MASK_NAME=${OUTPUT_PREFIX}_defaceMask.nii.gz
OUTPUT_NAME=${OUTPUT_PREFIX}_defaced.nii.gz

if [ -z "$force_syn" ]; then
    force_syn=0
    issyn="no"
else
    issyn="yes"
fi

if [ -z "$depad" ]; then
    depad=0
    isdepad="no"
else
    isdepad="yes"
fi

################################################################################
#
# REPORT INPUT PARAMETERS
#
################################################################################

reportParameters

################################################################################
#
# MAP TO TEMPLATE
#
################################################################################
start_time0=$(date +%s)

${ANTSPATH}/antsAI \
    --dimensionality 3 \
    --random-seed 13 \
    --transform AlignCentersOfMass \
    --metric MI[ $TEMPLATE_DIR/OASIS_T1w.nii.gz , $input_file , 32 , Regular , 0.25 ] \
    --output $TEMPLATE_DIR/REG_INPUT_TO_TEMP_INIT.mat

ants_reg_affine='${ANTSPATH}/antsRegistration --verbose 0 --dimensionality 3 --float 0 --collapse-output-transforms 1 --output [ $TEMPLATE_DIR/REG_INPUT_TO_TEMP_, 1 , 1 ] --interpolation Linear --use-histogram-matching 0 --winsorize-image-intensities [ 0.005,0.995 ] -x [ $TEMPLATE_DIR/OASIS_registrationMask.nii.gz, 1 ] --initial-moving-transform [ $TEMPLATE_DIR/OASIS_T1w.nii.gz,$input_file,1 ] --transform Rigid[ 0.1 ] --metric MI[ $TEMPLATE_DIR/OASIS_T1w.nii.gz,$input_file,1,32,Regular,0.25 ] --convergence [ 1000x500x250x100,1e-6,10 ] --shrink-factors 12x8x4x2 --smoothing-sigmas 4x3x2x1vox --transform Affine[ 0.1 ] --metric MI[ $TEMPLATE_DIR/OASIS_T1w.nii.gz,$input_file,1,32,Regular,0.25 ] --convergence [ 1000x500x250x100,1e-6,10 ] --shrink-factors 12x8x4x2 --smoothing-sigmas 4x3x2x1vox'

ants_syn_addon=' --transform SyN[ 0.1,3,0 ] --metric CC[ $TEMPLATE_DIR/OASIS_T1w.nii.gz , $input_file , 1 , 2 ] --convergence [ 50x25,1e-6,10 ] --shrink-factors 2x1 --smoothing-sigmas 1x0vox'

if [ $force_syn -eq 1 ]; then
    echo "  ${bold} Additional SyN stage will be used. ${normal}"
    echo " "

    ants_cmd="$ants_reg_affine$ants_syn_addon"
    eval $ants_cmd

    echo "  ${bold} 1. Mapped to template.    ${normal}"
    echo "--------------------------------------------------------------------------------"

else
    ants_cmd="$ants_reg_affine"
    eval $ants_cmd

    echo "  ${bold} 1. Mapped to template.    ${normal}"
    echo "--------------------------------------------------------------------------------"
fi

################################################################################
#
# APPLY TRANSFORMS
#
################################################################################
if [ $force_syn -eq 1 ]; then
    ${ANTSPATH}/antsApplyTransforms \
        --dimensionality 3 \
        --interpolation GenericLabel \
        --reference-image $input_file \
        --input $TEMPLATE_DIR/OASIS_defaceMask.nii.gz \
        --output $OUTPUT_MASK_NAME \
        --transform $TEMPLATE_DIR/REG_INPUT_TO_TEMP_1InverseWarp.nii.gz \
        --transform [ $TEMPLATE_DIR/REG_INPUT_TO_TEMP_0GenericAffine.mat , 1 ] \
        --verbose 0

    echo "  ${bold} 2. Deface mask created.    ${normal}"
    echo "--------------------------------------------------------------------------------"
else
    ${ANTSPATH}/antsApplyTransforms \
        --dimensionality 3 \
        --interpolation GenericLabel \
        --reference-image $input_file \
        --input $TEMPLATE_DIR/OASIS_defaceMask.nii.gz \
        --output $OUTPUT_MASK_NAME \
        --transform [ $TEMPLATE_DIR/REG_INPUT_TO_TEMP_0GenericAffine.mat , 1 ] \
        --verbose 0

    echo "  ${bold} 2. Deface mask created.    ${normal}"
    echo "--------------------------------------------------------------------------------"

fi

################################################################################
#
# APPLY MASK
#
################################################################################
${ANTSPATH}/ImageMath \
    3 \
    ${OUTPUT_NAME} \
    m \
    $input_file \
    $OUTPUT_MASK_NAME

echo "  ${bold} 3. Defacing completed.    ${normal}"
echo "--------------------------------------------------------------------------------"

if [[ $depad -eq 1 ]]; then
    OUTPUT_MASK_NAME=${OUTPUT_PREFIX}_depadMask.nii.gz
    OUTPUT_NAME=${OUTPUT_PREFIX}_depadded.nii.gz

    ${ANTSPATH}/antsApplyTransforms \
        --dimensionality 3 \
        --interpolation GenericLabel \
        --reference-image $input_file \
        --input $TEMPLATE_DIR/OASIS_dePadMask.nii.gz \
        --output $OUTPUT_MASK_NAME \
        --transform [ $TEMPLATE_DIR/REG_INPUT_TO_TEMP_0GenericAffine.mat , 1 ] \
        --verbose 0

    echo "  ${bold} 4. DePad mask created.    ${normal}"
    echo "--------------------------------------------------------------------------------"
    # Invert DePadMask
    ${ANTSPATH}/ImageMath \
        3 \
        $OUTPUT_MASK_NAME \
        Neg \
        $OUTPUT_MASK_NAME

    ${ANTSPATH}/ImageMath \
        3 \
        ${OUTPUT_PREFIX}_depadded.nii.gz \
        m \
        $input_file \
        $OUTPUT_MASK_NAME

    ${ANTSPATH}/ImageMath \
        3 \
        ${OUTPUT_PREFIX}_combinedMask.nii.gz \
        m \
        ${OUTPUT_PREFIX}_depadMask.nii.gz \
        ${OUTPUT_PREFIX}_defaceMask.nii.gz

    ${ANTSPATH}/ImageMath \
        3 \
        ${OUTPUT_PREFIX}_defaced_depadded.nii.gz \
        m \
        $input_file \
        ${OUTPUT_PREFIX}_combinedMask.nii.gz

    echo "  ${bold} 5. DePadding completed.    ${normal}"
    echo "--------------------------------------------------------------------------------"
fi

end_time0=$(date +%s)
nettime0=$(expr $end_time0 - $start_time0)

################################################################################
#
# CLEAN UP
#
################################################################################

rm $TEMPLATE_DIR/REG_INPUT_TO_TEMP_*.*

################################################################################
#
# DISPLAY DONE
#
################################################################################

echo "  ${bold} 4. FaceOff ended. It took $(($nettime0 / 3600))h:$(($nettime0 % 3600 / 60))m:$(($nettime0 % 60))s.    ${normal}"
echo "================================================================================"
