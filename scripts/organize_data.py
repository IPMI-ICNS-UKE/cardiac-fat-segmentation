"""Organize DICOM images and manual segmentation masks for the annotated EAT/PAT cases.

For every patient with a manual segmentation in ``eat_segmentations``, this script:

1. Locates the 4D short-axis (SAX) cine DICOM series for that patient in
   ``eat_images_all`` (one DICOM series per slice position, named
   ``CINE_segmented_SAX_KA_b<n>``, each containing all cardiac phases).
2. Reconstructs the 3D end-diastolic (ED, first cardiac phase) volume and the
   full 4D cine volume, choosing the slice order (and, if the DICOM export is
   missing a few basal/apical slices relative to the annotation, the slice
   window) that reproduces the existing segmentation's geometry exactly. This
   is necessary because the historical annotation tool did not use a single
   fixed slice-ordering convention (see the run summary for details).
3. Writes the ED volume, the 4D volume, and a compressed copy of the
   segmentation mask as NIfTI files, and records the case in an Excel table.

Cases whose segmentation geometry cannot be reproduced from the available
DICOM data (missing series, or a segmentation that geometrically matches a
*different* patient's images -- i.e. a mislabeled case) are excluded from the
table and reported separately so they can be reviewed manually.
"""

import argparse
import os
import re
import sys
import traceback
from dataclasses import dataclass, field

import numpy as np
import pydicom
import SimpleITK as sitk
from openpyxl import Workbook

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_IMG_ROOT = "/home/gkolokolnikov/PhD_project/vault_data/EAT/eat_images_all"
DEFAULT_SEG_ROOT = "/home/gkolokolnikov/PhD_project/vault_data/EAT/eat_segmentations"

OUT_TABLE = os.path.join(PROJECT_ROOT, "data", "table", "cases.xlsx")
OUT_LABELS_DIR = os.path.join(PROJECT_ROOT, "data", "labels_ed_3d")
OUT_IMAGES_ED_DIR = os.path.join(PROJECT_ROOT, "data", "images_ed_3d")
OUT_IMAGES_4D_DIR = os.path.join(PROJECT_ROOT, "data", "images_4d")

# Matches the standard cine acquisition ("CINE_segmented_SAX_KA_b3"), one
# series per slice position. Deliberately anchored so it does not also match
# unrelated extra acquisitions such as "CINE_segm_SAX 64 Phasen_KA_b3".
SAX_SERIES_RE = re.compile(r"^CINE_segmented_SAX(_KA)?_b(\d+)$")
SEG_FOLDER_RE = re.compile(r"^seg_([A-Za-z0-9]{9})(_.*)?$")

AFFINE_ATOL = 1e-1


@dataclass
class SeriesInfo:
    bnum: int
    series_dir: str
    files_by_instance: list  # filenames, sorted by InstanceNumber
    headers_by_instance: list = field(default_factory=list)  # pydicom headers, no pixel data


def discover_cases(seg_root):
    """Map base patient_id -> chosen segmentation folder, resolving duplicates.

    Returns (chosen, skipped_duplicates) where skipped_duplicates lists
    folders that were not chosen because another folder for the same
    patient_id was preferred (the one without an annotator suffix).
    """
    by_patient = {}
    for name in sorted(os.listdir(seg_root)):
        full = os.path.join(seg_root, name)
        if not os.path.isdir(full):
            continue
        m = SEG_FOLDER_RE.match(name)
        if not m:
            continue
        patient_id, suffix = m.group(1), m.group(2)
        by_patient.setdefault(patient_id, []).append((name, suffix))

    chosen = {}
    skipped_duplicates = []
    for patient_id, entries in by_patient.items():
        if len(entries) == 1:
            chosen[patient_id] = entries[0][0]
            continue
        # Prefer the folder without an annotator suffix; otherwise take the
        # first (alphabetically) and log the rest.
        no_suffix = [e for e in entries if not e[1]]
        pick = no_suffix[0][0] if no_suffix else sorted(entries)[0][0]
        chosen[patient_id] = pick
        for name, _ in entries:
            if name != pick:
                skipped_duplicates.append((patient_id, name, pick))
    return chosen, skipped_duplicates


def find_segmentation_nifti(seg_folder):
    """Return the path to the segmentation NIfTI in seg_folder, or None.

    Segmentation exports use inconsistent naming across cases (Segmentation.nii,
    Segmentation.nii.gz, Segmentation_1.nii(.gz), SAX_ED_segmentation.nii.gz,
    ...). We take the (single) distinct file stem present, preferring the
    compressed form if both exist.
    """
    files = [f for f in os.listdir(seg_folder) if f.endswith(".nii") or f.endswith(".nii.gz")]
    if not files:
        return None
    stems = {}
    for f in files:
        stem = f[:-7] if f.endswith(".nii.gz") else f[:-4]
        stems.setdefault(stem, []).append(f)
    stem = sorted(stems.keys())[0]
    variants = stems[stem]
    gz = [f for f in variants if f.endswith(".nii.gz")]
    chosen = gz[0] if gz else variants[0]
    return os.path.join(seg_folder, chosen)


def find_study_dir(patient_id, img_root):
    patient_dir = os.path.join(img_root, patient_id)
    studies = sorted(d for d in os.listdir(patient_dir) if os.path.isdir(os.path.join(patient_dir, d)))
    if not studies:
        raise RuntimeError(f"No study folder found for patient {patient_id}")
    return os.path.join(patient_dir, studies[0])


def find_sax_series(patient_id, img_root):
    """Return SeriesInfo list (headers only, no pixel data), sorted by b-number."""
    study_dir = find_study_dir(patient_id, img_root)
    series_list = []
    for series_name in sorted(os.listdir(study_dir)):
        series_dir = os.path.join(study_dir, series_name)
        if not os.path.isdir(series_dir):
            continue
        files = sorted(os.listdir(series_dir))
        if not files:
            continue
        first = pydicom.dcmread(os.path.join(series_dir, files[0]), stop_before_pixels=True)
        desc = getattr(first, "SeriesDescription", "") or ""
        m = SAX_SERIES_RE.match(desc)
        if not m:
            continue
        headers = [pydicom.dcmread(os.path.join(series_dir, f), stop_before_pixels=True) for f in files]
        order = sorted(range(len(headers)), key=lambda i: int(headers[i].InstanceNumber))
        files_sorted = [files[i] for i in order]
        headers_sorted = [headers[i] for i in order]
        series_list.append(SeriesInfo(int(m.group(2)), series_dir, files_sorted, headers_sorted))
    series_list.sort(key=lambda s: s.bnum)
    return series_list


def spatial_orders(series_list):
    """Return [ascending, descending] orderings of series_list by slice position."""
    ref = series_list[0].headers_by_instance[0]
    iop = [float(x) for x in ref.ImageOrientationPatient]
    dir_x = np.array(iop[0:3]); dir_x /= np.linalg.norm(dir_x)
    dir_y = np.array(iop[3:6]); dir_y /= np.linalg.norm(dir_y)
    normal = np.cross(dir_x, dir_y)
    normal /= np.linalg.norm(normal)
    proj = [
        float(np.dot(np.array([float(x) for x in s.headers_by_instance[0].ImagePositionPatient]), normal))
        for s in series_list
    ]
    idx_asc = list(np.argsort(proj))
    ascending = [series_list[i] for i in idx_asc]
    descending = ascending[::-1]
    return {"asc": ascending, "desc": descending}


def geometry_for_window(window, frame_idx):
    """Compute (dir_x, dir_y, dir_z_unit, spacing_x, spacing_y, spacing_z, origin) for a
    slice window at a given frame index, using only DICOM headers (no pixel data)."""
    ref = window[0].headers_by_instance[frame_idx]
    iop = [float(x) for x in ref.ImageOrientationPatient]
    dir_x = np.array(iop[0:3]); dir_x /= np.linalg.norm(dir_x)
    dir_y = np.array(iop[3:6]); dir_y /= np.linalg.norm(dir_y)
    pos0 = np.array([float(x) for x in window[0].headers_by_instance[frame_idx].ImagePositionPatient])
    pos1 = np.array([float(x) for x in window[1].headers_by_instance[frame_idx].ImagePositionPatient])
    k = pos1 - pos0
    spacing_z = float(np.linalg.norm(k))
    dir_z = k / spacing_z if spacing_z > 0 else np.cross(dir_x, dir_y)
    sp = [float(x) for x in ref.PixelSpacing]
    spacing_x, spacing_y = sp[1], sp[0]
    return dir_x, dir_y, dir_z, spacing_x, spacing_y, spacing_z, pos0


def affine_ras_for_window(window, frame_idx=0):
    dir_x, dir_y, dir_z, sx, sy, sz, origin = geometry_for_window(window, frame_idx)
    a_lps = np.column_stack([dir_x * sx, dir_y * sy, dir_z * sz])
    a_ras = a_lps.copy()
    a_ras[0, :] *= -1
    a_ras[1, :] *= -1
    origin_ras = origin.copy()
    origin_ras[0] *= -1
    origin_ras[1] *= -1
    affine = np.eye(4)
    affine[:3, :3] = a_ras
    affine[:3, 3] = origin_ras
    return affine


def get_series(patient_id, img_root, cache):
    """Cached, header-only lookup of a patient's SAX series (no pixel data)."""
    if patient_id not in cache:
        try:
            cache[patient_id] = find_sax_series(patient_id, img_root)
        except Exception:
            cache[patient_id] = []
    return cache[patient_id]


def find_geometry_match_elsewhere(seg_shape, seg_affine, exclude_patient_id, candidate_patient_ids, img_root, cache):
    """Check whether seg_affine actually matches a *different* patient's DICOM
    geometry (i.e. the segmentation file may have been saved under the wrong
    patient during annotation). Returns a list of matching patient_ids."""
    matches = []
    for pid in candidate_patient_ids:
        if pid == exclude_patient_id:
            continue
        series_list = get_series(pid, img_root, cache)
        if len(series_list) < 2:
            continue
        if find_matching_window(series_list, seg_shape, seg_affine) is not None:
            matches.append(pid)
    return matches


def find_matching_window(series_list, seg_shape, seg_affine):
    """Search slice order (asc/desc) and slice-window offset for the one that
    reproduces seg_affine (handles cases where the DICOM export has more
    slices than were included in the annotation). Returns (order_label,
    window) or None."""
    n = len(series_list)
    n_cols, n_rows, n_slices_needed = seg_shape  # seg_shape is (x, y, z) = (Columns, Rows, Slices)
    if n < n_slices_needed:
        return None
    for label, ordered in spatial_orders(series_list).items():
        for start in range(0, n - n_slices_needed + 1):
            window = ordered[start:start + n_slices_needed]
            ref = window[0].headers_by_instance[0]
            if (int(ref.Rows), int(ref.Columns)) != (n_rows, n_cols):
                continue
            aff = affine_ras_for_window(window, frame_idx=0)
            if np.allclose(aff, seg_affine, atol=AFFINE_ATOL):
                return label, window
    return None


def load_frame_array(series_dir, filename):
    ds = pydicom.dcmread(os.path.join(series_dir, filename))
    arr = ds.pixel_array.astype(np.float32)
    slope = float(getattr(ds, "RescaleSlope", 1))
    intercept = float(getattr(ds, "RescaleIntercept", 0))
    return arr * slope + intercept


def build_frame_image(window, frame_idx):
    dir_x, dir_y, dir_z, sx, sy, sz, origin = geometry_for_window(window, frame_idx)
    arrays = [load_frame_array(s.series_dir, s.files_by_instance[frame_idx]) for s in window]
    arr = np.stack(arrays, axis=0)
    direction = np.column_stack([dir_x, dir_y, dir_z])
    img = sitk.GetImageFromArray(arr)
    img.SetOrigin(tuple(origin.tolist()))
    img.SetSpacing((sx, sy, sz))
    img.SetDirection(direction.flatten(order="C").tolist())
    return img


def build_4d_image(window):
    n_frames = min(len(s.files_by_instance) for s in window)
    frames = [build_frame_image(window, f) for f in range(n_frames)]
    return sitk.JoinSeries(frames)


def process_case(patient_id, seg_folder, img_root, seg_nifti_path, cache, candidate_patient_ids):
    seg_img = sitk.ReadImage(seg_nifti_path)
    seg_arr = sitk.GetArrayFromImage(seg_img)  # (z, y, x)
    seg_shape = (seg_arr.shape[2], seg_arr.shape[1], seg_arr.shape[0])  # (x, y, z) like nibabel .shape
    seg_affine = sitk_to_ras_affine(seg_img)

    series_list = get_series(patient_id, img_root, cache)
    if len(series_list) < 2:
        observation = (
            f"Only {len(series_list)} SAX cine series (CINE_segmented_SAX_KA_b<n>) "
            f"found in this patient's DICOM folder; at least 2 are needed to "
            f"reconstruct the 3D geometry."
        )
        return None, "insufficient SAX series in DICOM", observation

    match = find_matching_window(series_list, seg_shape, seg_affine)
    if match is None:
        elsewhere = find_geometry_match_elsewhere(
            seg_shape, seg_affine, patient_id, candidate_patient_ids, img_root, cache
        )
        if elsewhere:
            observation = (
                f"This segmentation's geometry does not match patient {patient_id}'s own "
                f"DICOM data. It exactly matches patient {', '.join(elsewhere)}'s DICOM data "
                f"instead, which already has its own correctly-matching segmentation -- the "
                f".nii(.gz) file in this folder was very likely saved under the wrong patient "
                f"during annotation. Excluded to avoid pairing a mismatched image/mask; "
                f"recommend manual review of the original Slicer scene."
            )
        else:
            observation = (
                f"This segmentation's geometry does not match patient {patient_id}'s own "
                f"DICOM data, and no matching DICOM geometry was found among the other "
                f"{len(candidate_patient_ids) - 1} annotated patients either. Likely causes: "
                f"the DICOM export is missing slices relative to the annotation, or the true "
                f"source patient is outside the annotated cohort. Needs manual investigation."
            )
        return None, "segmentation geometry mismatch", observation
    order_label, window = match

    ed_img = build_frame_image(window, 0)
    fourd_img = build_4d_image(window)

    ed_path = os.path.join(OUT_IMAGES_ED_DIR, f"{patient_id}.nii.gz")
    fourd_path = os.path.join(OUT_IMAGES_4D_DIR, f"{patient_id}.nii.gz")
    label_path = os.path.join(OUT_LABELS_DIR, f"{patient_id}.nii.gz")

    sitk.WriteImage(ed_img, ed_path, useCompression=True)
    sitk.WriteImage(fourd_img, fourd_path, useCompression=True)
    sitk.WriteImage(seg_img, label_path, useCompression=True)

    row = {
        "case": patient_id,
        "label": os.path.relpath(label_path, PROJECT_ROOT).replace(os.sep, "/"),
        "image_ed_3d": os.path.relpath(ed_path, PROJECT_ROOT).replace(os.sep, "/"),
        "image_4d": os.path.relpath(fourd_path, PROJECT_ROOT).replace(os.sep, "/"),
        "n_slices": len(window),
        "n_frames": min(len(s.files_by_instance) for s in window),
        "slice_order": order_label,
        "seg_source_folder": os.path.basename(seg_folder),
    }
    return row, None, None


def sitk_to_ras_affine(img):
    """Convert a SimpleITK (LPS) image's geometry to a nibabel-style RAS affine."""
    direction = np.array(img.GetDirection()).reshape(3, 3)
    spacing = np.array(img.GetSpacing())
    origin = np.array(img.GetOrigin())
    a_lps = direction * spacing  # columns scaled by spacing
    a_ras = a_lps.copy()
    a_ras[0, :] *= -1
    a_ras[1, :] *= -1
    origin_ras = origin.copy()
    origin_ras[0] *= -1
    origin_ras[1] *= -1
    affine = np.eye(4)
    affine[:3, :3] = a_ras
    affine[:3, 3] = origin_ras
    return affine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--img-root", default=DEFAULT_IMG_ROOT)
    parser.add_argument("--seg-root", default=DEFAULT_SEG_ROOT)
    args = parser.parse_args()

    os.makedirs(OUT_LABELS_DIR, exist_ok=True)
    os.makedirs(OUT_IMAGES_ED_DIR, exist_ok=True)
    os.makedirs(OUT_IMAGES_4D_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT_TABLE), exist_ok=True)

    chosen, skipped_duplicates = discover_cases(args.seg_root)
    print(f"Found {len(chosen)} candidate patients with a segmentation "
          f"({len(skipped_duplicates)} duplicate folder(s) skipped).")

    candidate_patient_ids = sorted(chosen)
    series_cache = {}

    rows = []
    excluded = []
    for patient_id, seg_folder_name, kept_folder in skipped_duplicates:
        excluded.append({
            "case": patient_id,
            "seg_folder": seg_folder_name,
            "reason": "duplicate annotation for this patient",
            "observation": (
                f"Both '{seg_folder_name}' and '{kept_folder}' exist as segmentation "
                f"folders for this patient. Kept '{kept_folder}' (no annotator suffix) "
                f"and excluded '{seg_folder_name}'. Review manually if the suffixed "
                f"version should be preferred instead (e.g. it may be a corrected "
                f"re-annotation)."
            ),
        })

    for patient_id in candidate_patient_ids:
        seg_folder = os.path.join(args.seg_root, chosen[patient_id])
        seg_nifti_path = find_segmentation_nifti(seg_folder)
        if seg_nifti_path is None:
            contents = sorted(os.listdir(seg_folder))
            excluded.append({
                "case": patient_id,
                "seg_folder": chosen[patient_id],
                "reason": "no segmentation file",
                "observation": (
                    f"Folder contains no .nii/.nii.gz file. "
                    + (f"Actual contents: {', '.join(contents)}." if contents else "The folder is empty.")
                ),
            })
            print(f"[SKIP] {patient_id}: no segmentation NIfTI in {chosen[patient_id]}")
            continue
        try:
            row, reason, observation = process_case(
                patient_id, seg_folder, args.img_root, seg_nifti_path, series_cache, candidate_patient_ids
            )
        except Exception as e:
            row, reason, observation = None, "error", f"Unhandled error while processing this case: {e}"
            traceback.print_exc()
        if row is None:
            excluded.append({"case": patient_id, "seg_folder": chosen[patient_id],
                              "reason": reason, "observation": observation})
            print(f"[SKIP] {patient_id}: {reason}")
        else:
            rows.append(row)
            print(f"[OK]   {patient_id}: {row['n_slices']} slices x {row['n_frames']} frames "
                  f"(order={row['slice_order']})")

    wb = Workbook()
    ws = wb.active
    ws.title = "cases"
    headers = ["case", "label", "image_ed_3d", "image_4d", "n_slices", "n_frames", "slice_order", "seg_source_folder"]
    ws.append(headers)
    for row in rows:
        ws.append([row[h] for h in headers])

    ws2 = wb.create_sheet("excluded")
    ws2.append(["case", "seg_folder", "reason", "observation"])
    for row in excluded:
        ws2.append([row["case"], row["seg_folder"], row["reason"], row["observation"]])
    for col in ws2.columns:
        max_len = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws2.column_dimensions[col[0].column_letter].width = min(max_len + 2, 100)

    wb.save(OUT_TABLE)

    print()
    print(f"Wrote {len(rows)} cases to {os.path.relpath(OUT_TABLE, PROJECT_ROOT)}")
    print(f"Excluded {len(excluded)} folders/cases (see the 'excluded' sheet for reasons/observations).")


if __name__ == "__main__":
    sys.exit(main())
