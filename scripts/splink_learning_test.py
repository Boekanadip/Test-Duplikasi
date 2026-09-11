"""Show whether Splink learns from labels vs relying on defaults.

Runs two Splink models on the same fabricated dataset:
  A: no labels — EM on u-probabilities only, no m-estimation
  B: with stratified labels — EM trains m-probabilities

Results differ -> proves Splink learns from human-reviewed labels.
Also shows: threshold sweep, identity guard, blocking coverage, and
concept explainer at the end.

Usage: python scripts/splink_learning_test.py
Prereq: python scripts/fake_data_builder.py first
"""
from __future__ import annotations

import argparse
import random
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
FAKE = ROOT / "data" / "processed" / "fake_500.csv"
RUN_DIR = ROOT / "data" / "processed" / "splink_learning"
RNG = random.Random(11)

BLOCK_RULES = ["email_std", "phone_digits_std", "name_key_std|dob_std", "city_std|dob_std"]


def true_pairs(df: pd.DataFrame) -> set[tuple[int, int]]:
    ent_map: dict[str, list[int]] = {}
    for idx, ent in enumerate(df["true_entity_id"].apply(str)):
        if ent.startswith("decoy"):
            continue
        ent_map.setdefault(ent, []).append(idx)
    return {(min(a, b), max(a, b))
            for idxs in ent_map.values()
            for i in range(len(idxs))
            for a, b in [(idxs[i], idxs[j]) for j in range(i + 1, len(idxs))]}


def labels_from_df(df: pd.DataFrame, truth: set[tuple[int, int]], n_pos: int = 40, n_neg: int = 40) -> pd.DataFrame:
    pos = list(truth)[:n_pos]
    neg: list[tuple[int, int]] = []
    decoy = df.index[df["true_entity_id"].apply(lambda s: str(s).startswith("decoy"))].tolist()
    while len(neg) < n_neg:
        if decoy and RNG.random() < 0.5:
            a = RNG.choice(decoy)
            b = RNG.choice(range(len(df)))
            if str(df.iloc[b]["true_entity_id"]).startswith("decoy"):
                continue
        else:
            a, b = RNG.sample(range(len(df)), 2)
        if str(df.iloc[a]["true_entity_id"]) != str(df.iloc[b]["true_entity_id"]):
            neg.append((min(a, b), max(a, b)))
    rows = ([{"record_id_l": str(a), "record_id_r": str(b), "clerical_match_score": 1} for a, b in pos]
            + [{"record_id_l": str(a), "record_id_r": str(b), "clerical_match_score": 0} for a, b in neg])
    return pd.DataFrame(rows)


def splink_predict(standardized: pd.DataFrame, labels: pd.DataFrame | None, use_labels: bool) -> pd.DataFrame:
    from splink import block_on, DuckDBAPI, Linker, SettingsCreator
    from splink.comparison_library import ExactMatch, LevenshteinAtThresholds

    settings = SettingsCreator(
        link_type="dedupe_only",
        unique_id_column_name="record_id",
        comparisons=[
            ExactMatch("email_std"), ExactMatch("phone_digits_std"),
            LevenshteinAtThresholds("name_key_std", [1, 2]),
            LevenshteinAtThresholds("address_std", [2, 4]),
            ExactMatch("city_std"), ExactMatch("dob_std"),
        ],
        blocking_rules_to_generate_predictions=[
            block_on("email_std"), block_on("phone_digits_std"),
            block_on("name_key_std", "dob_std"), block_on("city_std", "dob_std"),
        ],
    )
    linker = Linker(standardized, settings, db_api=DuckDBAPI())
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000, seed=42)

    if use_labels and labels is not None:
        linker._db_api.register_table(labels, "reviewed_labels", overwrite=True)
        linker.training.estimate_probability_two_random_records_match(
            deterministic_matching_rules=[block_on("email_std"), block_on("phone_digits_std")], recall=0.8)
        linker.training.estimate_m_from_pairwise_labels("reviewed_labels")
    # else: EM-only on u, default m

    return linker.inference.predict().as_pandas_dataframe()


def prf(pred: set[tuple[int, int]], truth: set[tuple[int, int]]) -> tuple[int, int, int, float, float, float]:
    tp = len(pred & truth); fp = len(pred - truth); fn = len(truth - pred)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return tp, fp, fn, p, r, f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    fake_path = ROOT / "data" / "processed" / "fake_500.csv"
    if not fake_path.exists() or args.rebuild:
        from scripts.fake_data_builder import build
        build()

    df = pd.read_csv(fake_path)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    truth = true_pairs(df)
    print(f"dataset rows={len(df)}  true_dup_pairs={len(truth)}")

    from src.splink_pipeline import prepare_splink_input
    std = prepare_splink_input(df)
    labels = labels_from_df(df, truth, 40, 40)
    labels.to_csv(RUN_DIR / "train_labels.csv", index=False)
    print(f"labels: pos={int(labels['clerical_match_score'].sum())} neg={len(labels)-int(labels['clerical_match_score'].sum())}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        preds_A = splink_predict(std, labels, use_labels=False)
        preds_B = splink_predict(std, labels, use_labels=True)

    for name, preds in [("A_no_labels", preds_A), ("B_with_labels", preds_B)]:
        preds["pair_key"] = preds.apply(lambda r: tuple(sorted((int(r["record_id_l"]), int(r["record_id_r"])))), axis=1)
        preds.to_csv(RUN_DIR / f"pred_{name}.csv", index=False)

    print("\n=== A: Splink WITHOUT labels (u-only, default m) ===")
    print("mean match_probability:", preds_A["match_probability"].mean())
    print("max probability pairs (top 5):")
    print(preds_A.nlargest(5, "match_probability")[["record_id_l","record_id_r","match_probability"]].to_string(index=False))

    print("\n=== B: Splink WITH labels (EM-trained m) ===")
    print("mean match_probability:", preds_B["match_probability"].mean())
    print("max probability pairs (top 5):")
    print(preds_B.nlargest(5, "match_probability")[["record_id_l","record_id_r","match_probability"]].to_string(index=False))

    sweep_A, sweep_B = [], []
    for t in [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9]:
        tp, fp, fn, p, r, f = prf(set(preds_A.loc[preds_A["match_probability"]>=t, "pair_key"]), truth)
        sweep_A.append({"thr": t, "pred": len(preds_A[preds_A["match_probability"]>=t]), "TP": tp, "FP": fp, "P": round(p,3), "R": round(r,3), "F1": round(f,3)})
        tp, fp, fn, p, r, f = prf(set(preds_B.loc[preds_B["match_probability"]>=t, "pair_key"]), truth)
        sweep_B.append({"thr": t, "pred": len(preds_B[preds_B["match_probability"]>=t]), "TP": tp, "FP": fp, "P": round(p,3), "R": round(r,3), "F1": round(f,3)})

    print("\n=== threshold sweep ===")
    print("\n--- Branch A (no labels) ---")
    print(pd.DataFrame(sweep_A).to_string(index=False))
    print("\n--- Branch B (with labels) ---")
    print(pd.DataFrame(sweep_B).to_string(index=False))
    pd.DataFrame(sweep_A).assign(branch="A").to_csv(RUN_DIR / "sweep_A.csv", index=False)
    pd.DataFrame(sweep_B).assign(branch="B").to_csv(RUN_DIR / "sweep_B.csv", index=False)

    from src.splink_pipeline import cluster_predictions
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cl = cluster_predictions(std, preds_B, threshold=args.threshold)
    cl_nu = cl["cluster_id"].nunique()
    print(f"\nClustering (B@{args.threshold}): records={len(cl)} clusters={cl_nu} (dup clumped={len(cl)-cl_nu})")

    from src.standardization import standardize_customers
    from src.blocking import generate_candidate_pairs
    from src.comparison import build_comparison_vectors
    from src.decision import apply_match_policy
    std_b = standardize_customers(df)
    bp = generate_candidate_pairs(std_b)
    comp2 = build_comparison_vectors(std_b, bp)
    dec = apply_match_policy(comp2)
    blocked_gt = len(truth & {(min(int(r.left_row_index), int(r.right_row_index)), max(int(r.left_row_index), int(r.right_row_index))) for _, r in dec.iterrows()})
    guard2 = set()
    guard3 = set()
    id_count = sum(dec[f"{l}_agree"] for l in ("email", "phone", "name"))
    for row_idx, r in dec.iterrows():
        k = (min(int(r.left_row_index), int(r.right_row_index)), max(int(r.left_row_index), int(r.right_row_index)))
        if r.match_decision == "high_confidence_candidate":
            if id_count.loc[row_idx] >= 2:
                guard2.add(k)
            if id_count.loc[row_idx] >= 3:
                guard3.add(k)
    print(f"blocking recall: {blocked_gt}/{len(truth)} = {blocked_gt/len(truth):.1%}")
    print(f"high_conf candidate pairs: {len(dec[dec.match_decision=='high_confidence_candidate'])}")
    print(f"concord guard=2: {len(guard2)}  guard=3: {len(guard3)}")

    print("\n--- CONCEPT EXPLAINER ---")
    print("""
BLOCKING
  Pairwise N(N-1)/2 = 90,000 pairs for 422 records.
  Blocking keys: exact email, exact phone, name+dob, city+dob.
  Only records sharing a key are compared -> blocking_candidates << total.
  Blocking recall = how many true duplicates survive into candidate set.
  Missing a true dup in blocking = permanent recall loss.

SIMILARITY SCORE (match_probability)
  For each candidate pair, Splink compares 6 fields.
  Each field gets an agreement score (0/1 or Levenshtein level).
  The model combines these via:  P(match) ~ prior * product( m_i / u_i )
  where m_i = P(field agrees | same person) and u_i = P(field agrees | diff person).
  Labels (clerical_match_score 0/1) are used to estimate m via EM.
  More labels -> more accurate m estimates -> better probability ranking.

GROUND TRUTH
  true_entity_id is known in synthetic data (in production it is NOT known).
  We build label files from pairs of records: record_a, record_b, label(0/1).
  The 80 labels used here are sampled: 40 true matches + 40 negatives including decoys.
  Without ground truth you CANNOT compute precision/recall — only inspect clusters.

TUNING
  Grid search over threshold (e.g. 0.05, 0.1, ... 0.95) on a held-out review set.
  For each threshold, threshold -> predicted positive = (match_probability >= threshold).
  F1 = 2 * P * R / (P + R). Pick the threshold with highest F1.
  Identity guard (min_identity_agreement) is another tuning parameter:
  require >=N of (email, phone, name) to agree exactly, reducing shared-field decoy FPs.

THRESHOLD & DECISION
  threshold = operating point on P-R curve.
  Lower threshold = more recall, fewer missed matches (more review queue).
  Higher threshold = more precision, fewer false merges (some true dupes missed).
  Production decision: baseline(agree) AND Splink(>=threshold) AND guard(>=N identity)
  -> auto_merge; everything else -> review queue.
""")
    print(f"Artifacts: {RUN_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
