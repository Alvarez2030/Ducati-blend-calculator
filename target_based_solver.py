
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blend-by-weight calculator (whole batches only, exact MILP, hard limits).
Now supports **sequential multi-blend** computation: after finding the best
blend, it removes the used batches and repeats on the remaining ones until
it can no longer form a feasible blend (either insufficient remaining weight
or infeasible w.r.t. spec limits).

NEW in this version:
 - Separate lower/upper weight tolerances via `weight_tolerance_lower` and
   `weight_tolerance_upper` (both non-negative). Backward compatible with
   legacy `weight_tolerance` (used for both sides if present).
 - Human output and JSON include the asymmetric tolerances.
 - Stage-2 uses ε*z + e with z2 >= z_opt (no hard equality) → robust & faster.
 - Optional solver time limit via --time_limit (CBC).
 - Clear solver errors; non-zero exit code on error (so GUI reports it correctly).
 - Multi-blend loop with summary JSON output.
 - **IMPORTANT**: The script prints **JSON as the last output and exits**,
   so the GUI can reliably parse it. (No trailing lines after JSON.)
 - **Leaching 20% cap**: If `leaching_limits` are provided, at most 20% (or a user
   provided `leaching_cap_share`) of the selected blend weight may come from batches
   whose variable is **outside** the leaching interval. Equality to bounds counts as
   outside per current spec.

Usage:
 python blending_by_weight_selected_batches.py --input <path_to_json> [--quiet] [--time_limit 20] [--single]
By default, the script computes **multiple blends** sequentially.
Use --single to compute only the first blend (original behaviour).

Input JSON envelope (example):
{
  "rows": [
    ["B001", 102.0, 540.0],
    ["B002", 97.0, 860.0],
    ...
  ],
  "meta": { "order": ["batch","variable","weight"] },
  "specs": {
    "target": 100.0,
    "lower": 95.0,
    "upper": 105.0,
    "blend_weight": 3000.0,
    // NEW (asymmetric tolerance):
    "weight_tolerance_lower": 80.0, // optional; default falls back to 100.0
    "weight_tolerance_upper": 120.0, // optional; default falls back to 100.0
    // Legacy (symmetric tolerance; used for both if provided and the *_lower/_upper keys are absent):
    "weight_tolerance": 100.0,
    "preference": "Random", // or "Choose batches" (GUI currently uses "Random")
    "selected_batches": ["B017"], // optional when forcing-in
    "leaching_limits": {"lower": 90.0, "upper": 110.0},
    // Optional: override cap share (default 0.20)
    "leaching_cap_share": 0.20
  }
}

Output (multi): prints an optional human summary (one section per blend) **before**
a single JSON block to stdout. The final printed text is always pure JSON.
Exit code: 0 on success; non-zero on error.
"""
import json
import argparse
import sys
from typing import Any, Dict, List, Tuple

def _within_with_tol(value: float, lo: float, up: float,
                     rtol: float = 1e-9, atol: float = 1e-9) -> bool:
    """Robust [lo, up] check with combined relative/absolute tolerance."""
    if value != value:  # NaN
        return False
    span = max(abs(lo), abs(up), 1.0)
    tol = max(atol, rtol * span)
    return (value >= lo - tol) and (value <= up + tol)


def _validate_specs(specs: Dict[str, Any]) -> Tuple[float, float, float, float, float, float, str, List[str]]:
    """
    Validate and coerce specs. Returns:
    (t, lo, up, W_star, W_tol_lower, W_tol_upper, preference, selected_ids)
    Raises ValueError on invalid input.
    """
    if not isinstance(specs, dict):
        raise ValueError("Specs missing.")
    try:
        t = float(specs["target"])  # target value
        lo = float(specs["lower"])  # lower limit
        up = float(specs["upper"])  # upper limit
    except Exception:
        raise ValueError("Non-numeric target/lower/upper in specs.")
    if lo > up or not (lo <= t <= up):
        raise ValueError("Invalid limits/target relationship (require lower ≤ target ≤ upper).")
    try:
        W_star = float(specs["blend_weight"])  # requested blend weight
    except Exception:
        raise ValueError("Missing or non-numeric 'blend_weight' in specs.")

    # NEW: asymmetric lower/upper tolerances, fallback to legacy symmetric value
    try:
        W_tol_lower = float(specs.get("weight_tolerance_lower",
                                      specs.get("weight_tolerance", 100.0)))
    except Exception:
        W_tol_lower = 100.0
    try:
        W_tol_upper = float(specs.get("weight_tolerance_upper",
                                      specs.get("weight_tolerance", 100.0)))
    except Exception:
        W_tol_upper = 100.0
    if W_tol_lower < 0 or W_tol_upper < 0:
        raise ValueError("weight_tolerance_lower/upper must be non-negative.")

    preference = str(specs.get("preference", "Random") or "Random")
    selected_ids = specs.get("selected_batches", []) or []
    if not isinstance(selected_ids, list):
        raise ValueError("'selected_batches' must be a list of batch IDs when provided.")

    return t, lo, up, W_star, W_tol_lower, W_tol_upper, preference, selected_ids


def _prepare_items(rows: List[List[Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parse rows [[batch, variable, weight], ...] into items:
    [{"batch": str, "v": float, "w": float}, ...]
    Returns (items_kept, items_dropped).
    """
    items, dropped = [], []
    for r in rows:
        batch = str(r[0]) if len(r) > 0 else ""
        # variable
        try:
            v = float(r[1]) if len(r) > 1 and r[1] not in ("", None) else float("nan")
        except Exception:
            v = float("nan")
        # weight
        try:
            w = float(r[2]) if len(r) > 2 and r[2] not in ("", None) else 0.0
        except Exception:
            w = 0.0
        itm = {"batch": batch, "v": v, "w": w}
        if (w > 0.0) and (v == v):  # keep only positive weight and finite variable
            items.append(itm)
        else:
            dropped.append(itm)
    return items, dropped


def _parse_leaching(specs: Dict[str, Any]) -> Tuple[Dict[str, float], float]:
    """Parse leaching limits and cap share. Equality to bounds counts as OUTSIDE."""
    leaching_limits = None
    try:
        ll = specs.get("leaching_limits")
        if isinstance(ll, dict):
            leaching_limits = {
                "lower": float(ll.get("lower")) if ll.get("lower") not in (None, "") else None,
                "upper": float(ll.get("upper")) if ll.get("upper") not in (None, "") else None,
            }
    except Exception:
        leaching_limits = None
    # Cap share (fraction of W allowed to be out-of-leaching). Default 0.20.
    try:
        cap_share_raw = specs.get("leaching_cap_share", 0.20)
        cap_share = float(cap_share_raw)
        if not (0.0 <= cap_share <= 1.0):
            cap_share = 0.20
    except Exception:
        cap_share = 0.20
    return leaching_limits or {"lower": None, "upper": None}, cap_share


def solve_blend_by_weight_milp(rows: List[List[Any]], specs: Dict[str, Any], time_limit=None) -> Dict[str, Any]:
    """
    Exact MILP with 0/1 selection (single blend):
    - weight window [W* - tol_lower, W* + tol_upper]
    - average within [lo, up] (hard limits)
    - Stage-1: minimize absolute deviation numerator vs target
    - Stage-2: with z >= z_opt, minimize e (absolute weight error), objective ε*z + e
    - **Leaching cap**: if leaching limits present, at most `cap_share` of W may come from
      outside-leaching batches, where equality to bounds is considered outside.

    Returns a dict with metrics and selected/unused batches, or {"error": "..."}.
    """
    # Validate specs
    try:
        t, lo, up, W_star, W_tol_lower, W_tol_upper, preference, selected_ids = _validate_specs(specs)
    except Exception as e:
        return {"error": str(e)}

    # Parse leaching
    leaching_limits, cap_share = _parse_leaching(specs)

    # Prepare items
    items, dropped = _prepare_items(rows)
    if not items:
        return {"error": "No valid items (after filtering NaNs and zero weights)."}

    # Try to import PuLP and CBC
    try:
        import pulp
        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit) if time_limit else pulp.PULP_CBC_CMD(msg=False)
    except Exception:
        return {"error": "PuLP/CBC solver not available. Install 'pulp' and ensure CBC is on PATH."}

    N = len(items)
    w = [itm["w"] for itm in items]
    v = [itm["v"] for itm in items]
    ids = [itm["batch"] for itm in items]

    W_low = max(0.0, W_star - W_tol_lower)
    W_high = W_star + W_tol_upper

    # Build outside-leaching index set (equality counts as outside)
    leach_lo = leaching_limits.get("lower") if isinstance(leaching_limits, dict) else None
    leach_up = leaching_limits.get("upper") if isinstance(leaching_limits, dict) else None
    outside_idx = []
    if (leach_lo is not None) and (leach_up is not None):
        for i in range(N):
            if (v[i] <= leach_lo) or (v[i] >= leach_up):
                outside_idx.append(i)

    # -------------------- Stage-1 --------------------
    m1 = pulp.LpProblem("BlendByWeight_Stage1_MinAbsDev", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("x", range(N), lowBound=0, upBound=1, cat=pulp.LpBinary)
    W_total = pulp.lpSum(x[i] * w[i] for i in range(N))
    S_total = pulp.lpSum(x[i] * w[i] * v[i] for i in range(N))
    y = pulp.lpSum(x[i] * w[i] * (v[i] - t) for i in range(N))
    z = pulp.LpVariable("z", lowBound=0, upBound=None, cat=pulp.LpContinuous)

    # Constraints: weight window, average limits
    m1 += W_total >= W_low
    m1 += W_total <= W_high
    m1 += S_total >= lo * W_total
    m1 += S_total <= up * W_total

    # Absolute value
    m1 += z >= y
    m1 += z >= -y

    # Force-in selected IDs
    if selected_ids:
        sel = set(selected_ids)
        for i in range(N):
            if ids[i] in sel:
                m1 += x[i] == 1

    # **Leaching cap**
    if outside_idx:
        W_out = pulp.lpSum(x[i] * w[i] for i in outside_idx)
        m1 += W_out <= cap_share * W_total

    # Objective
    m1 += z
    status1 = m1.solve(solver)
    status_str1 = pulp.LpStatus[status1]
    if status_str1 != "Optimal":
        return {"error": f"No optimal solution. Solver status: {status_str1}"}

    z_opt = float(pulp.value(z) or 0.0)
    W_val1 = pulp.value(W_total)
    if W_val1 is None or W_val1 <= 0:
        return {"error": "Solver produced empty selection; treat as infeasible."}

    # -------------------- Stage-2 --------------------
    EPS = 1e-6
    m2 = pulp.LpProblem("BlendByWeight_Stage2_MinWeightError", pulp.LpMinimize)
    x2 = pulp.LpVariable.dicts("x", range(N), lowBound=0, upBound=1, cat=pulp.LpBinary)
    W_total_2 = pulp.lpSum(x2[i] * w[i] for i in range(N))
    S_total_2 = pulp.lpSum(x2[i] * w[i] * v[i] for i in range(N))
    y2 = pulp.lpSum(x2[i] * w[i] * (v[i] - t) for i in range(N))
    z2 = pulp.LpVariable("z2", lowBound=0, upBound=None, cat=pulp.LpContinuous)

    # Feasibility (same) + lexicographic pin
    m2 += W_total_2 >= W_low
    m2 += W_total_2 <= W_high
    m2 += S_total_2 >= lo * W_total_2
    m2 += S_total_2 <= up * W_total_2
    m2 += z2 >= y2
    m2 += z2 >= -y2
    m2 += z2 >= z_opt  # keep deviation no worse than stage-1 optimum

    # Preference: force-in again if needed
    if selected_ids:
        sel = set(selected_ids)
        for i in range(N):
            if ids[i] in sel:
                m2 += x2[i] == 1

    # **Leaching cap** (repeat for stage-2)
    if outside_idx:
        W_out_2 = pulp.lpSum(x2[i] * w[i] for i in outside_idx)
        m2 += W_out_2 <= cap_share * W_total_2

    "Objective: just keep z2 as small as possible"
    m2 += z2
    status2 = m2.solve(solver)
    status_str2 = pulp.LpStatus[status2]

    # Extract
    use_stage2 = (status_str2 in ("Optimal", "Integer Feasible", "Feasible"))
    x_vals = [float(((x2[i] if use_stage2 else x[i]).value()) or 0.0) for i in range(N)]
    chosen_idx = [i for i in range(N) if x_vals[i] > 0.5]
    chosen = [items[i] for i in chosen_idx]
    unused = [items[i]["batch"] for i in range(N) if i not in chosen_idx]

    W_sel = sum(itm["w"] for itm in chosen)
    S_sel = sum(itm["w"] * itm["v"] for itm in chosen)
    avg = (S_sel / W_sel) if W_sel > 0 else float("nan")
    meets_limits = _within_with_tol(avg, lo, up)

    dev_num_signed = sum(itm["w"] * (itm["v"] - t) for itm in chosen)
    dev_num_abs = abs(dev_num_signed)
    weight_err = abs(W_sel - W_star)

    # Leaching outputs
    W_out_sel = 0.0
    out_batches_selected = []
    if (leach_lo is not None) and (leach_up is not None):
        for i in chosen_idx:
            if (v[i] <= leach_lo) or (v[i] >= leach_up):
                W_out_sel += w[i]
                out_batches_selected.append(ids[i])
    out_share_sel = (W_out_sel / W_sel) if W_sel > 0 else None

    # Build result
    tolerances = {"lower": W_tol_lower, "upper": W_tol_upper}
    legacy_tolerance = W_tol_lower if abs(W_tol_lower - W_tol_upper) <= 1e-12 else None
    result = {
        "status": status_str2 if use_stage2 else status_str1,
        "preference": preference,
        "requested_weight": W_star,
        # NEW: asymmetric tolerances
        "tolerances": tolerances,
        # Legacy (populated only when both sides equal):
        "tolerance": legacy_tolerance,
        "target": t,
        "limits": {"lower": lo, "upper": up},
        "selected_batches": [{"batch": it["batch"], "weight": it["w"], "variable": it["v"]} for it in chosen],
        "unused_batches": unused,
        "total_weight": W_sel,
        "avg_variable": avg,
        "meets_limits": meets_limits,
        "deviation_numerator_abs": dev_num_abs,
        "leaching_limits": leaching_limits,
        # NEW: leaching metrics for the selected blend
        "leaching_cap_share": cap_share,
        "leaching_out_weight": W_out_sel,
        "leaching_out_share": out_share_sel,
        "leaching_out_batches": out_batches_selected,
        "weight_error": weight_err,
        "weight_window": {"low": W_low, "high": W_high},
        "note": f"MILP stage-1={status_str1}, stage-2={status_str2}, dropped={len(dropped)}"
                + (f" ({{{[d['batch'] for d in dropped]}}})" if dropped else "")
    }
    return result


def solve_blends_exhaustive(rows: List[List[Any]], specs: Dict[str, Any], time_limit=None) -> Dict[str, Any]:
    """
    Repeatedly compute blends by weight, removing used batches after each success.
    Stops when remaining total weight < W_low OR when MILP becomes infeasible.
    Returns a dict with a list of blend results under key "blends" and a final summary.
    If the very first blend is infeasible, returns {"error": "..."} (same behaviour as single).
    """
    # Validate once and compute weight window
    try:
        t, lo, up, W_star, W_tol_lower, W_tol_upper, preference, selected_ids = _validate_specs(specs)
    except Exception as e:
        return {"error": str(e)}
    W_low = max(0.0, W_star - W_tol_lower)

    # Parse leaching limits & cap
    leaching_limits, cap_share = _parse_leaching(specs)

    # Prepare items and a working copy of rows
    items_all, dropped0 = _prepare_items(rows)
    # Build a rows_remaining list from kept items to preserve shape [[b,v,w], ...]
    rows_rem = [[it["batch"], it["v"], it["w"]] for it in items_all]

    blends: List[Dict[str, Any]] = []
    loop_idx = 0
    stop_reason = None

    while True:
        loop_idx += 1
        # Quick stop: insufficient remaining weight for the window lower bound
        rem_weight = sum(r[2] for r in rows_rem if r[2] > 0)
        if rem_weight < W_low:
            stop_reason = "not_enough_weight"
            break

        # Solve one blend on current remainder
        res = solve_blend_by_weight_milp(rows_rem, specs, time_limit=time_limit)
        if "error" in res:
            # If first attempt fails, propagate the error
            if not blends:
                return res
            # Otherwise, we stop and report reason
            stop_reason = "infeasible_with_remaining"
            break

        # Record this blend
        blends.append(res)

        # Remove used batches from rows_rem
        used_ids = {x["batch"] for x in res.get("selected_batches", [])}
        rows_rem = [r for r in rows_rem if str(r[0]) not in used_ids]

        # Safety: if nothing was removed (degenerate), break to avoid infinite loop
        if not used_ids:
            stop_reason = "no_batches_removed"
            break

    # Build final summary
    unused_batches_final = [str(r[0]) for r in rows_rem]

    summary = {
        "status": "OK",
        "blend_count": len(blends),
        "requested_weight": W_star,
        "tolerances": {"lower": W_tol_lower, "upper": W_tol_upper},
        "tolerance": W_tol_lower if abs(W_tol_lower - W_tol_upper) <= 1e-12 else None,
        "target": t,
        "limits": {"lower": lo, "upper": up},
        "leaching_limits": leaching_limits,  # existing
        "leaching_cap_share": cap_share,      # NEW in summary
        "stop_reason": stop_reason,
        "unused_batches_after": unused_batches_final,
        "time_limit_applied": bool(time_limit),
        "solver": "CBC",
        "any_non_optimal": any(b.get("solution_quality") != "optimal" for b in blends)
    }
    return {"summary": summary, "blends": blends}


def main():
    ap = argparse.ArgumentParser(
        description="Blend-by-weight (whole batches, exact MILP, hard limits) — supports multi-blend"
    )
    ap.add_argument("--input", required=True, help="Path to JSON input (rows, meta, specs)")
    ap.add_argument("--quiet", action="store_true", help="Suppress human-readable summaries; print only final JSON")
    ap.add_argument("--time_limit", type=int, default=None, help="CBC time limit (seconds)")
    ap.add_argument("--single", action="store_true", help="Compute only the first blend (original behaviour)")
    args = ap.parse_args()

    # Load JSON
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: Could not read input JSON: {e}")
        sys.exit(1)

    rows = data.get("rows", []) or []
    specs = data.get("specs", {}) or {}
    order = data.get("meta", {}).get("order", ["batch", "variable", "weight"])

    # Early display of requested weight & tolerances (human banner)
    if not args.quiet:
        # Compute preview of window using validation (safe-guarded)
        try:
            t, lo, up, W_star, L_tol, U_tol, preference, _ = _validate_specs(specs)
            W_low = max(0.0, W_star - L_tol)
            W_high = W_star + U_tol
            tol_str = f"(+{U_tol}/-{L_tol}) kg"
        except Exception:
            W_low = W_high = None
            tol_str = "(tolerances invalid)"
        print("==== Blend-by-Weight (whole batches, exact MILP) ====")
        print(f"Rows received: {len(rows)}")
        print(f"Order: {order}")
        print(
            f"Specs: target={specs.get('target')}, "
            f"limits=[{specs.get('lower')}, {specs.get('upper')}], "
            f"blend_weight={specs.get('blend_weight')} {tol_str}"
        )
        if W_low is not None and W_high is not None:
            print(f"Weight window=[{W_low}, {W_high}]")
        if specs.get("selected_batches"):
            print(f"Selected (forced-in) batches: {specs.get('selected_batches')}")
        # Show leaching preview if present
        leach, cap_share = _parse_leaching(specs)
        if isinstance(leach, dict) and (leach.get('lower') is not None) and (leach.get('upper') is not None):
            print(f"Leaching limits: [{leach.get('lower')}, {leach.get('upper')}] — cap_share={cap_share}")

    if args.single:
        res = solve_blend_by_weight_milp(rows, specs, time_limit=args.time_limit)
        if "error" in res:
            print("ERROR:", res["error"])
            # Do not print anything after; exit non-zero (GUI will show error dialog)
            sys.exit(2)
        # Human summary (optional)
        if not args.quiet:
            avg_str = "NaN" if (res["avg_variable"] != res["avg_variable"]) else f"{res['avg_variable']:.6f}"
            L_tol = (res.get("tolerances") or {}).get("lower")
            U_tol = (res.get("tolerances") or {}).get("upper")
            lines = [
                f"Status: {res['status']}",
                f"Requested weight: {res['requested_weight']} (+{U_tol}/-{L_tol}) kg "
                f"(window=[{res['weight_window']['low']}, {res['weight_window']['high']}])",
                f"Total weight: {res['total_weight']:.6f} (error={res['weight_error']:.6f})",
                f"Average variable: {avg_str} (target={res['target']})",
                f"Meets limits: {res['meets_limits']}",
                f"Abs deviation numerator: {res['deviation_numerator_abs']:.6f}",
                # NEW: leaching diagnostics
                f"Leaching out weight: {res.get('leaching_out_weight', 0.0):.6f}",
                f"Leaching out share: {('%.4f' % res.get('leaching_out_share')) if res.get('leaching_out_share') is not None else 'N/A'}",
                f"Selected batches: {len(res['selected_batches'])}",
                f"Unused batches: {len(res['unused_batches'])}",
                res["note"],
                f"Batch IDs: {[x['batch'] for x in res.get('selected_batches', [])]}",
            ]
            print("\n".join(lines))
        # Final JSON block (single) — **must be last**
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Multi-blend mode (default)
    res_multi = solve_blends_exhaustive(rows, specs, time_limit=args.time_limit)
    if "error" in res_multi:
        print("ERROR:", res_multi["error"])
        sys.exit(2)

    # Human summary (optional)
    if not args.quiet:
        summary = res_multi.get("summary", {})
        blends = res_multi.get("blends", [])
        L_tol = (summary.get("tolerances") or {}).get("lower")
        U_tol = (summary.get("tolerances") or {}).get("upper")
        print(f"Computed {len(blends)} blend(s). Stop reason: {summary.get('stop_reason')}")
        for i, b in enumerate(blends, start=1):
            avg_str = "NaN" if (b["avg_variable"] != b["avg_variable"]) else f"{b['avg_variable']:.6f}"
            lines = [
                f"\n--- Blend {i} ---",
                f"Status: {b['status']}",
                f"Requested weight: {summary.get('requested_weight')} (+{U_tol}/-{L_tol}) kg "
                f"(window=[{b['weight_window']['low']}, {b['weight_window']['high']}])",
                f"Total weight: {b['total_weight']:.6f} (error={b['weight_error']:.6f})",
                f"Average variable: {avg_str} (target={b['target']})",
                f"Meets limits: {b['meets_limits']}",
                f"Abs deviation numerator: {b['deviation_numerator_abs']:.6f}",
                # NEW: leaching diagnostics
                f"Leaching out weight: {b.get('leaching_out_weight', 0.0):.6f}",
                f"Leaching out share: {('%.4f' % b.get('leaching_out_share')) if b.get('leaching_out_share') is not None else 'N/A'}",
                f"Selected batches: {len(b['selected_batches'])}",
                f"Unused batches (this round): {len(b['unused_batches'])}",
                b["note"],
                f"Batch IDs: {[x['batch'] for x in b.get('selected_batches', [])]}",
            ]
            print("\n".join(lines))
    # Final JSON block (multi) — **must be last**
    print(json.dumps(res_multi, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

