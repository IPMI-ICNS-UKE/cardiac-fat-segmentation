import os
import re
import vtk
import qt
import ctk
import slicer
import numpy as np
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
)


# ─────────────────────────────────────────────────────────────────────
# Module registration
# ─────────────────────────────────────────────────────────────────────
class SAXCineHelper(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        parent.title = "SAX Cine Helper"
        parent.categories = ["Cardiac"]
        parent.contributors = ["Your team"]
        parent.helpText = (
            "Workflow:\n"
            "1. Load SAX cine DICOM series (must import as Volume Sequence).\n"
            "2. Click 'Stack SAX series'.\n"
            "3. Play the 4D sequence, note ED frame (largest LV) and ES frame (smallest LV).\n"
            "4. Click 'Prepare ED/ES segmentations'.\n"
            "5. Annotate Perikard and Epikard in Segment Editor for both frames.\n"
            "6. Enter patient ID and output directory, click 'Save outputs'."
        )


# ─────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────
class SAXCineHelperWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = SAXCineHelperLogic()

        # --- Section 1: Stack ----------------------------------------
        box1 = ctk.ctkCollapsibleButton()
        box1.text = "1. Stack SAX cine series"
        self.layout.addWidget(box1)
        l1 = qt.QFormLayout(box1)

        self.stackButton = qt.QPushButton("Stack loaded SAX sequences")
        self.stackButton.toolTip = (
            "Finds all sequences whose name contains 'SAX' and '_bN' "
            "(excluding InlineVF), stacks them into one 4D sequence "
            "plus per-frame 3D volumes, and removes the original imports."
        )
        self.stackButton.connect("clicked()", self.onStack)
        l1.addRow(self.stackButton)

        self.statusLabel = qt.QLabel("Not stacked yet.")
        l1.addRow("Status:", self.statusLabel)

        # --- Section 2: Prepare segmentations -----------------------
        box2 = ctk.ctkCollapsibleButton()
        box2.text = "2. Prepare ED/ES segmentations"
        self.layout.addWidget(box2)
        l2 = qt.QFormLayout(box2)

        self.edFrameSpin = qt.QSpinBox()
        self.edFrameSpin.minimum, self.edFrameSpin.maximum = 0, 50
        self.edFrameSpin.value = 0
        l2.addRow("ED frame index:", self.edFrameSpin)

        self.esFrameSpin = qt.QSpinBox()
        self.esFrameSpin.minimum, self.esFrameSpin.maximum = 0, 50
        self.esFrameSpin.value = 9
        l2.addRow("ES frame index:", self.esFrameSpin)

        self.allowOverlapCheck = qt.QCheckBox("Allow overlapping segments")
        self.allowOverlapCheck.checked = True
        self.allowOverlapCheck.toolTip = (
            "Sets the Segment Editor's 'Modify other segments' to "
            "'Allow overlap' so Perikard and Epikard can be nested "
            "without erasing each other."
        )
        l2.addRow(self.allowOverlapCheck)

        self.prepareButton = qt.QPushButton(
            "Create empty segmentations for these frames"
        )
        self.prepareButton.connect("clicked()", self.onPrepare)
        l2.addRow(self.prepareButton)

        self.openEditorButton = qt.QPushButton("Open Segment Editor")
        self.openEditorButton.connect(
            "clicked()", lambda: slicer.util.selectModule("SegmentEditor")
        )
        l2.addRow(self.openEditorButton)

        # --- Section 3: Save ----------------------------------------
        box3 = ctk.ctkCollapsibleButton()
        box3.text = "3. Save outputs"
        self.layout.addWidget(box3)
        l3 = qt.QFormLayout(box3)

        self.patientIdEdit = qt.QLineEdit()
        self.patientIdEdit.placeholderText = "e.g. 00GKD51K0"
        l3.addRow("Patient ID:", self.patientIdEdit)

        self.outputDirButton = ctk.ctkDirectoryButton()
        l3.addRow("Output folder:", self.outputDirButton)

        self.saveButton = qt.QPushButton("Save 5 files (4D + ED/ES MRI + ED/ES seg)")
        self.saveButton.connect("clicked()", self.onSave)
        l3.addRow(self.saveButton)

        self.layout.addStretch(1)

    # ----- callbacks ----------------------------------------------
    def onStack(self):
        try:
            n_slices, n_frames = self.logic.stackSAXSequences()
            self.statusLabel.text = (
                f"OK: {n_slices} slices × {n_frames} frames. "
                f"4D volume + {n_frames} per-frame volumes created."
            )
            self.edFrameSpin.maximum = n_frames - 1
            self.esFrameSpin.maximum = n_frames - 1
            # Try to pre-fill patient ID from DICOM
            pid = self.logic.guessPatientId()
            if pid and not self.patientIdEdit.text:
                self.patientIdEdit.text = pid
        except Exception as e:
            slicer.util.errorDisplay(f"Stacking failed:\n{e}")

    def onPrepare(self):
        try:
            self.logic.prepareSegmentations(
                self.edFrameSpin.value,
                self.esFrameSpin.value,
                allow_overlap=self.allowOverlapCheck.checked,
            )
            slicer.util.infoDisplay(
                "Empty ED and ES segmentations created with 'Perikard' "
                "and 'Epikard' segments. Open Segment Editor to annotate."
            )
        except Exception as e:
            slicer.util.errorDisplay(f"Preparation failed:\n{e}")

    def onSave(self):
        try:
            paths = self.logic.saveOutputs(
                patient_id=self.patientIdEdit.text.strip(),
                ed_frame=self.edFrameSpin.value,
                es_frame=self.esFrameSpin.value,
                output_dir=self.outputDirButton.directory,
            )
            slicer.util.infoDisplay(
                "Saved:\n" + "\n".join(os.path.basename(p) for p in paths)
            )
        except Exception as e:
            slicer.util.errorDisplay(f"Save failed:\n{e}")


# ─────────────────────────────────────────────────────────────────────
# Logic
# ─────────────────────────────────────────────────────────────────────
class SAXCineHelperLogic(ScriptedLoadableModuleLogic):

    FRAME_VOL_PREFIX = "SAX_frame_"
    FOURD_NAME = "SAX_4D"
    BROWSER_NAME = "SAX_4D_browser"
    ED_SEG_NAME = "SAX_ED_segmentation"
    ES_SEG_NAME = "SAX_ES_segmentation"

    # ----- stacking ----------------------------------------------
    def stackSAXSequences(self):
        all_seqs = slicer.util.getNodesByClass("vtkMRMLSequenceNode")
        sax = [
            s for s in all_seqs
            if "SAX" in s.GetName()
            and "InlineVF" not in s.GetName()
            and re.search(r"_b\d+", s.GetName())
        ]
        if len(sax) < 2:
            raise RuntimeError(
                f"Found only {len(sax)} SAX b-series. "
                "Make sure DICOM is imported as 'volume sequence' "
                "(Edit → Application Settings → DICOM)."
            )

        # Sort by b-number, then verify against actual slice origin
        def bnum(seq):
            m = re.search(r"_b(\d+)", seq.GetName())
            return int(m.group(1))
        sax.sort(key=bnum)
        # Verify spatial monotonicity along slice normal
        self._verify_or_resort_by_origin(sax)

        n_frames = sax[0].GetNumberOfDataNodes()
        n_slices = len(sax)

        # Build 4D sequence
        out_seq = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSequenceNode", self.FOURD_NAME
        )
        out_seq.SetIndexName("Frame")
        out_seq.SetIndexUnit("")

        for f in range(n_frames):
            stacked = np.stack(
                [slicer.util.arrayFromVolume(s.GetNthDataNode(f))[0] for s in sax],
                axis=0,
            )
            vol = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLScalarVolumeNode", f"{self.FRAME_VOL_PREFIX}{f:02d}"
            )
            slicer.util.updateVolumeFromArray(vol, stacked)
            vol.SetIJKToRASMatrix(self._build_stacked_matrix(sax, f))
            vol.CreateDefaultDisplayNodes()
            out_seq.SetDataNodeAtValue(vol, str(f))

        # Sequence browser so they can scrub/play
        browser = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSequenceBrowserNode", self.BROWSER_NAME
        )
        browser.AddSynchronizedSequenceNode(out_seq)
        slicer.modules.sequences.toolBar().setActiveBrowserNode(browser)

        # Show the first frame in slice views
        slicer.util.setSliceViewerLayers(
            background=slicer.util.getNode(f"{self.FRAME_VOL_PREFIX}00"),
            fit=True,
        )

        # Clean up original imports
        self._remove_original_imports()
        return n_slices, n_frames

    def _verify_or_resort_by_origin(self, sax):
        """If b-number order doesn't match spatial order, re-sort by origin."""
        ref = sax[0]
        m = vtk.vtkMatrix4x4()
        ref.GetNthDataNode(0).GetIJKToRASMatrix(m)
        normal = np.array(
            [m.GetElement(0, 2), m.GetElement(1, 2), m.GetElement(2, 2)]
        )
        normal /= np.linalg.norm(normal)
        positions = [
            float(np.dot(np.array(s.GetNthDataNode(0).GetOrigin()), normal))
            for s in sax
        ]
        if positions != sorted(positions) and positions != sorted(
            positions, reverse=True
        ):
            order = np.argsort(positions)
            sax[:] = [sax[i] for i in order]

    def _build_stacked_matrix(self, sax, frame_index):
        """IJK→RAS for the stacked volume: in-plane axes from slice 0,
        through-plane axis from origin difference between slice 0 and 1."""
        ref = sax[0].GetNthDataNode(frame_index)
        m_ref = vtk.vtkMatrix4x4()
        ref.GetIJKToRASMatrix(m_ref)
        o0 = np.array(sax[0].GetNthDataNode(frame_index).GetOrigin())
        o1 = np.array(sax[1].GetNthDataNode(frame_index).GetOrigin())
        k = o1 - o0
        m = vtk.vtkMatrix4x4()
        m.Identity()
        for r in range(3):
            m.SetElement(r, 0, m_ref.GetElement(r, 0))
            m.SetElement(r, 1, m_ref.GetElement(r, 1))
            m.SetElement(r, 2, float(k[r]))
            m.SetElement(r, 3, float(o0[r]))
        return m

    def _remove_original_imports(self):
        """Remove original SAX sequences, their proxy volumes, and orphan browsers."""
        kept_names = {self.FOURD_NAME}
        for n in list(slicer.util.getNodesByClass("vtkMRMLSequenceNode")):
            if n.GetName() not in kept_names and (
                "SAX" in n.GetName() or "InlineVF" in n.GetName()
            ):
                slicer.mrmlScene.RemoveNode(n)
        for n in list(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")):
            nm = n.GetName()
            if nm.startswith(self.FRAME_VOL_PREFIX):
                continue
            if "SAX" in nm or "InlineVF" in nm:
                slicer.mrmlScene.RemoveNode(n)
        for n in list(slicer.util.getNodesByClass("vtkMRMLSequenceBrowserNode")):
            if n.GetName() != self.BROWSER_NAME:
                if n.GetNumberOfSynchronizedSequenceNodes() == 0 or (
                    "SAX" in n.GetName()
                ):
                    slicer.mrmlScene.RemoveNode(n)

    # ----- segmentations -----------------------------------------
    def prepareSegmentations(self, ed_frame, es_frame, allow_overlap=True):
        for name, frame in (
            (self.ED_SEG_NAME, ed_frame),
            (self.ES_SEG_NAME, es_frame),
        ):
            existing = slicer.mrmlScene.GetFirstNodeByName(name)
            if existing:
                slicer.mrmlScene.RemoveNode(existing)
            vol = slicer.util.getNode(f"{self.FRAME_VOL_PREFIX}{frame:02d}")
            seg = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode", name
            )
            seg.CreateDefaultDisplayNodes()
            seg.SetReferenceImageGeometryParameterFromVolumeNode(vol)
            seg.GetSegmentation().AddEmptySegment(
                "Perikard", "Perikard", [0.95, 0.35, 0.35]
            )
            seg.GetSegmentation().AddEmptySegment(
                "Epikard", "Epikard", [0.35, 0.65, 0.95]
            )

        if allow_overlap:
            self._configure_allow_overlap()

    def _configure_allow_overlap(self):
        """Set the Segment Editor's 'Modify other segments' to 'Allow overlap'."""
        editor_nodes = slicer.util.getNodesByClass("vtkMRMLSegmentEditorNode")
        if not editor_nodes:
            # No editor node yet — create a singleton so the Segment Editor
            # picks it up when the radiologist opens the module.
            node = slicer.vtkMRMLSegmentEditorNode()
            node.SetSingletonTag("SegmentEditor")
            node = slicer.mrmlScene.AddNode(node)
            editor_nodes = [node]
        for node in editor_nodes:
            node.SetOverwriteMode(
                slicer.vtkMRMLSegmentEditorNode.OverwriteNone
            )

    # ----- save ---------------------------------------------------
    def saveOutputs(self, patient_id, ed_frame, es_frame, output_dir):
        if not patient_id:
            raise ValueError("Patient ID is empty.")
        if not output_dir or not os.path.isdir(output_dir):
            raise ValueError(f"Output directory does not exist: {output_dir}")

        ed_vol = slicer.util.getNode(f"{self.FRAME_VOL_PREFIX}{ed_frame:02d}")
        es_vol = slicer.util.getNode(f"{self.FRAME_VOL_PREFIX}{es_frame:02d}")
        ed_seg = slicer.mrmlScene.GetFirstNodeByName(self.ED_SEG_NAME)
        es_seg = slicer.mrmlScene.GetFirstNodeByName(self.ES_SEG_NAME)
        if ed_seg is None or es_seg is None:
            raise RuntimeError(
                "ED/ES segmentations not found. Run step 2 first."
            )

        paths = {
            "ed_mri": os.path.join(output_dir, f"{patient_id}_3D_ED_MRI.nii.gz"),
            "es_mri": os.path.join(output_dir, f"{patient_id}_3D_ES_MRI.nii.gz"),
            "ed_seg": os.path.join(
                output_dir, f"{patient_id}_3D_ED_segmentation.nii.gz"
            ),
            "es_seg": os.path.join(
                output_dir, f"{patient_id}_3D_ES_segmentation.nii.gz"
            ),
            "fourd": os.path.join(output_dir, f"{patient_id}_4D_MRI.nii.gz"),
        }
        slicer.util.saveNode(ed_vol, paths["ed_mri"])
        slicer.util.saveNode(es_vol, paths["es_mri"])
        self._save_segmentation(ed_seg, ed_vol, paths["ed_seg"])
        self._save_segmentation(es_seg, es_vol, paths["es_seg"])
        self._save_4d_nifti(paths["fourd"])
        return list(paths.values())

    def _save_segmentation(self, seg_node, ref_vol, path):
        """Export segmentation as a labelmap NIfTI aligned to the reference volume.
        Label values: 1 = Perikard, 2 = Epikard (in the order segments were added)."""
        labelmap = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        try:
            ok = slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(
                seg_node, labelmap, ref_vol
            )
            if not ok:
                raise RuntimeError("Segmentation export failed.")
            slicer.util.saveNode(labelmap, path)
        finally:
            slicer.mrmlScene.RemoveNode(labelmap)

    def _save_4d_nifti(self, path):
        import SimpleITK as sitk
        import sitkUtils

        frame_nodes = sorted(
            [
                n
                for n in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
                if n.GetName().startswith(self.FRAME_VOL_PREFIX)
            ],
            key=lambda n: int(n.GetName().split("_")[-1]),
        )
        if not frame_nodes:
            raise RuntimeError("No per-frame volumes found.")
        sitk_imgs = [sitkUtils.PullVolumeFromSlicer(v) for v in frame_nodes]
        img_4d = sitk.JoinSeries(sitk_imgs)
        sitk.WriteImage(img_4d, path)

    # ----- helpers ------------------------------------------------
    def guessPatientId(self):
        """Try to read PatientID from the DICOM database for any loaded series."""
        try:
            db = slicer.dicomDatabase
            patients = db.patients()
            if patients:
                studies = db.studiesForPatient(patients[0])
                if studies:
                    series = db.seriesForStudy(studies[0])
                    if series:
                        files = db.filesForSeries(series[0])
                        if files:
                            return db.fileValue(files[0], "0010,0020")  # PatientID
        except Exception:
            pass
        return ""