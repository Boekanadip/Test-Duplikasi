"""Phase 3: Auto-merge concord from baseline decisions + Splink probabilities.

Rule:
  baseline == high_confidence_candidate AND splink >= threshold AND identity_guard -> auto_merge
  baseline == not_match AND splink < threshold -> not_match
  everything else -> review_required

identity_guard = at least min_identity_agreement of (email, phone, name) agree
exactly, blocking the shared-phone/email decoy false positives found in Phase 2.

Survivorship: for each auto-merged pair group, keep the longest non-empty raw
value per field (most complete record wins). Non-merged records pass through.

Usage:
  python -m src.merge --input data/processed/_complex_500_test.csv \
      --predictions data/processed/_complex_eval/predictions.csv \
      --threshold 0.7 --min-identity-agreement 2 --output-dir data/processed/merge_demo
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from .blocking import generate_candidate_pairs
from .comparison import build_comparison_vectors
from .decision import apply_match_policy
from .io import load_customer_csv, save_artifact
from .standardization import standardize_customers

IDENTITY_LABELS = ("email", "phone", "name")

CONCORD_WEIGHTS = {"baseline": 0.30, "splink": 0.40, "identity": 0.30}


def concord_score(
    dec: pd.DataFrame,
    *,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """Weighted concord score replacing the hard identity gate.

    baseline term: 1.0 for high_confidence, 0.5 for candidate, 0.0 otherwise.
    splink term: raw match_probability.
    identity term: fraction of (email, phone, name) that agree exactly.

    A low identity agreement no longer vetoes a pair outright; it just
    lowers the score. Tune ``merge_threshold`` on a holdout set.
    """
    w = CONCORD_WEIGHTS if weights is None else weights
    baseline = dec["match_decision"].map(
        {"high_confidence_candidate": 1.0, "candidate": 0.5}
    ).fillna(0.0)
    splink = dec["match_probability"].astype(float)
    identity = dec["identity_agreement"].astype(float) / len(IDENTITY_LABELS)
    return w["baseline"] * baseline + w["splink"] * splink + w["identity"] * identity


def build_pair_frame(
    df: pd.DataFrame, standardized: pd.DataFrame, predictions: pd.DataFrame
) -> pd.DataFrame:
    pairs = generate_candidate_pairs(standardized)
    comp = build_comparison_vectors(standardized, pairs)
    dec = apply_match_policy(comp, high_confidence_threshold=4, candidate_threshold=2)

    preds = predictions.copy()
    preds["pair_key"] = preds.apply(
        lambda r: tuple(sorted((str(r["record_id_l"]), str(r["record_id_r"])))),
        axis=1,
    )
    pred_lookup = preds.set_index("pair_key")["match_probability"].to_dict()

    dec["pair_key"] = dec.apply(
        lambda r: tuple(sorted((str(r["left_row_index"]), str(r["right_row_index"])))),
        axis=1,
    )
    dec["match_probability"] = dec["pair_key"].map(pred_lookup).fillna(0.0)
    identity_count = sum(dec[f"{label}_agree"] for label in IDENTITY_LABELS)
    dec["identity_agreement"] = identity_count
    return dec


def apply_concord(
    dec: pd.DataFrame, *,
    auto_threshold: float = 0.95,
    review_threshold: float = 0.15,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Probabilistic concord with an explicit review band.

    - concord_score >= auto_threshold    -> auto_merge (strong exact identity + high prob)
    - concord_score <  review_threshold  -> not_match
    - between them                       -> review_required (ambiguous band)

    Scalable: decoys sharing one identity field land in the review band at
    ~0.9 instead of being rejected, so human review is the arbiter, not a
    hard gate. Adjust thresholds on a holdout.
    """
    result = dec.copy()
    result["concord_score"] = concord_score(result, weights=weights)
    result["merge_decision"] = "review_required"
    result.loc[result["concord_score"].ge(auto_threshold), "merge_decision"] = "auto_merge"
    result.loc[result["concord_score"].lt(review_threshold), "merge_decision"] = "not_match"
    return result


def survive(group: pd.DataFrame) -> pd.Series:
    merged = {}
    for col in group.columns:
        vals = [v for v in group[col].tolist() if pd.notna(v) and str(v).strip() != ""]
        merged[col] = max(vals, key=lambda v: len(str(v))) if vals else pd.NA
    return pd.Series(merged)


def merge_entities(
    raw: pd.DataFrame, dec: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    auto = dec[dec["merge_decision"] == "auto_merge"]
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for _, r in auto.iterrows():
        union(int(r["left_row_index"]), int(r["right_row_index"]))

    groups: dict[int, list[int]] = {}
    for idx in raw.index.tolist():
        groups.setdefault(find(int(idx)), []).append(int(idx))

    merged_rows: list[pd.Series] = []
    members: list[dict] = []
    for root, idxs in groups.items():
        block = raw.loc[idxs]
        surv = survive(block)
        surv["entity_id"] = f"entity_{root:06d}"
        surv["member_count"] = len(idxs)
        surv["member_indices"] = "|".join(str(i) for i in sorted(idxs))
        merged_rows.append(surv)
        for i in idxs:
            members.append({"record_index": i, "entity_id": surv["entity_id"]})
    merged = pd.DataFrame(merged_rows)
    members_df = pd.DataFrame(members)
    counts = dec["merge_decision"].value_counts().to_dict()
    summary = {
        "input_records": len(raw),
        "candidate_pairs": len(dec),
        "auto_merge_pairs": int(counts.get("auto_merge", 0)),
        "review_required_pairs": int(counts.get("review_required", 0)),
        "not_match_pairs": int(counts.get("not_match", 0)),
        "output_entities": len(merged),
        "records_merged": int(len(raw) - len(merged)),
    }
    return merged, members_df, summary


def run_merge_pipeline(
    input_path: str | Path,
    predictions_path: str | Path,
    output_dir: str | Path,
    *,
    auto_threshold: float = 0.95,
    review_threshold: float = 0.15,
    weights: dict[str, float] | None = None,
) -> dict:
    raw = load_customer_csv(input_path)
    standardized = standardize_customers(raw)
    predictions = pd.read_csv(predictions_path)
    dec = build_pair_frame(raw, standardized, predictions)
    dec = apply_concord(dec, auto_threshold=auto_threshold,
                           review_threshold=review_threshold, weights=weights)
    merged, members, summary = merge_entities(raw, dec)
    summary.update({"auto_threshold": auto_threshold,
                    "review_threshold": review_threshold,
                    "concord_weights": CONCORD_WEIGHTS if weights is None else weights})

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dec_path = out / "merge_decisions.csv"
    merged_path = out / "merged_records.csv"
    members_path = out / "entity_members.csv"
    review_path = out / "review_queue.csv"
    summary_path = out / "merge_summary.json"
    save_artifact(dec, dec_path)
    save_artifact(merged, merged_path)
    save_artifact(members, members_path)
    save_artifact(dec[dec["merge_decision"] == "review_required"], review_path)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {
        "decisions": dec,
        "merged": merged,
        "members": members,
        "summary": summary,
        "paths": {
            "decisions": dec_path,
            "merged": merged_path,
            "members": members_path,
            "review": review_path,
            "summary": summary_path,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="merge-concord",
        description="Auto-merge where baseline and Splink agree; rest goes to review.",
    )
    parser.add_argument("--input", required=True, help="Path to customer CSV.")
    parser.add_argument("--predictions", required=True, help="Path to Splink predictions CSV.")
    parser.add_argument("--output-dir", required=True, help="Directory for merge artifacts.")
    parser.add_argument("--auto-threshold", type=float, default=0.95,
                        help="Concord score >= this -> auto_merge.")
    parser.add_argument("--review-threshold", type=float, default=0.15,
                        help="Concord score < this -> not_match; in between -> review.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_merge_pipeline(
        args.input, args.predictions, args.output_dir,
        auto_threshold=args.auto_threshold, review_threshold=args.review_threshold,
    )
    print(f"summary={result['summary']}")
    for key, path in result["paths"].items():
        print(f"{key}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
