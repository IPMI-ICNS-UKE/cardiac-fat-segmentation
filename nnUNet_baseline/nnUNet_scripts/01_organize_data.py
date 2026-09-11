"""Build the nnU-Net raw dataset folder from the organized EAT/PAT cases.

Reads ``data/table/cases.xlsx`` (produced by ``scripts/organize_data.py``) and
copies each case's ED-phase image and segmentation mask into the nnU-Net v2
raw-data layout:

    nnUNet_baseline/nnUNet_raw/Dataset001_EAT/
        dataset.json
        imagesTr/<case>_0000.nii.gz
        labelsTr/<case>.nii.gz

Cases known to be missing an Epikard annotation entirely (found during the
EDA QC pass, see output/eda/case_metrics.xlsx) are excluded.

As a sanity check, every case's label volume is scanned slice-by-slice for
"interior gaps" -- an unlabeled slice sandwiched between labeled ones, which
usually indicates a skipped annotation rather than anatomical absence (the
expected pattern is unlabeled slices only at the base/apex edges of the
stack). Any such case is reported but not excluded automatically.
"""

import json
import os
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

# Found during EDA (output/eda/case_metrics.xlsx, "flags" sheet): these two
# cases have an entirely empty Epikard mask (only the outer Perikard contour
# was ever drawn), so their volumes/shape are not representative training
# examples for a 2-label model.
EXCLUDED_CASES = {"0EAH0EUQ7", "0ELJPP4FX"}


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


def main():
    os.makedirs(IMAGES_TR_DIR, exist_ok=True)
    os.makedirs(LABELS_TR_DIR, exist_ok=True)

    df = pd.read_excel(TABLE_PATH, sheet_name="cases")
    print(f"Loaded {len(df)} cases from {os.path.relpath(TABLE_PATH, PROJECT_ROOT)}")

    included = 0
    interior_gap_cases = []

    for _, row in df.iterrows():
        case_id = row["case"]
        if case_id in EXCLUDED_CASES:
            print(f"[SKIP] {case_id}: excluded (empty Epikard annotation)")
            continue

        src_image = os.path.join(PROJECT_ROOT, row["image_ed_3d"])
        src_label = os.path.join(PROJECT_ROOT, row["label"])
        dst_image = os.path.join(IMAGES_TR_DIR, f"{case_id}_0000.nii.gz")
        dst_label = os.path.join(LABELS_TR_DIR, f"{case_id}.nii.gz")

        shutil.copy2(src_image, dst_image)
        shutil.copy2(src_label, dst_label)
        included += 1

        n_gap = find_interior_label_gaps(src_label)
        if n_gap > 0:
            interior_gap_cases.append((case_id, n_gap))
            print(f"[OK]   {case_id}  -- WARNING: {n_gap} interior unlabeled slice(s), likely a skipped annotation")
        else:
            print(f"[OK]   {case_id}")

    dataset_json = build_dataset_json(included)
    with open(os.path.join(DATASET_DIR, "dataset.json"), "w") as f:
        json.dump(dataset_json, f, indent=4)

    print()
    print(f"Wrote {included} cases to {os.path.relpath(DATASET_DIR, PROJECT_ROOT)}")
    print(f"Excluded: {sorted(EXCLUDED_CASES)}")
    if interior_gap_cases:
        print(f"Cases with a likely skipped annotation slice (not excluded, needs manual review): {interior_gap_cases}")


if __name__ == "__main__":
    sys.exit(main())
