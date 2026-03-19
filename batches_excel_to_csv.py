
import os
import sys
import pandas as pd

def get_engine_for_extension(ext: str) -> str:
    ext = ext.lower()
    if ext in (".xlsx", ".xlsm"):
        return "openpyxl"
    elif ext == ".xls":
        return "xlrd"
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

def sanitize_sheet_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name).strip("_")

def export_sheet_to_csv(excel_path, sheet_name, engine, out_dir, encoding):
    df = pd.read_excel(excel_path, sheet_name=sheet_name, engine=engine, keep_default_na=True)
    base = os.path.splitext(os.path.basename(excel_path))[0]
    safe_sheet = sanitize_sheet_name(sheet_name) or "Sheet"
    out_name = f"{base}__{safe_sheet}.csv"
    out_path = os.path.join(out_dir, out_name)
    df.to_csv(out_path, index=False, encoding=encoding)
    # CRLF fix
    with open(out_path, "r", encoding=encoding) as f:
        content = f.read().replace("\n", "\r\n")
    with open(out_path, "w", encoding=encoding) as f:
        f.write(content)
    return out_path

def list_sheets(excel_path, engine):
    xls = pd.ExcelFile(excel_path, engine=engine)
    return xls.sheet_names

# CLI Mode
def main():
    print("=== Excel → CSV Converter ===")
    excel_path = input("Enter Excel file path: ").strip('"').strip()
    if not os.path.isfile(excel_path):
        print(f"File not found: {excel_path}")
        sys.exit(1)
    ext = os.path.splitext(excel_path)[1]
    try:
        engine = get_engine_for_extension(ext)
    except ValueError as e:
        print(e)
        sys.exit(1)
    sheets = list_sheets(excel_path, engine)
    print("\nAvailable sheets:")
    for i, s in enumerate(sheets, start=1):
        print(f" {i}. {s}")
    choice = input("\nSelect sheets (numbers comma-separated or 'all'): ").strip().lower()
    if choice == "all":
        selected = sheets
    else:
        indices = [int(x) for x in choice.split(",")]
        selected = [sheets[i-1] for i in indices]
    use_bom = input("Add BOM? [y/N]: ").strip().lower() == "y"
    encoding = "utf-8-sig" if use_bom else "utf-8"
    out_dir = os.path.dirname(excel_path)
    for sheet in selected:
        try:
            out_path = export_sheet_to_csv(excel_path, sheet, engine, out_dir, encoding)
            print(f"✔ Created: {out_path}")
        except Exception as e:
            print(f"✖ Failed: {sheet} ({e})")
    print("\nDone.")

if __name__ == "__main__":
    main()

