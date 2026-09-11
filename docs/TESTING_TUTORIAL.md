# Tutorial Cara Test Pipeline

## 1. Unit / Komponen Test

```powershell
python -m pytest tests/ -v
```

Tiap file mengecek satu komponen secara terisolasi:

| File | Yang diuji |
|---|---|
| `test_standardization.py` | email/phone/name normalization |
| `test_blocking.py` | blocking key generation |
| `test_comparison.py` | agreement vector per pair |
| `test_decision.py` | match_decision labeling |
| `test_integration.py` | seluruh pipeline + Splink di fixture kecil |

---

## 2. Sanity-check Fixture

File `tests/fixtures/customers_sample.csv` berisi 5 baris:

| Baris | Siapa | Catatan |
|---|---|---|
| 0 | Alice Smith | email normal |
| 1 | ALICE Smith | email kapital, phone pakai kurung — **harus match baris 0** |
| 2 | Bob Jones | email `shared@example.com` |
| 3 | Carol White | email sama `shared@example.com` — tapi nama beda jauh → **bukan dup** |
| 4 | Dave Brown | standalone |

Jalankan:
```powershell
python -m src.cli --input tests/fixtures/customers_sample.csv
```

Yang muncul:
- Baris 0 ↔ 1: `high_confidence_candidate` (email + name + dob + city sama)
- Baris 2 ↔ 3: `not_match` (hanya email sama, nama/dob/city beda → agreement_count rendah)

Ini yang diharapkan: **email sama tidak otomatis jadi dup**, kalau field lain beda.

---

## 3. Baseline Deterministik (Data Besar)

```powershell
python -m src.cli --input data/raw/crm_50000_customers_dirty_v3.csv --output data/processed/candidate_decisions.csv
```

Output `candidate_decisions.csv` kolom penting:

| Kolom | Arti |
|---|---|
| `left_row_index` / `right_row_index` | pasangan record |
| `agreement_count` | berapa field identik (0-6) |
| `match_decision` | `not_match` / `candidate` / `high_confidence_candidate` |
| `review_required` | `True` kalau `candidate` atau `high_confidence_candidate` |

**`review_required = True`** = pasangan ini layak direview manusia.

---

## 4. Splink (Train + Predict + Cluster)

Persiapan:
```powershell
python -m pip install -e ".[splink]"
```

Jalankan:
```powershell
python -m src.splink_cli --input data/raw/crm_50000_customers_dirty_v3.csv --labels data/processed/splink_reviewed_labels.csv --output-dir data/processed/splink_demo
```

Output di `data/processed/splink_demo/`:

| File | Isi |
|---|---|
| `splink_predictions.csv` | semua pasangan + `match_probability` |
| `splink_clusters.csv` | tiap record → `cluster_id` (entity group) |
| `splink_evaluation.csv` | precision/recall/F1 per threshold |
| `splink_summary.json` | best threshold, jumlah cluster, best F1 |

`match_probability` tinggi = Splink yakin dua record = entity sama.
`cluster_id` sama = record itu masuk entity yang sama → ini output akhir dedup.

---

## 5. Tes Pola Duplikat Kompleks

```powershell
python scripts/complex_pattern_test.py
```

Menghasilkan `data/processed/_complex_500_test.csv` dengan:

| Tier | Jumlah pair | Pola |
|---|---|---|
| T1 (easy) | 20 | typo / casing / spasi |
| T2 (moderate) | 20 | nama dibalik, abbreviation (Mike/Michael) |
| T3 (hard) | 30 | email domain swap, phone +62/0, DOB dd/mm vs mm/dd |
| T4 (decoy) | 30 row | share email/phone tapi beda orang → harus **tidak** match |

Pipeline otomatis jalankan baseline + Splink, laporkan recall & false positive per tier.

---

## 6. Import Data dari Form

Google Form export biasanya header-nya "Timestamp - Nama Depan - Email ..." (pakai dash).

```powershell
python scripts/import_form_csv.py --input responses.csv --output data/processed/form_data.csv
```

Script mengubah header ke format: `first_name`, `last_name`, `email`, `phone_number`, `dob`, `address`, `city`.

Setelah itu, jalankan baseline:
```powershell
python -m src.cli --input data/processed/form_data.csv
```

Atau langsung ke Splink:
```powershell
python -m src.splink_cli --input data/processed/form_data.csv --output-dir data/processed/form_eval
```

---

## 7. Membaca Hasil

**Kalau semua `high_confidence_candidate`:**
→ Record ini benar-benar mirip. Tapi cek dulu field yang sama: kalau cuma `city + dob` → bisa collisi keluarga, bukan dup sebenarnya.

**Kalau `candidate` (bukan high):**
→ Perlu review. Agreement cukup tapi ada ketidakpastian.

**Kalau `match_probability` Splink tinggi tapi baseline `not_match`:**
→ Splink menangkap fuzzy pattern yang deterministik tidak lihat. Perlu review.

**Kalau `match_probability` rendah tapi baseline `high_confidence_candidate`:**
→ Baseline lebih optimistis. Review untuk validasi.

**False positive terbesar** selalu dari field *shared* antar orang: email perusahaan, nomor telepon keluarga, kota yang sama. Identity guard (perlu nama + kota/dob juga sama) mengurangi ini.

---

## 7a. Evaluation Rule — Holdout Only, Never Training Pairs

**Aturan tetap: evaluation selalu pakai holdout fold, tidak pernah pair yang dipakai training Splink.**

Alur:

```python
from src.splink_pipeline import split_labels, evaluate_splink_holdout

train, holdout = split_labels(labels)          # stratified, tidak overlap
predictions = train_splink_pipeline(input, train)  # m/u hanya dari train fold
metrics = evaluate_splink_holdout(predictions, holdout, threshold=0.7)  # metrik hanya di holdout
```

- Pair di train fold → hanya untuk `estimate_m_from_pairwise_labels`, tidak dihitung metrik.
- Pair di holdout fold → hanya untuk evaluasi, tidak pernah dilihat model saat training.
- Berlaku di `scripts/complex_hard_test.py` dan `scripts/form_merge_test.py`.

---

## 7b. Auto-Merge Concord (Phase 3)

Concord menggunakan skor berbobot (bukan gate biner):

```powershell
python -m src.merge --input <customers.csv> --predictions <splink_predictions.csv> --output-dir <merge_dir> --auto-threshold 0.95 --review-threshold 0.15
```

| `merge_decision` | Kondisi |
|---|---|
| `auto_merge` | concord_score ≥ 0.95 (identity 3/3 + high prob + high baseline) |
| `review_required` | 0.15 ≤ concord_score < 0.95 (ambiguus — band ini menangkap decoy & P2-P6) |
| `not_match` | concord_score < 0.15 (bukti sangat lemah) |

Concord weights: baseline 0.30 + splink 0.40 + identity 0.30.

> **Issue #3 fix:** guard biner lama (hanya id_agree ≥ N) diganti skor kontinu. Duplikat dengan probability Splink tinggi namun identity lemah (typo, email-var, phone-fmt) masuk **review band** → manusia putuskan, bukan auto-reject atau auto-merge.

Output: `merge_decisions.csv`, `merged_records.csv`, `entity_members.csv`, `review_queue.csv`, `merge_summary.json`.

---

## 7c. Review Queue UI (Streamlit)

```powershell
review_ui.bat                                         # queue default complex_hard + 500 customers
review_ui.bat data\processed\form_merge\review_queue.csv data\processed\form_clean.csv
```

Fitur: tampil pasangan kiri/kanan dengan highlight field agree (✅) vs beda (⚠️), tombol **Match / Not match / Skip**, label tersimpan ke SQLite (`data/processed/review_labels.db`), tombol Export menghasilkan `record_id_l,record_id_r,clerical_match_score` — format yang langsung dipakai `train_splink_pipeline`.

Loop: `review_queue.csv` → UI label → export → `train_splink_pipeline` retrain → threshold update → `src.merge` ulang.

---

## 8. Alur Setelah Orang Input

```
1. Reviewer buka manual_review_queue.csv atau review.csv
2. Beri label: 1 = match, 0 = not match, kolom review_label
3. Label baru → feed ke Splink training (retrain m/u)
4. Splink predict ulang → threshold mungkin bergeser
5. Evaluasi ulang precision/recall dengan label baru
6. Kalau sudah cukup stabil → keputusan final: merge / not merge / skip
```

Saat ini: semua masih to-review. Belum ada auto-merge by design (lihat `src/decision.py` — tidak ada kode merge, hanya labeling).

---

## 9. Hasil Uji 500 Kompleks (sudah dijalankan)

`python scripts/complex_pattern_test.py` pada 500 record (400 distinct + 70 true pair + 30 decoy):

| Metode | TP | FP | Precision | Recall |
|---|---|---|---|---|
| Baseline decisioning | 70 | 36 | 0.66 | 1.00 |
| Splink (train 80 label, m-value default) | 70 | 36 | 0.66 | 1.00 |
| **Auto-merge guard=3** (baseline+Splink concord) | **41** | **0** | **1.00** | 0.59 |
| Auto-merge guard=2 | 69 | 31 | 0.69 | 0.99 |

**Temuan:**
- Baseline recall = 1.0 di semua tier (bahkan T3 hard) — blocking + comparison menangkap semua.
- 36 FP seluruhnya dari decoy berbagi phone/email, nama+dob+city sama → family/patungan.
- Guard=3 (email+phone+name semua agree) → auto-merge 100% bersih, tapi recall 0.59.
- Band ambigu (id_agree=2) → 65 pasangan di `review_queue.csv` untuk manusia — sesuai desain concord.
- Splink tidak diskriminatif di label 80: semua prob = 1.0 — butuh label lebih banyak.

Artifact: `data/processed/_complex_eval_summary.json`, `data/processed/merge_demo_g3/`.

### Form Test (300 data, 40 true pairs)

```powershell
python scripts/form_merge_test.py
```

Merangkum alur lengkap: form export → import → baseline → Splink → merge → validasi.

Hasil: **40 TP, 0 FP, 0 FN**:
- auto_merge menangkap semua 40 duplikat benar, tanpa false positive
- review queue 1 pair (agreement=2, non-dup sharing field lemah)
- merged_records: 260 entity (40 multi-member)

Artifact: `data/processed/form_merge/`
(merge_decisions.csv, merged_records.csv, entity_members.csv, review_queue.csv, merge_summary.json)

---

---

## 10. Fabricated Data & Learning Test

Dataset buatan dengan ground truth diketahui — membuktikan bahwa Splink
memang belajar dari label, bukan sekadar mengikuti baseline.

### Generate

```powershell
python scripts/fake_data_builder.py  # -> data/processed/fake_500.csv (422 rows, 12 dup pairs)
```

### Splink Training vs Baseline Follow

```powershell
python scripts/splink_learning_test.py --threshold 0.7
```

Output di `data/processed/splink_learning/`:

| File | Isi |
|---|---|
| `pred_A_no_labels.csv` | tanpa label: 12 pair, blok-mirroring saja |
| `pred_B_with_labels.csv` | dengan label (80): 74 pair @0.05, ranking probabilitas diskriminatif |
| `sweep_A.csv`, `sweep_B.csv` | threshold sweep dua branch |

**Hasil:**
- Tanpa label → Splink = baseline (12 pair, flat ranking)
- Dengan label (40 pos + 40 neg termasuk decoy) → Splink eksplor 74 pair, threshold 0.7 → 12 TP, 0 FP (F1=1.0)
- Label tidak hanya "meningkatkan" — diperlukan agar Splink berfungsi di luar blocking-checker.

Baca detail di `docs/SP_LINK_LEARNING_FINDINGS.md`.

---

## 11. Konsep: Block, Skor, Ground Truth, Tuning, Threshold & Keputusan

### Block (Blocking)

N(N-1)/2 = 90,000 kandidat untuk 422 record — semua perbandingan naif.
Blocking key (email tepat, phone tepat, nama+dob, kota+dob) hanya membandingkan
record dengan key yang sama → `blocking_candidates << N(N-1)/2`.

**Blocking recall** = seberapa banyak duplikat benar selamat ke candidate set.
Jika duplikat benar punya key block berbeda, hilang permanen (recall loss).

### Skor Kemiripan (match_probability)

Per pasangan kandidat, Splink membandingkan 6 field. Setiap field dapat skor
agreement (0/1 atau level Levenshtein). Model menggabungkan via:

  P(match) ≈ prior × ∏(m_i / u_i)

di mana m_i = P(field sama | orang sama), u_i = P(field sama | orang beda).
Label melatih m via EM. Semakin beragam label → m lebih akurat → ranking lebih baik.

### Ground Truth

`true_entity_id` — siapa pemilik record sebenarnya. Pada data sintetis diketahui; produksi TIDAK diketahui. Buat file label dari pasangan yang direview (record_a, record_b, label 0/1). Tanpa ground truth TIDAK bisa hitung precision/recall — hanya inspeksi cluster.

### Tuning

Grid search threshold (mis. 0.05, 0.1, …, 0.95) pada review set.
Per threshold: predicted = (match_prob >= threshold), F1 = 2·P·R/(P+R). Pilih F1 tertinggi.
`concord_score` menggantikan guard biner: baris dengan identity lemah tapi Splink tinggi masuk **review band** (`src/merge.py` `auto_threshold`/`review_threshold`).

### Threshold & Keputusan

- Threshold rendah → recall tinggi (sedikit terlewat), queue review lebih besar.
- Threshold tinggi → precision tinggi (sedikit salah gabung), ada duplikat terlewat.

**Aturan keputusan produksi:**

  `concord_score` = 0.30·baseline + 0.40·splink + 0.30·identity
  ≥ auto_threshold (0.95) → auto_merge
  dalam band [review_threshold, auto_threshold) → review queue manusia
  < review_threshold (0.15) → not_match
