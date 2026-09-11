# Materi Presentasi — Sistem Deteksi Duplikasi Customer (Entity Resolution)

Angka di bawah diambil dari hasil eksperimen yang **benar-benar dijalankan**,
bukan perkiraan. File pendukung di `data/processed/`.

---

## Slide 0 — Judul

**Deteksi Duplikasi Pelanggan Otomatis**
Pipeline Entity Resolution: Deterministic + Probabilistic + Review Manusia
MagangHub — Bulan 1

---

## Slide 1 — Masalah

> **Q:** Bagaimana tahu dua record pelanggan itu orang yang sama?

Contoh nyata:
| Record A | Record B |
|---|---|
| Budi Santoso | BUDI SANTOSO |
| budi@gmail.com | budi@googlemail.com |
| 0812-3456-7890 | +62 812-3456-7890 |
| Jl. Merdeka No 5, Jakarta | Jalan Merdeka No. 5, Jakarta |

Field sama, tapi penulisan beda → sistem harus belajar nickhr/format.

**Risiko:**
- Salah gabung (false positive) → profil dua orang jadi satu. **Bahaya.**
- Terlewat (false negative) → profil satu orang terpecah.

---

## Slide 2 — Solusi: 3 Lapis

```
Input (Form/CSV)
   ▼
1. Baseline Deterministik  — aturan eksplisit, transparan, bisa di-audit
   ▼
2. Splink (Probabilistik)  — probabilitas dua record = entity sama
   ▼
3. Concord Score           — gabung: 0.30·baseline + 0.40·splink + 0.30·identity
   ▼
   0.95+ → auto-merge  │  0.15–0.95 → review manusia  │  <0.15 → tolak
   ▼
4. Review UI (Streamlit)  — manusia beri label → Splink retrain → belajar terus
```

---

## Slide 3 — Kenapa Dua Metode Sekaligus?

| | Baseline Deterministik | Splink Probabilistik |
|---|---|---|
| Cara kerja | Hitung berapa field identik (agreement_count) | P(match) dari m/u probability per field |
| Kelebihan | Transparan, interpretable, tanpa training | Tangkap typo / format tanpa aturan keras |
| Kekurangan | Miss kalau banyak variasi | Butuh label untuk belajar |
| Tanpa label | ✅ jalan | ❌ hanya mirroring baseline (lihat hasil) |

**Temuan eksperimen:** tanpa label, Splink = baseline (12 pair). Dengan label,
Splink eksplor 74 pair & bisa ranking → membuktikan label dibutuhkan.

> Bukti: `docs/SP_LINK_LEARNING_FINDINGS.md`

---

## Slide 4 — Data Uji (Fabricated, ground truth = true_entity_id)

Data diciptakan sintetis dari 50k real + pola duplikat tersuntik, jadi **jawaban
benar diketahui** → bisa ukur precision/recall jujur.

| Tier | Pola | Jumlah |
|---|---|---|
| T1 easy | typo / casing / spasi | 20 pair |
| T2 moderate | nama dibalik, abbreviation (Mike↔Michael) | 20 pair |
| T3 hard | email domain swap, phone +62/0, DOB dd/mm vs mm/dd | 30 pair |
| T4 decoy | share email/phone tapi beda orang (jebakan FP) | 30 row |

---

## Slide 5 — Hasil 1: Baseline Recall 100% tapi FP dari decoy

**Dataset** `_complex_500_test.csv`: 500 row, 70 true pair + 30 decoy.

| Metode | TP | FP | Precision | Recall | F1 |
|---|---|---|---|---|---|
| Baseline decisioning | 70 | 36 | 0.66 | **1.00** | 0.80 |

**Baca:**
- Recall 1.00 — semua duplikat benar (bahkan T3 hard) ketangkap.
- FP 36 — seluruhnya decoy berbagi phone/email tapi beda orang.
- Kesimpulan: butuh lapisan tambahan (Splink + identity) untuk menekan FP.

---

## Slide 6 — Hasil 2: Concord auto-merge konservatif, sisanya review

**Dataset** `_complex_hard_500.csv`: 443 row, 13 true pair, 30 decoy.

| Keluaran | TP | FP | Catatan |
|---|---|---|---|
| auto_merge (concord ≥0.95) | 5 | 0 | identity 3/3 exact selalu benar |
| review band (0.15–0.95) | 8 | 33 | ambigu → manusia putuskan |
| not_match (<0.15) | 0 | — | tolak |

**Per-pattern:**
| Pattern | auto_merge |
|---|---|
| P1 exact / P7 dob-format | 100% |
| P2 typo / P3 abbrev / P4 order / P5 email / P6 phone | 0% → review |

**Baca:** auto-merge = precision 100%. Yang ragu tidak ditolak, tapi diserahkan
ke manusia (recoverable review, bukan loss).

---

## Slide 7 — Hasil 3: Form input end-to-end (300 data)

`data/raw/synthetic_300.csv` → import → baseline → Splink → merge → validasi.

| Metrik | Hasil |
|---|---|
| Candidate pairs | 65 |
| auto_merge | **40** |
| **TP / FP** | **40 / 0** (100%) |
| Review queue | 1 pair (agreement=2) |
| Missed (FN) | 0 |

**Form import** menangani: header Google-Form `Pertanyaan N - Nama Depan...`
+ `Timestamp` → kolom pipeline; padanan `googlemail→gmail`, `+62→0`.

---

## Slide 8 — Anti-Data-Leakage (kejujuran evaluasi)

Label training TIDAK pernah dipakai untuk evaluasi.

```python
train, holdout = split_labels(labels)      # stratified, tidak overlap
predictions = train_splink_pipeline(input, train)
metrics = evaluate_splink_holdout(predictions, holdout, threshold=0.7)
```

- Pair di train → hanya untuk estimasi m/u.
- Pair di holdout → hanya untuk metric.
- Hasil holdout contoh (P1–P7): **4/4 TP, 0 FP, F1 1.0** di seluruh threshold.

---

## Slide 9 — Review UI (Streamlit) — belajar terus

4 tab:
| Tab | Fungsi |
|---|---|
| 📥 Input Baru | upload CSV → pipeline penuh di UI |
| ✅ Review | Match / Not-match / Skip → SQLite per-session |
| 📊 Hasil | merged entities + summary |
| 🔁 Retrain | label → retrain Splink → best threshold → merge ulang |

**Loop pembelajaran:**
```
upload → pipeline → review → label bertambah → retrain → threshold baru → merge
                     ↑_____________________________________|
```

---

## Slide 10 — Ringkasan & Rekomendasi

**Done:**
- Pipeline 3-lapis (deterministic + Splink + concord) berjalan.
- Anti-leakage (holdout-only evaluation).
- UI 4-tab end-to-end + import Google-Form.
- Format comparison lebih fleksibel (Jaro-Winkler, +62/gmial normalization).

**Next step (rekomendasi):**
1. Label review yang lebih banyak (stratified) → Splink makin diskriminatif.
2. Uji dengan data form asli (bukan sintetis) volume 100–1000.
3. Threshold final disetujui bisnis sebelum dipakai untuk auto-merge produksi.
4. (opsional) dashboard monitoring drift label vs probability.

**Catatan penting:** hasil semua eksperimen di atas berbasis data syntetis —
belum menyatakan kinerja di produksi tanpa validasi set yang representatif.

---

## Rekomendasi Graf & Gambar untuk PPT

1. **Diagram alur 3-lapis** (Slide 2) — buat di PowerPoint: 3 kotak berpanah,
   warnai output: hijau auto-merge / kuning review / merah tolak.
2. **Grafik Precision-Recall by threshold** dari `data/processed/splink_learning/sweep_B.csv`.
   - sumbu X threshold 0.05→0.9, garis precision & recall.
   - cerita: threshold tinggi = precision naik, recall turun.
3. **Bar chart FP by tier** — baseline FP 36 = decoy (Slide 5): batang T1/T2/T3
   = 0 FP, batang decoy = 36. Menunjukkan kelemahan hanya pada shared-field.
4. **Screenshot Review UI** — jalankan `review_ui.bat`, screenshot tab Review
   menampilkan pasangan + tombol Match/Not-match.
5. **Tabel "per-pattern"** (Slide 6) — bisa langsung jadi tabel PPT.