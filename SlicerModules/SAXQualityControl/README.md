# SAX Quality Control — 3D Slicer extension

A scripted 3D Slicer module for reviewing and correcting existing
epicardial and pericardial segmentations of 4D short-axis (SAX) cine
cardiac MRI. Companion to
[SAXCineHelper](../SAXCineHelper/README.md), which produces the
initial annotations.

## What it does

Given a patient's SAX cine DICOM already loaded in Slicer and an
existing segmentation on disk, this module:

1. **Stitches** the loaded SAX slice-sequences (`_b1`, `_b2`, …) into
   a single 4D volume plus a standalone 3D end-diastolic (ED) volume.
2. **Loads** an existing segmentation from a folder (`.nii.gz` +
   `.labels.csv`), preserving segment names and colors used at
   annotation time.
3. **Exports** the 4D and 3D ED volumes as NIfTI to a `nii_<patient>`
   folder next to the DICOM — useful for downstream model development.
4. **Opens** the Segment Editor with the segmentation and ED volume
   pre-selected and *Allow overlap* pre-configured.
5. **Saves** corrections back to the original `.nii.gz` and
   `.labels.csv` files, overwriting them after a confirmation prompt.

The patient code and parent folder are auto-detected from the loaded
DICOM files, so the segmentation folder and NIfTI target paths pre-fill
correctly for the standard project layout.
 
 
## Installation

1. Clone or download this repository.
2. In Slicer: *Edit → Application Settings → Modules → Additional
   module paths → Add* → select the folder `SlicerModules/SAXQualityControl/`.
3. Restart Slicer. The module appears under *Modules → Cardiac → SAX
   Quality Control*.

On macOS, place the extension folder outside the Slicer app bundle
(e.g. `~/SlicerModules/SAXQualityControl/`) so it survives Slicer
updates.


## Workflow

1. **Load the SAX cine DICOM** through Slicer's standard DICOM module.
   Import only the SAX series (or all series — the module ignores
   non-SAX and InlineVF sequences during stitching).
2. **Open SAX Quality Control** and set the *ED frame index* if it
   differs from the default (0).
3. **Stitch loaded SAX series.** The original per-slice sequences are
   replaced by a single 4D volume (`SAX_4D`) and a 3D ED volume
   (`SAX_ED`). The 4D volume is shown in the slice viewers and the
   Sequence toolbar is wired up so you can play through the cardiac
   cycle. The status field reports the detected patient code and
   folder.
4. **Load segmentation.** The segmentation folder path pre-fills to
   `<parent>/seg_<patient_code>` if that folder exists. If not, browse
   to it manually. Clicking *Load segmentation* imports the `.nii.gz`
   as an editable segmentation node with segment names and colors
   restored from the `.labels.csv`.
5. **(Optional) Save 4D + 3D ED as NIfTI.** Writes both volumes to
   `<parent>/nii_<patient_code>/` using the standard project naming.
6. **Open Segment Editor.** Corrects contours slice by slice. *Allow
   overlap* is ticked by default so nested Perikard/Epikard contours
   are not erased.
7. **Save corrected segmentation.** After a confirmation prompt,
   overwrites the original `.nii.gz` and `.labels.csv` in place.

## Known limitations

- **DICOM import mode matters.** If Slicer's DICOM module is set to
  copy files into the database cache, the module cannot recover the
  original patient folder path and auto-detection will fail. Re-import
  by reference to fix.
- **Patient folder detection assumes standard exporter layouts**
  (Siemens `SDY…/SRS…/IMG…`, or plain DICOM folders). If your export
  uses a different intermediate-folder naming convention, the module
  falls back to prompting for the segmentation folder manually and the
  NIfTI-save target cannot be computed automatically.
- **Saving corrections overwrites** the source files. Confirmation is
  requested but no automatic backup is created.