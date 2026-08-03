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
4. **Reloads** a previously annotated case for quality control review
   and correction, with segmentations restored as editable overlays
   on the corresponding MRIs.

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

## Workflow — annotating a new case

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
   `Epikard` (blue) segments. The *Allow overlapping segments* checkbox
   (ticked by default) configures the Segment Editor's "Modify other
   segments" mode to *Allow overlap*.
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

## Workflow — reviewing and correcting an existing case

The module supports quality control: an already-saved case
can be reloaded, corrected in the Segment Editor, and saved back to
the same files.

1. **Point to the case folder.** In section 4 of the module panel,
   pick the folder containing the patient's NIfTI files. The patient ID
   is auto-detected from the filename pattern (or can be entered
   manually).
2. **Load.** Click *Load ED + ES MRI and segmentations*. Both MRI
   volumes come in as `SAX_ED` and `SAX_ES`; the segmentation files are
   re-imported as proper editable segmentation nodes with named
   `Perikard` (red) and `Epikard` (blue) segments. The Segment Editor
   is configured with *Allow overlap*, matching the annotation
   convention.
3. **Correct.** Open the Segment Editor. Switch the source volume
   between `SAX_ED` and `SAX_ES` (and the corresponding segmentation)
   to make corrections in either phase.
4. **Save back.** Click *Save corrections back to the same files*. After
   a confirmation prompt, the two segmentation NIfTIs are overwritten
   in place. The MRI files are not modified.

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
- The review workflow (section 4) expects all four NIfTI files
  (ED MRI, ES MRI, ED segmentation, ES segmentation) to be present in
  the same folder with the standard naming pattern. The 4D file is
  not required for review.
- Saving corrections overwrites the segmentation files in place. No
  automatic backup is created — versioning is expected to be handled
  externally.