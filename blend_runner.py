
# services/blend_runner.py
from __future__ import annotations
import json
import os
import sys
import tempfile
import subprocess
from typing import Any, Dict, List, Optional

Row = List[Any]  # [batch:str, variable:float|nan, weight:float]
Specs = Dict[str, Any]
MappingHeaders = Dict[str, Optional[str]]


class BlendInput:
    """
    Immutable container for the solver payload.
    """
    __slots__ = ("rows", "mapping_headers", "specs")

    def __init__(self, rows: List[Row], mapping_headers: MappingHeaders, specs: Specs) -> None:
        self.rows = rows
        self.mapping_headers = mapping_headers
        self.specs = specs

    def to_payload(self) -> Dict[str, Any]:
        return {
            "rows": self.rows,
            "meta": {
                "order": ["batch", "variable", "weight"],
                "mapping_headers": self.mapping_headers,
            },
            "specs": self.specs,
        }


# ----------------------------
# Internal helpers
# ----------------------------
def _this_script_dir() -> str:
    base = getattr(sys.modules.get(__name__), "__file__", None) or sys.argv[0]
    return os.path.dirname(os.path.abspath(base))

def _write_temp_json(payload: Dict[str, Any], filename: str = "blend_input.json") -> str:
    tmp_path = os.path.join(tempfile.gettempdir(), filename)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return tmp_path

def _parse_stdout_json(stdout: str) -> Optional[Dict[str, Any]]:
    # Attempt direct parse
    try:
        return json.loads(stdout)
    except Exception:
        pass
    # Fallback: extract first {...} block
    try:
        s = stdout.find("{")
        e = stdout.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(stdout[s:e + 1])
    except Exception:
        pass
    return None


# ----------------------------
# Public API
# ----------------------------
def run_blend_all(input_data: BlendInput, prefer_alt: bool = True) -> Dict[str, Any]:
    """
    Call 'blending_calculator.py' (or 'blend_by_number_batches_solver.py' if not found)
    using '--strategy milp'. Returns parsed JSON dict on success,
    raises RuntimeError on failure.
    """
    script_dir = _this_script_dir()
    calc_path = os.path.join(script_dir, "blend_by_number_batches_solver.py")
    if not os.path.exists(calc_path):
        alt_path = os.path.join(script_dir, "weight_based.py")
        if prefer_alt and os.path.exists(alt_path):
            calc_path = alt_path
        else:
            raise FileNotFoundError(f"Could not find '{calc_path}'")

    payload = input_data.to_payload()
    input_json_path = _write_temp_json(payload)

    cmd = [sys.executable, calc_path, "--input", input_json_path, "--strategy", "milp"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    obj = _parse_stdout_json(stdout)

    if result.returncode != 0 or (isinstance(obj, dict) and obj.get("error")):
        err_msg = (obj or {}).get("error") if isinstance(obj, dict) else None
        msg = "\n".join([
            "Calculator failed.",
            "",
            "Stdout:",
            stdout or "(none)",
            "",
            "Stderr:",
            err_msg or stderr or "(none)"
        ])
        raise RuntimeError(msg)

    if not isinstance(obj, dict):
        raise RuntimeError("Calculator returned no valid JSON.")

    return obj


def run_blend_by_weight(input_data: BlendInput,
                        time_limit: Optional[int] = None,
                        quiet: bool = True) -> Dict[str, Any]:
    """
    Call 'target_based_solver.py' with optional --time_limit and --quiet.
    Returns parsed JSON dict on success, raises RuntimeError otherwise.

    UPDATED:
    - Propagates:
        other_columns
        headers
        rows_full
        mapping_headers
      so the GUI can compute weighted averages of extra columns.
    """

    script_dir = _this_script_dir()
    calc_path = os.path.join(script_dir, "target_based_solver.py")

    if not os.path.exists(calc_path):
        raise FileNotFoundError(f"Could not find '{calc_path}'")

    # Build payload JSON
    payload = input_data.to_payload()
    input_json_path = _write_temp_json(payload)

    # Build python command
    cmd = [sys.executable, calc_path, "--input", input_json_path]
    if quiet:
        cmd.append("--quiet")
    if time_limit is not None:
        cmd += ["--time_limit", str(time_limit)]

    # Run solver
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    # Parse JSON from solver stdout
    obj = _parse_stdout_json(stdout)

    # Check solver errors
    if result.returncode != 0 or (isinstance(obj, dict) and obj.get("error")):
        fallback = (stdout.strip() or stderr.strip() or "(unknown)")
        err_msg = (obj or {}).get("error") if isinstance(obj, dict) else None
        msg = f"Calculator failed.\n\nError: {err_msg or fallback}"
        raise RuntimeError(msg)

    if not isinstance(obj, dict):
        raise RuntimeError("Calculator returned no valid JSON.")

    # ---------------------------------------------------------------------
    # NEW: Propagate GUI information into results for the Blend Info tab
    # ---------------------------------------------------------------------
    specs = input_data.specs or {}

    # Extra column names
    other_cols = specs.get("other_columns")
    if other_cols:
        obj["other_columns"] = other_cols

    # Full header list
    headers = specs.get("headers")
    if headers:
        obj["headers"] = headers

    # Full rows (all column values)
    rows_full = specs.get("rows_full")
    if rows_full:
        obj["rows_full"] = rows_full

    # Mapping (which column is batch / variable / weight)
    if hasattr(input_data, "mapping_headers"):
        obj["mapping_headers"] = input_data.mapping_headers

    # ---------------------------------------------------------------------

    return obj



