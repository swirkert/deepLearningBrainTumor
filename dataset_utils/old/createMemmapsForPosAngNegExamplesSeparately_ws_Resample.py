__author__ = 'fabian'
import numpy as np
import skimage
import lmdb
import matplotlib.pyplot as plt
import os.path
import os
import SimpleITK as sitk
import cPickle
import IPython
from numpy import memmap
from skimage.transform import resize
import threading
from multiprocessing.dummy import Pool as ThreadPool

PATCH_SIZE = 128
PERCENT_VAL = 0.15

entries_per_datum = PATCH_SIZE**2 * 2
expected_pos_to_neg_ratio = 10000./126964.
expected_n_samples = 600000

train_neg_shape = (expected_n_samples, entries_per_datum)
train_pos_shape = (int(expected_n_samples * expected_pos_to_neg_ratio), entries_per_datum)
val_neg_shape = (int(expected_n_samples * PERCENT_VAL), entries_per_datum)
val_pos_shape = (int(expected_n_samples * PERCENT_VAL * expected_pos_to_neg_ratio), entries_per_datum)

memmap_name = "patchClassification_ws_resampled"

train_neg_memmap = memmap("%s_train_neg.memmap" % memmap_name, dtype=np.float32, mode="w+", shape=train_neg_shape)
train_pos_memmap = memmap("%s_train_pos.memmap" % memmap_name, dtype=np.float32, mode="w+", shape=train_pos_shape)
val_neg_memmap = memmap("%s_val_neg.memmap" % memmap_name, dtype=np.float32, mode="w+", shape=val_neg_shape)
val_pos_memmap = memmap("%s_val_pos.memmap" % memmap_name, dtype=np.float32, mode="w+", shape=val_pos_shape)

path = "/home/fabian/datasets/Hirntumor_von_David/"
subdirs = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
# subdirs = [os.path.join(path, '017')]
subdirs.sort()
voxels_in_patch = PATCH_SIZE**2


n_positive_train = 0
n_negative_train = 0
n_positive_val = 0
n_negative_val = 0
img_mean = 0

val_dirs = ['001', '002', '004', '005', '006', '007', '008', '009', '011', '012', '013', '014', '015', '016']
labels = []
valid_patient_ids = []
for curr_dir in subdirs:
    test = False
    if curr_dir in val_dirs:
        test = True
    patient_id = os.path.split(curr_dir)[-1]
    print patient_id
    # check if image exists
    if not os.path.isfile(os.path.join(curr_dir, "T1_m2_bc_ws.nii.gz")):
        continue
    if not os.path.isfile(os.path.join(curr_dir, "seg_ce.nii.gz")):
        continue
    if not os.path.isfile(os.path.join(curr_dir, "seg_edema.nii.gz")):
        continue
    if not os.path.isfile(os.path.join(curr_dir, "seg_necrosis_ce.nii.gz")):
        continue
    valid_patient_ids.append(curr_dir)

    # load image
    itk_img = sitk.ReadImage(os.path.join(curr_dir, "T1_m2_bc_ws.nii.gz"))
    seg_ce = sitk.GetArrayFromImage(sitk.ReadImage(os.path.join(curr_dir, "seg_ce.nii.gz"))).astype(np.float)
    seg_edema = sitk.GetArrayFromImage(sitk.ReadImage(os.path.join(curr_dir, "seg_edema.nii.gz"))).astype(np.float)
    seg_necrosis_ce = sitk.GetArrayFromImage(sitk.ReadImage(os.path.join(curr_dir, "seg_necrosis_ce.nii.gz"))).astype(np.float)
    brain_mask = sitk.GetArrayFromImage(sitk.ReadImage(os.path.join(curr_dir, "T1_mutualinfo2_bet_mask.nii.gz"))).astype(np.float)
    t1_image = sitk.GetArrayFromImage(itk_img).astype(np.float)

    assert seg_ce.shape == t1_image.shape
    assert seg_edema.shape == t1_image.shape
    assert seg_necrosis_ce.shape == t1_image.shape
    assert brain_mask.shape == t1_image.shape

    # correct nans
    t1_image_corr = np.array(t1_image)
    isnan_coords = np.where(np.isnan(t1_image))
    if len(isnan_coords[0]) > 0:
        for coord in zip(isnan_coords[0], isnan_coords[1], isnan_coords[2]):
            coord = list(coord)
            region = t1_image[coord[0]-5 : coord[0]+5, coord[1]-5 : coord[1]+5, coord[2]-5 : coord[2]+5]
            t1_image_corr[tuple(coord)] = np.max(region[~np.isnan(region)])
    t1_image = t1_image_corr

    spacing = np.array(itk_img.GetSpacing())[[2, 1, 0]]
    spacing_target = [1, 0.5, 0.5]

    new_shape = (int(spacing[0]/spacing_target[0]*float(t1_image.shape[0])),
                 int(spacing[1]/spacing_target[1]*float(t1_image.shape[1])),
                 int(spacing[2]/spacing_target[2]*float(t1_image.shape[2])))

    # t1_image = resize(t1_image/maxVal, new_shape)
    def resize_star(args):
        return resize(*args)

    outside_value = t1_image[0,0,0]
    pool = ThreadPool(5)
    (t1_image, seg_ce, seg_edema, seg_necrosis_ce, brain_mask) = pool.map(resize_star, [(t1_image, new_shape, 3, 'edge'),
                                                                                                       (seg_ce, new_shape, 1, 'edge'),
                                                                                                       (seg_edema, new_shape, 1, 'edge'),
                                                                                                       (seg_necrosis_ce, new_shape, 1, 'edge'),
                                                                                                       (brain_mask, new_shape, 1, 'edge')])
    pool.close()
    pool.join()

    t1_image = t1_image.astype(np.float32)
    seg_ce = np.round(seg_ce).astype(np.int32)
    seg_edema = np.round(seg_edema).astype(np.int32)
    seg_necrosis_ce = np.round(seg_necrosis_ce).astype(np.int32)
    brain_mask = np.round(brain_mask).astype(np.int32)

    t1_image[brain_mask == 0] = outside_value
    # outside_value = 0
    # t1_image -= outside_value

    # create joint segmentation map (useful for later)
    seg_combined = np.zeros(t1_image.shape, dtype=np.int32)

    # necrosis is 3, ce tumor is 2, edema is 1
    seg_combined[seg_necrosis_ce == 1] = 3
    seg_combined[seg_ce == 1] = 2
    seg_combined[seg_edema == 1] = 1

    # images are brain extracted, they have some funky value everywhere outside of the brain region. we only want
    # slices with enough brain voxels. We can ensure that by counting background pixels

    # iterate over patches
    for z in xrange(t1_image.shape[0]):
        y0 = 0
        # print "z", z
        while (y0 + PATCH_SIZE) < t1_image.shape[2]:
            x0 = 0
            # print "y0", y0
            while (x0 + PATCH_SIZE) < t1_image.shape[1]:
                # print "x0", x0
                patch = t1_image[z, x0:x0+PATCH_SIZE, y0:y0+PATCH_SIZE]
                seg_patch = seg_combined[z, x0:x0+PATCH_SIZE, y0:y0+PATCH_SIZE]
                brain_mask_patch = brain_mask[z, x0:x0+PATCH_SIZE, y0:y0+PATCH_SIZE]
                patch = patch[np.newaxis, :, :]
                seg_patch = seg_patch[np.newaxis, :, :]
                # discard patch if more than 60% are background
                if float(np.sum(brain_mask_patch))/float(voxels_in_patch) < 0.6:
                    x0 += PATCH_SIZE
                    continue

                # find label of patch. We label a patch as tumor if it has more than 8% tumor pixels. if it has
                # between 0 and 10% it will be discarded (belongs to neither class)
                label = 0
                percent_of_tumor_voxels = float(np.sum(seg_patch > 1)) / float(voxels_in_patch)
                if percent_of_tumor_voxels > 0:
                    if percent_of_tumor_voxels < 0.08:
                        x0 += PATCH_SIZE
                        continue
                    label = 1
                str_id = "%s_z%i_y%i_x%i_patchSize%i"%(patient_id, z, y0, x0, PATCH_SIZE)

                img_mean += np.mean(patch)

                # test = np.random.rand() < PERCENT_VAL
                if test:
                    if label == 0:
                        val_neg_memmap[n_negative_val][:128**2] = patch.flatten()
                        val_neg_memmap[n_negative_val][128**2:128**2*2] = seg_patch.flatten()
                        n_negative_val += 1
                    elif label == 1:
                        val_pos_memmap[n_positive_val][:128**2] = patch.flatten()
                        val_pos_memmap[n_positive_val][128**2:128**2*2] = seg_patch.flatten()
                        n_positive_val += 1
                else:
                    if label == 0:
                        train_neg_memmap[n_negative_train][:128**2] = patch.flatten()
                        train_neg_memmap[n_negative_train][128**2:128**2*2] = seg_patch.flatten()
                        n_negative_train += 1
                    if label == 1:
                        train_pos_memmap[n_positive_train][:128**2] = patch.flatten()
                        train_pos_memmap[n_positive_train][128**2:128**2*2] = seg_patch.flatten()
                        n_positive_train += 1
                # plt.imsave("%s.jpg" % str_id, patch, cmap="gray")
                x0 += int(PATCH_SIZE / 5)
            y0 += int(PATCH_SIZE / 5)
    print "current pos train: ", n_positive_train, " max allowed: ", train_pos_shape[0]
    print "current pos val: ", n_positive_val, " max allowed: ", val_pos_shape[0]
    print "current neg train: ", n_negative_train, " max allowed: ", train_neg_shape[0]
    print "current neg val: ", n_negative_val, " max allowed: ", val_neg_shape[0]


print "train: ", n_negative_train + n_positive_train, n_positive_train, n_negative_train
print "test: ", n_positive_val + n_negative_val, n_positive_val, n_negative_val
print "image mean: ", img_mean / float(n_negative_train + n_positive_train + n_positive_val + n_negative_val)


my_dict = {
    "train_total" : n_negative_train + n_positive_train,
    "train_pos": n_positive_train,
    "train_neg": n_negative_train,
    "val_total" : n_positive_val + n_negative_val,
    "val_pos": n_positive_val,
    "val_neg": n_negative_val,
    "train_neg_shape": train_neg_shape,
    "train_pos_shape": train_pos_shape,
    "val_neg_shape": val_neg_shape,
    "val_pos_shape": val_pos_shape

}
with open("%s_properties.pkl" % memmap_name, 'w') as f:
    cPickle.dump(my_dict, f)