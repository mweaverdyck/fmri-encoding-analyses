#!/bin/bash
#$ -cwd
# error = Merged with joblog
#$ -o joblogs/joblog.fmriprep.$JOB_ID.log
#$ -j y
#$ -pe shared 8
#$ -l h_rt=23:00:00,h_data=7G
# Notify when
#$ -m ae
#
# runs fmriprep on inputted subjects

# break if error raised
set -e

# load modules and functions
source funcs
setup_modules $fsl_v $python_v freesurfer/6.0.0 ants/ants-2.2.0 afni ica-aroma itksnap/3.6.0-RC1.QT4 $fmriprep_v

label='FMRIPREP'
in_dir=${RECON_DIR}
out_dir=${FMRIPREP_DIR}
work_dir="${SCRATCH}/fmriprep_work"

begin_script -l ${label} -i ${in_dir} -o ${out_dir} -f numid $@
log_args="${LOG_ARGS}"
subs=( "${SUBS[@]}" )

# run fmriprep
fmriprep ${BIDS_DIR} ${PREP_DIR} --work-dir ${work_dir} --ignore slicetiming --fs-license-file $FREESURFER_HOME/.license participant --participant-label "${SUBS[@]}" --output-spaces ${SPACES[@]} fsaverage --nthreads 8 --omp-nthreads 8 | tee -a ${log_file}

# run motion QA
if [[ $1 == 'all' ]]; then subs='all'; fi
python3 qa_motion.py ${SUBS[@]}

# log end
log_end $log_args
