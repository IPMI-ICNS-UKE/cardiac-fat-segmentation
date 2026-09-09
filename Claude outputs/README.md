# Papers thumbnails — segmentation methods for EAT/PAT in CMR

Literature scan for **WP 2 (Development of DL models for EAT and PAT segmentation)** of the EKFS project
*"Epicardial and Paracardial Adipose Tissue as Imaging Biomarkers of Myocardial Scar and Outcome Predictors in the Hamburg City Health Study"*.

Compiled 2026-09-07. One `.md` per paper: bibliographic header, abstract, and a short note on relevance to this project.
Numbering groups papers by theme; it is not a ranking.

---

## 00–09 · Core: EAT/PAT segmentation and quantification in CMR

| # | Paper | Why |
|---|---|---|
| [01](01_Zhang_2026_EAT-PAT_shortaxis_cine_DL.md) | Zhang et al. 2026, MAGMA — EAT/PAT in short-axis cine, modified U-Net | **Closest published work to WP 2**; the "Zhang et al. 2025" of the sketch. Dice ≈ 0.77 both compartments — the number to beat |
| [02](02_Bard_2021_UKBiobank_pericardial_fat_CNN.md) | Bard et al. 2021, Front Cardiovasc Med — UK Biobank pericardial fat CNN | Sketch starting point. **Monte-Carlo-dropout quality control predicting per-case Dice** → case triage for the HiL queue |
| [03](03_Daude_2022_four-chamber_EAT_multiframe_UNet.md) | Daudé et al. 2022, Diagnostics — four-chamber EAT, multi-frame U-Net | Sketch starting point. Multi-frame input; benchmarked against inter-observer bias |
| [04](04_Feng_2026_spatial_phenotyping_EAT_CMR.md) | Feng et al. 2026, Med Image Anal — spatial phenotyping of EAT | Newest SOTA. **CNN–Transformer**, thickness maps, chamber-resolved regional EAT |
| [05](05_Guglielmo_2024_EAT_stressCMR_MACE.md) | Guglielmo et al. 2024, Atherosclerosis — DL EAT volume, stress CMR, MACE | Prior claim of DL EAT *volume* in CMR — scope the novelty statement. Statistical template for WP 5.2 |

## 10–19 · EAT/PAT in CT (where the DL tooling already exists)

| # | Paper | Why |
|---|---|---|
| [10](10_Eisenberg_2020_EAT_CT_MACE_deeplearning.md) | Eisenberg et al. 2020, Circ Cardiovasc Imaging | The reference in the sketch; **basis of the WP 1 sample-size calculation**. Volume + attenuation ≈ your volume + T1 |
| [11](11_Commandeur_2018_EAT_TAT_CT_multitask_CNN.md) | Commandeur et al. 2018, IEEE TMI | **Most structurally relevant CT paper**: CNN + statistical shape model detects the *pericardium*, fat derived between boundaries — the CT twin of your contour strategy |
| [12](12_Militello_2019_semiautomatic_EAT_CT_quartiles.md) | Militello et al. 2019, Comput Biol Med | Semi-automatic, no training data; area *and* distance metrics; density-quartile analysis |
| [13](13_Lian_2025_finegrained_EAT_CT_position_priors.md) | Lian et al. 2025, Biomed Eng Lett | Names the problem: class imbalance + thin structures. **Position priors + edge-enhancement branch** |

## 20–29 · Thin structures, contours, level sets, shape priors, meshes

| # | Paper | Why |
|---|---|---|
| [20](20_Wang_2021_LsUnet_levelset_endo_epicardium.md) | Wang et al. 2021, QIMS — LsUnet | **The "Y. Wang et al. 2021" of WP 2.2.** CNN contours + annular-shape level set. Your three borders are nested annuli |
| [21](21_Kervadec_2019_boundary_loss.md) | Kervadec et al., Med Image Anal — boundary loss | Cheapest first intervention for the thin-fissure / imbalance problem; active-contour flow as a differentiable loss |
| [22](22_Shit_2021_clDice_topology_preserving_loss.md) | Shit et al. 2021, CVPR — clDice | Topology-preserving loss *and* connectivity-sensitive metric |
| [23](23_Kirchhoff_2024_skeleton_recall_loss.md) | Kirchhoff et al. 2024, ECCV — Skeleton Recall Loss | **Highest-value cheap experiment**: 3D, multi-class, drops into nnU-Net |
| [24](24_Oktay_2018_ACNN_anatomically_constrained.md) | Oktay et al. 2018, IEEE TMI — ACNN | Answers "prior knowledge about the heart shape?" — learned shape regulariser, end-to-end |
| [25](25_Kong_2021_direct_wholeheart_mesh_reconstruction.md) | Kong, Wilson & Shadden 2021, Med Image Anal — MeshDeformNet | Mesh route. Kills stair-case artefacts from thick SAX slices; **sub-voxel volumes between two closed surfaces** |
| [26](26_Gaggion_2025_HybridVNet_volume_to_mesh_CMR.md) | Gaggion et al. 2025, Med Image Anal — HybridVNet | **CMR-native mesh method**, multi-view SAX + long-axis, UK Biobank scale. Answers "graph machine learning?" |
| [27](27_Ngo_2017_deeplearning_levelset_LV.md) | Ngo, Lu & Carneiro 2017, Med Image Anal | Origin of the DL + level-set argument, motivated explicitly by **small training sets** |

## 30–39 · Baselines, backbones, benchmarks, vendor generalization

| # | Paper | Why |
|---|---|---|
| [30](30_Isensee_2021_nnUNet.md) | Isensee et al. 2021, Nat Methods — nnU-Net | The mandatory baseline. Answers your "what if nnU-Net already works?" question |
| [31](31_Isensee_2024_nnUNet_revisited.md) | Isensee et al. 2024, MICCAI — nnU-Net Revisited | Transformers usually *don't* beat a well-scaled CNN. Validation protocol to adopt now |
| [32](32_Hatamizadeh_2022_UNETR.md) | Hatamizadeh et al. 2022, WACV — UNETR | Transformer arm, option A |
| [33](33_Hatamizadeh_2022_SwinUNETR.md) | Hatamizadeh et al. 2022 — Swin UNETR | Transformer arm, option B; **self-supervised pretraining on your unlabelled HCHS scans** |
| [34](34_Roy_2023_MedNeXt.md) | Roy et al. 2023, MICCAI — MedNeXt | "Transformer-inspired" but data-efficient; large kernels; runs inside nnU-Net |
| [35](35_Campello_2021_MMs_challenge.md) | Campello et al. 2021, IEEE TMI — M&Ms | **Evidence base for WP 6.** Intensity-driven augmentation is what actually helped. Open 4-vendor dataset |
| [36](36_Ma_2024_MedSAM.md) | Ma et al. 2024, Nat Commun — MedSAM | Foundation-model reference point; better used as an interaction engine than a primary model |
| [37](37_Bernard_2018_ACDC_challenge.md) | Bernard et al. 2018, IEEE TMI — ACDC | Public SAX benchmark; pretraining for the heart-localisation stage; framing contrast for the intro |

## 40–49 · Human-in-the-loop, interactive segmentation, continual learning

| # | Paper | Why |
|---|---|---|
| [40](40_DiazPinto_2024_MONAILabel.md) | Diaz-Pinto et al. 2024, Med Image Anal — MONAI Label | **The WP 2.3 infrastructure**, already used by your group; 3D Slicer client + server retraining; two active-learning strategies |
| [41](41_Isensee_2025_nnInteractive.md) | Isensee et al. 2025 — nnInteractive | **Accelerates WP 2.1 too.** Lasso/scribble → 3D; maintained 3D Slicer extension |
| [42](42_Kolokolnikov_2025_anatomy_informed_NF_segmentation.md) | Kolokolnikov et al. 2025, Comput Med Imaging Graph | In-house precedent cited in WP 2.3. **Anatomy mask as extra input channel**; anisotropic 3D U-Net; Slicer integration |
| [43](43_Kolokolnikov_2025_MOIS_SAM2.md) | Kolokolnikov et al. 2025, Comput Biol Med — MOIS-SAM2 | Exemplar-based correction propagation; evaluation under vendor/field-strength shift **against inter-reader agreement** |
| [44](44_Kumari_2023_continual_learning_medical_imaging_review.md) | Kumari et al. 2023 — continual learning review | Answers "prevent catastrophic forgetting" for the 4–5 HiL cycles of WP 2.4: frozen test set + rehearsal buffer |

---

## Reading order if time is short

1. **01, 11, 20** — the three that most directly shape the WP 2.2 design (current SOTA; boundary-not-region strategy in CT; DL + level set in CMR).
2. **23, 21** — two cheap losses to add to an nnU-Net baseline before building anything custom.
3. **25, 26** — decide early whether the mesh route is in scope, because it changes the annotation format (contours/surfaces vs. masks) and the correction UI.
4. **02, 40, 41** — the WP 2.3/2.4 machinery: quality-control-driven triage + MONAI Label + nnInteractive.

## Notes on gaps

- **No published work does EAT *and* PAT volumes from the short-axis stack via boundary/surface contouring.** Zhang 2026 is short-axis but direct volumetric masks; Commandeur 2018 is boundary-based but CT. That intersection is the methodological contribution of WP 2.
- Deliberately excluded: clinical/epidemiological EAT papers (Iacobellis, Nelson, Ng, Lu, Goeller, Cau, van Meijeren) — those belong to WP 4/WP 5 rather than to the segmentation question. Say the word and I'll add a `literature/papers_thumbnails_clinical/` for them.
- Not yet retrieved: Painchaud et al., *Cardiac Segmentation with Strong Anatomical Guarantees* (IEEE TMI 2020, arXiv:2006.08825) — post-hoc projection of a segmentation onto a learned space of anatomically valid shapes; relevant to guaranteeing the nesting of your three borders. Worth adding.
- Abstracts marked *"condensed rendering"* (files 30, 32, 36) could not be retrieved verbatim through the available route; the DOI/arXiv links in those files give the published text.
