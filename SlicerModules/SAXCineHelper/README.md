# SAX Cine Helper — 3D Slicer extension

A scripted 3D Slicer module for manual annotation of the epicardial and pericardial
boundaries in 4D short-axis (SAX) cine cardiac MRI.

## What it does

Cardiac SAX cine MRI is typically stored as one DICOM series per slice
position, each containing all 25 cardiac phases. This module:

1. **Stacks** individual SAX slice-sequences (`_b1`, `_b2`, …) into a
   single 4D volume plus one 3D volume per cardiac phase.
2. **Prepares** empty segmentations with `Perikard` and `Epikard` labels
   for user-selected end-diastolic (ED) and end-systolic (ES) frames,
   with the Segment Editor pre-configured to allow overlapping segments.
3. **Exports** the annotated data as five NIfTI files.

## Requirements

- [3D Slicer](https://slicer.org) 5.4 or newer
- SAX cine data imported as **Volume Sequence** (not MultiVolume). Set
  this in *Edit → Application Settings → DICOM → Preferred multi-volume
  import format*, then restart Slicer.

## Installation

1. Clone or download this repository.
2. In Slicer: *Edit → Application Settings → Modules → Additional module
   paths → Add* → select the folder `SlicerModules/SAXCineHelper/`.
3. Restart Slicer. The module appears under *Modules → Cardiac → SAX
   Cine Helper*.

On macOS, place the extension folder outside the Slicer app bundle
(e.g. `~/SlicerModules/SAXCineHelper/`) so it survives Slicer updates.

## Workflow

1. **Load DICOM.** Import the SAX cine series through Slicer's DICOM
   module. The InlineVF series, if present, is ignored automatically.
2. **Stack.** Click *Stack loaded SAX sequences*. The original per-slice
   sequences are replaced by a single 4D volume (`SAX_4D`) and one 3D
   volume per phase (`SAX_frame_00` … `SAX_frame_NN`).
3. **Identify ED and ES.** Play the 4D sequence using the Sequence
   toolbar. Note the frame where the LV cavity is largest (ED, usually
   frame 0) and smallest (ES, typically frames 8–12).
4. **Prepare segmentations.** Enter the ED and ES frame indices and
   click *Create empty segmentations for these frames*. Two empty
   segmentation nodes are created, each with `Perikard` (red) and
   `Epikard` (blue) segments. The Segment Editor is configured to
   *Allow overlap* by default.
5. **Annotate.** Open the Segment Editor. Draw the Perikard contour
   (outer, includes pericardial fat) and Epikard contour (inner,
   at the myocardial outer boundary) on each SAX slice, for both the
   ED and ES volumes.
6. **Save.** Enter the patient ID and an output folder, then click
   *Save 5 files*. The following NIfTI files are written:

   - `<patient_id>_3D_ED_MRI.nii.gz`
   - `<patient_id>_3D_ED_segmentation.nii.gz`
   - `<patient_id>_3D_ES_MRI.nii.gz`
   - `<patient_id>_3D_ES_segmentation.nii.gz`
   - `<patient_id>_4D_MRI.nii.gz`

## Output conventions

Segmentation label values:

| Label | Structure    |
|------:|--------------|
|   `0` | Background   |
|   `1` | Perikard     |
|   `2` | Epikard      |

Segments may overlap in the nested-contour convention (Epikard inside
Perikard). Downstream fat volumes are computed as `Perikard − Epikard`.

## Known limitations

- SAX slices are acquired in separate breath-holds; the stacked 4D
  volume therefore has residual through-plane misalignment. This is
  typical of standard CMR workflows and is expected to be handled by
  the downstream analysis, not corrected here.
- Through-plane spacing is inferred from the origin difference between
  the first two slices. Non-uniform slice gaps are not supported.
