"""Full form-data test: import -> baseline -> splink predict -> merge -> validate vs true_entity_id."""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data/raw/synthetic_300.csv"
FORM_CSV = ROOT / "data/processed/form_responses.csv"
CLEAN = ROOT / "data/processed/form_clean.csv"
BASE_OUT = ROOT / "data/processed/form_baseline.csv"
PRED_OUT = ROOT / "data/processed/form_predictions.csv"
MERGE_DIR = ROOT / "data/processed/form_merge"
LABELS = ROOT / "data/processed/form_labels.csv"
RNG = random.Random(5)

# 1. Simulate a Google Form export: Indonesian-ish headers + Timestamp column
df = pd.read_csv(RAW)
form = df.rename(columns={
    "first_name": "Pertanyaan 1 - Nama Depan",
    "last_name": "Pertanyaan 2 - Nama Belakang",
    "email": "Pertanyaan 3 - Email",
    "phone_number": "Pertanyaan 4 - Nomor Telepon",
    "dob": "Pertanyaan 5 - Tanggal Lahir",
    "address": "Pertanyaan 6 - Alamat",
    "city": "Pertanyaan 7 - Kota",
})
form.insert(0, "Timestamp", ["2026-01-01 10:00:00"] * len(form))
form = form[["Timestamp"] + [c for c in form.columns if c != "Timestamp"] + ["true_entity_id"]]
form.to_csv(FORM_CSV, index=False)
print(f"[1] form export written: {FORM_CSV} ({len(form)} rows)")

# 2. Import via importer
import importlib.util as _i
_s = _i.spec_from_file_location("import_form_csv", Path(__file__).parent / "import_form_csv.py")
_mod = _i.module_from_spec(_s); _s.loader.exec_module(_mod); import_form_csv = _mod.import_form_csv
clean = import_form_csv(FORM_CSV)
clean["true_entity_id"] = df["true_entity_id"]
clean.to_csv(CLEAN, index=False)
print(f"[2] imported columns: {list(clean.columns)} rows={len(clean)}")

# 3. Baseline
from src.pipeline import run_candidate_pipeline
import warnings
warnings.filterwarnings("ignore")
base = run_candidate_pipeline(CLEAN, BASE_OUT, log_level="WARNING")
print(f"[3] baseline candidate_pairs={len(base)} decisions={base['match_decision'].value_counts().to_dict()}")

# 4. Splink predictions (self-training on synthetic true_entity_id pairs we KNOW)
ent_map: dict[str, list[int]] = {}
for idx, ent in enumerate(clean["true_entity_id"]):
    ent_map.setdefault(str(ent), []).append(idx)
pos = []
for idxs in ent_map.values():
    for i in range(len(idxs)):
        for j in range(i + 1, len(idxs)):
            pos.append({"record_id_l": str(idxs[i]), "record_id_r": str(idxs[j]), "clerical_match_score": 1})
neg = []
while len(neg) < 60:
    a, b = RNG.sample(range(len(clean)), 2)
    if str(clean.loc[a, "true_entity_id"]) != str(clean.loc[b, "true_entity_id"]):
        neg.append({"record_id_l": str(a), "record_id_r": str(b), "clerical_match_score": 0})
labels = pd.DataFrame(pos + neg)
labels.to_csv(LABELS, index=False)
print(f"[4] labels for splink: {len(labels)} (pos={len(pos)} neg={len(neg)})")

# --- leakage fix: train m only on train fold, evaluate on holdout ---
from src.splink_pipeline import (
    split_labels,
    train_splink_pipeline,
    evaluate_splink_holdout,
)
train, holdout = split_labels(labels)
TRAIN_LABELS = ROOT / "data/processed/form_train_labels.csv"
HOLDOUT_LABELS = ROOT / "data/processed/form_holdout_labels.csv"
train.to_csv(TRAIN_LABELS, index=False)
holdout.to_csv(HOLDOUT_LABELS, index=False)
print(f"[4b] split: train={len(train)} (pos={int(train['clerical_match_score'].sum())}) "
      f"| holdout={len(holdout)} (pos={int(holdout['clerical_match_score'].sum())})")
pred = train_splink_pipeline(CLEAN, TRAIN_LABELS, PRED_OUT)
print(f"[5] splink predictions={len(pred)} (m trained on train fold only)")
holdout_metrics = evaluate_splink_holdout(pred, holdout, threshold=0.7)
print(f"[5b] holdout evaluation @0.7: TP={holdout_metrics['true_positive']} "
      f"FP={holdout_metrics['false_positive']} FN={holdout_metrics['false_negative']} "
      f"P={holdout_metrics['precision']:.3f} R={holdout_metrics['recall']:.3f} F1={holdout_metrics['f1']:.3f}")

# 5. Merge concord
from src.merge import run_merge_pipeline
res = run_merge_pipeline(CLEAN, PRED_OUT, MERGE_DIR, auto_threshold=0.95, review_threshold=0.15)
print(f"[6] merge summary: {res['summary']}")

# 6. Validate merged clusters vs true_entity_id
dec = pd.read_csv(MERGE_DIR / "merge_decisions.csv")
truth_pairs = set()
for idxs in ent_map.values():
    for i in range(len(idxs)):
        for j in range(i + 1, len(idxs)):
            truth_pairs.add((min(idxs[i], idxs[j]), max(idxs[i], idxs[j])))
auto_pairs = {(min(int(r.left_row_index), int(r.right_row_index)), max(int(r.left_row_index), int(r.right_row_index)))
              for _, r in dec[dec.merge_decision == "auto_merge"].iterrows()}
review_pairs = {(min(int(r.left_row_index), int(r.right_row_index)), max(int(r.left_row_index), int(r.right_row_index)))
                for _, r in dec[dec.merge_decision == "review_required"].iterrows()}
tp = len(auto_pairs & truth_pairs); fp = len(auto_pairs - truth_pairs)
r_tp = len(review_pairs & truth_pairs); r_fp = len(review_pairs - truth_pairs)
fn = len(truth_pairs - auto_pairs - review_pairs)
print(f"\n[7] VALIDATION vs true_entity_id (ground truth)")
print(f"    true dup pairs: {len(truth_pairs)}")
print(f"    auto_merge: TP={tp} FP={fp}")
print(f"    review_queue: TP={r_tp} FP={r_fp}  (human review can recover {r_tp} TP)")
print(f"    missed entirely (not in auto nor review): FN={fn}")
print(f"    review queue size: {len(review_pairs)} pairs -> {MERGE_DIR / 'review_queue.csv'}")

# 8. Review queue rows with evidence
rq = pd.read_csv(MERGE_DIR / "review_queue.csv")
print(f"\n    review_queue columns: {list(rq.columns)}")
print(f"    agreement_count distribution: {rq['agreement_count'].value_counts().sort_index().to_dict()}")

# 9. merged_records snapshot
merged = pd.read_csv(MERGE_DIR / "merged_records.csv")
multi = merged[merged["member_count"] > 1]
print(f"\n[8] merged_records: {len(merged)} | multi-member entities: {len(multi)}")
print(multi[["entity_id", "member_count", "email"]].head(10).to_string(index=False))