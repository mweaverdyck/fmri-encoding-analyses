# searchlight
import warnings
import sys
if not sys.warnoptions:
    warnings.simplefilter("ignore")

# Import libraries
#import nibabel as nib
#import numpy as np
#import os
import time
from nilearn import plotting
from brainiak.searchlight.searchlight import Searchlight
from brainiak.fcma.preprocessing import prepare_searchlight_mvpa_data
from brainiak import io
from pathlib import Path
#from shutil import copyfile

# Import rsa functions
from funcs import *
from rsa_funcs import *

import matplotlib.pyplot as plt
#import seaborn as sns

print(str(datetime.now()) + ": Begin rsa_sl.py")

all_sub = []
tasks=[]
# read in arguments
for arg in sys.argv[1:]:
    if arg in TASKS or arg == 'avg':
        tasks += [arg]
    else:
        all_sub += [arg]

if len(tasks) == 0:
    tasks = ['avg']

# print variables to log file
print(str(datetime.now()) + ": Project directory = " + PROJECT_DIR)
print(str(datetime.now()) + ": Analyzing " + str(len(all_sub)) + " subjects: " + str(all_sub))

# set variables
procedure=SL
corr = 'corr'
corr_label = 'spear' if corr=='corr' else 'reg'
val_label = 'r' if corr=='corr' else 'beta'
parc_label = SL+str(SL_RADIUS) if isSl(procedure) else str(N_PARCELS)
deg_label = 'deg'
dist_label = 'dist'

# subject-general predictors:
deg = np.array([1, 4, 2, 2, 3, 4, 2, 3, 2, 3])
dist_mat = np.array([
       [0, 2, 3, 3, 3, 2, 3, 3, 3, 1],
       [2, 0, 1, 1, 1, 2, 3, 3, 3, 1],
       [3, 1, 0, 2, 1, 3, 4, 4, 4, 2],
       [3, 1, 2, 0, 1, 3, 4, 4, 4, 2],
       [3, 1, 1, 1, 0, 3, 4, 4, 4, 2],
       [2, 2, 3, 3, 3, 0, 1, 1, 1, 1],
       [3, 3, 4, 4, 4, 1, 0, 1, 2, 2],
       [3, 3, 4, 4, 4, 1, 1, 0, 1, 2],
       [3, 3, 4, 4, 4, 1, 2, 1, 0, 2],
       [1, 1, 2, 2, 2, 1, 2, 2, 2, 0]])

# Degree RDM
deg_tri = make_model_RDM(deg)
print(str(datetime.now()) + ": Degree RDM: ")
print(squareform(deg_tri))

# Distance RDM
dist_tri = squareform(dist_mat)
print(str(datetime.now()) + ": Distance RDM: ")
print(dist_mat)

# social network RDM dictionary
sn_rdms = {deg_label: deg_tri, dist_label: dist_tri}

# MASK
# reference image for saving parcellation output
parcellation_template = nib.load(MNI_PARCELLATION, mmap=False)
parcellation_template.set_data_dtype(np.double)
sub_mask_fname = FMRIPREP_DIR + '%s/func/%s_task-%s*_space-'+SPACE+'_desc-brain_mask.nii.gz'
# Set printing precision
np.set_printoptions(precision=2, suppress=True)

# run regression for each subject
for s in all_sub:
    # get correct form of subID
    sub=convert2subid(s)
    print(str(datetime.now()) + ": Analyzing subject %s" % sub)
    print(str(datetime.now()) + ": Reading in data for subject " + sub)

    model_keys = sn_rdms.keys()
    print(str(datetime.now())+ ": Using models ")
    print(model_keys)
    out_tasks = {}
    # iterate through inputted tasks
    for task in tasks:
        print(str(datetime.now()) + ": Starting task " + task)

        # load all functional masks and make largest mask
        t = task if task in TASKS else "*"
        print(str(datetime.now()) + ": Reading in masks")
        func_mask_names = glob.glob(sub_mask_fname % (sub, sub, t))
        for i,m in enumerate(func_mask_names):
            print(m)
            m_data = load_nii(m)
            if i == 0:
                m_sum = deepcopy(m_data)
            else:
                m_sum += m_data
        whole_brain_mask = np.where(m_sum > 0, 1, 0)

        # read in subject's image
        sub_template = nib.load(data_fnames % (sub, sub, TASKS[0], 0), mmap=False)
        sub_dims = sub_template.get_data().shape + (N_NODES,)
        sub_data = np.empty(sub_dims)
        ref_img = sub_template
        for n in range(N_NODES):
            print(str(datetime.now()) + ": Reading in node " + str(n))
            if task=='avg':
                # average this node's data from both runs
                d1 = load_nii(data_fnames % (sub, sub, TASKS[0], n))
                d2 = load_nii(data_fnames % (sub, sub, TASKS[1], n))
                d = (d1+d2)/2
            else:
                d = load_nii(data_fnames % (sub, sub, task, n))
            # save to fourth dimension
            sub_data[:,:,:,n] = d

        # Preset the variables to be used in the searchlight
        data = sub_data
        mask = whole_brain_mask
        bcvar = range(N_NODES) #None
        sl_rad = int(SL_RADIUS)
        max_blk_edge = 5
        pool_size = 1

        # We will get back to these commands once we finish running a simple searchlight.
        #comm = MPI.COMM_WORLD
        #rank = comm.rank
        #size = comm.size

        # Start the clock to time searchlight
        begin_time = time.time()

        # Create the searchlight object
        sl = Searchlight(sl_rad=sl_rad,max_blk_edge=max_blk_edge)
        print("Setup searchlight inputs")
        print("Input data shape: " + str(data.shape))
        print("Input mask shape: " + str(mask.shape) + "\n")

        # Distribute the information to the searchlights (preparing it to run)
        sl.distribute([data], mask)
        # Data that is needed for all searchlights is sent to all cores via the sl.broadcast function. In this example, we are sending the labels for classification to all searchlights.
        sl.broadcast(bcvar)

        # turn model dictionary into matrix, s.t. column = model RDM lower triangle
        for i,k in enumerate(model_keys):
            model_rdm = sn_rdms[k]
            def calc_rsa(data, sl_mask, myrad, bcvar, model_mat=model_rdm):
                data4D = data[0]
                labels = bcvar
                bolddata_sl = data4D.reshape(sl_mask.shape[0] * sl_mask.shape[1] * sl_mask.shape[2], data[0].shape[3]).T
                roi_tri = pdist(bolddata_sl, metric='correlation')
                roi_tri[np.isnan(roi_tri)] = 0.
                rho, pval = spearmanr(roi_tri, model_mat)
                return rho

            print("Begin Searchlight\n")
            sl_result = sl.run_searchlight(calc_rsa, pool_size=pool_size)
            print("End Searchlight\n")

            end_time = time.time()

            # Print outputs
            print("Number of searchlights run: " + str(len(sl_result[mask==1])))
            print("Rho values for each kernel function: " +str(sl_result[mask==1].astype('double')))
            print('Total searchlight duration (including start up time): %.2f' % (end_time - begin_time))

            # Save the results to a .nii file
            sl_result = sl_result.astype('double')  # Convert the output into a precision format that can be used by other applications
            sl_result[np.isnan(sl_result)] = 0  # Exchange nans with zero to ensure compatibility with other applications
            fname = out_fname % (sub, corr_label, sub, task, corr_label, parc_label, val_label, k)
            save_nii(sl_result, ref_img, fname)

print(str(datetime.now()) + ": End rsa_sl.py")