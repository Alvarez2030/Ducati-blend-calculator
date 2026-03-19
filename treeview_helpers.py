
# treeview_helpers.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Tuple

# --- Selection highlight box placement ---
def place_selection_box(tree: ttk.Treeview, box: tk.Frame, item, col_index: int) -> None:
    column_id = f"#{col_index + 1}"
    bbox = tree.bbox(item, column_id)
    if not bbox:
        box.place_forget()
        return
    x, y, w, h = bbox
    box.place(x=x, y=y, width=w, height=h)

# --- Inline edit overlay lifecycle ---
def begin_cell_edit(
    tree: ttk.Treeview,
    item,
    col_index: int,
    on_commit: Callable[[str], None],
    on_cancel: Optional[Callable[[], None]] = None
) -> tk.Entry:
    """Create an Entry over the current cell and wire Enter/Esc/FocusOut."""
    column_id = f"#{col_index + 1}"
    bbox = tree.bbox(item, column_id)
    if not bbox:
        return None
    x, y, width, height = bbox
    values = list(tree.item(item, 'values'))
    # normalize to width of headers inferred from tree columns
    try:
        headers = tree["columns"]
        while len(values) < len(headers):
            values.append("")
    except Exception:
        pass
    current_value = values[col_index] if col_index < len(values) else ""
    entry = tk.Entry(tree)
    entry.insert(0, current_value)
    entry.select_range(0, tk.END)
    entry.focus_set()
    entry.place(x=x, y=y, width=width, height=height)

    def _commit_and_destroy(_=None):
        new_text = entry.get()
        try:
            on_commit(new_text)
        finally:
            try:
                entry.destroy()
            except Exception:
                pass

    def _cancel_and_destroy(_=None):
        try:
            if on_cancel:
                on_cancel()
        finally:
            try:
                entry.destroy()
            except Exception:
                pass

    entry.bind('<Return>', _commit_and_destroy)
    entry.bind('<Escape>', _cancel_and_destroy)
    entry.bind('<FocusOut>', _commit_and_destroy)
    return entry

# --- Keyboard navigation among cells ---
def move_cell_selection(
    tree: ttk.Treeview,
    current_item,
    current_col_index: int,
    dx: int,
    dy: int
) -> Tuple[object, int]:
    items = list(tree.get_children())
    if not items:
        return None, None
    if current_item is None or current_col_index is None:
        return items[0], 0
    new_col = max(0, min(len(tree["columns"]) - 1, current_col_index + dx))
    try:
        row_idx = items.index(current_item)
    except ValueError:
        row_idx = 0
    new_row_idx = max(0, min(len(items) - 1, row_idx + dy))
    return items[new_row_idx], new_col
