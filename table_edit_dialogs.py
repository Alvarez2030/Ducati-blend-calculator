
# table_edit_dialogs.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

# ---- Add Column ----
def add_column_dialog(parent, headers, snapshot, configure_columns, iter_rows, update_row, on_update_status):
    dlg = tk.Toplevel(parent)
    dlg.title("Add Column")
    dlg.geometry("380x220")
    dlg.transient(parent)
    dlg.grab_set()

    ttk.Label(dlg, text="Column name:").pack(anchor="w", padx=10, pady=(10, 0))
    name_var = tk.StringVar()
    tk.Entry(dlg, textvariable=name_var).pack(fill="x", padx=10)

    ttk.Label(dlg, text="Insert position (1 = first):").pack(anchor="w", padx=10, pady=(10, 0))
    pos_var = tk.IntVar(value=len(headers) + 1)
    tk.Spinbox(dlg, from_=1, to=max(1, len(headers) + 1), textvariable=pos_var).pack(fill="x", padx=10)

    ttk.Label(dlg, text="Default value (optional):").pack(anchor="w", padx=10, pady=(10, 0))
    default_var = tk.StringVar()
    tk.Entry(dlg, textvariable=default_var).pack(fill="x", padx=10)

    def confirm():
        name = name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation", "Column name cannot be empty.", parent=dlg)
            return
        insert_index = max(0, min(pos_var.get() - 1, len(headers)))
        snapshot()
        headers.insert(insert_index, name)
        configure_columns()
        for item, values in iter_rows():
            vals = list(values)
            vals.insert(insert_index, default_var.get())
            update_row(item, vals)
        on_update_status()
        dlg.destroy()

    ttk.Button(dlg, text="Add Column", command=confirm).pack(pady=12)
    ttk.Button(dlg, text="Cancel", command=dlg.destroy).pack()

# ---- Remove Columns ----
def remove_column_dialog(parent, headers, snapshot, configure_columns, iter_rows, update_row, on_update_status):
    if not headers:
        messagebox.showwarning("Warning", "No columns to remove.", parent=parent)
        return
    dlg = tk.Toplevel(parent)
    dlg.title("Remove Columns")
    dlg.geometry("500x420")
    dlg.transient(parent)
    dlg.grab_set()

    ttk.Label(dlg, text="Select columns to remove:").pack(anchor="w", padx=10, pady=(10, 0))
    lb_height = max(6, min(12, len(headers)))
    listbox = tk.Listbox(dlg, selectmode=tk.MULTIPLE, height=lb_height)
    listbox.pack(fill="both", expand=True, padx=10, pady=10)
    for h in headers:
        listbox.insert(tk.END, h)

    btns = ttk.Frame(dlg)
    btns.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Button(btns, text="Select All", command=lambda: listbox.select_set(0, tk.END)).pack(side="left")
    ttk.Button(btns, text="Clear", command=lambda: listbox.select_clear(0, tk.END)).pack(side="left")

    def confirm():
        selected = listbox.curselection()
        if not selected:
            messagebox.showwarning("Validation", "Please select at least one column.", parent=dlg)
            return
        snapshot()
        for idx in sorted(selected, reverse=True):
            if 0 <= idx < len(headers):
                del headers[idx]
            for item, values in iter_rows():
                vals = list(values)
                if idx < len(vals):
                    del vals[idx]
                update_row(item, vals)
        configure_columns()
        on_update_status()
        dlg.destroy()

    ttk.Button(dlg, text="Remove Columns", command=confirm).pack(pady=8)
    ttk.Button(dlg, text="Cancel", command=dlg.destroy).pack()

# ---- Add Row ----
def add_row_dialog(parent, headers, snapshot, insert_row, on_update_status):
    dlg = tk.Toplevel(parent)
    dlg.title("Add Row")
    dlg.geometry("500x400")
    dlg.transient(parent)
    dlg.grab_set()

    if not headers:
        ttk.Label(dlg, text="No columns defined.", foreground="red").pack(pady=20)
        ttk.Button(dlg, text="Close", command=dlg.destroy).pack()
        return

    ttk.Label(dlg, text="Enter values for the new row:", font=("Arial", 11, "bold")).pack(pady=10)

    canvas = tk.Canvas(dlg, borderwidth=0)
    frame = ttk.Frame(canvas)
    vsb = ttk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.create_window((0, 0), window=frame, anchor="nw")

    entries = []
    for h in headers:
        rowf = ttk.Frame(frame)
        rowf.pack(fill="x", padx=10, pady=5)
        ttk.Label(rowf, text=h + ":").pack(side="left")
        var = tk.StringVar()
        tk.Entry(rowf, textvariable=var).pack(side="left", fill="x", expand=True, padx=(8, 0))
        entries.append(var)

    def on_frame_config(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    frame.bind("<Configure>", on_frame_config)

    def confirm():
        values = [v.get() for v in entries]
        snapshot()
        insert_row(values)
        on_update_status()
        dlg.destroy()

    buttons = ttk.Frame(dlg)
    buttons.pack(fill="x", pady=10)
    ttk.Button(buttons, text="Add Row", command=confirm).pack(side="left", padx=10)
    ttk.Button(
        buttons, text="Add Blank Row",
        command=lambda: (snapshot(), insert_row([""] * len(headers)), on_update_status(), dlg.destroy())
    ).pack(side="left", padx=10)
    ttk.Button(buttons, text="Cancel", command=dlg.destroy).pack(side="right", padx=10)

# ---- Remove Rows ----
def remove_row_dialog(parent, snapshot, get_all_items, get_row_values, delete_items, on_update_status):
    selected = get_all_items(selected_only=True)
    if selected:
        snapshot()
        delete_items(selected)
        on_update_status()
        return

    dlg = tk.Toplevel(parent)
    dlg.title("Remove Rows")
    dlg.geometry("500x420")
    dlg.transient(parent)
    dlg.grab_set()

    def is_row_empty(values):
        return all((str(v).strip() == "") for v in values)

    def count_empty_rows():
        return sum(1 for item in get_all_items() if is_row_empty(get_row_values(item)))

    ttk.Label(dlg, text="Select row(s) to remove:").pack(anchor="w", padx=10, pady=(10, 0))
    all_items = get_all_items()
    lb_height = max(6, min(12, len(all_items)))
    listbox = tk.Listbox(dlg, selectmode=tk.MULTIPLE, height=lb_height)
    listbox.pack(fill="both", expand=True, padx=10, pady=10)
    for i in range(len(all_items)):
        listbox.insert(tk.END, f"Row {i+1}")

    btns = ttk.Frame(dlg)
    btns.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Button(btns, text="Select All", command=lambda: listbox.select_set(0, tk.END)).pack(side="left")
    ttk.Button(btns, text="Clear", command=lambda: listbox.select_clear(0, tk.END)).pack(side="left")

    status_frame = ttk.Frame(dlg)
    status_frame.pack(fill="x", padx=10, pady=(0, 10))
    empty_count_var = tk.StringVar(value=f"Empty rows: {count_empty_rows()}")
    ttk.Label(status_frame, textvariable=empty_count_var, foreground="blue").pack(side="left")

    def remove_empty_rows():
        items = get_all_items()
        to_delete = [it for it in items if is_row_empty(get_row_values(it))]
        if not to_delete:
            messagebox.showinfo("Remove Empty Rows", "No empty rows found.", parent=dlg)
            return
        snapshot()
        delete_items(to_delete)
        on_update_status()
        empty_count_var.set(f"Empty rows: {count_empty_rows()}")

    ttk.Button(status_frame, text="Remove Empty Rows", command=remove_empty_rows).pack(side="right")

    def confirm():
        selected_indices = listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Validation", "Please select at least one row.", parent=dlg)
            return
        items = get_all_items()
        to_delete = [items[idx] for idx in sorted(selected_indices, reverse=True) if idx < len(items)]
        snapshot()
        delete_items(to_delete)
        on_update_status()
        dlg.destroy()

    ttk.Button(dlg, text="Remove Rows", command=confirm).pack(pady=8)
    ttk.Button(dlg, text="Cancel", command=dlg.destroy).pack()
