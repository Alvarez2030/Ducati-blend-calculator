
import json
import argparse
import sys
import math
import time

# ======================
# Existing helper: parse_rows (kept for completeness)
# ======================
def parse_rows(rows):
    """
    Convert raw rows [[batch, var, weight], ...] to typed tuples (batch:str, var:float|NaN, weight:float).
    """
    parsed = []
    for idx, r in enumerate(rows, 1):
        batch = str(r[0]) if len(r) > 0 else "Row{}".format(idx)
        # variable
        try:
            variable = float(r[1]) if len(r) > 1 and r[1] not in ("", None) else float("nan")
        except Exception:
            variable = float("nan")
        # weight
        try:
            weight = float(r[2]) if len(r) > 2 and r[2] not in ("", None) else 0.0
        except Exception:
            weight = 0.0
        parsed.append((batch, variable, weight))
    return parsed

# Existing heuristic (unaltered)

def compute_blends(rows, specs, time_budget_seconds=2.0):
    """
    Greedy construction + local improvement + targeted rescue for out-of-spec blends.
    Returns a structured result; printing is done in main().
    """
    import time
    import math
    k = specs.get("batches_per_blend")
    t = specs.get("target")
    lo = specs.get("lower")
    up = specs.get("upper")
    if not isinstance(k, int) or k < 1:
        return {"error": "Invalid batches_per_blend"}

    # --- Parse input into items ---
    items = []
    for r in rows:
        batch = str(r[0])
        try:
            var = float(r[1]) if r[1] not in ("", None) else float("nan")
        except Exception:
            var = float("nan")
        try:
            wt = float(r[2]) if r[2] not in ("", None) else 0.0
        except Exception:
            wt = 0.0
        dev = (var - t) if (var == var) else 0.0  # NaN check: var==var is True unless NaN
        impact = abs(dev) * wt
        items.append({"batch": batch, "var": var, "wt": wt, "dev": dev, "impact": impact})

    # Buckets
    pos = [x for x in items if x["var"] == x["var"] and x["dev"] >= 0.0]
    neg = [x for x in items if x["var"] == x["var"] and x["dev"] < 0.0]
    nanv = [x for x in items if not (x["var"] == x["var"])]
    pos.sort(key=lambda x: x["impact"], reverse=True)
    neg.sort(key=lambda x: x["impact"], reverse=True)
    nanv.sort(key=lambda x: x["wt"], reverse=True)

    # Metrics helpers
    def blend_metrics(group):
        wsum = sum(x["wt"] for x in group)
        num = sum(x["wt"] * x["var"] for x in group if x["var"] == x["var"])
        avg = (num / wsum) if wsum > 0 else float("nan")
        dev_num = abs(sum(x["wt"] * (x["var"] - t) for x in group if x["var"] == x["var"]))
        meets = None

        if (avg == avg) and (lo is not None) and (up is not None):
            meets = _within_with_tol(avg, lo, up)
        return avg, wsum, dev_num, meets

    # --- Greedy construction (alternate pos/neg, then fill leftovers balanced by weight) ---
    blends = []
    i_pos = i_neg = 0
    while (i_pos < len(pos)) or (i_neg < len(neg)):
        group = []
        while len(group) < k and (i_pos < len(pos) or i_neg < len(neg)):
            if len(group) % 2 == 0 and i_pos < len(pos):
                group.append(pos[i_pos]); i_pos += 1
            elif i_neg < len(neg):
                group.append(neg[i_neg]); i_neg += 1
            elif i_pos < len(pos):
                group.append(pos[i_pos]); i_pos += 1
        blends.append(group)
    leftovers = pos[i_pos:] + neg[i_neg:] + nanv
    def total_wsum(g): return sum(x["wt"] for x in g)
    for x in leftovers:
        # place into blend with smallest total weight (balance denominators)
        tgt = None; min_w = None
        for bi, g in enumerate(blends):
            w = total_wsum(g)
            if (min_w is None) or (w < min_w):
                min_w = w; tgt = bi
        if tgt is None or len(blends[tgt]) >= k:
            blends.append([x])
        else:
            blends[tgt].append(x)
    for bi in range(len(blends)):
        blends[bi] = blends[bi][:k]

    # --- Local improvement: 1-for-1 swaps ---
    start = time.time()
    improved = True
    while improved and (time.time() - start) < time_budget_seconds/2.0:
        improved = False
        for gi in range(len(blends)):
            for gj in range(gi + 1, len(blends)):
                g1, g2 = blends[gi], blends[gj]
                # precompute old devs
                _, _, dev1_old, _ = blend_metrics(g1)
                _, _, dev2_old, _ = blend_metrics(g2)
                for i in range(len(g1)):
                    for j in range(len(g2)):
                        if (time.time() - start) >= time_budget_seconds/2.0: break
                        new_g1 = list(g1); new_g2 = list(g2)
                        new_g1[i], new_g2[j] = new_g2[j], new_g1[i]
                        _, _, dev1_new, _ = blend_metrics(new_g1)
                        _, _, dev2_new, _ = blend_metrics(new_g2)
                        if (dev1_new + dev2_new) < (dev1_old + dev2_old) - 1e-12:
                            blends[gi], blends[gj] = new_g1, new_g2
                            improved = True
                            g1, g2 = new_g1, new_g2
                            dev1_old, dev2_old = dev1_new, dev2_new

    # --- Targeted rescue for out-of-spec blends: try swaps among top-impact candidates ---
    def blend_gap(group):
        # signed gap (numerator) toward target; aim for ~0
        return sum(x["wt"] * (x["var"] - t) for x in group if x["var"] == x["var"])

    # Build candidate list (top-impact items per blend)
    def top_candidates(group, m=3):
        return sorted(group, key=lambda x: x["impact"], reverse=True)[:m]

    # Identify worst blends by abs gap or out-of-spec
    worst_indices = []
    for bi, g in enumerate(blends):
        avg, _, _, meets = blend_metrics(g)
        gap = abs(blend_gap(g))
        worst_indices.append((gap, (avg != avg), (meets is False), bi))
    # Sort: larger gap, NaN avg first, then out-of-spec first
    worst_indices.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    deadline = start + time_budget_seconds
    for _, _, _, gi in worst_indices:
        if time.time() >= deadline: break
        g1 = blends[gi]
        # If already in spec, skip
        avg1, _, _, meets1 = blend_metrics(g1)
        if meets1 is True: continue
        # Search partner blends
        for gj in range(len(blends)):
            if time.time() >= deadline: break
            if gj == gi: continue
            g2 = blends[gj]
            cand1 = top_candidates(g1, m=min(3, len(g1)))
            cand2 = top_candidates(g2, m=min(3, len(g2)))
            # 1) Try 1-for-1 rescue first (fast)
            _, _, dev1_old, _ = blend_metrics(g1)
            _, _, dev2_old, _ = blend_metrics(g2)
            best_delta = 0.0; best_swap = None
            for a in cand1:
                for b in cand2:
                    new_g1 = [x if x is not a else b for x in g1]
                    new_g2 = [x if x is not b else a for x in g2]
                    _, _, dev1_new, _ = blend_metrics(new_g1)
                    _, _, dev2_new, _ = blend_metrics(new_g2)
                    delta = (dev1_old + dev2_old) - (dev1_new + dev2_new)
                    if delta > best_delta + 1e-12:
                        best_delta = delta; best_swap = (a, b, new_g1, new_g2)
            if best_swap:
                a, b, new_g1, new_g2 = best_swap
                blends[gi], blends[gj] = new_g1, new_g2
                # Re-check spec; continue to next worst if fixed
                avg1, _, _, meets1 = blend_metrics(blends[gi])
                if meets1 is True: break  # rescued
            # 2) Try 2-for-2 (bounded) if still out-of-spec
            if time.time() >= deadline: break
            if len(cand1) >= 2 and len(cand2) >= 2:
                # generate pairs
                pairs1 = [(cand1[i], cand1[j]) for i in range(len(cand1)) for j in range(i+1, len(cand1))]
                pairs2 = [(cand2[i], cand2[j]) for i in range(len(cand2)) for j in range(i+1, len(cand2))]
                best_delta2 = 0.0; best_pair = None
                for (a1, a2) in pairs1:
                    for (b1, b2) in pairs2:
                        if time.time() >= deadline: break
                        new_g1 = [x for x in g1]
                        new_g2 = [x for x in g2]
                        # swap a1<->b1 and a2<->b2
                        def swap_into(grp, old, new):
                            for idx in range(len(grp)):
                                if grp[idx] is old: grp[idx] = new; break
                        swap_into(new_g1, a1, b1); swap_into(new_g1, a2, b2)
                        swap_into(new_g2, b1, a1); swap_into(new_g2, b2, a2)
                        _, _, dev1_new, _ = blend_metrics(new_g1)
                        _, _, dev2_new, _ = blend_metrics(new_g2)
                        _, _, dev1_old, _ = blend_metrics(g1)
                        _, _, dev2_old, _ = blend_metrics(g2)
                        delta = (dev1_old + dev2_old) - (dev1_new + dev2_new)
                        if delta > best_delta2 + 1e-12:
                            best_delta2 = delta; best_pair = (new_g1, new_g2)
                if best_pair:
                    blends[gi], blends[gj] = best_pair
                    avg1, _, _, meets1 = blend_metrics(blends[gi])
                    if meets1 is True: break  # rescued

    # --- Build results ---
    results = []
    total_dev = 0.0
    for group in blends:
        avg, wsum, dev_num, meets = blend_metrics(group)
        total_dev += dev_num
        results.append({
            "batches": [x["batch"] for x in group],
            "avg_variable": avg,
            "total_weight": wsum,
            "meets_target": meets,
            "deviation_numerator": dev_num
        })
    return {
        "objective_total_deviation_numerator": total_dev,
        "blend_count": len(blends),
        "blends": results
    }

# ======================
# NEW: Validation + MILP exact solver via PuLP
# ======================

def _validate_specs(specs):
    """Validate and coerce specs. Returns (t, lo, up, k) or dict(error=...)."""
    if not isinstance(specs, dict):
        return {"error": "Specs missing"}
    # Require target and limits
    try:
        t = float(specs["target"])
        lo = float(specs["lower"])
        up = float(specs["upper"])
    except Exception:
        return {"error": "Non-numeric target/limits in specs"}
    if lo > up or not (lo <= t <= up):
        return {"error": "Invalid limits/target relationship"}
    # batches_per_blend
    k = specs.get("batches_per_blend")
    if not isinstance(k, int) or k < 1:
        return {"error": "Invalid batches_per_blend"}
    return (t, lo, up, k)

def _within_with_tol(value, lo, up, rtol=1e-9, atol=1e-9):
    """
    Robust [lo, up] check with combined relative/absolute tolerance to handle floating-point noise.
    """
    if value != value:  # NaN
        return False
    span = max(abs(lo), abs(up), 1.0)
    tol = max(atol, rtol * span)
    return (value >= lo - tol) and (value <= up + tol)
# END PATCH

def _prepare_items(rows):
    """Parse rows into [{'batch', 'var', 'wt'}], preserving order."""
    items = []
    for r in rows:
        batch = str(r[0])
        try:
            var = float(r[1]) if r[1] not in ("", None) else float("nan")
        except Exception:
            var = float("nan")
        try:
            wt = float(r[2]) if r[2] not in ("", None) else 0.0
        except Exception:
            wt = 0.0
        items.append({"batch": batch, "var": var, "wt": wt})
    return items



# BEGIN PATCH: compute_blends_milp with last smaller blend and spec constraints
def compute_blends_milp(rows, specs):
    """
    Exact solver via PuLP/CBC:
      Minimize sum_b | sum_i x_{i,b} * w_i * (v_i - t) |
      s.t. each item assigned exactly once,
           first B_full blends have exactly k items,
           last blend has r items (if N % k != 0),
           each blend's average is within [lower, upper].
    Returns same structured dict as heuristic, or {"error": "..."}.
    """
    # Validate specs
    vs = _validate_specs(specs)
    if isinstance(vs, dict) and "error" in vs:
        return vs
    t, lo, up, k = vs

    # Prepare & filter items: drop NaNs and zero-weight for the MILP
    items_all = _prepare_items(rows)
    items = [itm for itm in items_all if (itm["wt"] > 0.0) and (itm["var"] == itm["var"])]
    dropped = [itm for itm in items_all if itm not in items]

    N = len(items)
    if N == 0:
        return {"error": "No valid items (after filtering NaNs and zero weights)"}

    # Allow last smaller blend if N % k != 0
    B_full = N // k
    r = N % k
    B = B_full + (1 if r > 0 else 0)

    # Precompute constants for linear expressions
    w = [itm["wt"] for itm in items]
    s = [itm["wt"] * itm["var"] for itm in items]           # S term coefficients
    d = [itm["wt"] * (itm["var"] - t) for itm in items]     # numerator coefficients (objective)

    # Try to import PuLP
    try:
        import pulp
    except Exception:
        return {"error": "PuLP not available. Please install 'pulp' or use --strategy heuristic."}

    # Build MILP
    m = pulp.LpProblem("BlendMinAbsNumerators_with_Specs_and_LastSmallBlend", pulp.LpMinimize)

    # Binary assignment x[i,b]
    x = pulp.LpVariable.dicts("x", (range(N), range(B)), lowBound=0, upBound=1, cat=pulp.LpBinary)
    # Blend numerators y_b and absolute z_b
    y = pulp.LpVariable.dicts("y", range(B), lowBound=None, upBound=None, cat=pulp.LpContinuous)
    z = pulp.LpVariable.dicts("z", range(B), lowBound=0, upBound=None, cat=pulp.LpContinuous)

    # Each item in exactly one blend
    for i in range(N):
        m += pulp.lpSum(x[i][b] for b in range(B)) == 1

    # Cardinalities: first B_full blends of size k, last one of size r (if r>0)
    for b in range(B_full):
        m += pulp.lpSum(x[i][b] for i in range(N)) == k
    if r > 0:
        m += pulp.lpSum(x[i][B-1] for i in range(N)) == r

    # Define y_b = sum d_i * x[i,b]
    for b in range(B):
        m += y[b] == pulp.lpSum(x[i][b] * d[i] for i in range(N))

    # |y_b| via z_b
    for b in range(B):
        m += z[b] >= y[b]
        m += z[b] >= -y[b]

    # Spec constraints on averages:
    # S_b = sum s_i * x[i,b]; W_b = sum w_i * x[i,b]
    # Enforce: lower * W_b <= S_b <= upper * W_b
    for b in range(B):
        S_b = pulp.lpSum(x[i][b] * s[i] for i in range(N))
        W_b = pulp.lpSum(x[i][b] * w[i] for i in range(N))
        m += S_b >= lo * W_b
        m += S_b <= up * W_b

    # Objective: minimize sum z_b
    m += pulp.lpSum(z[b] for b in range(B))

    # Solve with CBC
    start = time.time()
    status = m.solve(pulp.PULP_CBC_CMD(msg=False))
    elapsed = time.time() - start

    # Informative statuses
    if pulp.LpStatus[status] == "Infeasible":
        return {"error": "No feasible assignment satisfies the specification limits with the given k (and last smaller blend if needed)."}
    if pulp.LpStatus[status] != "Optimal":
        return {"error": f"MILP solver status: {pulp.LpStatus[status]} (time={elapsed:.3f}s)"}

    # Extract blends (indices in 'items')
    blends_idx = [[] for _ in range(B)]
    for b in range(B):
        for i in range(N):
            if pulp.value(x[i][b]) > 0.5:
                blends_idx[b].append(i)

    # Build structured output
    results = []
    total_dev = 0.0
    for b in range(B):
        group = [items[i] for i in blends_idx[b]]
        wsum = sum(g["wt"] for g in group)
        num = sum(g["wt"] * g["var"] for g in group)
        avg = (num / wsum) if wsum > 0 else float("nan")
        dev_num_signed = sum(g["wt"] * (g["var"] - t) for g in group)
        dev_num = abs(dev_num_signed)
        meets = None
        if (avg == avg):
            meets = _within_with_tol(avg, lo, up)

        total_dev += dev_num
        results.append({
            "batches": [g["batch"] for g in group],
            "avg_variable": avg,
            "total_weight": wsum,
            "meets_target": meets,
            "deviation_numerator": dev_num
        })

    meta_note = (
        f"PuLP CBC status=Optimal • time={elapsed:.3f}s • items={N} • blends={B} • "
        f"dropped={len(dropped)}" + (f" ({[d['batch'] for d in dropped]})" if dropped else "")
    )

    return {
        "objective_total_deviation_numerator": total_dev,
        "blend_count": len(results),
        "blends": results,
        "meta_note": meta_note
    }
# END PATCH

# ======================
# Main: add --strategy flag to choose heuristic or MILP
# ======================
def main():
    ap = argparse.ArgumentParser(description="Blending Calculator (heuristic + MILP)")
    ap.add_argument("--input", required=True, help="Path to JSON input (rows, meta, specs)")
    ap.add_argument("--strategy", choices=["heuristic", "milp"], default="milp",
                help="Algorithm: heuristic or milp (exact via PuLP; default)")

    ap.add_argument("--time-budget", type=float, default=1.0,
                    help="Time budget seconds for heuristic (ignored by MILP)")
    ap.add_argument("--quiet", action="store_true", help="Suppress extra header printing")
    args = ap.parse_args()

    # Load JSON
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("ERROR: Could not read input JSON: {}".format(e))
        sys.exit(1)

    rows = data.get("rows", [])
    specs = data.get("specs", {}) or {}
    order = data.get("meta", {}).get("order", ["batch", "variable", "weight"])

    # Header
    if not args.quiet:
        print("==== Blending Calculator (heuristic + MILP) ====")
        print("Rows received: {} \n order: {}".format(len(rows), order))
        print("Specs: target={}, limits=[{}, {}], batches_per_blend={}".format(
            specs.get("target"), specs.get("lower"), specs.get("upper"), specs.get("batches_per_blend")))
        print("------------------------------------------------------------")

    # Compute
    if args.strategy == "milp":
        res = compute_blends_milp(rows, specs)
    else:
        res = compute_blends(rows, specs, time_budget_seconds=args.time_budget)

    if "error" in res:
        print(json.dumps({"error": res["error"]}, ensure_ascii=False))
        return

    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
