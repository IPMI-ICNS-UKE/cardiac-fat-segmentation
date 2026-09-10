"""Exploratory data analysis and QC checks for the organized EAT/PAT dataset.

Reads the case table produced by ``organize_data.py`` (``data/table/cases.xlsx``)
and, for every case:

1. Collects ED-volume geometry (size, spacing, direction, origin) and the 4D
   volume's frame count, for aggregate distributions.
2. Checks the label mask for missing/empty labels or unexpected values.
3. Checks that Epikard (label 2) is topologically nested inside Perikard
   (label 1) -- i.e. that Epikard does not directly touch the background,
   which would indicate a broken/un-reconstructed nested-contour export.
4/5. Computes Perikard and Epikard volumes in mL.
6/7. Computes image intensity statistics for the whole image and for each
   label region.
8. Renders a mid-slice image + mask overlay PNG per case for visual QC.

Outputs:
- output/eda/case_metrics.xlsx  (per-case metrics, flagged issues, summary stats)
- output/eda/plots/*.png        (distribution plots)
- output/qc_overlays/<case>.png (one overlay image per case, for click-through review)
"""

import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import seaborn as sns
import SimpleITK as sitk
from matplotlib.ticker import MaxNLocator
from scipy import ndimage

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE_PATH = os.path.join(PROJECT_ROOT, "data", "table", "cases.xlsx")

PLOT_DPI = 300
QC_OVERLAY_DPI = 130

OUT_EDA_DIR = os.path.join(PROJECT_ROOT, "output", "eda")
OUT_PLOTS_DIR = os.path.join(OUT_EDA_DIR, "plots")
OUT_QC_DIR = os.path.join(PROJECT_ROOT, "output", "qc_overlays")
METRICS_PATH = os.path.join(OUT_EDA_DIR, "case_metrics.xlsx")

# Fraction of Epikard's 2D boundary (per slice) allowed to touch background
# directly before we flag the case as having a broken nesting/export.
NESTING_TOUCH_BG_THRESHOLD = 0.02

DILATION_FOOTPRINT = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)

sns.set_theme(style="whitegrid", font_scale=0.95)


def load_cases(table_path):
    return pd.read_excel(table_path, sheet_name="cases")


def read_geometry_header(path):
    """Read image geometry without decoding the pixel buffer."""
    reader = sitk.ImageFileReader()
    reader.SetFileName(path)
    reader.ReadImageInformation()
    return reader.GetSize(), reader.GetSpacing(), reader.GetOrigin(), reader.GetDirection()


def nesting_touch_fraction(label_arr):
    """Fraction of Epikard (label 2) voxels that are 2D-adjacent to background
    (label 0), computed slice by slice. Near 0 means Epikard is fully
    enclosed by Perikard on every slice, as expected from the nested-contour
    annotation convention. NaN if the case has no Epikard voxels at all."""
    total_border = 0
    total_epikard = 0
    for z in range(label_arr.shape[0]):
        m2 = label_arr[z] == 2
        n2 = int(m2.sum())
        if n2 == 0:
            continue
        bg = label_arr[z] == 0
        bg_dilated = ndimage.binary_dilation(bg, structure=DILATION_FOOTPRINT)
        total_border += int((m2 & bg_dilated).sum())
        total_epikard += n2
    if total_epikard == 0:
        return np.nan
    return total_border / total_epikard


def build_overlay_png(case_id, img_arr, label_arr, spacing, n_frames, out_path):
    """Mid-slice grayscale image with a Perikard/Epikard mask overlay,
    respecting the true in-plane pixel spacing (aspect ratio)."""
    mid = img_arr.shape[0] // 2
    img_slice = img_arr[mid]
    lbl_slice = label_arr[mid]

    vmin, vmax = np.percentile(img_arr, [1, 99])
    aspect = spacing[1] / spacing[0]  # spacing = (x, y, z); rows scale with spacing_y

    overlay = np.zeros((*lbl_slice.shape, 4))
    overlay[lbl_slice == 1] = (1.0, 0.80, 0.0, 0.40)   # Perikard - gold
    overlay[lbl_slice == 2] = (0.85, 0.05, 0.35, 0.45)  # Epikard - crimson

    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.imshow(img_slice, cmap="gray", vmin=vmin, vmax=vmax, aspect=aspect)
    ax.imshow(overlay, aspect=aspect)
    ax.set_title(
        f"{case_id}\nslice {mid + 1}/{img_arr.shape[0]}  |  {n_frames} cardiac phases",
        fontsize=11,
    )
    ax.axis("off")
    handles = [
        mpatches.Patch(color=(1.0, 0.80, 0.0), label="Perikard"),
        mpatches.Patch(color=(0.85, 0.05, 0.35), label="Epikard"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.6)
    fig.tight_layout()
    fig.savefig(out_path, dpi=QC_OVERLAY_DPI)
    plt.close(fig)


def compute_case_record(case_id, img_path, lbl_path, img4d_path):
    img_sitk = sitk.ReadImage(img_path)
    lbl_sitk = sitk.ReadImage(lbl_path)
    img_arr = sitk.GetArrayFromImage(img_sitk).astype(np.float32)
    lbl_arr = sitk.GetArrayFromImage(lbl_sitk).astype(np.int16)

    size = img_sitk.GetSize()
    spacing = img_sitk.GetSpacing()
    origin = img_sitk.GetOrigin()
    direction = img_sitk.GetDirection()

    size4, spacing4, origin4, _ = read_geometry_header(img4d_path)
    n_frames = int(size4[3]) if len(size4) == 4 else np.nan
    geometry_mismatch = not (
        tuple(size4[:3]) == tuple(size)
        and np.allclose(spacing4[:3], spacing, atol=1e-3)
        and np.allclose(origin4[:3], origin, atol=1e-3)
    )

    unique_labels = np.unique(lbl_arr)
    unexpected = [int(v) for v in unique_labels if v not in (0, 1, 2)]
    n0 = int((lbl_arr == 0).sum())
    n1 = int((lbl_arr == 1).sum())
    n2 = int((lbl_arr == 2).sum())
    label1_empty = n1 == 0
    label2_empty = n2 == 0

    touch_frac = nesting_touch_fraction(lbl_arr)
    nesting_flag = (not np.isnan(touch_frac)) and touch_frac > NESTING_TOUCH_BG_THRESHOLD

    voxel_vol_mm3 = spacing[0] * spacing[1] * spacing[2]
    perikard_mL = n1 * voxel_vol_mm3 / 1000.0
    epikard_mL = n2 * voxel_vol_mm3 / 1000.0

    img_p1, img_p50, img_p99 = np.percentile(img_arr, [1, 50, 99])
    perikard_vals = img_arr[lbl_arr == 1]
    epikard_vals = img_arr[lbl_arr == 2]

    record = dict(
        case=case_id,
        size_x=size[0], size_y=size[1], size_z=size[2],
        spacing_x=spacing[0], spacing_y=spacing[1], spacing_z=spacing[2],
        origin_x=origin[0], origin_y=origin[1], origin_z=origin[2],
        **{f"direction_{i}": direction[i] for i in range(9)},
        n_frames=n_frames,
        ed_4d_geometry_mismatch=geometry_mismatch,
        n_voxels_label0=n0, n_voxels_label1=n1, n_voxels_label2=n2,
        unexpected_labels=str(unexpected) if unexpected else "",
        label1_empty=label1_empty, label2_empty=label2_empty,
        epikard_touch_background_frac=touch_frac,
        nesting_flag=nesting_flag,
        voxel_volume_mm3=voxel_vol_mm3,
        perikard_volume_mL=perikard_mL,
        epikard_volume_mL=epikard_mL,
        img_mean=float(img_arr.mean()), img_std=float(img_arr.std()),
        img_p1=float(img_p1), img_p50=float(img_p50), img_p99=float(img_p99),
        perikard_mean_intensity=float(perikard_vals.mean()) if perikard_vals.size else np.nan,
        perikard_std_intensity=float(perikard_vals.std()) if perikard_vals.size else np.nan,
        epikard_mean_intensity=float(epikard_vals.mean()) if epikard_vals.size else np.nan,
        epikard_std_intensity=float(epikard_vals.std()) if epikard_vals.size else np.nan,
    )
    flags = []
    if unexpected:
        flags.append((case_id, "unexpected_label_values", str(unexpected)))
    if label1_empty:
        flags.append((case_id, "empty_perikard", "label 1 (Perikard) has 0 voxels"))
    if label2_empty:
        flags.append((case_id, "empty_epikard", "label 2 (Epikard) has 0 voxels"))
    if nesting_flag:
        flags.append((
            case_id, "nesting_broken",
            f"{touch_frac * 100:.1f}% of Epikard's boundary touches background "
            f"directly (threshold {NESTING_TOUCH_BG_THRESHOLD * 100:.0f}%) -- Epikard "
            f"may not be fully enclosed by Perikard",
        ))
    if geometry_mismatch:
        flags.append((case_id, "ed_4d_geometry_mismatch",
                      "image_ed_3d and image_4d geometry do not match"))

    return record, flags, img_arr, lbl_arr, n_frames


def _int_axis(ax, axis="y"):
    getattr(ax, f"{axis}axis").set_major_locator(MaxNLocator(integer=True))


def _grid_hist(df, columns, title, filename, ncols=3, bins=20, round_decimals=None):
    """Histogram grid for continuous-valued columns."""
    round_decimals = round_decimals or {}
    n = len(columns)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.4 * nrows), squeeze=False)
    axes = axes.flatten()
    for ax, col in zip(axes, columns):
        data = df[col].dropna()
        if col in round_decimals:
            data = data.round(round_decimals[col])
        use_kde = data.nunique() >= 5
        sns.histplot(data, bins=min(bins, max(data.nunique(), 1)), kde=use_kde, ax=ax, color="steelblue")
        ax.axvline(data.mean(), color="firebrick", linestyle="--", linewidth=1)
        ax.set_title(f"{col}\nmean={df[col].mean():.4g}  sd={df[col].std():.4g}", fontsize=10)
        ax.set_xlabel("")
        _int_axis(ax, "y")
    for ax in axes[n:]:
        ax.axis("off")
    fig.suptitle(title, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(os.path.join(OUT_PLOTS_DIR, filename), dpi=PLOT_DPI)
    plt.close(fig)


def _grid_count(df, columns, title, filename, ncols=3):
    """Bar/count plot grid for discrete integer-valued columns (voxel counts,
    frame counts, ...): only observed integer values are shown on the x-axis
    and both axes use integer ticks."""
    n = len(columns)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.4 * nrows), squeeze=False)
    axes = axes.flatten()
    for ax, col in zip(axes, columns):
        data = df[col].dropna().round().astype(int)
        sns.countplot(x=data, ax=ax, color="steelblue", order=sorted(data.unique()))
        ax.set_title(f"{col}\nmean={data.mean():.4g}  sd={data.std():.4g}", fontsize=10)
        ax.set_xlabel("")
        ax.set_ylabel("count")
        _int_axis(ax, "y")
    for ax in axes[n:]:
        ax.axis("off")
    fig.suptitle(title, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(os.path.join(OUT_PLOTS_DIR, filename), dpi=PLOT_DPI)
    plt.close(fig)


def make_geometry_plots(df):
    _grid_count(df, ["size_x", "size_y", "size_z"], "image_ed_3d: size (voxels)", "01_ed_size.png")
    # spacing_z is a nominal ~10 mm slice gap; the raw value carries ~1e-5 mm
    # floating-point reconstruction noise that makes a raw histogram
    # unreadable, so round it for display purposes only.
    _grid_hist(df, ["spacing_x", "spacing_y", "spacing_z"], "image_ed_3d: spacing (mm)",
               "02_ed_spacing.png", round_decimals={"spacing_z": 2})
    _grid_hist(df, ["origin_x", "origin_y", "origin_z"], "image_ed_3d: origin (mm)", "03_ed_origin.png")
    _grid_count(df, ["n_frames"], "image_4d: number of cardiac phases (frames)",
                "04_4d_n_frames.png", ncols=1)


def make_volume_plots(df):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    specs = [
        ("perikard_volume_mL", "Perikard volume [mL]", "goldenrod"),
        ("epikard_volume_mL", "Epikard volume [mL]", "crimson"),
    ]
    for ax, (col, label, color) in zip(axes, specs):
        data = df[col].dropna()
        sns.histplot(data, bins=20, kde=True, ax=ax, color=color)
        ax.axvline(data.mean(), color="black", linestyle="--", linewidth=1)
        ax.set_title(f"{label}\nmean={data.mean():.1f}  median={data.median():.1f}  sd={data.std():.1f}")
        ax.set_xlabel("mL")
        _int_axis(ax, "y")
    fig.suptitle("Label volume distributions", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(OUT_PLOTS_DIR, "05_volumes.png"), dpi=PLOT_DPI)
    plt.close(fig)


def make_intensity_plots(df, cache_img, cache_lbl):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    specs = [
        ("img_mean", "Whole image\nper-case mean intensity", "steelblue"),
        ("perikard_mean_intensity", "Perikard region\nper-case mean intensity", "goldenrod"),
        ("epikard_mean_intensity", "Epikard region\nper-case mean intensity", "crimson"),
    ]
    for ax, (col, title, color) in zip(axes, specs):
        data = df[col].dropna()
        sns.histplot(data, bins=20, kde=True, ax=ax, color=color)
        ax.axvline(data.mean(), color="black", linestyle="--", linewidth=1)
        ax.set_title(f"{title}\nmean={data.mean():.1f}  sd={data.std():.1f}", fontsize=10)
        _int_axis(ax, "y")
    fig.suptitle("Per-case mean intensity distributions", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(os.path.join(OUT_PLOTS_DIR, "06_intensity_per_case_mean.png"), dpi=PLOT_DPI)
    plt.close(fig)

    make_pooled_intensity_plotly(cache_img, cache_lbl)


def make_pooled_intensity_plotly(cache_img, cache_lbl):
    """Interactive pooled voxel-intensity histogram (whole image vs. Perikard
    vs. Epikard), since the label regions are much smaller than the whole
    image and benefit from zoom/hover rather than a fixed static plot."""
    all_whole = np.concatenate([a.ravel() for a in cache_img.values()])
    all_perikard = np.concatenate([cache_img[c][cache_lbl[c] == 1] for c in cache_img])
    all_epikard = np.concatenate([cache_img[c][cache_lbl[c] == 2] for c in cache_img])

    common_max = float(np.percentile(all_whole, 99.5))
    bin_edges = np.linspace(0, common_max, 81)
    bin_width = bin_edges[1] - bin_edges[0]
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # Pre-bin server-side with numpy: a go.Histogram trace would otherwise
    # embed the full multi-million-voxel arrays into the HTML file.
    fig = go.Figure()
    for name, values, color in [
        ("Whole image", all_whole, "#4C78A8"),
        ("Perikard", all_perikard, "#E4A11B"),
        ("Epikard", all_epikard, "#D6395B"),
    ]:
        counts, _ = np.histogram(values, bins=bin_edges, density=True)
        fig.add_trace(go.Bar(
            x=bin_centers, y=counts, name=name, width=bin_width,
            marker_color=color, opacity=0.55,
        ))
    fig.update_layout(
        barmode="overlay",
        title="Pooled voxel-level intensity distribution across all cases",
        xaxis_title="Pixel intensity (a.u.)",
        yaxis_title="Density",
        xaxis_range=[0, common_max],
        template="plotly_white",
        legend_title_text="Region",
        width=900, height=550,
    )
    fig.write_html(os.path.join(OUT_PLOTS_DIR, "07_intensity_pooled.html"))


def main():
    os.makedirs(OUT_PLOTS_DIR, exist_ok=True)
    os.makedirs(OUT_QC_DIR, exist_ok=True)

    df_cases = load_cases(TABLE_PATH)
    print(f"Loaded {len(df_cases)} cases from {os.path.relpath(TABLE_PATH, PROJECT_ROOT)}")

    records, all_flags = [], []
    cache_img, cache_lbl = {}, {}

    for _, row in df_cases.iterrows():
        case_id = row["case"]
        img_path = os.path.join(PROJECT_ROOT, row["image_ed_3d"])
        lbl_path = os.path.join(PROJECT_ROOT, row["label"])
        img4d_path = os.path.join(PROJECT_ROOT, row["image_4d"])

        record, flags, img_arr, lbl_arr, n_frames = compute_case_record(
            case_id, img_path, lbl_path, img4d_path
        )
        records.append(record)
        all_flags.extend(flags)
        cache_img[case_id] = img_arr
        cache_lbl[case_id] = lbl_arr

        build_overlay_png(
            case_id, img_arr, lbl_arr,
            (record["spacing_x"], record["spacing_y"], record["spacing_z"]),
            n_frames, os.path.join(OUT_QC_DIR, f"{case_id}.png"),
        )

        flag_note = f" -- {len(flags)} flag(s)" if flags else ""
        print(f"[{case_id}] processed{flag_note}")

    df = pd.DataFrame(records)
    df_flags = pd.DataFrame(all_flags, columns=["case", "flag", "detail"])
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df_summary = df[numeric_cols].describe().T

    with pd.ExcelWriter(METRICS_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="metrics", index=False)
        df_flags.to_excel(writer, sheet_name="flags", index=False)
        df_summary.to_excel(writer, sheet_name="summary_stats")

    print()
    print(f"Saved per-case metrics to {os.path.relpath(METRICS_PATH, PROJECT_ROOT)} "
          f"({len(df)} cases, {len(df_flags)} flags across {df_flags['case'].nunique() if len(df_flags) else 0} cases)")

    make_geometry_plots(df)
    make_volume_plots(df)
    make_intensity_plots(df, cache_img, cache_lbl)
    print(f"Saved plots to {os.path.relpath(OUT_PLOTS_DIR, PROJECT_ROOT)}")
    print(f"Saved QC overlay PNGs to {os.path.relpath(OUT_QC_DIR, PROJECT_ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
