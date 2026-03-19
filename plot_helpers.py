
# plot_helpers.py
from __future__ import annotations
from typing import List
from matplotlib.figure import Figure

def make_figure(title: str, figsize=(7.2, 5.0), dpi=100):
    fig = Figure(figsize=figsize, dpi=dpi)
    ax = fig.add_subplot(111)
    ax.set_title(title)
    ax.grid(True, linestyle=":", alpha=0.25)
    return fig, ax

def add_hlines(ax, *, spec_lower=None, spec_upper=None, target=None,
               spec_color="#2ecc71", target_color="#3498db",
               leach_lower=None, leach_upper=None, leach_color="#e74c3c"):
    try:
        if spec_lower is not None:
            ax.axhline(float(spec_lower), color=spec_color, linestyle="--", linewidth=1.5, alpha=0.8, label="Spec")
        if spec_upper is not None:
            ax.axhline(float(spec_upper), color=spec_color, linestyle="--", linewidth=1.5, alpha=0.8, label="_nolegend_")
        if target is not None:
            ax.axhline(float(target), color=target_color, linestyle="--", linewidth=1.5, alpha=0.8, label="Target")
        if leach_lower is not None:
            ax.axhline(float(leach_lower), color=leach_color, linestyle="--", linewidth=1.5, alpha=0.8, label="Leaching")
        if leach_upper is not None:
            ax.axhline(float(leach_upper), color=leach_color, linestyle="--", linewidth=1.5, alpha=0.8, label="_nolegend_")
    except Exception:
        pass

def attach_hover(fig, ax, scatter, labels: List[str], pixel_tol: float = 8.0):
    """Grey rounded, arrow-less hover. Includes nearest-pixel fallback."""
    annot = ax.annotate(
        "", xy=(0, 0), xytext=(10, 10), textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.25", fc="#eeeeee", ec="#333333", alpha=0.95),
        fontsize=9, color="#111111", ha="left", va="bottom", zorder=20
    )
    annot.set_visible(False)
    offsets = scatter.get_offsets()
    disp_cache = {"xy": None}

    def _recompute_disp(event=None):
        try:
            import numpy as np
            disp_cache["xy"] = ax.transData.transform(offsets) if len(offsets) else None
        except Exception:
            disp_cache["xy"] = None

    _recompute_disp()
    fig.canvas.mpl_connect("draw_event", _recompute_disp)

    def _update_annot(idx: int):
        x, y = offsets[idx]
        annot.xy = (x, y)
        annot.set_text(str(labels[idx]))

    def _on_move(event):
        if event.inaxes != ax:
            if annot.get_visible():
                annot.set_visible(False)
                fig.canvas.draw_idle()
            return

        contains, info = scatter.contains(event)
        if contains and info.get("ind"):
            idx = info["ind"][0]
            _update_annot(idx)
            if not annot.get_visible():
                annot.set_visible(True)
            fig.canvas.draw_idle()
            return

        try:
            import numpy as np
            xy = disp_cache.get("xy")
            if xy is not None and len(xy):
                d = np.hypot(xy[:, 0] - event.x, xy[:, 1] - event.y)
                idx = int(np.argmin(d))
                if d[idx] <= pixel_tol:
                    _update_annot(idx)
                    if not annot.get_visible():
                        annot.set_visible(True)
                    fig.canvas.draw_idle()
                    return
        except Exception:
            pass

        if annot.get_visible():
            annot.set_visible(False)
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", _on_move)
