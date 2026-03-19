
# results_views.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Any, List

# Plotting guard (mirrors your main file's pattern)
try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _PLOTTING_AVAILABLE = True
    # Use the helpers you already extracted
    from plot_helpers import make_figure, add_hlines, attach_hover
except Exception:
    _PLOTTING_AVAILABLE = False


def _blends_list(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a list of blend dicts whether single or multi result."""
    return results.get("blends", []) if "blends" in results else [results]


# ---------------------------
# Overview tab
# ---------------------------
def build_overview_tab(
    nb: ttk.Notebook,
    results: Dict[str, Any],
    get_variable_label: Callable[[], str],
    get_summary: Callable[[], Dict[str, Any]],
) -> None:
    """
    Build the 'Overview' tab into the provided Notebook.

    Parameters
    ----------
    nb : ttk.Notebook
        Notebook widget to attach the tab to.
    results : dict
        Results JSON you currently pass around (single or multi-blend).
    get_variable_label : () -> str
        Callback to get the y-axis label (your BlendResultsView._variable_label()).
    get_summary : () -> dict
        Callback to get the summary dict (your BlendResultsView._summary_dict()).
    """
    tab = ttk.Frame(nb)
    nb.add(tab, text="Overview")

    container = ttk.Frame(tab)
    container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
    container.grid_rowconfigure(0, weight=2)
    container.grid_rowconfigure(1, weight=3)
    container.grid_columnconfigure(0, weight=1)

    # Top table
    cols = ("Blend", "Total weight (kg)", "Avg variable", "Selected count", "Out-of-leach share")
    tree = ttk.Treeview(container, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c, anchor="center")
        width = 130 if c != "Blend" else 90
        tree.column(c, width=width, anchor="center")
    vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")

    blends = _blends_list(results)
    for i, b in enumerate(blends, start=1):
        avg = b.get("avg_variable")
        avg_str = "NaN" if (avg != avg) else f"{avg:.1f}"
        share = b.get('leaching_out_share')
        share_str = f"{share*100:.1f}%" if (share is not None) else "N/A"
        tree.insert(
            "",
            tk.END,
            values=(i, f"{b.get('total_weight', 0):.1f}", avg_str, len(b.get("selected_batches", [])), share_str),
            tags=('odd' if (i % 2) else '',)
        )
    tree.tag_configure('odd', background='#f7f7f7')

    # Bottom plot
    plot_frame = ttk.Frame(container)
    plot_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")

    if not _PLOTTING_AVAILABLE:
        ttk.Label(plot_frame, text="Plotting unavailable (matplotlib not installed).",
                  foreground="#7a7a7a").pack(anchor="w", padx=8, pady=6)
        return

    # Plot all input rows, colored by used vs unused
    all_rows = results.get("all_rows", []) or []

    # Build a set of used batch IDs across all blends
    used_ids = set()
    for b in blends:
        for x in b.get("selected_batches", []) or []:
            bid = str(x.get("batch"))
            if bid:
                used_ids.add(bid)

    # Prepare data in original CSV order (index → x position)
    used_x, used_y, used_labels = [], [], []
    unused_x, unused_y, unused_labels = [], [], []
    for i, r in enumerate(all_rows, start=1):
        try:
            batch = str(r[0])
            vval = float(r[1])
            if vval != vval:  # NaN check
                continue
        except Exception:
            continue
        v_str = f"{vval:.1f}"  # 1 decimal in tooltip
        if batch in used_ids:
            used_x.append(i); used_y.append(vval); used_labels.append(f"{batch}\n{v_str}")
        else:
            unused_x.append(i); unused_y.append(vval); unused_labels.append(f"{batch}\n{v_str}")

    fig, ax = make_figure("Overview", figsize=(7.2, 5.0), dpi=100)
    anything_plotted = False

    if unused_x and unused_y:
        scatter_unused = ax.scatter(unused_x, unused_y, s=26, marker='o', color='#111111', alpha=0.55, label="Unused")
        attach_hover(fig, ax, scatter_unused, unused_labels)
        anything_plotted = True

    if used_x and used_y:
        scatter_used = ax.scatter(used_x, used_y, s=32, marker='o', color='#1f77b4', alpha=0.85, label="Used")
        attach_hover(fig, ax, scatter_used, used_labels)
        anything_plotted = True

    ax.set_xticks([]); ax.set_xticklabels([]); ax.set_xlabel("")
    ax.set_ylabel(get_variable_label())

    # Limits & target lines from summary
    sdict = get_summary()
    limits = sdict.get('limits') or {}
    target = sdict.get('target')
    lo = limits.get('lower'); up = limits.get('upper')
    leach = sdict.get('leaching_limits') or results.get('leaching_limits') or {}
    add_hlines(ax, spec_lower=lo, spec_upper=up, target=target,
               leach_lower=leach.get('lower'), leach_upper=leach.get('upper'))

    ax.legend(loc="upper left", fontsize=9)
    if not anything_plotted:
        ax.text(0.5, 0.5, "No valid rows to plot.", transform=ax.transAxes,
                ha="center", va="center", fontsize=11, color="#7a7a7a")
    ax.set_xticks([]); ax.set_yticks([])

    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.draw()
    w = canvas.get_tk_widget()
    w.configure(borderwidth=0, highlightthickness=0)
    w.pack(fill=tk.BOTH, expand=True, padx=0, pady=8)


# ---------------------------
# Per-blend tabs
# ---------------------------
def build_blend_tabs(
    nb: ttk.Notebook,
    results: Dict[str, Any],
    get_variable_label: Callable[[], str],
) -> None:
    """
    Build one tab per blend.

    CHANGE: At the bottom of each Blend tab, we now place a mini-Notebook
    with two tabs:
        • "Selected Batches"  → your existing table + plot (unchanged)
        • "Blend Info"        → new read-only summary panel
    """
    blends = _blends_list(results)

    for i, b in enumerate(blends, start=1):
        tab = ttk.Frame(nb)
        nb.add(tab, text=f"Blend {i}")

        # ------------------ Metrics (top; unchanged content) ------------------
        metrics = ttk.LabelFrame(tab, text="Metrics")
        metrics.pack(fill=tk.X, padx=8, pady=6)

        avg_val = b.get("avg_variable")
        try:
            is_nan = (avg_val != avg_val)
        except Exception:
            is_nan = False
        avg_str = "NaN" if is_nan else f"{avg_val:.6f}"

        lines = [
            f"Status: {b.get('status')}",
            f"Total weight: {b.get('total_weight', 0):.6f} (error={b.get('weight_error', 0):.6f})",
            f"Average variable: {avg_str} (target={b.get('target')})",
            f"Meets limits: {b.get('meets_limits')}",
            f"Abs deviation numerator: {b.get('deviation_numerator_abs', 0):.6f}",
        ]
        if b.get('leaching_cap_share') is not None:
            share = b.get('leaching_out_share')
            share_str = ("%.4f" % share) if share is not None else "N/A"
            lines.append(f"Leaching cap share: {b.get('leaching_cap_share')}\nout share: {share_str}")

        ttk.Label(metrics, text="\n".join(lines), justify="left").pack(anchor="w", padx=8, pady=6)

        # ------------------ Bottom: mini-Notebook with two tabs ------------------
        bottom_nb = ttk.Notebook(tab)
        bottom_nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # ======== Tab A: Selected Batches ========
        tab_sel = ttk.Frame(bottom_nb)
        bottom_nb.add(tab_sel, text="Selected Batches")

        box = ttk.LabelFrame(tab_sel, text="Selected Batches")
        box.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        cols = ("Batch", "Weight (kg)", "Variable")
        tree = ttk.Treeview(box, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c, anchor="center")
            width = 130 if c != "Batch" else 160
            tree.column(c, anchor="center", width=width)
        vsb = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=1)

        for idx, x in enumerate(b.get("selected_batches", []) or [], start=1):
            tree.insert(
                "",
                tk.END,
                values=(x.get("batch"), x.get("weight"), x.get("variable")),
                tags=('odd' if (idx % 2) else '',)
            )
        tree.tag_configure('odd', background='#f7f7f7')

        # ---- Plot code (unchanged) ----
        plot_frame = ttk.Frame(box)
        plot_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        box.grid_rowconfigure(1, weight=3)

        if not _PLOTTING_AVAILABLE:
            ttk.Label(
                plot_frame,
                text="Plotting unavailable (matplotlib not installed).",
                foreground="#7a7a7a"
            ).pack(anchor="w", padx=8, pady=6)
        else:
            try:
                sel = b.get("selected_batches", []) or []
                y_vals, sizes = [], []
                for x in sel:
                    vval = x.get("variable"); wval = x.get("weight")
                    try:
                        if vval is not None:
                            y_vals.append(float(vval))
                            sv = float(wval) if (wval is not None) else 0.0
                            sizes.append(max(36.0, min(160.0, (sv ** 0.5) * 6)))
                    except Exception:
                        pass

                fig, ax = make_figure(f"Blend {i}", figsize=(3.6, 5.0), dpi=100)
                if y_vals:
                    x_vals = list(range(1, len(y_vals) + 1))
                    labels = []
                    for x in sel:
                        v = x.get("variable")
                        try:
                            v_is_nan = (v != v)
                        except Exception:
                            v_is_nan = False
                        v_str = "NaN" if v_is_nan else f"{float(v):.1f}"
                        labels.append(f"{x.get('batch')}\n{v_str}")

                    scatter = ax.scatter(
                        x_vals, y_vals, s=sizes or 48, marker='o',
                        color='#1f77b4', alpha=0.90, edgecolor='white', linewidth=0.6
                    )
                    attach_hover(fig, ax, scatter, labels)
                    ax.set_xticks([]); ax.set_xticklabels([]); ax.set_xlabel("")
                    ax.set_ylabel(get_variable_label())

                    limits = b.get('limits') or {}
                    target = b.get('target')
                    lo = limits.get('lower'); up = limits.get('upper')
                    leach = b.get('leaching_limits') or {}
                    add_hlines(ax, spec_lower=lo, spec_upper=up, target=target,
                               leach_lower=leach.get('lower'), leach_upper=leach.get('upper'))
                    ax.margins(x=0.02, y=0.12)
                    ax.legend(loc="upper left", fontsize=9)
                else:
                    ax.text(0.5, 0.5, "No selected batches to plot.", transform=ax.transAxes,
                            ha="center", va="center", fontsize=11, color="#7a7a7a")
                    ax.set_xticks([]); ax.set_yticks([])

                canvas = FigureCanvasTkAgg(fig, master=plot_frame)
                canvas.draw()
                w = canvas.get_tk_widget()
                w.configure(borderwidth=0, highlightthickness=0)
                w.pack(fill=tk.BOTH, expand=True, padx=0, pady=6)
            except Exception:
                ttk.Label(plot_frame, text="Plot could not be rendered.",
                          foreground="#7a7a7a").pack(anchor="w", padx=8, pady=6)

        # ======== Tab B: NEW "Blend Info" ========
        tab_info = ttk.Frame(bottom_nb)
        bottom_nb.add(tab_info, text="Blend Info")

        info_box = ttk.LabelFrame(tab_info, text="Blend Info")
        info_box.pack(fill=tk.X, expand=False, padx=8, pady=8)

        info_lines = [
            f"Total weight: {b.get('total_weight', 0.0):.6f}",
            f"Weight error: {b.get('weight_error', 0.0):.6f}",
            f"Average variable: {avg_str}",
            f"Meets limits: {b.get('meets_limits')}",
            f"Abs deviation numerator: {b.get('deviation_numerator_abs', 0.0):.6f}",
        ]

        if (b.get('leaching_out_weight') is not None) or (b.get('leaching_out_share') is not None):
            info_lines.append(f"Leaching out weight: {b.get('leaching_out_weight', 0.0):.6f}")
            share = b.get('leaching_out_share')
            info_lines.append(
                "Leaching out share: " + (("%.4f" % share) if (share is not None) else "N/A")
            )

        tol_pair = (b.get("tolerances") or {})
        L_tol = tol_pair.get("lower"); U_tol = tol_pair.get("upper")
        win = b.get("weight_window") or {}
        if (L_tol is not None) and (U_tol is not None) and ("low" in win and "high" in win):
            info_lines.append(
                f"Requested weight: {b.get('requested_weight')} (+{U_tol}/-{L_tol}) kg "
                f"(window=[{win.get('low')}, {win.get('high')}])"
            )

        # ------------------------------------------------------
        # EXTRA COLUMN WEIGHTED AVERAGES
        # ------------------------------------------------------
        other_cols = b.get("other_columns") or results.get("other_columns")
        rows_full = b.get("rows_full") or results.get("rows_full")
        headers = b.get("headers") or results.get("headers")
        mapping = b.get("mapping_headers") or results.get("mapping_headers")

        if other_cols and rows_full and headers and mapping:

            try:
                batch_idx = headers.index(mapping["batch"])
                weight_idx = headers.index(mapping["weight"])
            except Exception:
                batch_idx = None
                weight_idx = None

            if batch_idx is not None and weight_idx is not None:

                info_lines.append("")
                info_lines.append("Extra properties (weighted averages):")
                info_lines.append("Property           Weighted Avg")
                info_lines.append("-----------------------------------")

                row_map = {str(r[batch_idx]): r for r in rows_full}

                W_sel = b.get("total_weight", 0.0)

                for colname in other_cols:
                    if colname not in headers:
                        continue

                    col_idx = headers.index(colname)
                    numerator = 0.0

                    for sb in b.get("selected_batches", []):
                        batch_id = str(sb.get("batch"))
                        weight_val = float(sb.get("weight"))
                        row = row_map.get(batch_id)

                        if not row:
                            continue

                        try:
                            cval = float(row[col_idx])
                        except Exception:
                            continue

                        numerator += weight_val * cval

                    avg = numerator / W_sel if W_sel > 0 else float("nan")
                    info_lines.append(f"{colname:<18} {avg:.6f}")

        ttk.Label(info_box, text="\n".join(info_lines),
                  justify="left").pack(anchor="w", padx=8, pady=4)
# ---------------------------
# Unused tab
# ---------------------------
def build_unused_tab(
    nb: ttk.Notebook,
    results: Dict[str, Any],
    get_variable_label: Callable[[], str],
    get_summary: Callable[[], Dict[str, Any]],
) -> None:
    """Build the 'Unused' tab."""
    tab = ttk.Frame(nb)
    nb.add(tab, text="Unused")

    container = ttk.Frame(tab)
    container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
    container.grid_rowconfigure(0, weight=2)
    container.grid_rowconfigure(1, weight=3)
    container.grid_columnconfigure(0, weight=1)

    blends = _blends_list(results)
    all_rows = results.get("all_rows", []) or []

    # Build a set of used batch IDs across all blends
    used_ids = set()
    for b in blends:
        for x in b.get("selected_batches", []) or []:
            bid = str(x.get("batch"))
            if bid:
                used_ids.add(bid)

    # Derive unused from all_rows
    unused_rows = []
    for r in all_rows:
        try:
            batch = str(r[0])
        except Exception:
            batch = ""
        if batch and batch not in used_ids:
            unused_rows.append(r)

    # Top table
    cols = ("Batch", "Variable", "Weight (kg)")
    tree = ttk.Treeview(container, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c, anchor="center")
        width = 160 if c == "Batch" else 130
        tree.column(c, width=width, anchor="center")
    vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")

    # Populate
    for i, r in enumerate(unused_rows, start=1):
        try:
            batch = str(r[0]); vval = r[1]; wval = r[2]
            try:
                fv = float(vval); v_show = f"{fv:.1f}" if (fv == fv) else "NaN"
            except Exception:
                v_show = "NaN"
            try:
                fw = float(wval) if wval not in ("", None) else 0.0
                w_show = f"{fw:.1f}"
            except Exception:
                w_show = ""
        except Exception:
            batch, v_show, w_show = "", "NaN", ""
        tree.insert("", tk.END, values=(batch, v_show, w_show), tags=('odd' if (i % 2) else '',))
    tree.tag_configure('odd', background='#f7f7f7')

    # Bottom plot
    plot_frame = ttk.Frame(container)
    plot_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")

    if not _PLOTTING_AVAILABLE:
        ttk.Label(plot_frame, text="Plotting unavailable (matplotlib not installed).",
                  foreground="#7a7a7a").pack(anchor="w", padx=8, pady=6)
        return

    x_vals, y_vals, labels = [], [], []
    for i, r in enumerate(all_rows, start=1):
        try:
            batch = str(r[0]); vval = float(r[1])
            if (batch in used_ids) or (vval != vval):
                continue
            x_vals.append(i); y_vals.append(vval); labels.append(f"{batch}\n{vval:.1f}")
        except Exception:
            continue

    fig, ax = make_figure("Unused batches", figsize=(7.2, 5.0), dpi=100)
    if x_vals and y_vals:
        scatter = ax.scatter(x_vals, y_vals, s=26, marker='o', color='#111111', alpha=0.70, label="Unused")
        attach_hover(fig, ax, scatter, labels)
        ax.set_xticks([]); ax.set_xticklabels([]); ax.set_xlabel("")
        ax.set_ylabel(get_variable_label())

        # Spec/target/leaching lines
        sdict = get_summary()
        limits = sdict.get('limits') or {}
        target = sdict.get('target')
        lo = limits.get('lower'); up = limits.get('upper')
        leach = sdict.get('leaching_limits') or results.get('leaching_limits') or {}
        add_hlines(ax, spec_lower=lo, spec_upper=up, target=target,
                   leach_lower=leach.get('lower'), leach_upper=leach.get('upper'))

        ax.legend(loc="upper left", fontsize=9)
    else:
        ax.text(0.5, 0.5, "No unused batches to plot.", transform=ax.transAxes,
                ha="center", va="center", fontsize=11, color="#7a7a7a")
        ax.set_xticks([]); ax.set_yticks([])

    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.draw()
    w = canvas.get_tk_widget()
    w.configure(borderwidth=0, highlightthickness=0)
    w.pack(fill=tk.BOTH, expand=True, padx=0, pady=8)

