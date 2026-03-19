import os
import csv
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import sys
import json
from typing import Optional
import ttkbootstrap as tb
# Runner extracted module (same folder)

from blend_runner import (
    BlendInput,
    run_blend_all,
    run_blend_by_weight,

)

# Dialogs extracted module (same folder)
from table_edit_dialogs import (
    add_column_dialog as show_add_column_dialog,
    remove_column_dialog as show_remove_column_dialog,
    add_row_dialog as show_add_row_dialog,
    remove_row_dialog as show_remove_row_dialog,
)
# Results tabs extracted module (same folder)
from results_views import build_overview_tab, build_blend_tabs, build_unused_tab
# NEW: Treeview editing/selection helpers (same folder)
from treeview_helpers import place_selection_box, begin_cell_edit, move_cell_selection
# Try matplotlib once; use a flag for this file (results_views has its own guard)
try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _PLOTTING_AVAILABLE = True
    # Plotting helpers extracted module (same folder)
    from plot_helpers import make_figure, add_hlines, attach_hover
except Exception:
    _PLOTTING_AVAILABLE = False
from batches_excel_to_csv import get_engine_for_extension, list_sheets, export_sheet_to_csv

# =============================================================================
# Main application: start directly in the Viewer (empty table)
# =============================================================================
# =============================================================================
# Main application: start directly in the Viewer (empty table)
# =============================================================================


# =============================================================================
# Main application: start directly in the Viewer (empty table)
# =============================================================================



class MainApp:
    def __init__(self):
        # -------------------------------------------
        # NORMAL WINDOW (no custom title bar)
        # -------------------------------------------
        self.root = tb.Window(themename="flatly")   # or tk.Tk(); tb.Style("flatly")
        self.root.geometry("1100x760")
        self.root.iconbitmap("blendingappicon.ico")
        self.root.title("Ducati Blend calculator")

        self.root.update_idletasks()
        enable_acrylic_strong_blue(self.root)

        # Make sure NO overrideredirect is used
        # (it breaks minimize / taskbar entry)
        # self.root.overrideredirect(True)   # <-- REMOVED
        # self.root.overrideredirect(False)  # <-- REMOVED

        # -------------------------------------------
        # Main content container
        # -------------------------------------------
        self.container = tk.Frame(self.root, bg="#f5f6f7")
        self.container.pack(fill=tk.BOTH, expand=True)

        self.current_view = None

        # Start directly in the CSV viewer
        self.show_viewer(None)

    # --------------------------------------------------------------
    # View switching logic
    # --------------------------------------------------------------
    def _set_view(self, frame: tk.Frame):
        if self.current_view is not None:
            try:
                self.current_view.destroy()
            except Exception:
                pass
        self.current_view = frame
        self.current_view.pack(fill=tk.BOTH, expand=True)

    def show_excel(self):
        view = ExcelConverterView(self.container, on_back=lambda: self.show_viewer(None))
        self._set_view(view.frame)

    def show_viewer(self, csv_path=None):
        view = CSVViewerView(
            self.container,
            csv_path,
            on_back=None,
            on_show_results=self.show_results,
            on_select_excel=self.show_excel,
        )
        self._set_view(view.frame)

    def show_results(self, results_obj: dict):
        if not isinstance(results_obj, dict) or not results_obj:
            messagebox.showerror("Results", "No valid results JSON to display.", parent=self.root)
            return

        view = BlendResultsView(
            self.container,
            results_obj,
            on_back=lambda: self.show_viewer(None)
        )
        self._set_view(view.frame)

    def run(self):
        self.root.mainloop()

def enable_acrylic_strong_blue(window):
    import ctypes
    import ctypes.wintypes as wintypes

    hwnd = window.winfo_id()

    # --- Strong blue accent color (ARGB) ---
    # ARGB format: 0xAARRGGBB
    # Here: AA = opacity, RR = Red, GG = Green, BB = Blue
    # 0xFF007BFF = 100% opaque Windows 11 accent blue
    ACCENT_COLOR = 0xFF007BFF

    DWMWA_CAP_COLOR = 35  # undocumented but works for Win11 acrylic
    color_value = ctypes.c_int(ACCENT_COLOR)

    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_CAP_COLOR,
        ctypes.byref(color_value),
        ctypes.sizeof(color_value)
    )

    # --- Enable Acrylic backdrop ---
    DWMWA_SYSTEMBACKDROP_TYPE = 38
    acrylic_value = ctypes.c_int(3)  # 3 = Acrylic

    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_SYSTEMBACKDROP_TYPE,
        ctypes.byref(acrylic_value),
        ctypes.sizeof(acrylic_value)
    )

    # --- Dark mode titlebar text (recommended for contrast) ---
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    dark = ctypes.c_int(1)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(dark),
        ctypes.sizeof(dark)
    )
class ExcelConverterView:
    def __init__(self, parent, on_back):
        self.parent = parent
        self.on_back = on_back

        self.frame = ttk.Frame(parent)

        # Header toolbar: back + title
        header = ttk.Frame(self.frame)
        header.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(header, text="◀ Back", command=self.on_back).pack(side=tk.LEFT)
        ttk.Label(header, text="Excel → CSV Converter", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=12)

        # Body
        body = ttk.Frame(self.frame)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.excel_path = None
        self.sheet_names = []
        self.engine = None

        self.label_file = ttk.Label(body, text="No file selected", foreground="#1f4d99")
        self.label_file.pack(pady=10)
        self.btn_select = ttk.Button(body, text="Select Excel File", command=self.select_file)
        self.btn_select.pack(pady=5)

        self.listbox = tk.Listbox(body, selectmode=tk.MULTIPLE, width=50, height=10)
        self.listbox.pack(pady=10, fill=tk.X)

        self.var_select_all = tk.BooleanVar()
        self.chk_select_all = ttk.Checkbutton(
            body, text="Select All Sheets", variable=self.var_select_all, command=self.toggle_select_all
        )
        self.chk_select_all.pack(pady=5)

        self.var_bom = tk.BooleanVar()
        self.chk_bom = ttk.Checkbutton(
            body, text="Add BOM for Excel UTF-8 detection", variable=self.var_bom
        )
        self.chk_bom.pack(pady=5)

        self.btn_convert = ttk.Button(body, text="Convert Selected Sheets", command=self.convert_sheets)
        self.btn_convert.pack(pady=10)

        self.status = ttk.Label(body, text="", foreground="green")
        self.status.pack(pady=10)

    def select_file(self):
        path = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls *.xlsm"), ("All files", "*.*")]
        )
        if path:
            self.excel_path = path
            self.label_file.config(text=os.path.basename(path))
            try:
                ext = os.path.splitext(path)[1]
                self.engine = get_engine_for_extension(ext)
                self.sheet_names = list_sheets(path, self.engine)
                self.listbox.delete(0, tk.END)
                for sheet in self.sheet_names:
                    self.listbox.insert(tk.END, sheet)
                self.status.config(text=f"Loaded {len(self.sheet_names)} sheets.")
                self.var_select_all.set(False)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open Excel file:{e}", parent=self.parent)

    def toggle_select_all(self):
        if self.var_select_all.get():
            self.listbox.select_set(0, tk.END)
        else:
            self.listbox.select_clear(0, tk.END)

    def convert_sheets(self):
        if not self.excel_path or not self.sheet_names:
            messagebox.showwarning("Warning", "Please select an Excel file first.", parent=self.parent)
            return
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Warning", "Please select at least one sheet.", parent=self.parent)
            return
        sheets_to_export = [self.sheet_names[i] for i in selected_indices]
        encoding = "utf-8-sig" if self.var_bom.get() else "utf-8"
        out_dir = os.path.dirname(self.excel_path)
        created = []
        for sheet in sheets_to_export:
            try:
                out_path = export_sheet_to_csv(self.excel_path, sheet, self.engine, out_dir, encoding)
                created.append(out_path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export sheet '{sheet}':{e}", parent=self.parent)
        if created:
            self.status.config(text=f"Created {len(created)} file(s).")
            messagebox.showinfo("Success", f"Exported {len(created)} sheet(s) to CSV.", parent=self.parent)

# =============================================================================
# CSV viewer view (starts empty; can load list or open Excel)
# =============================================================================
class CSVViewerView:
    def __init__(self, parent, csv_path, on_back, on_show_results=None, on_select_excel=None):
        self.parent = parent
        self.csv_path = csv_path  # can be None at startup
        self.on_back = on_back
        self.on_show_results = on_show_results
        self.on_select_excel = on_select_excel

        self.frame = ttk.Frame(parent)

        # Header toolbar
        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill=tk.X, padx=10, pady=(10))
        ttk.Label(toolbar, text="Samples to Blend", font=("Arial", 14, "bold")).pack(side=tk.LEFT)

        left_tools = ttk.Frame(toolbar)
        left_tools.pack(side=tk.LEFT, padx=12)
        ttk.Button(left_tools, text="Select List", command=self._select_csv_and_load).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(left_tools, text="Convert Excel",
                   command=(self.on_select_excel if self.on_select_excel else lambda: None)).pack(side=tk.LEFT)

        # Right tools
        right_tools = ttk.Frame(toolbar)
        right_tools.pack(side=tk.RIGHT)
        self.btn_calc_blend = ttk.Button(right_tools, text="Calculate Blend", command=self._show_blend_config)
        self.btn_calc_blend.pack(side=tk.RIGHT, padx=(5, 0))

        modify_var = tk.StringVar(value="Modify")
        modify_options = ["Modify", "Add Column", "Remove Columns", "Add Row", "Remove Rows"]
        modify_menu = ttk.Combobox(right_tools, textvariable=modify_var, values=modify_options,
                                   state="readonly", width=18)
        modify_menu.pack(side=tk.RIGHT, padx=(5, 0))

        def on_modify_select(event):
            action = modify_var.get()
            if action == "Add Column": self.add_column_dialog()
            elif action == "Remove Columns": self.remove_column_dialog()
            elif action == "Add Row": self.add_row_dialog()
            elif action == "Remove Rows": self.remove_row_dialog()
            modify_var.set("Modify")

        modify_menu.bind("<<ComboboxSelected>>", on_modify_select)
        self.btn_save_as = ttk.Button(right_tools, text="Save As", command=self.save_as)
        self.btn_save_as.pack(side=tk.RIGHT, padx=(5, 0))
        self.btn_save = ttk.Button(right_tools, text="Save", command=self.save)
        self.btn_save.pack(side=tk.RIGHT, padx=(5, 0))
        self.btn_undo = ttk.Button(right_tools, text="↩", command=self.undo)
        self.btn_undo.pack(side=tk.RIGHT, padx=(5, 0))

        # Split content
        self.content = tk.PanedWindow(self.frame, orient="horizontal", sashrelief=tk.RAISED,
                                      sashwidth=0, bg="#f5f6f7")
        self.content.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.left_pane = ttk.Frame(self.content)  # table
        self.right_pane = ttk.Frame(self.content)  # blend config panel
        self.content.add(self.left_pane)

        # Table view
        self.table_frame = ttk.Frame(self.left_pane)
        self.table_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.tree = ttk.Treeview(self.table_frame, show="headings")
        self.vsb = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(self.table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.table_frame.grid_rowconfigure(0, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)

        # Blend config
        self.wizard_frame = None

        # Selection highlight box (styled as a thin blue border)
        self._cell_box = tk.Frame(self.tree, highlightbackground="#4a90e2", highlightcolor="#4a90e2",
                                  highlightthickness=2, bd=0)

        # Inline editing & navigation
        self.tree.bind("<Double-1>", self._begin_cell_edit)
        self.tree.bind("<Button-1>", self._select_cell, add="+")
        self.tree.bind("<Return>", lambda e: self._begin_cell_edit_on_selected())
        self.tree.bind("<F2>", lambda e: self._begin_cell_edit_on_selected())
        self.tree.bind("<Left>", lambda e: self._move_cell_selection(dx=-1, dy=0))
        self.tree.bind("<Right>", lambda e: self._move_cell_selection(dx=+1, dy=0))
        self.tree.bind("<Up>", lambda e: self._move_cell_selection(dx=0, dy=-1))
        self.tree.bind("<Down>", lambda e: self._move_cell_selection(dx=0, dy=+1))

        # Status bar
        self.status = ttk.Label(self.frame, text="", anchor="w")
        self.status.pack(fill=tk.X, padx=6, pady=(0, 6))

        # Data & blend state
        self.headers = []
        self.undo_stack = []
        self.delimiter = ","
        self._edit_entry = None
        self._edit_item = None
        self._edit_col_index = None
        self._cell_sel_item = None
        self._cell_sel_col_index = None

        self.blend_config = {'batch_col': None, 'variable_col': None, 'weight_col': None}
        self.blend_specs = {'target': None, 'lower': None, 'upper': None,
                            'batches_per_blend': None, 'blend_weight': None, 'preference': None,
                            'weight_tolerance_lower': None, 'weight_tolerance_upper': None,
                            'selected_batches': None,
                            'leaching_limits': None}

        # Cache of all rows passed to the solver (for Overview plotting)
        self._last_input_rows = None

        # Load the CSV if provided; otherwise start with an empty table
        if self.csv_path:
            try:
                self.load_csv(self.csv_path)
            except Exception as e:
                messagebox.showerror("Load CSV", f"Failed to load file:\n{e}", parent=self.parent)
                self._init_empty_table()
        else:
            self._init_empty_table()

    # ---- Empty table setup ----
    def _init_empty_table(self):
        self.headers = ["Batch", "Variable", "Weight"]
        self._configure_columns()
        self._update_status()

    # ---- Inline cell editing & selection (delegated to helpers) ----
    def _begin_cell_edit(self, event):
        if self.tree.identify_region(event.x, event.y) != 'cell':
            return
        item = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not item or not column_id:
            return
        try:
            col_index = int(column_id.replace('#','')) - 1
        except Exception:
            return
        if col_index < 0 or col_index >= len(self.headers):
            return
        self._cell_sel_item = item
        self._cell_sel_col_index = col_index
        self._place_cell_box(item, col_index)

        def _commit(new_text: str):
            self._snapshot_state()
            vals = list(self.tree.item(item, 'values'))
            if len(vals) < len(self.headers):
                vals += [""] * (len(self.headers) - len(vals))
            vals[col_index] = new_text
            self.tree.item(item, values=vals)
            self._update_status()
            self._place_cell_box(item, col_index)

        # Create overlay entry and wire enter/esc/focusout
        self._edit_entry = begin_cell_edit(self.tree, item, col_index, on_commit=_commit, on_cancel=lambda: None)

    def _select_cell(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            self._cell_box.place_forget()
            return
        item = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not item or not col_id:
            return
        try:
            col_index = int(col_id.replace('#','')) - 1
        except Exception:
            return
        if col_index < 0 or col_index >= len(self.headers):
            return
        self._cell_sel_item = item
        self._cell_sel_col_index = col_index
        self.tree.focus(item)
        self.tree.selection_set(item)
        self._place_cell_box(item, col_index)

    def _begin_cell_edit_on_selected(self):
        if self._cell_sel_item is None or self._cell_sel_col_index is None:
            return
        item = self._cell_sel_item
        col_index = self._cell_sel_col_index

        def _commit(new_text: str):
            self._snapshot_state()
            vals = list(self.tree.item(item, "values"))
            if len(vals) < len(self.headers):
                vals += [""] * (len(self.headers) - len(vals))
            vals[col_index] = new_text
            self.tree.item(item, values=vals)
            self._update_status()
            self._place_cell_box(item, col_index)

        self._edit_entry = begin_cell_edit(self.tree, item, col_index, on_commit=_commit, on_cancel=lambda: None)

    def _move_cell_selection(self, dx=0, dy=0):
        new_item, new_col = move_cell_selection(self.tree, self._cell_sel_item, self._cell_sel_col_index, dx, dy)
        if new_item is None:
            return
        self._cell_sel_item = new_item
        self._cell_sel_col_index = new_col
        self.tree.see(new_item)
        self.tree.focus(new_item)
        self.tree.selection_set(new_item)
        self._place_cell_box(new_item, new_col)

    def _place_cell_box(self, item, col_index):
        place_selection_box(self.tree, self._cell_box, item, col_index)

    # ---- Select list into table ----
    def _select_csv_and_load(self):
        path = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            self.load_csv(path)
            self.csv_path = path
        except Exception as e:
            messagebox.showerror("Load CSV", f"Failed to load file:\n{e}", parent=self.parent)

    # ---- Blend config on RIGHT pane ----
    def _show_blend_config(self):
        if not self.headers:
            messagebox.showwarning("No headers", "Load a CSV with headers first.", parent=self.parent)
            return

        panes = self.content.panes() if hasattr(self.content, "panes") else []
        if self.right_pane not in panes:
            self.content.add(self.right_pane, minsize=360)
            self._lock_wide_table(right_width_px=420)

        if self.wizard_frame is not None:
            try:
                self.wizard_frame.destroy()
            except Exception:
                pass
        self.wizard_frame = ttk.Frame(self.right_pane)
        self.wizard_frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(self.wizard_frame)
        header.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(header, text="Blend — Configure", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Close", command=self._close_blend_config).pack(side=tk.RIGHT)

        body = ttk.Frame(self.wizard_frame)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        footer = ttk.Frame(self.wizard_frame)
        footer.pack(fill="x", padx=12, pady=8)

        batch_var = tk.StringVar(value=self.headers[0] if self.headers else "")
        var_var = tk.StringVar(value=self.headers[1] if len(self.headers) > 1 else (self.headers[0] if self.headers else ""))
        wgt_col_var = tk.StringVar(value=self.headers[2] if len(self.headers) > 2 else (self.headers[0] if self.headers else ""))

        target_var = tk.StringVar()
        lower_var = tk.StringVar()
        upper_var = tk.StringVar()
        bpb_var = tk.StringVar()
        weight_var = tk.StringVar()
        preference_var = tk.StringVar(value='')
        preference_options = ['Random', 'Choose batches']
        blend_type_var = tk.StringVar(value="Target based")
        type_values = ["Target based", "Blend by number of batches"]

        # Replaced tolerance variables with absolute limits:
        min_weight_var = tk.StringVar()
        max_weight_var = tk.StringVar()

        time_limit_var = tk.StringVar(value="20")
        leach_lower_var = tk.StringVar()
        leach_upper_var = tk.StringVar()

        # Type row
        type_row = ttk.Frame(body)
        type_row.pack(anchor="w", pady=(0, 10), fill="x")
        ttk.Label(type_row, text="Blend type:").pack(side="left", padx=(0, 8))
        type_combo = ttk.Combobox(type_row, textvariable=blend_type_var, values=type_values, state="readonly", width=22)
        type_combo.pack(side="left")

        if not hasattr(self, "_blend_fields_frame"):
            self._blend_fields_frame = ttk.Frame(body)
        else:
            # Clear everything previously drawn
            for child in self._blend_fields_frame.winfo_children():
                child.destroy()

        self._blend_fields_frame.pack_forget()
        self._blend_fields_frame.pack(fill="both", expand=True)

        fields_frame = self._blend_fields_frame

        ENTRY_WIDTH = 12

        def render_form():
            print("MODE SELECTED:", blend_type_var.get())
            for w in fields_frame.winfo_children():
                w.destroy()

            ttk.Label(fields_frame, text="Select columns for blend calculation:", font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 8))

            r1 = ttk.Frame(fields_frame); r1.pack(fill="x", pady=6)
            ttk.Label(r1, text="Batch number:").pack(side="left")
            ttk.Combobox(r1, textvariable=batch_var, values=self.headers, state="readonly", width=20).pack(side="left")

            r2 = ttk.Frame(fields_frame); r2.pack(fill="x", pady=6)
            ttk.Label(r2, text="Variable to blend (e.g., viscosity):").pack(side="left")
            ttk.Combobox(r2, textvariable=var_var, values=self.headers, state="readonly", width=20).pack(side="left")

            r3 = ttk.Frame(fields_frame); r3.pack(fill="x", pady=6)
            ttk.Label(r3, text="Weight / available mass:").pack(side="left")
            ttk.Combobox(r3, textvariable=wgt_col_var, values=self.headers, state="readonly", width=20).pack(side="left")

            ttk.Label(fields_frame, text="Blend specifications:", font=("Arial", 11, "bold")).pack(anchor="w", pady=(12, 8))

            if blend_type_var.get() == "Target based":
                r_t = ttk.Frame(fields_frame); r_t.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_t, text="Target value:").pack(side="left", padx=(0, 8))
                tk.Entry(r_t, textvariable=target_var, width=ENTRY_WIDTH).pack(side="left")

                r_lo = ttk.Frame(fields_frame); r_lo.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_lo, text="Lower limit:").pack(side="left", padx=(0, 8))
                tk.Entry(r_lo, textvariable=lower_var, width=ENTRY_WIDTH).pack(side="left")

                r_up = ttk.Frame(fields_frame); r_up.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_up, text="Upper limit:").pack(side="left", padx=(0, 8))
                tk.Entry(r_up, textvariable=upper_var, width=ENTRY_WIDTH).pack(side="left")

                r_leach_lo = ttk.Frame(fields_frame); r_leach_lo.pack(anchor="w", pady=3, fill="x")
                ttk.Label(r_leach_lo, text="Lower Leaching limit:").pack(side="left", padx=(0, 8))
                tk.Entry(r_leach_lo, textvariable=leach_lower_var, width=ENTRY_WIDTH).pack(side="left")

                r_leach_up = ttk.Frame(fields_frame); r_leach_up.pack(anchor="w", pady=3, fill="x")
                ttk.Label(r_leach_up, text="Upper Leaching limit:").pack(side="left", padx=(0, 8))
                tk.Entry(r_leach_up, textvariable=leach_upper_var, width=ENTRY_WIDTH).pack(side="left")

                r_bw = ttk.Frame(fields_frame);
                r_bw.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_bw, text="Blend weight (kg):").pack(side="left", padx=(0, 8))
                tk.Entry(r_bw, textvariable=weight_var, width=ENTRY_WIDTH).pack(side="left")

                # NEW: Absolute weight limits (converted to tolerances on Calculate)
                r_min_w = ttk.Frame(fields_frame); r_min_w.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_min_w, text="Minimum weight (kg):").pack(side="left", padx=(0, 8))
                tk.Entry(r_min_w, textvariable=min_weight_var, width=ENTRY_WIDTH).pack(side="left")

                r_max_w = ttk.Frame(fields_frame); r_max_w.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_max_w, text="Maximum weight (kg):").pack(side="left", padx=(0, 8))
                tk.Entry(r_max_w, textvariable=max_weight_var, width=ENTRY_WIDTH).pack(side="left")

                r_pref = ttk.Frame(fields_frame); r_pref.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_pref, text="Preference:").pack(side="left", padx=(0, 8))
                ttk.Combobox(r_pref, textvariable=preference_var, values=preference_options, state="readonly", width=16).pack(side="left")

                r_time = ttk.Frame(fields_frame); r_time.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_time, text="Solver time limit (s):").pack(side="left", padx=(0, 8))
                tk.Entry(r_time, textvariable=time_limit_var, width=ENTRY_WIDTH).pack(side="left")

                note = ("Note: If both leaching limits are provided, the solver caps the "
                        "share of out-of-leaching weight (<= lower or >= upper) to 20% "
                        "by default (or to the provided cap).")
                ttk.Label(fields_frame, text=note, foreground="gray").pack(anchor="w", pady=(6, 0))
            elif blend_type_var.get() == "Blend by number of batches":
                r_t = ttk.Frame(fields_frame); r_t.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_t, text="Target value:").pack(side="left", padx=(0, 8))
                tk.Entry(r_t, textvariable=target_var, width=ENTRY_WIDTH).pack(side="left")

                r_lo = ttk.Frame(fields_frame); r_lo.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_lo, text="Lower limit:").pack(side="left", padx=(0, 8))
                tk.Entry(r_lo, textvariable=lower_var, width=ENTRY_WIDTH).pack(side="left")

                r_up = ttk.Frame(fields_frame); r_up.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_up, text="Upper limit:").pack(side="left", padx=(0, 8))
                tk.Entry(r_up, textvariable=upper_var, width=ENTRY_WIDTH).pack(side="left")

                r_leach_lo = ttk.Frame(fields_frame); r_leach_lo.pack(anchor="w", pady=3, fill="x")
                ttk.Label(r_leach_lo, text="Lower Leaching limit:").pack(side="left", padx=(0, 8))
                tk.Entry(r_leach_lo, textvariable=leach_lower_var, width=ENTRY_WIDTH).pack(side="left")

                r_leach_up = ttk.Frame(fields_frame); r_leach_up.pack(anchor="w", pady=3, fill="x")
                ttk.Label(r_leach_up, text="Upper Leaching limit:").pack(side="left", padx=(0, 8))
                tk.Entry(r_leach_up, textvariable=leach_upper_var, width=ENTRY_WIDTH).pack(side="left")

                r_bpb = ttk.Frame(fields_frame); r_bpb.pack(anchor="w", pady=6, fill="x")
                ttk.Label(r_bpb, text="Batches per blend:").pack(side="left", padx=(0, 8))
                tk.Entry(r_bpb, textvariable=bpb_var, width=ENTRY_WIDTH).pack(side="left")


        render_form()
        type_combo.bind("<<ComboboxSelected>>", lambda e: render_form())

        # --- Footer: Calculate button ---
        def calculate():
            try:
                b_idx = self.headers.index(batch_var.get())
                v_idx = self.headers.index(var_var.get())
                w_idx = self.headers.index(wgt_col_var.get())
            except ValueError:
                messagebox.showwarning("Validation", "Please choose valid columns.", parent=self.parent)
                return
            if len({b_idx, v_idx, w_idx}) < 3:
                messagebox.showwarning("Validation", "Columns must be distinct.", parent=self.parent)
                return

            self.blend_config['batch_col'] = b_idx
            self.blend_config['variable_col'] = v_idx
            self.blend_config['weight_col'] = w_idx

            if blend_type_var.get() == "Target based":
                pref = (preference_var.get() or '').strip()
                if pref != 'Random':
                    messagebox.showinfo("Not ready", "Only 'Random' is implemented for Target based.", parent=self.parent)
                    return

                w_txt = (weight_var.get() or '').strip()
                try:
                    blend_w = float(w_txt)
                    if blend_w <= 0:
                        raise ValueError
                except Exception:
                    messagebox.showwarning("Validation", "Blend weight must be a positive number (kg).", parent=self.parent)
                    return

                try:
                    t = float((target_var.get() or '').strip())
                    lo = float((lower_var.get() or '').strip())
                    up = float((upper_var.get() or '').strip())
                except Exception:
                    messagebox.showwarning("Validation", "Please enter numeric target and limits.", parent=self.parent)
                    return
                if lo > up or not (lo <= t <= up):
                    messagebox.showwarning("Validation", "Require lower ≤ target ≤ upper.", parent=self.parent)
                    return

                # --- NEW: capture absolute min/max and convert to tolerances ---
                try:
                    min_w_str = (min_weight_var.get() or '').strip()
                    max_w_str = (max_weight_var.get() or '').strip()
                    # If left blank, treat as exact blend weight ⇒ zero tolerances
                    min_w = float(min_w_str) if min_w_str != '' else blend_w
                    max_w = float(max_w_str) if max_w_str != '' else blend_w
                except Exception:
                    messagebox.showwarning("Validation", "Minimum and maximum weight must be numeric values.", parent=self.parent)
                    return

                if min_w > blend_w or max_w < blend_w:
                    messagebox.showwarning(
                        "Validation",
                        "Minimum weight must be ≤ blend weight ≤ maximum weight.",
                        parent=self.parent
                    )
                    return

                tol_lower = max(0.0, blend_w - min_w)
                tol_upper = max(0.0, max_w - blend_w)

                tl_value = (time_limit_var.get() or '').strip()
                try:
                    time_limit = int(tl_value) if tl_value else None
                except Exception:
                    messagebox.showwarning("Validation", "Solver time limit must be an integer (seconds).", parent=self.parent)
                    return

                leach_lower = (leach_lower_var.get() or '').strip()
                leach_upper = (leach_upper_var.get() or '').strip()
                self.blend_specs['leaching_limits'] = {'lower': leach_lower, 'upper': leach_upper}
                self.blend_specs['target'] = t
                self.blend_specs['lower'] = lo
                self.blend_specs['upper'] = up
                self.blend_specs['blend_weight'] = blend_w
                # Store the computed tolerances (unchanged interface to solver)
                self.blend_specs['weight_tolerance_lower'] = float(tol_lower)
                self.blend_specs['weight_tolerance_upper'] = float(tol_upper)
                self.blend_specs['preference'] = 'Random'

                # Build input and call the runner (no subprocess here)
                try:
                    inp = self._make_blend_input()
                    res_obj = run_blend_by_weight(inp, time_limit=time_limit, quiet=True)
                    # Preserve labeling & cached rows
                    try:
                        var_col_idx = self.blend_config.get('variable_col')
                        var_header = self.headers[var_col_idx] if var_col_idx is not None and 0 <= var_col_idx < len(self.headers) else "Variable"
                    except Exception:
                        var_header = "Variable"
                    res_obj['variable_label'] = var_header
                    if self._last_input_rows:
                        res_obj['all_rows'] = self._last_input_rows

                    self._close_blend_config()
                    if self.on_show_results and isinstance(res_obj, dict):
                        self.on_show_results(res_obj)
                    else:
                        msg_lines = ["Blend-by-weight ran successfully.", "", "Output:", json.dumps(res_obj, indent=2)]
                        messagebox.showinfo("Blending Calculator", "\n".join(msg_lines), parent=self.parent)
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    err_lines = ["Unexpected error:", str(e), "", "Traceback:", tb]
                    messagebox.showerror("Blending Calculator", "\n".join(err_lines), parent=self.parent)
                self._update_status()
                return
            elif blend_type_var.get() == "Blend by number of batches":
                bpb_text = (bpb_var.get() or '').strip()
                if bpb_text:
                    try:
                        bpb = int(bpb_text)
                        if bpb < 1:
                            raise ValueError
                        self.blend_specs['batches_per_blend'] = bpb
                    except Exception:
                        messagebox.showwarning("Validation", "'Batches per blend' must be a positive integer.", parent=self.parent)
                        return
                try:
                    t = float((target_var.get() or '').strip())
                    lo = float((lower_var.get() or '').strip())
                    up = float((upper_var.get() or '').strip())
                except Exception:
                    messagebox.showwarning("Validation", "Please enter numeric target and limits.", parent=self.parent)
                    return
                if lo > up:
                    messagebox.showwarning("Validation", "Lower limit cannot be greater than upper limit.", parent=self.parent)
                    return
                if not (lo <= t <= up):
                    messagebox.showwarning("Validation", "Target must be within [lower, upper] limits.", parent=self.parent)
                    return

                leach_lower = (leach_lower_var.get() or '').strip()
                leach_upper = (leach_upper_var.get() or '').strip()
                self.blend_specs['leaching_limits'] = {'lower': leach_lower, 'upper': leach_upper}
                self.blend_specs['target'] = t
                self.blend_specs['lower'] = lo
                self.blend_specs['upper'] = up
                self.blend_specs['preference'] = None
                self.blend_specs['blend_weight'] = None

                self._call_blending_calculator()
                self._update_status()
                self._close_blend_config()




        ttk.Button(footer, text="Calculate", command=calculate).pack(side="right", padx=6)



    def _close_blend_config(self):
        if self.wizard_frame is not None:
            try:
                self.wizard_frame.destroy()
            except Exception:
                pass
        self.wizard_frame = None
        try:
            panes = self.content.panes() if hasattr(self.content, "panes") else []
            if self.right_pane in panes:
                self.content.forget(self.right_pane)
            self.content.update_idletasks()
        except Exception:
            pass

    def _lock_wide_table(self, right_width_px=360):
        try:
            self.content.update_idletasks()
            total_w = self.content.winfo_width()
            if total_w <= 1:
                total_w = self.frame.winfo_width() or 1100
            sash_x = max(360, total_w - int(right_width_px))
            self.content.sash_place(0, sash_x, 0)
        except Exception:
            pass

    # ---- CSV Loading ----
    def _detect_delimiter(self, sample_text):
        try:
            dialect = csv.Sniffer().sniff(sample_text, delimiters=",;\t")
            return dialect.delimiter
        except Exception:
            return ','

    def load_csv(self, path):
        for item in self.tree.get_children():
            self.tree.delete(item)
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            sample = f.read(4096)
            f.seek(0)
            self.delimiter = self._detect_delimiter(sample)
            reader = csv.reader(f, delimiter=self.delimiter)
            headers = next(reader, [])
            headers = [h.strip() for h in headers]
            if not headers:
                raise ValueError("CSV appears to have no header row.")
            self.headers = headers
            self._configure_columns()
            for row in reader:
                self.tree.insert("", tk.END, values=self._normalize_row_length(row))
        self._update_status()

    def _configure_columns(self):
        self.tree["columns"] = self.headers
        for h in self.headers:
            self.tree.heading(h, text=h)
            self.tree.column(h, width=max(80, min(240, len(h) * 12)), stretch=True)

    def _normalize_row_length(self, row):
        if len(row) < len(self.headers):
            row += [""] * (len(self.headers) - len(row))
        elif len(row) > len(self.headers):
            row = row[:len(self.headers)]
        return row

    def _snapshot_state(self):
        rows = [self.tree.item(item, "values") for item in self.tree.get_children()]
        self.undo_stack.append((list(self.headers), rows))

    def undo(self):
        if not self.undo_stack:
            messagebox.showinfo("Undo", "No actions to undo.", parent=self.parent)
            return
        headers, rows = self.undo_stack.pop()
        self.headers = headers
        self._configure_columns()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert("", tk.END, values=row)
        self._update_status()

    def _update_status(self):
        mapping_txt = ""
        if all(self.blend_config[k] is not None for k in ['batch_col','variable_col','weight_col']) and self.headers:
            b = self.headers[self.blend_config['batch_col']]
            v = self.headers[self.blend_config['variable_col']]
            w = self.headers[self.blend_config['weight_col']]
            mapping_txt = f" • Blend mapping: Batch='{b}', Var='{v}', Weight='{w}'"
        rows_count = len(self.tree.get_children())
        cols_count = len(self.headers)
        self.status.config(text=f"Delimiter: '{self.delimiter}' • Columns: {cols_count} • Rows: {rows_count}{mapping_txt}")

    def _this_script_dir(self):
        base = getattr(sys.modules.get(__name__), "__file__", None)
        if not base:
            base = sys.argv[0]
        return os.path.dirname(os.path.abspath(base))

    # -- NEW helper: build BlendInput in-memory (and fill _last_input_rows) --
    def _make_blend_input(self) -> BlendInput:
        """
        Build the BlendInput object for the solver.
        This version includes a new field: 'other_columns'
        which lists all column names not used as batch/variable/weight.
        """

        # Column indices selected by the user
        b = self.blend_config.get('batch_col')
        v = self.blend_config.get('variable_col')
        w = self.blend_config.get('weight_col')

        if b is None or v is None or w is None:
            messagebox.showwarning(
                "Validation",
                "Please set the blend mapping (batch/variable/weight) first.",
                parent=self.parent
            )
            raise RuntimeError("Blend mapping not set")

        rows = []
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            vals = self._normalize_row_length(vals)

            batch_raw = vals[b] if b < len(vals) else ""
            var_raw = vals[v] if v < len(vals) else ""
            wt_raw = vals[w] if w < len(vals) else ""

            batch = str(batch_raw)

            try:
                variable = float(var_raw) if str(var_raw).strip() not in ("", "None") else float("nan")
            except Exception:
                variable = float("nan")

            try:
                weight = float(wt_raw) if str(wt_raw).strip() not in ("", "None") else 0.0
            except Exception:
                weight = 0.0

            rows.append([batch, variable, weight])

        # Cache for Overview plotting
        self._last_input_rows = list(rows)

        # Mapping of column names
        mapping_headers = {
            "batch": self.headers[b] if b is not None else None,
            "variable": self.headers[v] if v is not None else None,
            "weight": self.headers[w] if w is not None else None,
        }

        # Build solver specs
        specs = {
            "target": self.blend_specs.get("target"),
            "lower": self.blend_specs.get("lower"),
            "upper": self.blend_specs.get("upper"),
            "batches_per_blend": self.blend_specs.get("batches_per_blend"),
            "blend_weight": self.blend_specs.get("blend_weight"),
            "weight_tolerance_lower": self.blend_specs.get("weight_tolerance_lower"),
            "weight_tolerance_upper": self.blend_specs.get("weight_tolerance_upper"),
            "preference": self.blend_specs.get("preference"),
            "selected_batches": self.blend_specs.get("selected_batches"),
            "leaching_limits": self.blend_specs.get("leaching_limits"),
        }

        # -------------------------
        # NEW: Identify other columns
        # -------------------------
        used_indices = {b, v, w}
        other_columns = [
            self.headers[i]
            for i in range(len(self.headers))
            if i not in used_indices
        ]
        specs["other_columns"] = other_columns

        specs["headers"] = self.headers
        specs["rows_full"] = [
            self._normalize_row_length(list(self.tree.item(item, "values")))
            for item in self.tree.get_children()
        ]

        inp = BlendInput(rows, mapping_headers, specs)  # create the object
        inp.mapping_headers = mapping_headers  # <-- FIX 2 added here
        return inp


        # ---- Use runner instead of subprocess for the all-blends path ----
    def _call_blending_calculator(self):
        try:
            inp = self._make_blend_input()
            res_obj = run_blend_all(inp)
            # carry over label and all_rows for Overview
            try:
                var_col_idx = self.blend_config.get('variable_col')
                if var_col_idx is not None and 0 <= var_col_idx < len(self.headers):
                    res_obj['variable_label'] = self.headers[var_col_idx]
            except Exception:
                pass
            if self._last_input_rows:
                res_obj['all_rows'] = self._last_input_rows

            if self.on_show_results and isinstance(res_obj, dict):
                self.on_show_results(res_obj)
            else:
                msg_lines = ["Calculator ran successfully.", "", "Output:", json.dumps(res_obj, indent=2)]
                messagebox.showinfo("Blending Calculator", "\n".join(msg_lines), parent=self.parent)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            err_lines = ["Unexpected error:", str(e), "", "Traceback:", tb]
            messagebox.showerror("Blending Calculator", "\n".join(err_lines), parent=self.parent)

    # ---- File saving ----
    def save(self):
        if not self.csv_path:
            return self.save_as()
        self._write_csv(self.csv_path)
        messagebox.showinfo("Saved", f"Changes saved to {self.csv_path}", parent=self.parent)

    def save_as(self):
        new_path = filedialog.asksaveasfilename(
            title="Save As",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if new_path:
            self._write_csv(new_path)
            self.csv_path = new_path
            messagebox.showinfo("Saved", f"File saved as {new_path}", parent=self.parent)

    def _write_csv(self, path):
        rows = [self.tree.item(item, "values") for item in self.tree.get_children()]
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f, delimiter=self.delimiter)
            writer.writerow(self.headers)
            writer.writerows(rows)

    # ---- Dialog wrappers (delegating to table_edit_dialogs) ----
    def add_column_dialog(self):
        show_add_column_dialog(
            parent=self.parent,
            headers=self.headers,
            snapshot=self._snapshot_state,
            configure_columns=self._configure_columns,
            iter_rows=lambda: [(item, self.tree.item(item, "values")) for item in self.tree.get_children()],
            update_row=lambda item, vals: self.tree.item(item, values=self._normalize_row_length(vals)),
            on_update_status=self._update_status,
        )

    def remove_column_dialog(self):
        show_remove_column_dialog(
            parent=self.parent,
            headers=self.headers,
            snapshot=self._snapshot_state,
            configure_columns=self._configure_columns,
            iter_rows=lambda: [(item, self.tree.item(item, "values")) for item in self.tree.get_children()],
            update_row=lambda item, vals: self.tree.item(item, values=self._normalize_row_length(vals)),
            on_update_status=self._update_status,
        )

    def add_row_dialog(self):
        show_add_row_dialog(
            parent=self.parent,
            headers=self.headers,
            snapshot=self._snapshot_state,
            insert_row=lambda values: self.tree.insert("", tk.END, values=self._normalize_row_length(values)),
            on_update_status=self._update_status,
        )

    def remove_row_dialog(self):
        show_remove_row_dialog(
            parent=self.parent,
            snapshot=self._snapshot_state,
            get_all_items=lambda selected_only=False: (list(self.tree.selection()) if selected_only else list(self.tree.get_children())),
            get_row_values=lambda item: self.tree.item(item, "values"),
            delete_items=lambda items: [self.tree.delete(it) for it in items],
            on_update_status=self._update_status,
        )

# =============================================================================
# Results view — Summary + Overview + per-blend tabs
# =============================================================================
class BlendResultsView:
    def __init__(self, parent, results_obj: dict, on_back):
        self.parent = parent
        self.results = results_obj or {}
        self.on_back = on_back

        self.frame = ttk.Frame(parent)
        header = ttk.Frame(self.frame)
        header.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(header, text="◀ Back", command=self.on_back).pack(side=tk.LEFT)
        ttk.Label(header, text="Blend Results", font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=12)

        right = ttk.Frame(header); right.pack(side=tk.RIGHT)
        ttk.Button(right, text="Save JSON…", command=self._save_json).pack(side=tk.RIGHT, padx=(5,0))
        ttk.Button(right, text="Export CSV…", command=self._export_csv).pack(side=tk.RIGHT, padx=(5,0))

        body = tk.PanedWindow(self.frame, orient="horizontal", sashrelief=tk.RAISED, bg="#f5f6f7")
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        left = ttk.Frame(body); right = ttk.Frame(body)
        body.add(left, minsize=280); body.add(right)

        self._build_summary(left)

        self.nb = ttk.Notebook(right)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Delegate tab construction to the extracted builders
        build_overview_tab(self.nb, self.results, self._variable_label, self._summary_dict)
        build_blend_tabs(self.nb, self.results, self._variable_label)
        build_unused_tab(self.nb, self.results, self._variable_label, self._summary_dict)

    # Small helpers kept here (used by the builders)
    def _is_multi(self):
        return isinstance(self.results, dict) and ("blends" in self.results)

    def _variable_label(self):
        return self.results.get("variable_label") or "Variable value"

    def _summary_dict(self):
        if self._is_multi():
            return self.results.get("summary", {})
        b = self.results
        return {
            "status": b.get("status"),
            "blend_count": 1,
            "requested_weight": b.get("requested_weight"),
            "tolerances": b.get("tolerances"),
            "tolerance": b.get("tolerance"),
            "target": b.get("target"),
            "limits": b.get("limits"),
            "stop_reason": None,
            "unused_batches_after": b.get("unused_batches", []),
            "leaching_limits": b.get("leaching_limits"),
            "leaching_cap_share": b.get("leaching_cap_share"),
        }

    def _build_summary(self, parent):
        box = ttk.LabelFrame(parent, text="Summary")
        box.pack(fill=tk.BOTH, expand=False, padx=6, pady=6)
        s = self._summary_dict()
        limits = s.get('limits') or {}
        tol_pair = s.get('tolerances') or {}
        L_tol = tol_pair.get('lower')
        U_tol = tol_pair.get('upper')
        legacy_tol = s.get('tolerance')
        if L_tol is not None and U_tol is not None:
            weight_line = f"Requested weight: {s.get('requested_weight')} (+{U_tol}/-{L_tol}) kg"
        elif legacy_tol is not None:
            weight_line = f"Requested weight: {s.get('requested_weight')} ± {legacy_tol} kg"
        else:
            weight_line = f"Requested weight: {s.get('requested_weight')}"
        lines = [
            f"Status: {s.get('status')}",
            f"Blends: {s.get('blend_count')}",
            weight_line,
            f"Spec limits: [{limits.get('lower')}, {limits.get('upper')}]\nTarget: {s.get('target')}",
        ]
        if s.get('stop_reason'):
            lines.append(f"Stopped because: {s.get('stop_reason')}")
        if s.get('unused_batches_after'):
            lines.append(f"Unused batches remaining: {len(s.get('unused_batches_after'))}")
        if s.get('leaching_cap_share') is not None:
            lines.append(f"Leaching cap share: {s.get('leaching_cap_share')}")
        ttk.Label(box, text="\n".join(lines), justify="left").pack(anchor="w", padx=8, pady=8)

    def _save_json(self):
        path = filedialog.asksaveasfilename(title="Save Results JSON", defaultextension=".json",
                                            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Saved", f"Results saved to {path}", parent=self.parent)
        except Exception as e:
            messagebox.showerror("Save JSON", f"Failed: {e}", parent=self.parent)

    def _export_csv(self):
        dlg = tk.Toplevel(self.parent)
        dlg.title("Export CSV"); dlg.geometry("420x220"); dlg.transient(self.parent); dlg.grab_set()
        ttk.Label(dlg, text="Choose export:", font=("Arial", 11, "bold")).pack(pady=(10,6))

        def export_overview():
            path = filedialog.asksaveasfilename(title="Save Overview CSV", defaultextension=".csv",
                                                filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
            if not path: return
            try:
                blends = self.results.get("blends", []) if self._is_multi() else [self.results]
                with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Blend", "Total weight (kg)", "Avg variable", "Selected count", "Out-of-leach share"])
                    for i, b in enumerate(blends, start=1):
                        avg = b.get('avg_variable'); avg_str = "NaN" if (avg != avg) else f"{avg:.6f}"
                        share = b.get('leaching_out_share')
                        share_str = f"{share*100:.1f}%" if (share is not None) else "N/A"
                        writer.writerow([i, f"{b.get('total_weight', 0):.6f}", avg_str, len(b.get('selected_batches', [])), share_str])
                messagebox.showinfo("Export", f"Overview saved to {path}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Export", f"Failed: {e}", parent=self.parent)

        def export_selected():
            path = filedialog.asksaveasfilename(title="Save Selected Batches CSV", defaultextension=".csv",
                                                filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
            if not path: return
            try:
                blends = self.results.get("blends", []) if self._is_multi() else [self.results]
                with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Blend", "Batch", "Weight (kg)", "Variable"])
                    for i, b in enumerate(blends, start=1):
                        for x in b.get('selected_batches', []):
                            writer.writerow([i, x.get('batch'), x.get('weight'), x.get('variable')])
                messagebox.showinfo("Export", f"Selected batches saved to {path}", parent=self.parent)
            except Exception as e:
                messagebox.showerror("Export", f"Failed: {e}", parent=self.parent)

        btns = ttk.Frame(dlg); btns.pack(fill=tk.X, padx=12, pady=12)
        ttk.Button(btns, text="Export Overview", command=lambda: (export_overview(), dlg.destroy())).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Export Selected Batches", command=lambda: (export_selected(), dlg.destroy())).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=6)

# =============================================================================
# Entry point
# =============================================================================
if __name__ == "__main__":
    MainApp().run()