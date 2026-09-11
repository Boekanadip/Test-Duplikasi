"""Hard complex test: inject fabricated P1-P7 patterns into real 50k base.

Combines the complexity of fake_data_builder (P1 exact, P2 typo, P3 abbrev,
P4 name-order, P5 email-var, P6 phone-fmt, P7 dob/address) with the claimed
ground truth of the complex test, then runs the SAME merge concord as
form_merge_test (threshold=0.7, guard=3) and validates vs true_entity_id.

Usage:
  python scripts/complex_hard_test.py --regenerate
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
INPUT_RAW = ROOT / "data" / "raw" / "crm_50000_customers_dirty_v3.csv"
OUT_CSV = ROOT / "data" / "processed" / "_complex_hard_500.csv"
OUT_DIR = ROOT / "data" / "processed" / "complex_hard_merge"
RNG = np.random.default_rng(42)

ABBREV = {"michael": "mike", "robert": "bob", "william": "bill", "jennifer": "jen", "elizabeth": "liz"}
PATTERNS = ["P1_exact", "P1_exact", "P2_typo", "P2_typo", "P3_abbrev", "P4_nameorder",
            "P5_emailvar", "P5_emailvar", "P6_phonefmt", "P6_phonefmt", "P7_dob", "P7_dob", "P7_dob"]


def load_base(n: int = 400) -> pd.DataFrame:
    raw = pd.read_csv(INPUT_RAW)
    base = raw.drop_duplicates(subset=["customer_id"]).iloc[:n].copy()
    base = base[["first_name", "last_name", "email", "phone_number", "dob", "address", "city"]].copy()
    base["true_entity_id"] = [f"ent_{i:04d}" for i in range(len(base))]
    return base.reset_index(drop=True)


def p1_exact(src: pd.Series) -> pd.Series:
    return src[["first_name", "last_name", "email", "phone_number", "dob", "address", "city", "true_entity_id"]].copy()


def p2_typo(src: pd.Series) -> pd.Series:
    d = p1_exact(src)
    field = RNG.choice(["first_name", "last_name", "email"])
    w = str(src[field])
    if len(w) > 2:
        pos = RNG.integers(0, len(w))
        d[field] = w[:pos] + str(RNG.choice(list("abcdefghijklmnopqrstuvwxyz0123456789"))) + w[pos + 1:]
    return d


def p3_abbrev(src: pd.Series) -> pd.Series:
    d = p1_exact(src)
    fn = str(src["first_name"]).strip().casefold()
    d["first_name"] = ABBREV.get(fn, fn[:4])
    return d


def p4_nameorder(src: pd.Series) -> pd.Series:
    d = p1_exact(src)
    d["first_name"], d["last_name"] = str(src["last_name"]), str(src["first_name"])
    return d


def p5_emailvar(src: pd.Series) -> pd.Series:
    d = p1_exact(src)
    email = str(src["email"])
    if "@" in email:
        local, dom = email.split("@", 1)
        if dom == "gmail.com":
            d["email"] = local + "@googlemail.com"
        else:
            d["email"] = local.replace(".", "") + "@" + dom
    return d


def p6_phonefmt(src: pd.Series) -> pd.Series:
    d = p1_exact(src)
    phone = str(src["phone_number"])
    if phone.startswith("0"):
        d["phone_number"] = "0" + phone.lstrip("0")
    elif phone:
        d["phone_number"] = "+62 " + phone
    if phone and d["phone_number"] == src["phone_number"]:
        d["phone_number"] = "62" + phone
    return d


def p7_dob(src: pd.Series) -> pd.Series:
    d = p1_exact(src)
    dob = str(src["dob"])
    d["dob"] = dob
    d["address"] = str(src["address"]).replace("Jl.", "Jalan").replace("No. ", "")
    return d


PAT_FCN = {"P1_exact": p1_exact, "P2_typo": p2_typo, "P3_abbrev": p3_abbrev,
           "P4_nameorder": p4_nameorder, "P5_emailvar": p5_emailvar,
           "P6_phonefmt": p6_phonefmt, "P7_dob": p7_dob}


def build_test_csv() -> pd.DataFrame:
    base = load_base(400)
    rows: list[pd.DataFrame] = [base]
    for i, pat in enumerate(PATTERNS):
        src = base.iloc[i % len(base)]
        dup = PAT_FCN[pat](src)
        dup = dup.copy()
        dup["pattern"] = pat
        rows.append(pd.DataFrame([dup]))
    # decoys: 30 rows sharing email/phone with a base record but DIFFERENT person
    decoys: list[dict] = []
    rand = random.Random(11)
    for dec in range(30):
        tgt = base.iloc[rand.randrange(len(base))]
        other = base.iloc[rand.randrange(len(base))]
        row = dict(tgt[["first_name", "last_name", "email", "phone_number", "dob", "address", "city"]])
        row["true_entity_id"] = f"decoy_{dec:04d}"
        if rand.random() < 0.5:
            row["email"] = other["email"]
        else:
            row["phone_number"] = other["phone_number"]
        row["pattern"] = "decoy"
        decoys.append(row)
    rows.append(pd.DataFrame(decoys))
    test = pd.concat(rows, ignore_index=True)
    test = test.sample(frac=1.0, random_state=3).reset_index(drop=True)
    test.to_csv(OUT_CSV, index=False)
    n_dup = test[test["pattern"] != "decoy"]
    dup_recs = int((test["true_entity_id"].value_counts() > 1).sum())
    print(f"rows={len(test)} entities={test['true_entity_id'].nunique()} dup_groups={dup_recs}")
    print(test["pattern"].value_counts(dropna=True).to_dict())


def true_pairs(df: pd.DataFrame) -> set[tuple[int, int]]:
    mp: dict[str, list[int]] = {}
    for idx, ent in df["true_entity_id"].items():
        if str(ent).startswith("decoy"):
            continue
        mp.setdefault(str(ent), []).append(idx)
    pairs: set[tuple[int, int]] = set()
    for idxs in mp.values():
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                pairs.add((min(idxs[i], idxs[j]), max(idxs[i], idxs[j])))
    return pairs


def evaluate_baseline(df: pd.DataFrame, all_true: set[tuple[int, int]]) -> pd.DataFrame:
    from src.standardization import standardize_customers
    from src.blocking import generate_candidate_pairs
    from src.comparison import build_comparison_vectors
    from src.decision import apply_match_policy

    std = standardize_customers(df)
    pairs = generate_candidate_pairs(std)
    comp = build_comparison_vectors(std, pairs)
    dec = apply_match_policy(comp, high_confidence_threshold=4, candidate_threshold=2)
    predicted = {(min(int(r["left_row_index"]), int(r["right_row_index"])), max(int(r["left_row_index"]), int(r["right_row_index"])))
                 for _, r in dec[dec["match_decision"] != "not_match"].iterrows()}
    tp = len(predicted & all_true); fp = len(predicted - all_true); fn = len(all_true - predicted)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    print(f"\n=== BASELINE: TP={tp} FP={fp} FN={fn} P={prec:.3f} R={rec:.3f} F1={f1:.3f} (candidates={len(dec)})")
    return dec


def make_labels(df: pd.DataFrame, all_true: set[tuple[int, int]], n_each: int = 40) -> pd.DataFrame:
    rand = random.Random(11)
    pos = list(all_true)[:n_each]
    neg: set[tuple[int, int]] = set()
    while len(neg) < n_each:
        a, b = rand.sample(range(len(df)), 2)
        if str(df.iloc[a]["true_entity_id"]) != str(df.iloc[b]["true_entity_id"]):
            neg.add((min(a, b), max(a, b)))
    rows = [{"record_id_l": str(l), "record_id_r": str(r), "clerical_match_score": 1} for l, r in pos]
    rows += [{"record_id_l": str(l), "record_id_r": str(r), "clerical_match_score": 0} for l, r in list(neg)]
    return pd.DataFrame(rows)


def evaluate_splink_and_merge(df: pd.DataFrame, all_true: set[tuple[int, int]]) -> None:
    from src.splink_pipeline import (
        split_labels,
        train_splink_pipeline,
        evaluate_splink_holdout,
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    labels = make_labels(df, all_true)
    labels_path = OUT_DIR / "labels.csv"
    labels.to_csv(labels_path, index=False)
    pred_path = OUT_DIR / "predictions.csv"

    # --- leakage fix: train m only on train fold, sweep thresholds on holdout ---
    train, holdout = split_labels(labels)
    print(f"labels: {len(labels)} -> train={len(train)} (pos={int(train['clerical_match_score'].sum())}) "
          f"| holdout={len(holdout)} (pos={int(holdout['clerical_match_score'].sum())})")
    train_path = OUT_DIR / "train_labels.csv"
    holdout_path = OUT_DIR / "holdout_labels.csv"
    train.to_csv(train_path, index=False)
    holdout.to_csv(holdout_path, index=False)

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        preds = train_splink_pipeline(str(OUT_CSV), str(train_path), str(pred_path))
    print(f"splink predictions={len(preds)} (m trained on train fold only)")

    # threshold sweep on HOLDOUT only --- no overlap with training pairs
    print("\n--- Splink threshold sweep vs HOLDOUT ground truth ---")
    sweep = []
    for t in [0.1, 0.3, 0.5, 0.7, 0.9]:
        r = evaluate_splink_holdout(preds, holdout, threshold=t)
        sweep.append({"thr": t, "pred": None, "TP": r['true_positive'], "FP": r['false_positive'],
                      "FN": r['false_negative'], "P": round(r['precision'], 3),
                      "R": round(r['recall'], 3), "F1": round(r['f1'], 3)})
    print(pd.DataFrame(sweep).to_string(index=False))
    print("(holdout folds guarantee the pairs above were never used for m/u training)")

    # merge concord — probabilistic concord score vs merge_threshold (no hard identity gate)
    from src.merge import run_merge_pipeline
    res = run_merge_pipeline(OUT_CSV, pred_path, OUT_DIR, auto_threshold=0.95, review_threshold=0.15)
    print("\n--- MERGE (concord auto=0.95, review<0.15, band 0.15-0.95 -> review) ---")
    print(res["summary"])

    dec = pd.read_csv(OUT_DIR / "merge_decisions.csv")
    auto = {(min(int(r.left_row_index), int(r.right_row_index)), max(int(r.left_row_index), int(r.right_row_index)))
            for _, r in dec[dec.merge_decision == "auto_merge"].iterrows()}
    review = {(min(int(r.left_row_index), int(r.right_row_index)), max(int(r.left_row_index), int(r.right_row_index)))
              for _, r in dec[dec.merge_decision == "review_required"].iterrows()}
    tp = len(auto & all_true); fp = len(auto - all_true)
    r_tp = len(review & all_true); r_fp = len(review - all_true)
    fn = len(all_true - auto - review)
    print(f"auto_merge: TP={tp} FP={fp}")
    print(f"review:     TP={r_tp} FP={r_fp}")
    print(f"missed:     FN={fn}")
    rq = pd.read_csv(OUT_DIR / "review_queue.csv")
    print(f"review_queue rows: {len(rq)}")

    # per-pattern recall of auto_merge
    print("\n--- auto_merge recall per pattern (vs ground truth) ---")
    for pat in ["P1_exact", "P2_typo", "P3_abbrev", "P4_nameorder", "P5_emailvar", "P6_phonefmt", "P7_dob"]:
        p_pairs = set()
        for _, r in df[df["pattern"] == pat].iterrows():
            idx = int(r.name)
            for m in df.index[df["true_entity_id"] == df.loc[idx, "true_entity_id"]]:
                if m != idx:
                    p_pairs.add((min(idx, int(m)), max(idx, int(m))))
        tp_pat = len(auto & p_pairs)
        print(f"  {pat:12s} pairs={len(p_pairs)} auto_merge={tp_pat} ({(tp_pat/len(p_pairs)*100) if p_pairs else 0:.0f}%)  review_recall={len(review & p_pairs)}/{len(p_pairs) if p_pairs else 0}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--regenerate", action="store_true")
    args = p.parse_args()
    if OUT_CSV.exists() and not args.regenerate:
        print(f"reusing {OUT_CSV}")
        df = pd.read_csv(OUT_CSV)
    else:
        build_test_csv()
        df = pd.read_csv(OUT_CSV)
    all_true = true_pairs(df)
    print(f"true dup pairs (ground truth): {len(all_true)} | rows={len(df)}")
    evaluate_baseline(df, all_true)
    evaluate_splink_and_merge(df, all_true)
    print(f"\nOUT: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())