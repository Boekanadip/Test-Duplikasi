from pathlib import Path
import pandas as pd

# ============================================================
# CONFIG
# ============================================================

INPUT_PATH = Path("data/processed/blocking_candidate_pairs.csv")
OUTPUT_PATH = Path("data/processed/review_queue.csv")

TARGET_SAMPLE = 1000
RANDOM_STATE = 42


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(INPUT_PATH)

print(f"Total candidate pairs : {len(df):,}")


# ============================================================
# BASIC VALIDATION
# ============================================================

required_columns = [
    "record_id_l",
    "record_id_r",
]

missing_columns = [
    col for col in required_columns
    if col not in df.columns
]

if missing_columns:
    raise ValueError(
        f"Kolom berikut tidak ditemukan: {missing_columns}"
    )


# ============================================================
# REMOVE SELF PAIRS
# ============================================================

df = df[
    df["record_id_l"] != df["record_id_r"]
].copy()


# ============================================================
# CANONICAL PAIR
# ============================================================
# Menghindari:
# (105, 891)
# dan
# (891, 105)
# dianggap sebagai dua pasangan berbeda.

df["pair_min"] = df[
    ["record_id_l", "record_id_r"]
].min(axis=1)

df["pair_max"] = df[
    ["record_id_l", "record_id_r"]
].max(axis=1)

df["pair_key"] = (
    df["pair_min"].astype(str)
    + "_"
    + df["pair_max"].astype(str)
)

df = df.drop_duplicates(
    subset="pair_key"
).copy()


# ============================================================
# CREATE STRATA
# ============================================================
# Script ini mengasumsikan ada kolom agreement_count.
#
# Kalau baseline lu punya score berbeda, bagian ini
# tinggal kita sesuaikan.

if "agreement_count" not in df.columns:
    raise ValueError(
        "Kolom 'agreement_count' tidak ditemukan. "
        "Sesuaikan bagian STRATIFICATION dengan output "
        "candidate pipeline lu."
    )


def assign_stratum(score):
    if score >= 5:
        return "very_high"

    elif score == 4:
        return "high"

    elif score == 3:
        return "medium"

    elif score == 2:
        return "low"

    else:
        return "very_low"


df["stratum"] = df["agreement_count"].apply(
    assign_stratum
)


# ============================================================
# CHECK STRATA
# ============================================================

print("\nDistribusi strata:")
print(
    df["stratum"]
    .value_counts()
    .sort_index()
)


# ============================================================
# TARGET PROPORSI
# ============================================================
# Jangan mengambil semua sampel hanya dari high score.
#
# Kita sengaja mempertahankan pasangan dari berbagai
# tingkat kemiripan.

stratum_target = {
    "very_high": 150,
    "high": 200,
    "medium": 300,
    "low": 200,
    "very_low": 150,
}


# ============================================================
# STRATIFIED SAMPLING
# ============================================================

sampled_parts = []

for stratum, target in stratum_target.items():

    group = df[
        df["stratum"] == stratum
    ]

    available = len(group)

    n_sample = min(
        target,
        available
    )

    if n_sample == 0:
        print(
            f"[WARNING] Stratum '{stratum}' "
            f"tidak memiliki data."
        )
        continue

    sampled = group.sample(
        n=n_sample,
        random_state=RANDOM_STATE
    )

    sampled_parts.append(sampled)

    print(
        f"{stratum:12s} | "
        f"available={available:6,} | "
        f"sampled={n_sample:4,}"
    )


# ============================================================
# COMBINE
# ============================================================

if not sampled_parts:
    raise ValueError(
        "Tidak ada data yang berhasil di-sampling."
    )

review_queue = pd.concat(
    sampled_parts,
    ignore_index=True
)


# ============================================================
# SHUFFLE
# ============================================================

review_queue = review_queue.sample(
    frac=1,
    random_state=RANDOM_STATE
).reset_index(drop=True)


# ============================================================
# ADD MANUAL REVIEW COLUMNS
# ============================================================

review_queue["reviewer_label"] = ""
review_queue["review_notes"] = ""


# ============================================================
# REMOVE INTERNAL COLUMNS
# ============================================================

review_queue = review_queue.drop(
    columns=[
        "pair_min",
        "pair_max",
        "pair_key",
    ],
    errors="ignore"
)


# ============================================================
# SAVE
# ============================================================

OUTPUT_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)

review_queue.to_csv(
    OUTPUT_PATH,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print("\n========================================")
print("STRATIFIED SAMPLING SELESAI")
print("========================================")

print(
    f"Candidate pairs : {len(df):,}"
)

print(
    f"Review samples  : {len(review_queue):,}"
)

print(
    f"Output          : {OUTPUT_PATH}"
)

print("\nDistribusi sample:")
print(
    review_queue["stratum"]
    .value_counts()
    .sort_index()
)