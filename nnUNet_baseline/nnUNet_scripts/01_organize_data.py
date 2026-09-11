"""Build the nnU-Net raw dataset folder from the organized EAT/PAT cases.

Reads ``data/table/cases.xlsx`` (produced by ``scripts/organize_data.py``),
excludes cases with no usable annotation, randomly splits the rest into a
train and a held-out test set, and copies each case's ED-phase image and
segmentation mask into the nnU-Net v2 raw-data layout:

    nnUNet_baseline/nnUNet_raw/Dataset001_EAT/
        dataset.json
        imagesTr/<case>_0000.nii.gz   labelsTr/<case>.nii.gz   (used for nnU-Net's 5-fold CV)
        imagesTs/<case>_0000.nii.gz   labelsTs/<case>.nii.gz   (held out; nnU-Net never sees these)
        train_test_split.csv          (case -> split, for the record)

Cases known to be missing an Epikard annotation entirely (found during the
EDA QC pass, see output/eda/case_metrics.xlsx) are excluded.

As a sanity check, every case's label volume is scanned slice-by-slice for
"interior gaps" -- an unlabeled slice sandwiched between labeled ones, which
usually indicates a skipped annotation rather than anatomical absence (the
expected pattern is unlabeled slices only at the base/apex edges of the
stack). Any such case is reported but not excluded automatically.

Re-running this script regenerates imagesTr/labelsTr/imagesTs/labelsTs from
scratch (old copies are removed first, so cases can't linger in the wrong
split), but leaves nnUNet_preprocessed/nnUNet_results untouched -- those must
be regenerated separately (nnUNetv2_plan_and_preprocess + retraining) since
the train/test composition changed.
"""

import csv
import json
import os
import random
import shutil
import sys

import pandas as pd
import SimpleITK as sitk

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE_PATH = os.path.join(PROJECT_ROOT, "data", "table", "cases.xlsx")

NNUNET_RAW_DIR = os.path.join(PROJECT_ROOT, "nnUNet_baseline", "nnUNet_raw")
DATASET_NAME = "Dataset001_EAT"
DATASET_DIR = os.path.join(NNUNET_RAW_DIR, DATASET_NAME)
IMAGES_TR_DIR = os.path.join(DATASET_DIR, "imagesTr")
LABELS_TR_DIR = os.path.join(DATASET_DIR, "labelsTr")
IMAGES_TS_DIR = os.path.join(DATASET_DIR, "imagesTs")
LABELS_TS_DIR = os.path.join(DATASET_DIR, "labelsTs")
SPLIT_RECORD_PATH = os.path.join(DATASET_DIR, "train_test_split.csv")

# Found during EDA (output/eda/case_metrics.xlsx, "flags" sheet): these two
# cases have an entirely empty Epikard mask (only the outer Perikard contour
# was ever drawn), so their volumes/shape are not representative training
# examples for a 2-label model.
EXCLUDED_CASES = {"0EAH0EUQ7", "0ELJPP4FX"}

TEST_FRACTION = 0.30
RANDOM_SEED = 42  # fixed so re-running this script reproduces the same split


def find_interior_label_gaps(label_path):
    """Return the number of unlabeled slices sandwiched between labeled ones.

    A well-annotated case should only have unlabeled slices at the base/apex
    edges of the stack (the heart genuinely isn't visible there). An
    "interior" gap -- a labeled slice, then an unlabeled slice, then labeled
    slices again -- usually means a slice was skipped during annotation.
    """
    label_arr = sitk.GetArrayFromImage(sitk.ReadImage(label_path))
    slice_has_label = [(label_arr[z] > 0).any() for z in range(label_arr.shape[0])]
    labeled_idx = [i for i, v in enumerate(slice_has_label) if v]
    if not labeled_idx:
        return 0
    first, last = labeled_idx[0], labeled_idx[-1]
    return sum(1 for i in range(first, last + 1) if not slice_has_label[i])


def build_dataset_json(num_training):
    return {
        "channel_names": {"0": "MRI"},
        "labels": {"background": 0, "Perikard": 1, "Epikard": 2},
        "numTraining": num_training,
        "file_ending": ".nii.gz",
    }


def split_cases(case_ids):
    """Deterministic random 70/30 train/test split."""
    shuffled = sorted(case_ids)  # sort first so the shuffle is independent of input order
    random.Random(RANDOM_SEED).shuffle(shuffled)
    n_test = round(len(shuffled) * TEST_FRACTION)
    test_cases = set(shuffled[:n_test])
    train_cases = set(shuffled[n_test:])
    return train_cases, test_cases


def reset_dir(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)


def copy_case(case_id, row, images_dir, labels_dir):
    src_image = os.path.join(PROJECT_ROOT, row["image_ed_3d"])
    src_label = os.path.join(PROJECT_ROOT, row["label"])
    shutil.copy2(src_image, os.path.join(images_dir, f"{case_id}_0000.nii.gz"))
    shutil.copy2(src_label, os.path.join(labels_dir, f"{case_id}.nii.gz"))
    return find_interior_label_gaps(src_label)


def main():
    for d in (IMAGES_TR_DIR, LABELS_TR_DIR, IMAGES_TS_DIR, LABELS_TS_DIR):
        reset_dir(d)

    df = pd.read_excel(TABLE_PATH, sheet_name="cases")
    print(f"Loaded {len(df)} cases from {os.path.relpath(TABLE_PATH, PROJECT_ROOT)}")

    df = df[~df["case"].isin(EXCLUDED_CASES)].reset_index(drop=True)
    print(f"Excluded: {sorted(EXCLUDED_CASES)} -- {len(df)} cases remain")

    train_cases, test_cases = split_cases(df["case"].tolist())
    print(f"Split: {len(train_cases)} train ({1 - TEST_FRACTION:.0%} target), "
          f"{len(test_cases)} test ({TEST_FRACTION:.0%} target), seed={RANDOM_SEED}")

    interior_gap_cases = []
    split_record = []

    for _, row in df.iterrows():
        case_id = row["case"]
        is_test = case_id in test_cases
        images_dir, labels_dir = (IMAGES_TS_DIR, LABELS_TS_DIR) if is_test else (IMAGES_TR_DIR, LABELS_TR_DIR)

        n_gap = copy_case(case_id, row, images_dir, labels_dir)
        split_record.append((case_id, "test" if is_test else "train"))

        note = ""
        if n_gap > 0:
            interior_gap_cases.append((case_id, n_gap))
            note = f"  -- WARNING: {n_gap} interior unlabeled slice(s), likely a skipped annotation"
        print(f"[{'TEST ' if is_test else 'TRAIN'}] {case_id}{note}")

    dataset_json = build_dataset_json(len(train_cases))
    with open(os.path.join(DATASET_DIR, "dataset.json"), "w") as f:
        json.dump(dataset_json, f, indent=4)

    with open(SPLIT_RECORD_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "split"])
        writer.writerows(sorted(split_record))

    print()
    print(f"Wrote {len(train_cases)} train + {len(test_cases)} test cases to "
          f"{os.path.relpath(DATASET_DIR, PROJECT_ROOT)}")
    print(f"Split record saved to {os.path.relpath(SPLIT_RECORD_PATH, PROJECT_ROOT)}")
    if interior_gap_cases:
        print(f"Cases with a likely skipped annotation slice (not excluded, needs manual review): {interior_gap_cases}")


if __name__ == "__main__":
    sys.exit(main())
