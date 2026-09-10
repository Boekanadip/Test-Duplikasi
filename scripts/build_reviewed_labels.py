from pathlib import Path
import warnings
warnings.filterwarnings("ignore")
import pandas as pd

from src.io import load_customer_csv
from src.standardization import standardize_customers
from src.blocking import generate_candidate_pairs
from src.comparison import build_comparison_vectors

OUT = Path("data/processed")
SEED = 42
RANDOM_STATE = 42

RAW = Path("data/raw/crm_50000_customers_dirty_v3.csv")

# ---- Build comparison vectors fresh (source of truth) ----
comp = build_comparison_vectors(
    standardize_customers(load_customer_csv(RAW)),
    generate_candidate_pairs(standardize_customers(load_customer_csv(RAW))),
)
print("candidate pairs:", len(comp))
flags = ["email_agree", "phone_agree", "name_agree", "address_agree", "city_agree", "dob_agree"]
identity_cols = ["email_agree", "phone_agree", "name_agree"]
comp["agreement_pattern"] = comp[flags].astype(str).agg("".join, axis=1)
comp["record_id_l"] = comp["left_row_index"].astype("int64").astype("string")
comp["record_id_r"] = comp["right_row_index"].astype("int64").astype("string")

# ---- Existing reviewed labels (107) ----
reviewed = pd.read_csv(OUT / "splink_reviewed_labels.csv")
reviewed["pair_key"] = reviewed.apply(
    lambda r: (min(int(r.record_id_l), int(r.record_id_r)), max(int(r.record_id_l), int(r.record_id_r))), axis=1
)
reviewed_keys = set(reviewed["pair_key"])
print("existing reviewed:", len(reviewed))
reviewed["auto_label_source"] = "manual_review"

# ---- Near-miss negatives: agree==1, ONLY "dob" agrees, all identity fields differ ----
mask_dobonly = (comp["agreement_pattern"] == "000001") & (comp[identity_cols].sum(axis=1) == 0)
dobonly = comp[mask_dobonly].copy()
print("agree==1 dob-only pairs:", len(dobonly))
n_sample = min(300, len(dobonly))
if n_sample > 0:
    sample_neg = dobonly.sample(n=n_sample, random_state=RANDOM_STATE)
    neg_labels = pd.DataFrame({
        "record_id_l": sample_neg["record_id_l"],
        "record_id_r": sample_neg["record_id_r"],
        "clerical_match_score": 0,
        "auto_label_source": "auto_agree1_dobonly",
    })
else:
    neg_labels = pd.DataFrame(columns=["record_id_l", "record_id_r", "clerical_match_score", "auto_label_source"])

# ---- Exclude duplicates vs existing reviewed keys ----
neg_labels["pair_key"] = neg_labels.apply(
    lambda r: (min(int(r.record_id_l), int(r.record_id_r)), max(int(r.record_id_l), int(r.record_id_r))), axis=1
)
neg_labels = neg_labels[~neg_labels["pair_key"].isin(reviewed_keys)]
print("nearmiss negatives (non-overlap):", len(neg_labels))

# ---- Boundary review queue: agree==1 "phone-only" (010000) -> pending review ----
mask_phone = (comp["agreement_pattern"] == "010000")
phone = comp[mask_phone].copy()
print("agree==1 phone-only pairs (pending review):", len(phone))
review_phone = phone.sample(n=min(300, len(phone)), random_state=RANDOM_STATE).copy()
review_phone["review_status"] = "pending"
review_phone["review_label"] = pd.NA
boundary = review_phone[["record_id_l", "record_id_r", "supporting_blocking_strategies", "agreement_count", "review_status", "review_label"]].copy()

neg_labels.to_csv(OUT / "reviewed_label_nearmiss_negatives.csv", index=False)
boundary.to_csv(OUT / "review_queue_pending_boundary.csv", index=False)
print("saved nearmiss negatives:", len(neg_labels))
print("saved pending boundary queue:", len(boundary))
