# Test-Duplikasi

Eksperimen sistem deduplikasi dan entity resolution yang menggabungkan pendekatan manual/deterministic matching, fuzzy matching, blocking, probabilistic record linkage (Splink), serta workflow review manusia — sampai keputusan merge dengan skor concord.

Project ini berfokus pada **entity resolution**: mengidentifikasi record yang merepresentasikan entity/customer yang sama sebelum digabung — bukan sekadar menghapus baris identik.

---

## 🎯 Tujuan Project

- Mendeteksi record identik maupun yang punya variasi penulisan (typo, casing, abbreviation, name-order, email/phone format).
- Membedakan exact duplicate dan potential duplicate.
- Mengurangi perbandingan N(N-1)/2 menggunakan blocking.
- Menggabungkan deterministic matching (baseline transparan) dengan probabilistic record linkage (Splink).
- Menyediakan proses review manusia sebelum merge.
- Evaluasi tanpa data leakage (train/holdout split).
- Mendukung input data baru secara terus-menerus via UI → model belajar dari label baru.

---

## 🧩 Arsitektur Pipeline

```text
Form / CSV (Google-Form atau first_name,...)
   │
   ▼
Import & Standardize  (src/standardization.py, scripts/import_form_csv.py)
   │
   ▼
Blocking / Candidate Generation   ← score/split
   │                (src/blocking.py)
   ├──────────────────────┐
   ▼                      ▼
Baseline Deterministic   Splink (probabilistic)
 src/decision.py         src/splink_pipeline.py
   │                      │
   └─────────┬────────────┘
            ▼
    Concord Score (src/merge.py)
     0.30·baseline + 0.40·splink + 0.30·identity
      ≥0.95 → auto_merge │ 0.15–0.95 → review │ <0.15 → not_match
            │
            ▼
    Review UI (app/review_app.py) — 4 tab
            │
            ▼
    Retrain Splink + tune threshold (holdout) → merge ulang
```

---

## 🛠️ Teknologi

- Python 3.11+
- Pandas / NumPy
- Splink (probabilistic record linkage) — optional
- Streamlit (review UI) — optional
- Pytest
- Jupyter Notebook

---

## 📁 Struktur

```text
src/                       implementasi reusable pipeline
  pipeline.py              baseline pipeline (standardize → block → compare → decide)
  standardization.py       normalisasi identity fields
  blocking.py              candidate generation
  comparison.py            agreement vectors
  decision.py              match_decision (candidate/high-conf)
  splink_pipeline.py       Splink adapter (+ split_labels, holdout eval)
  merge.py                 concord score + auto/review/not_match
scripts/                   eksperimen & tool
  import_form_csv.py       header Google-Form → kolom pipeline
  fake_data_builder.py     dataset sintetis P1–P7 + decoy
  splink_learning_test.py  bukti Splink belajar dari label
  complex_pattern_test.py  tes pola duplikat bertingkat
  complex_hard_test.py     tes P1–P7 + merge concord
  form_merge_test.py       alur form → import → merge → validasi
app/review_app.py          Streamlit 4-tab (Input/Review/Hasil/Retrain)
docs/                      tutorial, learning findings, policy, migration
tests/                     unit + integration
```

---

## 🚀 Instalasi

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
# opsional
pip install -e ".[splink]"      # Splink pipeline
pip install -e ".[review]"      # Streamlit UI
```

---

## ▶️ Menggunakan

### 1. Baseline deterministik (CLI)

```bash
python -m src.cli --input data/raw/crm_50000_customers_dirty_v3.csv --output data/processed/candidate_decisions.csv
```

### 2. Splink (train → predict → cluster → evaluate)

```bash
python -m src.splink_cli --input data/raw/crm_50000_customers_dirty_v3.csv \
                         --labels data/processed/splink_reviewed_labels.csv \
                         --output-dir data/processed/splink_demo
```

### 3. Merge concord (auto-merge / review / not-match)

```bash
python -m src.merge --input <customers.csv> --predictions <splink_predictions.csv> \
                    --output-dir <dir> --auto-threshold 0.95 --review-threshold 0.15
```

### 4. Review UI (4 tab: Input Baru → Review → Hasil → Retrain)

```bash
review_ui.bat          # atau: streamlit run app\review_app.py
```

Tab 1 menerima upload CSV (Google-Form atau format `first_name,last_name,...`), menjalankan pipeline penuh di dalam UI (10–500 baris), menghasilkan `review_queue.csv`. Tab 2 untuk labeling manusia. Tab 4 me-retrain Splink dari label baru dan mencari threshold terbaik di holdout.

---

## 🧪 Anti-Leakage (penting)

Evaluasi Splink **selalu memakai holdout fold**, tidak pernah pair yang dipakai training:

```python
from src.splink_pipeline import split_labels, evaluate_splink_holdout, train_splink_pipeline

train, holdout = split_labels(labels)                 # stratified, tidak overlap
predictions = train_splink_pipeline(input, train)     # m/u hanya dari train
metrics = evaluate_splink_holdout(predictions, holdout, threshold=0.7)
```

---

## 📊 Hasil Ringkas (fabricated, ground truth diketahui)

| Metode | Set | TP | FP | Precision | Recall |
|---|---|---|---|---|---|
| Baseline decisioning | 500 kompleks (70 true + 30 decoy) | 70 | 36 | 0.66 | 1.00 |
| Auto-merge concord (0.95) | P1–P7 (13 true + 30 decoy) | 5 | 0 | 1.00 | 0.38 |
| Review band (0.15–0.95) | P1–P7 | 8 TP + 33 FP diserahkan ke manusia | — | — | +0.62 |
| Merge concord | form/test 300 (40 true) | 40 | 0 | 1.00 | 1.00 |

Detail: `docs/TESTING_TUTORIAL.md`, `docs/SP_LINK_LEARNING_FINDINGS.md`.

---

## 🧪 Testing

```bash
python -m pytest tests/ -q
```

---

## 📄 Dokumentasi

- `docs/TESTING_TUTORIAL.md` — tutorial cara test, alur, anti-leakage
- `docs/SP_LINK_LEARNING_FINDINGS.md` — apakah Splink belajar dari label
- `docs/matching_policy.md` — policy baseline
- `docs/splink_migration.md` — migrasi baseline → Splink