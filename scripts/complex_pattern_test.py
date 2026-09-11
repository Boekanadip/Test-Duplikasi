"""Phase 2: Complex duplicate-pattern test (4 tiers + baseline vs Splink per tier).

Generates a synthetic 500-record CSV derived from 50k raw:
  T1 easy (20 pairs): typo / case / spacing on 1-2 fields
  T2 moderate (20): abbreviation, name-order flip
  T3 hard (30): email/phone transforms, DOB format, address tokens
  T4 decoy (30 true non-dup sharing email/phone) → FP trap

Ground truth via true_entity_id. Runs baseline + Splink, reports per-tier metrics.

Usage:
  python scripts/complex_pattern_test.py                       # generate + evaluate
  python scripts/complex_pattern_test.py --no-splink          # baseline only
  python scripts/complex_pattern_test.py --threshold 0.5
"""
from __future__ import annotations

import argparse
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
INPUT_RAW = ROOT / "data" / "raw" / "crm_50000_customers_dirty_v3.csv"
OUT_CSV = ROOT / "data" / "processed" / "_complex_500_test.csv"
OUT_DIR = ROOT / "data" / "processed" / "_complex_eval"
RNG = np.random.default_rng(7)

ABBREV = {"michael": "mike", "robert": "bob", "william": "bill", "jennifer": "jen", "elizabeth": "liz"}
NAME_FLIP_SEED = 42


def load_base(n: int = 400) -> pd.DataFrame:
    raw = pd.read_csv(INPUT_RAW)
    base = raw.drop_duplicates(subset=["customer_id"]).iloc[:n].copy()
    base = base[["first_name", "last_name", "email", "phone_number", "dob", "address", "city"]].copy()
    base["true_entity_id"] = [f"ent_{i:04d}" for i in range(len(base))]
    return base.reset_index(drop=True)


def t1_typo(src: pd.Series) -> pd.Series:
    dup = src[["first_name", "last_name", "email", "phone_number", "dob", "address", "city", "true_entity_id"]].copy()
    fields = list(RNG.choice(["email", "phone_number", "first_name", "address"], size=int(RNG.integers(1, 3)), replace=False))
    for f in fields:
        kind = RNG.choice(["typo", "case", "space"])
        v = str(src[f])
        if kind == "typo" and len(v) > 2:
            pos = RNG.integers(0, len(v))
            dup[f] = v[:pos] + str(RNG.choice(list("abcdefghijklmnopqrstuvwxyz0123456789"))) + v[pos + 1 :]
        elif kind == "case":
            dup[f] = v.swapcase()
        else:
            dup[f] = "  ".join(v.split()) + " "
    return dup


def t2_abbrev_or_flip(src: pd.Series) -> pd.Series:
    dup = src[["first_name", "last_name", "email", "phone_number", "dob", "address", "city", "true_entity_id"]].copy()
    if RNG.random() < 0.5:
        fn = str(src["first_name"]).strip().casefold()
        expanded = ABBREV.get(fn)
        if expanded:
            dup["first_name"] = expanded if fn != expanded else next(k for k, v in ABBREV.items() if v == fn)
        else:
            dup["first_name"] = fn.capitalize() if fn else fn
        dup["last_name"] = str(src["last_name"]).strip().casefold().capitalize()
    else:
        dup["first_name"] = str(src["last_name"]).strip()
        dup["last_name"] = str(src["first_name"]).strip()
    dup["address"] = str(src["address"]).replace("Street", "St.").replace("Avenue", "Ave.")
    return dup


def t3_hard(src: pd.Series) -> pd.Series:
    dup = src[["first_name", "last_name", "email", "phone_number", "dob", "address", "city", "true_entity_id"]].copy()
    email = str(src["email"])
    phone = str(src["phone_number"])
    dob = str(src["dob"])
    addr = str(src["address"])
    r = RNG.random()
    if "@" in email and r < 0.35:
        local, dom = email.split("@", 1)
        if "gmail" in dom:
            dup["email"] = email.replace("gmail.com", "googlemail.com")
        else:
            dup["email"] = local.replace(".", "") + "@" + dom
    elif r < 0.5:
        digits = re.sub(r"\D", "", phone)
        if digits.startswith("0"):
            dup["phone_number"] = "+62 " + digits.lstrip("0")
        elif digits:
            dup["phone_number"] = "0" + digits[-10:]
    if dob and "-" in dob and RNG.random() < 0.3:
        try:
            y, m, d = dob.split("-")
            dup["dob"] = f"{d}/{m}/{y}" if RNG.random() < 0.5 else f"{m}/{d}/{y}"
        except ValueError:
            pass
    if RNG.random() < 0.4:
        dup["address"] = addr.replace("No. ", "").replace("Jl. ", "Jalan ").replace("Apt.", "Apartment")
    return dup


def t4_decoy(base: pd.DataFrame, n: int = 30) -> pd.DataFrame:
    rand = random.Random(11)
    rows: list[pd.Series] = []
    for _ in range(n):
        a, b = rand.sample(range(len(base)), 2)
        src_a = base.iloc[a]
        row = src_a[["first_name", "last_name", "email", "phone_number", "dob", "address", "city"]].copy()
        row["true_entity_id"] = f"decoy_{len(rows):04d}"
        other = base.iloc[b]
        share = rand.choice(["email", "phone"])
        if share == "email":
            row["email"] = other["email"]
        else:
            row["phone_number"] = other["phone_number"]
        rows.append(row)
    return pd.DataFrame(rows)


def build_test_csv() -> pd.DataFrame:
    base = load_base(400)
    parts: list[pd.DataFrame] = [base]
    tier_counts = {"T1": 20, "T2": 20, "T3": 30}
    tier_labels: list[str] = []
    tier_labels.extend(["T1"] * 20)
    tier_labels.extend(["T2"] * 20)
    tier_labels.extend(["T3"] * 30)
    funcs = {"T1": t1_typo, "T2": t2_abbrev_or_flip, "T3": t3_hard}
    for idx, tier in enumerate(tier_labels):
        src = base.iloc[idx % len(base)]
        dup = funcs[tier](src)
        dup["tier"] = tier
        parts.append(pd.DataFrame([dup]))
    decoy = t4_decoy(base, 30)
    decoy["tier"] = "T4_decoy"
    parts.append(decoy)
    test = pd.concat(parts, ignore_index=True)
    test = test.sample(frac=1.0, random_state=3).reset_index(drop=True)
    test.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(test)} rows -> {OUT_CSV}")
    print("Rows per true_entity group:", test["true_entity_id"].value_counts().value_counts().sort_index().to_dict())
    print("Rows tagged by tier (non-NA):", test["tier"].value_counts(dropna=True).to_dict())
    return test


def true_pairs(df: pd.DataFrame) -> set[tuple[int, int]]:
    mp: dict[str, list[int]] = {}
    for idx, ent in df["true_entity_id"].items():
        mp.setdefault(str(ent), []).append(idx)
    pairs: set[tuple[int, int]] = set()
    for idxs in mp.values():
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                pairs.add((min(idxs[i], idxs[j]), max(idxs[i], idxs[j])))
    return pairs


def pairs_by_tier(df: pd.DataFrame, tier: str) -> set[tuple[int, int]]:
    sub = df[df["tier"] == tier] if "tier" in df.columns else pd.DataFrame()
    if sub.empty:
        return set()
    ent = sub["true_entity_id"].tolist()
    idxs_by_tier = sub.index.tolist()
    pairs: set[tuple[int, int]] = set()
    for idx, ent_id in zip(idxs_by_tier, ent, strict=True):
        mates = df.index[df["true_entity_id"] == ent_id].tolist()
        orig = [m for m in mates if df.loc[m, "tier"] != tier or pd.isna(df.loc[m, "tier"])]
        if not orig:
            orig = [m for m in mates if m != idx]
        for m in orig:
            pairs.add((min(idx, m), max(idx, m)))
    return pairs


def evaluate_baseline(df: pd.DataFrame, all_true: set[tuple[int, int]]) -> None:
    from src.comparison import build_comparison_vectors
    from src.decision import apply_match_policy
    from src.blocking import generate_candidate_pairs
    from src.standardization import standardize_customers

    std = standardize_customers(df)
    pairs = generate_candidate_pairs(std)
    comp = build_comparison_vectors(std, pairs)
    dec = apply_match_policy(comp, high_confidence_threshold=4, candidate_threshold=2)

    predicted = {
        (min(int(r["left_row_index"]), int(r["right_row_index"])), max(int(r["left_row_index"]), int(r["right_row_index"])))
        for _, r in dec[dec["match_decision"] != "not_match"].iterrows()
    }

    def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return prec, rec, f1

    tp, fp, fn = len(predicted & all_true), len(predicted - all_true), len(all_true - predicted)
    prec, rec, f1 = prf(tp, fp, fn)
    print("\n=== BASELINE overall ===")
    print(f"candidates={len(dec)} predicted={len(predicted)} TP={tp} FP={fp} FN={fn} P={prec:.3f} R={rec:.3f} F1={f1:.3f}")
    print("decision counts:", dec["match_decision"].value_counts().to_dict())

    pred_by_strat = dec.copy()
    print("\n=== BASELINE per-tier (True pairs only the tier injected) ===")
    for tier in ("T1", "T2", "T3"):
        tier_pairs = pairs_by_tier(df, tier)
        ttp = len(predicted & tier_pairs)
        tfn = len(tier_pairs - predicted)
        prec_t, rec_t, f1_t = prf(ttp, 0, tfn)
        print(f"  {tier}: tier_pairs={len(tier_pairs)} TP={ttp} FN={tfn} R={rec_t:.3f} F1={f1_t:.3f}")
    t4_predicted = len([p for p in predicted if any(
        str(df.loc[l, "true_entity_id"]).startswith("decoy") or str(df.loc[r, "true_entity_id"]).startswith("decoy")
        for l, r in [p]
    )])
    print(f"  T4 decoy FP (predicted where decoy entity participates) ~= {t4_predicted}")
    print("\nRaw candidate_pairs blocking breakdown (top):")
    bc = dec["supporting_blocking_strategies"].value_counts().head(8)
    for k, v in bc.items():
        print(f"  {k}: {v}")

    flagged = dec[dec["review_required"]]
    print(f"\nReview queue: {len(flagged)} pairs | not_match discarded: {len(dec) - len(flagged)}")


def evaluate_splink(df: pd.DataFrame, all_true: set[tuple[int, int]], threshold: float = 0.5) -> None:
    try:
        from src.splink_pipeline import train_splink_pipeline  # noqa
    except ImportError:
        print("\n[Splink skip] pip install -e .[splink]")
        return

    rand = random.Random(11)
    # 80 labels sampled from this df, checked vs df true_entity_id (true ground truth of this synthetic set)
    already_true = list(all_true)[:40]
    false_candidates: set[tuple[int, int]] = set()
    while len(false_candidates) < 40:
        a, b = rand.sample(range(len(df)), 2)
        if df.iloc[a]["true_entity_id"] != df.iloc[b]["true_entity_id"]:
            false_candidates.add((min(a, b), max(a, b)))
    rows = [{"record_id_l": str(l), "record_id_r": str(r), "clerical_match_score": 1} for l, r in already_true]
    rows += [{"record_id_l": str(l), "record_id_r": str(r), "clerical_match_score": 0} for l, r in list(false_candidates)]
    label_df = pd.DataFrame(rows)
    label_path = OUT_DIR / "_labels.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    label_df.to_csv(label_path, index=False)
    print(f"\nSplink labels: {len(label_df)} pos={int(label_df['clerical_match_score'].sum())} -> {label_path}")

    from src.splink_pipeline import train_splink_pipeline as tsp

    preds = tsp(str(OUT_CSV), str(label_path), str(OUT_DIR / "predictions.csv"))
    preds["pair_key"] = preds.apply(lambda r: tuple(sorted((int(r["record_id_l"]), int(r["record_id_r"])))), axis=1)

    def prf(pred: set[tuple[int, int]], true: set[tuple[int, int]]):
        tp = len(pred & true); fp = len(pred - true); fn = len(true - pred)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return tp, fp, fn, prec, rec, f1

    print("\n=== SPLINK by threshold (vs all 70 T1-T3 true pairs: decoy not in true set) ===")
    grid = []
    for t in [0.1, 0.3, threshold, 0.5, 0.7, 0.9] if threshold not in [0.1, 0.3, 0.5, 0.7, 0.9] else [0.1, 0.3, 0.5, 0.7, 0.9]:
        pos = set(preds.loc[preds["match_probability"] >= t, "pair_key"])
        tp, fp, fn, prec, rec, f1 = prf(pos, all_true)
        grid.append({"threshold": t, "predicted": len(pos), "TP": tp, "FP": fp, "FN": fn,
                     "P": round(prec, 3), "R": round(rec, 3), "F1": round(f1, 3)})
    print(pd.DataFrame(grid).to_string(index=False))
    print(f"\nChosen threshold={threshold} -> TP/FP/FN as above")
    preds["is_dup"] = preds["pair_key"].isin(all_true)
    print("\nTop 8 splink predictions:")
    print(preds.sort_values("match_probability", ascending=False)[["record_id_l","record_id_r","match_probability","is_dup"]].head(8).to_string(index=False))


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 2 complex-pattern test")
    p.add_argument("--no-splink", action="store_true", help="baseline only")
    p.add_argument("--threshold", type=float, default=0.5, help="Splink threshold to report")
    p.add_argument("--regenerate", action="store_true", help="regenerate OUT_CSV even if it exists")
    args = p.parse_args()

    if OUT_CSV.exists() and not args.regenerate:
        print(f"Reusing {OUT_CSV}")
        df = pd.read_csv(OUT_CSV)
    else:
        df = build_test_csv()

    print("rows:", len(df), "entities:", df["true_entity_id"].nunique())
    all_true = true_pairs(df)
    print("true duplicate pairs (ground truth):", len(all_true))
    # T4 decoy rows have unique true_entity_id each => they add 0 to all_true, as desired (they are FP traps, not positives)
    t4_count = int((df["tier"] == "T4_decoy").sum()) if "tier" in df.columns else 0
    print(f"T4 decoy rows: {t4_count} (each unique entity; any pair involving them should NOT be predicted)")

    evaluate_baseline(df, all_true)
    if not args.no_splink:
        evaluate_splink(df, all_true, threshold=args.threshold)
    else:
        print("\n[no-splink] done.")

    print(f"\nCSV: {OUT_CSV}")
    print(f"OUT: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
