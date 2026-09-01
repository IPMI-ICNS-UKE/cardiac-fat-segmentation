import os
import re
import csv as csvlib
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
class SAXQualityControl(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        parent.title = "SAX Quality Control"
        parent.categories = ["Cardiac"]
        parent.contributors = ["Your team"]
        parent.helpText = (
            "Quality control workflow for SAX cine segmentations.\n\n"
            "Before opening this module, load the patient's SAX cine series "
            "via the standard DICOM module.\n\n"
            "1. Stitch loaded SAX series → 4D MRI + 3D ED MRI.\n"
            "2. Load an existing segmentation from a folder.\n"
            "3. Optionally save 4D + 3D ED as NIfTI.\n"
            "4. Open Segment Editor to review and correct.\n"
            "5. Save corrected segmentation (overwrites original)."
        )


# ─────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────
class SAXQualityControlWidget(ScriptedLoadableModuleWidget):

    @staticmethod
    def _make_status_widget(placeholder_text, min_height=60):
        w = qt.QPlainTextEdit()
        w.readOnly = True
        w.setMinimumHeight(min_height)
        w.setMaximumHeight(min_height + 40)   # cap growth
        w.setLineWrapMode(qt.QPlainTextEdit.WidgetWidth)
        w.setFrameShape(qt.QFrame.NoFrame)
        w.setStyleSheet(
            "QPlainTextEdit { background-color: palette(window); "
            "font-size: 11px; padding: 2px; }"
        )
        w.setPlainText(placeholder_text)
        return w

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = SAXQualityControlLogic()

        # --- Section 1: Stitch ----------------------------------------
        box1 = ctk.ctkCollapsibleButton()
        box1.text = "1. Stitch loaded SAX series"
        self.layout.addWidget(box1)
        l1 = qt.QFormLayout(box1)

        self.edFrameSpin = qt.QSpinBox()
        self.edFrameSpin.minimum, self.edFrameSpin.maximum = 0, 100
        self.edFrameSpin.value = 0
        self.edFrameSpin.toolTip = (
            "Index of the end-diastolic frame. For most CINE MRI protocols "
            "this is frame 0."
        )
        l1.addRow("ED frame index:", self.edFrameSpin)

        self.stitchButton = qt.QPushButton("Stitch loaded SAX series")
        self.stitchButton.toolTip = (
            "Finds all sequences whose name contains 'SAX' and '_bN' "
            "(excluding InlineVF), stacks them into one 4D sequence plus "
            "one 3D ED volume, and removes the originals."
        )
        self.stitchButton.connect("clicked()", self.onStitch)
        l1.addRow(self.stitchButton)

        self.stitchStatusLabel = self._make_status_widget(
            "Not stitched yet.", min_height=100
        )
        l1.addRow("Status:", self.stitchStatusLabel)

        # --- Section 2: Load segmentation ----------------------------
        box2 = ctk.ctkCollapsibleButton()
        box2.text = "2. Load segmentation"
        self.layout.addWidget(box2)
        l2 = qt.QFormLayout(box2)

        seg_row = qt.QHBoxLayout()
        self.segFolderEdit = qt.QLineEdit()
        self.segFolderEdit.placeholderText = (
            "Auto-filled after stitching if detected"
        )
        seg_row.addWidget(self.segFolderEdit)
        self.segBrowseButton = qt.QPushButton("Browse…")
        self.segBrowseButton.connect("clicked()", self.onBrowseSegFolder)
        seg_row.addWidget(self.segBrowseButton)
        l2.addRow("Folder:", seg_row)

        self.nestedContourCheck = qt.QCheckBox(
            "Reconstruct nested contours (Perikard ⊇ Epikard)"
        )
        self.nestedContourCheck.checked = True
        self.nestedContourCheck.toolTip = (
            "The segmentations produced by SAXCineHelper use overlapping, "
            "nested contours: Perikard fully contains Epikard. NIfTI "
            "labelmaps can only store one label per voxel, so on reload "
            "Perikard would otherwise appear as only the fat ring. This "
            "option restores the nested convention. Uncheck for "
            "segmentations from other tools where segments should not "
            "overlap."
        )
        l2.addRow(self.nestedContourCheck)

        self.loadSegButton = qt.QPushButton("Load segmentation")
        self.loadSegButton.connect("clicked()", self.onLoadSegmentation)
        l2.addRow(self.loadSegButton)

        self.segStatusLabel = self._make_status_widget(
            "No segmentation loaded."
        )
        l2.addRow("Status:", self.segStatusLabel)

        # --- Section 3: Save NIfTI ------------------------------------
        box3 = ctk.ctkCollapsibleButton()
        box3.text = "3. Save 4D + 3D ED as NIfTI"
        self.layout.addWidget(box3)
        l3 = qt.QFormLayout(box3)

        self.niftiTargetLabel = self._make_status_widget(
            "Target folder: (shown after stitching)", min_height=40
        )
        l3.addRow(self.niftiTargetLabel)

        self.saveNiftiButton = qt.QPushButton("Save 4D + 3D ED")
        self.saveNiftiButton.connect("clicked()", self.onSaveNifti)
        l3.addRow(self.saveNiftiButton)

        self.niftiStatusLabel = self._make_status_widget(
            "Not saved yet."
        )
        l3.addRow("Status:", self.niftiStatusLabel)

        # --- Section 4: Open Segment Editor --------------------------
        box4 = ctk.ctkCollapsibleButton()
        box4.text = "4. Open Segment Editor"
        self.layout.addWidget(box4)
        l4 = qt.QFormLayout(box4)

        self.allowOverlapCheck = qt.QCheckBox("Allow overlapping segments")
        self.allowOverlapCheck.checked = True
        self.allowOverlapCheck.toolTip = (
            "Sets the Segment Editor's 'Modify other segments' to "
            "'Allow overlap'."
        )
        l4.addRow(self.allowOverlapCheck)

        self.openEditorButton = qt.QPushButton("Open Segment Editor")
        self.openEditorButton.connect("clicked()", self.onOpenEditor)
        l4.addRow(self.openEditorButton)

        # --- Section 5: Save corrected segmentation ------------------
        box5 = ctk.ctkCollapsibleButton()
        box5.text = "5. Save corrected segmentation"
        self.layout.addWidget(box5)
        l5 = qt.QFormLayout(box5)

        warn = qt.QLabel(
            "⚠ This overwrites the original .nii.gz and labels.csv "
            "in the segmentation folder."
        )
        warn.wordWrap = True
        l5.addRow(warn)

        self.saveCorrButton = qt.QPushButton("Save corrected segmentation")
        self.saveCorrButton.connect("clicked()", self.onSaveCorrections)
        l5.addRow(self.saveCorrButton)

        self.corrStatusLabel = self._make_status_widget(
            "Not saved yet."
        )
        l5.addRow("Status:", self.corrStatusLabel)

        self.layout.addStretch(1)

    # ----- callbacks ---------------------------------------------
    def onStitch(self):
        try:
            n_slices, n_frames = self.logic.stitchSAXSequences(
                ed_frame=self.edFrameSpin.value
            )
            self.edFrameSpin.maximum = n_frames - 1

            lines = [
                f"OK: {n_slices} slices × {n_frames} frames.",
                f"4D volume: {self.logic.FOURD_NAME}",
                f"3D ED (frame {self.edFrameSpin.value}): "
                f"{self.logic.ED_VOL_NAME}",
            ]
            if self.logic.patient_code:
                lines.append(f"Patient code: {self.logic.patient_code}")
            if self.logic.patient_dir:
                lines.append(f"Patient folder: {self.logic.patient_dir}")

            if self.logic.parent_folder and self.logic.patient_code:
                guess = os.path.join(
                    self.logic.parent_folder,
                    f"seg_{self.logic.patient_code}",
                )
                self.segFolderEdit.text = guess
                if not os.path.isdir(guess):
                    lines.append(
                        f"Note: guessed seg folder does not exist yet:\n{guess}"
                    )
                nii_target = os.path.join(
                    self.logic.parent_folder,
                    f"nii_{self.logic.patient_code}",
                )
                self.niftiTargetLabel.setPlainText(
                    f"Target folder: {nii_target}"
                )
            else:
                lines.append(
                    "Patient folder not auto-detected — please pick the "
                    "segmentation folder manually below."
                )
                self.niftiTargetLabel.setPlainText(
                    "Target folder: — (cannot compute; patient folder "
                    "not detected)"
                )

            self.stitchStatusLabel.setPlainText("\n".join(lines))
        except Exception as e:
            slicer.util.errorDisplay(f"Stitching failed:\n{e}")

    def onBrowseSegFolder(self):
        initial = self.segFolderEdit.text or self.logic.parent_folder or ""
        folder = qt.QFileDialog.getExistingDirectory(
            None, "Select segmentation folder", initial
        )
        if folder:
            self.segFolderEdit.text = folder

    def onLoadSegmentation(self):
        folder = self.segFolderEdit.text.strip()
        if not folder:
            slicer.util.warningDisplay(
                "Please specify a segmentation folder (browse or type)."
            )
            return
        if not os.path.isdir(folder):
            slicer.util.errorDisplay(f"Folder does not exist:\n{folder}")
            return
        try:
            info = self.logic.loadSegmentation(
                folder,
                reconstruct_nested=self.nestedContourCheck.checked,
            )
            ed_vol = slicer.mrmlScene.GetFirstNodeByName(
                self.logic.ED_VOL_NAME
            )
            if ed_vol:
                slicer.util.setSliceViewerLayers(background=ed_vol, fit=True)
            labels_note = (
                f" ({len(info['labels'])} labels)"
                if info["csv"] else " (no labels.csv found — used defaults)"
            )
            nesting_note = (
                "\nNested contours reconstructed."
                if self.nestedContourCheck.checked else ""
            )
            self.segStatusLabel.setPlainText(
                f"Loaded {os.path.basename(info['nifti'])}{labels_note}\n"
                f"from: {folder}{nesting_note}"
            )
        except Exception as e:
            slicer.util.errorDisplay(f"Loading failed:\n{e}")

    def onSaveNifti(self):
        try:
            if not self.logic.patient_code or not self.logic.parent_folder:
                slicer.util.errorDisplay(
                    "Patient code or parent folder not detected. Cannot "
                    "compute the target path automatically.\n\n"
                    "This usually means the DICOM was imported into "
                    "Slicer's database cache rather than referenced from "
                    "its original location. Re-import the patient with "
                    "'Copy imported files: OFF' and re-run stitching."
                )
                return
            paths = self.logic.saveNiftiVolumes()
            self.niftiStatusLabel.setPlainText(
                "Saved:\n" + "\n".join(os.path.basename(p) for p in paths)
            )
        except Exception as e:
            slicer.util.errorDisplay(f"Save failed:\n{e}")

    def onOpenEditor(self):
        if self.allowOverlapCheck.checked:
            self.logic.configureAllowOverlap()
        self.logic.configureSegmentEditor()
        slicer.util.selectModule("SegmentEditor")

    def onSaveCorrections(self):
        try:
            if not self.logic.seg_nifti_path:
                slicer.util.errorDisplay(
                    "No segmentation loaded — nothing to overwrite."
                )
                return
            if not slicer.util.confirmYesNoDisplay(
                f"Overwrite:\n{self.logic.seg_nifti_path}\n"
                f"and its labels CSV?"
            ):
                return
            paths = self.logic.saveCorrections()
            self.corrStatusLabel.setPlainText(
                "Saved:\n" + "\n".join(os.path.basename(p) for p in paths)
            )
        except Exception as e:
            slicer.util.errorDisplay(f"Save failed:\n{e}")


# ─────────────────────────────────────────────────────────────────────
# Logic
# ─────────────────────────────────────────────────────────────────────
class SAXQualityControlLogic(ScriptedLoadableModuleLogic):

    FOURD_NAME = "SAX_4D"
    BROWSER_NAME = "SAX_4D_browser"
    PROXY_NAME = "SAX_4D_proxy"
    ED_VOL_NAME = "SAX_ED"
    SEG_NAME = "SAX_segmentation"

    # Used when no labels.csv is found — matches SAXCineHelper defaults.
    DEFAULT_LABELS = {
        1: {"name": "Perikard", "color": [0.95, 0.35, 0.35]},
        2: {"name": "Epikard", "color": [0.35, 0.65, 0.95]},
    }

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.reset_state()

    def reset_state(self):
        self.patient_dir = None
        self.patient_code = None
        self.parent_folder = None
        self.ed_frame = 0
        self.seg_nifti_path = None
        self.seg_csv_path = None

    # ----- stitching --------------------------------------------
    def stitchSAXSequences(self, ed_frame=0):
        all_seqs = slicer.util.getNodesByClass("vtkMRMLSequenceNode")
        sax = [
            s for s in all_seqs
            if "SAX" in s.GetName()
            and "InlineVF" not in s.GetName()
            and re.search(r"_b\d+", s.GetName())
        ]
        if len(sax) < 2:
            raise RuntimeError(
                f"Found only {len(sax)} SAX b-series in the scene.\n\n"
                "Load the patient's SAX cine series via the DICOM module "
                "first, and ensure 'Preferred multi-volume import format' "
                "is set to 'volume sequence' under "
                "Edit → Application Settings → DICOM."
            )

        def bnum(seq):
            m = re.search(r"_b(\d+)", seq.GetName())
            return int(m.group(1))
        sax.sort(key=bnum)
        self._verify_or_resort_by_origin(sax)

        n_frames = sax[0].GetNumberOfDataNodes()
        n_slices = len(sax)

        if ed_frame < 0 or ed_frame >= n_frames:
            raise ValueError(
                f"ED frame {ed_frame} out of range [0, {n_frames - 1}]"
            )

        # Detect patient info from the loaded DICOM files BEFORE cleanup
        self._detect_patient_from_sequences(sax)

        # Fresh outputs
        self._clear_previous_results()
        self.seg_nifti_path = None
        self.seg_csv_path = None

        # Build the 4D sequence
        out_seq = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSequenceNode", self.FOURD_NAME
        )
        out_seq.SetIndexName("Frame")
        out_seq.SetIndexUnit("")

        ed_array = None
        ed_matrix = None
        temp_vols = []
        for f in range(n_frames):
            stacked = np.stack(
                [slicer.util.arrayFromVolume(s.GetNthDataNode(f))[0]
                 for s in sax],
                axis=0,
            )
            matrix = self._build_stacked_matrix(sax, f)
            vol = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLScalarVolumeNode", f"_tmp_frame_{f:02d}"
            )
            slicer.util.updateVolumeFromArray(vol, stacked)
            vol.SetIJKToRASMatrix(matrix)
            out_seq.SetDataNodeAtValue(vol, str(f))
            temp_vols.append(vol)
            if f == ed_frame:
                ed_array = stacked.copy()
                ed_matrix = matrix

        for v in temp_vols:
            slicer.mrmlScene.RemoveNode(v)

        # Browser + proxy
        browser = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSequenceBrowserNode", self.BROWSER_NAME
        )
        browser.AddSynchronizedSequenceNode(out_seq)
        slicer.modules.sequences.toolBar().setActiveBrowserNode(browser)

        proxy = browser.GetProxyNode(out_seq)
        if proxy:
            proxy.SetName(self.PROXY_NAME)
            proxy.CreateDefaultDisplayNodes()

        # Standalone 3D ED
        ed_vol = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode", self.ED_VOL_NAME
        )
        slicer.util.updateVolumeFromArray(ed_vol, ed_array)
        ed_vol.SetIJKToRASMatrix(ed_matrix)
        ed_vol.CreateDefaultDisplayNodes()

        # Cleanup original SAX b-series and any orphan browsers
        self._remove_original_sax()

        # Show 4D by default
        if proxy:
            slicer.util.setSliceViewerLayers(background=proxy, fit=True)

        self.ed_frame = ed_frame
        return n_slices, n_frames

    def _verify_or_resort_by_origin(self, sax):
        ref = sax[0]
        m = vtk.vtkMatrix4x4()
        ref.GetNthDataNode(0).GetIJKToRASMatrix(m)
        normal = np.array(
            [m.GetElement(0, 2), m.GetElement(1, 2), m.GetElement(2, 2)]
        )
        n = np.linalg.norm(normal)
        if n == 0:
            return
        normal /= n
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

    def _detect_patient_from_sequences(self, sax_sequences):
        """Infer patient DICOM folder by walking up from a loaded SAX file,
        skipping folders that look like DICOM export intermediate folders
        (SDY/SRS/IMG, DICOM/DICOMDIR)."""
        self.patient_dir = None
        self.patient_code = None
        self.parent_folder = None

        db = slicer.dicomDatabase
        if not db:
            return

        # Deliberately narrow: matches common Siemens/PACS exporter
        # intermediate folders. Real patient IDs like '2A9KD9T4M' or
        # 'S001' will not be confused with an intermediate.
        intermediate_re = re.compile(
            r"^(SDY\d+|SRS\d+|IMG\d+|DICOM|DICOMDIR|dicom)$"
        )

        for seq in sax_sequences:
            for i in range(seq.GetNumberOfDataNodes()):
                data_node = seq.GetNthDataNode(i)
                if data_node is None:
                    continue
                instance_uids = data_node.GetAttribute("DICOM.instanceUIDs")
                if not instance_uids:
                    continue
                first_uid = instance_uids.split()[0]
                file_path = db.fileForInstance(first_uid)
                if not (file_path and os.path.exists(file_path)):
                    continue

                # Walk up until we hit a folder that isn't a DICOM intermediate
                current = os.path.dirname(file_path)
                while True:
                    name = os.path.basename(current)
                    if name and not intermediate_re.match(name):
                        self.patient_dir = current
                        self.patient_code = name
                        self.parent_folder = os.path.dirname(current)
                        return
                    parent = os.path.dirname(current)
                    if parent == current:  # reached filesystem root
                        break
                    current = parent

                return  # give up on this sequence rather than trying more

    def _clear_previous_results(self):
        for name in (
            self.FOURD_NAME, self.BROWSER_NAME, self.PROXY_NAME,
            self.ED_VOL_NAME, self.SEG_NAME,
        ):
            n = slicer.mrmlScene.GetFirstNodeByName(name)
            if n:
                slicer.mrmlScene.RemoveNode(n)

    def _remove_original_sax(self):
        """Remove the SAX b-series inputs and orphan browsers."""
        keep = {
            self.FOURD_NAME, self.BROWSER_NAME, self.PROXY_NAME,
            self.ED_VOL_NAME, self.SEG_NAME,
        }
        for n in list(slicer.util.getNodesByClass("vtkMRMLSequenceNode")):
            nm = n.GetName()
            if nm in keep:
                continue
            if "SAX" in nm or "InlineVF" in nm:
                slicer.mrmlScene.RemoveNode(n)
        for n in list(slicer.util.getNodesByClass(
            "vtkMRMLSequenceBrowserNode"
        )):
            if n.GetName() in keep:
                continue
            slicer.mrmlScene.RemoveNode(n)
        for n in list(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")):
            nm = n.GetName()
            if nm in keep:
                continue
            if "SAX" in nm or "InlineVF" in nm:
                slicer.mrmlScene.RemoveNode(n)

    # ----- segmentation loading ----------------------------------
    def loadSegmentation(self, folder, reconstruct_nested=True):
        if not os.path.isdir(folder):
            raise ValueError(f"Not a folder: {folder}")

        files = os.listdir(folder)
        nifti_files = sorted([
            f for f in files
            if f.endswith(".nii.gz") or f.endswith(".nii")
        ])
        if not nifti_files:
            raise RuntimeError(f"No .nii.gz / .nii file found in:\n{folder}")
        nifti_path = os.path.join(folder, nifti_files[0])

        labels_dict = {}
        csv_path = None
        labels_files = [
            f for f in files
            if f.endswith(".labels.csv") or f.lower() == "labels.csv"
        ]
        if labels_files:
            csv_path = os.path.join(folder, labels_files[0])
            labels_dict = self._parse_labels_csv(csv_path)

        if not labels_dict:
            labels_dict = {
                k: dict(v) for k, v in self.DEFAULT_LABELS.items()
            }

        ref_vol = slicer.mrmlScene.GetFirstNodeByName(self.ED_VOL_NAME)
        if ref_vol is None:
            raise RuntimeError(
                "SAX_ED volume not found — run stitching first."
            )

        existing = slicer.mrmlScene.GetFirstNodeByName(self.SEG_NAME)
        if existing:
            slicer.mrmlScene.RemoveNode(existing)

        labelmap = slicer.util.loadLabelVolume(nifti_path)
        try:
            seg = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode", self.SEG_NAME
            )
            seg.CreateDefaultDisplayNodes()
            seg.SetReferenceImageGeometryParameterFromVolumeNode(ref_vol)

            ok = slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                labelmap, seg
            )
            if not ok:
                raise RuntimeError(f"Failed to import labelmap: {nifti_path}")

            self._apply_labels(seg, labels_dict)

            if reconstruct_nested:
                self._reconstruct_nested_contours(seg)
        finally:
            slicer.mrmlScene.RemoveNode(labelmap)

        # Store the original paths for save-back
        self.seg_nifti_path = nifti_path
        if csv_path:
            self.seg_csv_path = csv_path
        else:
            base = os.path.basename(nifti_path)
            if base.endswith(".nii.gz"):
                stem = base[:-7]
            elif base.endswith(".nii"):
                stem = base[:-4]
            else:
                stem = base
            self.seg_csv_path = os.path.join(folder, f"{stem}.labels.csv")

        return {"nifti": nifti_path, "labels": labels_dict, "csv": csv_path}

    def _parse_labels_csv(self, path):
        labels = {}
        try:
            with open(path, "r", newline="") as f:
                reader = csvlib.DictReader(f)
                if not reader.fieldnames:
                    return labels
                cols = {fn.lower().strip(): fn for fn in reader.fieldnames}

                def col(*aliases):
                    for a in aliases:
                        if a in cols:
                            return cols[a]
                    return None

                label_col = col("label", "labelvalue", "label_value",
                                "id", "value")
                name_col = col("name", "structure", "label_name",
                               "segmentname")
                r_col = col("r", "red", "color_r", "colorr")
                g_col = col("g", "green", "color_g", "colorg")
                b_col = col("b", "blue", "color_b", "colorb")

                if label_col is None or name_col is None:
                    return labels

                for row in reader:
                    try:
                        lv = int(row[label_col])
                        if lv <= 0:
                            continue
                        name = str(row[name_col]).strip()
                        color = None
                        if r_col and g_col and b_col:
                            r = float(row[r_col])
                            g = float(row[g_col])
                            b = float(row[b_col])
                            if max(r, g, b) > 1.0:
                                r, g, b = r / 255.0, g / 255.0, b / 255.0
                            color = [r, g, b]
                        labels[lv] = {"name": name, "color": color}
                    except (ValueError, KeyError, TypeError):
                        continue
        except Exception:
            pass
        return labels

    def _apply_labels(self, seg_node, labels_dict):
        if not labels_dict:
            return
        segmentation = seg_node.GetSegmentation()
        seg_ids = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(seg_ids)
        sorted_label_values = sorted(labels_dict.keys())
        for i in range(seg_ids.GetNumberOfValues()):
            if i >= len(sorted_label_values):
                break
            seg_id = seg_ids.GetValue(i)
            segment = segmentation.GetSegment(seg_id)
            info = labels_dict[sorted_label_values[i]]
            segment.SetName(info["name"])
            if info.get("color"):
                segment.SetColor(*info["color"])

    def _reconstruct_nested_contours(self, seg_node):
        """After loading a labelmap where inner segments overwrote outer ones,
        reconstruct the nested-contour convention: each segment (starting
        from the outermost / lowest label) is unioned with all segments
        below it in the label ordering.

        Assumes the annotation convention used by SAXCineHelper: segments
        are ordered outer-to-inner (Perikard = label 1, Epikard = label 2)
        and each outer segment fully contains the inner ones.
        """
        segmentation = seg_node.GetSegmentation()
        seg_ids = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(seg_ids)
        n = seg_ids.GetNumberOfValues()
        if n < 2:
            return

        ref_vol = slicer.mrmlScene.GetFirstNodeByName(self.ED_VOL_NAME)
        if ref_vol is None:
            return

        ids = [seg_ids.GetValue(i) for i in range(n)]

        # Snapshot every mask BEFORE modifying any of them
        masks = [
            slicer.util.arrayFromSegmentBinaryLabelmap(
                seg_node, sid, ref_vol
            ) > 0
            for sid in ids
        ]

        # Segment i absorbs segments i+1 .. n-1
        for i in range(n - 1):  # last segment (innermost) is left as-is
            union_mask = masks[i].copy()
            for j in range(i + 1, n):
                union_mask |= masks[j]
            if not np.array_equal(union_mask, masks[i]):
                slicer.util.updateSegmentBinaryLabelmapFromArray(
                    union_mask.astype(np.uint8),
                    seg_node, ids[i], ref_vol,
                )

    # ----- NIfTI save (4D + 3D ED) -------------------------------
    def saveNiftiVolumes(self):
        if not self.patient_code or not self.parent_folder:
            raise RuntimeError(
                "Patient code / parent folder not detected — cannot "
                "compute target path."
            )
        target = os.path.join(
            self.parent_folder, f"nii_{self.patient_code}"
        )
        os.makedirs(target, exist_ok=True)

        seq = slicer.mrmlScene.GetFirstNodeByName(self.FOURD_NAME)
        ed_vol = slicer.mrmlScene.GetFirstNodeByName(self.ED_VOL_NAME)
        if seq is None or ed_vol is None:
            raise RuntimeError(
                "Missing 4D or ED volume — run stitching first."
            )

        fourd_path = os.path.join(
            target, f"{self.patient_code}_4D_MRI.nii.gz"
        )
        ed_path = os.path.join(
            target, f"{self.patient_code}_3D_ED_MRI.nii.gz"
        )

        self._save_4d_as_nifti(seq, fourd_path)
        slicer.util.saveNode(ed_vol, ed_path)
        return [fourd_path, ed_path]

    def _save_4d_as_nifti(self, seq_node, path):
        import SimpleITK as sitk
        import sitkUtils

        n_frames = seq_node.GetNumberOfDataNodes()
        temp_nodes = []
        for f in range(n_frames):
            data = seq_node.GetNthDataNode(f)
            tmp = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLScalarVolumeNode", f"_save4d_tmp_{f:02d}"
            )
            arr = slicer.util.arrayFromVolume(data)
            slicer.util.updateVolumeFromArray(tmp, arr)
            matrix = vtk.vtkMatrix4x4()
            data.GetIJKToRASMatrix(matrix)
            tmp.SetIJKToRASMatrix(matrix)
            temp_nodes.append(tmp)
        try:
            sitk_imgs = [sitkUtils.PullVolumeFromSlicer(v)
                         for v in temp_nodes]
            img_4d = sitk.JoinSeries(sitk_imgs)
            sitk.WriteImage(img_4d, path)
        finally:
            for n in temp_nodes:
                slicer.mrmlScene.RemoveNode(n)

    # ----- Segment Editor helpers --------------------------------
    def configureAllowOverlap(self):
        editor_nodes = slicer.util.getNodesByClass("vtkMRMLSegmentEditorNode")
        if not editor_nodes:
            node = slicer.vtkMRMLSegmentEditorNode()
            node.SetSingletonTag("SegmentEditor")
            node = slicer.mrmlScene.AddNode(node)
            editor_nodes = [node]
        for node in editor_nodes:
            node.SetOverwriteMode(
                slicer.vtkMRMLSegmentEditorNode.OverwriteNone
            )

    def configureSegmentEditor(self):
        editor_nodes = slicer.util.getNodesByClass("vtkMRMLSegmentEditorNode")
        if not editor_nodes:
            node = slicer.vtkMRMLSegmentEditorNode()
            node.SetSingletonTag("SegmentEditor")
            node = slicer.mrmlScene.AddNode(node)
            editor_nodes = [node]

        seg = slicer.mrmlScene.GetFirstNodeByName(self.SEG_NAME)
        ed_vol = slicer.mrmlScene.GetFirstNodeByName(self.ED_VOL_NAME)

        for node in editor_nodes:
            if seg:
                node.SetAndObserveSegmentationNode(seg)
            if ed_vol:
                if hasattr(node, "SetAndObserveSourceVolumeNode"):
                    node.SetAndObserveSourceVolumeNode(ed_vol)
                elif hasattr(node, "SetAndObserveMasterVolumeNode"):
                    node.SetAndObserveMasterVolumeNode(ed_vol)

    # ----- Save corrections --------------------------------------
    def saveCorrections(self):
        if not self.seg_nifti_path:
            raise RuntimeError(
                "No segmentation loaded — nothing to overwrite."
            )
        seg = slicer.mrmlScene.GetFirstNodeByName(self.SEG_NAME)
        ref = slicer.mrmlScene.GetFirstNodeByName(self.ED_VOL_NAME)
        if seg is None or ref is None:
            raise RuntimeError(
                "Segmentation or ED volume missing from the scene."
            )

        self._save_segmentation_nifti(seg, ref, self.seg_nifti_path)
        self._save_labels_csv(seg, self.seg_csv_path)
        return [self.seg_nifti_path, self.seg_csv_path]

    def _save_segmentation_nifti(self, seg_node, ref_vol, path):
        labelmap = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLabelMapVolumeNode"
        )
        try:
            ok = slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(
                seg_node, labelmap, ref_vol
            )
            if not ok:
                raise RuntimeError("Segmentation export failed.")
            slicer.util.saveNode(labelmap, path)
        finally:
            slicer.mrmlScene.RemoveNode(labelmap)

    def _save_labels_csv(self, seg_node, csv_path):
        segmentation = seg_node.GetSegmentation()
        seg_ids = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(seg_ids)
        rows = []
        for i in range(seg_ids.GetNumberOfValues()):
            seg_id = seg_ids.GetValue(i)
            segment = segmentation.GetSegment(seg_id)
            color = segment.GetColor()
            rows.append({
                "label": i + 1,
                "name": segment.GetName(),
                "r": f"{color[0]:.4f}",
                "g": f"{color[1]:.4f}",
                "b": f"{color[2]:.4f}",
            })
        with open(csv_path, "w", newline="") as f:
            writer = csvlib.DictWriter(
                f, fieldnames=["label", "name", "r", "g", "b"]
            )
            writer.writeheader()
            writer.writerows(rows)