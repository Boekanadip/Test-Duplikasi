## Customer 360 Entity Resolution

Laboratory project untuk mempelajari dan membangun proses Customer 360 Deduplication / Entity Resolution secara bertahap, mulai dari data understanding hingga evaluasi dan pemilihan pendekatan yang scalable.

Status: `workin Progress / Research Laboratory`

Project ini berfokus pada proses eksperimen Data Science, bukan langsung pada production deployment.

1. Project Overview

Dalam data customer, satu orang dapat muncul sebagai beberapa record karena adanya:

perbedaan format nama,

typo,

variasi email,

variasi nomor telepon,

perbedaan format alamat,

missing value,

data noise,

dan variasi representasi lainnya.

Masalahnya bukan hanya mencari baris yang identik, tetapi menentukan:

Apakah dua atau lebih record merepresentasikan customer/entity yang sama?

Proses tersebut dikenal sebagai Entity Resolution.

Project ini menggunakan pendekatan eksperimental untuk memahami masalah tersebut sebelum menentukan metode matching yang paling sesuai.

2. Objectives

Tujuan utama project:

Memahami karakteristik dataset customer.

Mengidentifikasi masalah data quality.

Menemukan pola duplicate/entity variation.

Menguji standardization.

Membuat deterministic matching sebagai baseline.

Menguji fuzzy matching jika diperlukan.

Mengurangi computational cost melalui blocking/candidate generation.

Mengeksplorasi probabilistic entity resolution.

Melakukan evaluation dan error analysis.

Membandingkan accuracy, recall, precision, runtime, memory, dan scalability.

Menentukan pendekatan yang paling masuk akal untuk skala data yang lebih besar.

3. Dataset

Dataset utama yang digunakan dalam laboratory ini:

crm_50000_customers_dirty_v3.csv

Dataset ditempatkan pada:

data/raw/

Raw dataset dipertahankan sebagai data original dan tidak boleh ditimpa oleh proses cleaning atau standardization.

Struktur dan karakteristik aktual dataset harus selalu diverifikasi melalui notebook, bukan diasumsikan dari nama file.

4. Project Structure

Struktur project direncanakan sebagai berikut:

customer-360-entity-resolution/
│
├── PRD.md
├── skill.md
├── README.md
│
├── data/
│   ├── raw/
│   │   └── crm_50000_customers_dirty_v3.csv
│   │
│   ├── interim/
│   │
│   └── processed/
│
├── notebooks/
│   ├── 01_data_understanding.ipynb
│   ├── 02_data_quality.ipynb
│   ├── 03_duplicate_pattern_analysis.ipynb
│   ├── 04_standardization.ipynb
│   ├── 05_deterministic_matching.ipynb
│   ├── 06_fuzzy_matching.ipynb
│   ├── 07_blocking.ipynb
│   ├── 08_probabilistic_entity_resolution.ipynb
│   ├── 09_evaluation.ipynb
│   ├── 10_error_analysis.ipynb
│   ├── 11_benchmark.ipynb
│   └── 12_final_comparison.ipynb
│
├── src/
│
├── reports/
│
└── experiment_logs/

Tidak semua folder atau notebook harus langsung tersedia. Struktur akan berkembang berdasarkan hasil eksperimen.

5. Research Workflow

Workflow utama:

Business/Data Problem
        ↓
Data Understanding
        ↓
Data Quality
        ↓
Duplicate Pattern Analysis
        ↓
Standardization
        ↓
Deterministic Matching
        ↓
Fuzzy Matching
        ↓
Blocking / Candidate Generation
        ↓
Probabilistic Entity Resolution
        ↓
Evaluation
        ↓
Error Analysis
        ↓
Benchmark
        ↓
Final Comparison
        ↓
Scalable Pipeline

Workflow bersifat adaptif.

Jika suatu eksperimen menunjukkan bahwa suatu metode tidak diperlukan, tahap tersebut dapat dihentikan.

6. Experiment Philosophy

Setiap eksperimen mengikuti:

Hypothesis
    ↓
Experiment
    ↓
Result
    ↓
Analysis
    ↓
Decision
    ↓
Next Experiment

Contoh:

Hypothesis:
Normalisasi email dapat menemukan duplicate yang tidak
terdeteksi oleh exact matching.

Experiment:
Lowercase + trim email kemudian lakukan exact matching.

Result:
Diisi berdasarkan hasil eksperimen aktual.

Analysis:
Evaluasi perubahan coverage dan potensi collision.

Decision:
Lanjut / modifikasi / hentikan.

Next Experiment:
Ditentukan berdasarkan hasil.

Tidak ada hasil yang boleh ditulis sebelum eksperimen benar-benar dilakukan.

7. Notebook Progress

01 — Data Understanding

Tujuan:

memahami struktur dataset,

melihat rows/columns,

memeriksa dtype,

missing value,

unique value,

sample data,

exact duplicate,

kandidat identity fields.

Status: In Progress / Initial Stage

02 — Data Quality

Tujuan:

mengukur missingness,

uniqueness,

string quality,

email quality,

phone quality,

name quality,

date quality,

cross-field consistency.

03 — Duplicate Pattern Analysis

Tujuan:

memahami pola duplicate,

mencari repeated identifiers,

menemukan variasi entity,

menentukan field yang potensial digunakan untuk matching.

04 — Standardization

Tujuan:

menguji normalisasi field,

mengukur dampak sebelum dan sesudah standardization,

menghindari over-normalization.

05 — Deterministic Matching

Tujuan:

membangun baseline,

menguji exact/normalized matching,

memahami coverage dan collision.

06 — Fuzzy Matching

Tujuan:

menangani variasi yang tidak dapat ditangani exact matching,

menguji similarity metrics dan threshold.

07 — Blocking

Tujuan:

mengurangi jumlah candidate pairs,

meningkatkan scalability,

mempertahankan candidate recall.

08 — Probabilistic Entity Resolution

Tujuan:

mengeksplorasi metode probabilistic/advanced jika dibutuhkan.

09 — Evaluation

Tujuan:

mengevaluasi kualitas matching dengan ground truth jika tersedia,

atau menggunakan validation strategy yang sesuai jika ground truth tidak tersedia.

10 — Error Analysis

Tujuan:

memahami false positives,

false negatives,

candidate-generation errors,

threshold errors,

data-quality errors.

11 — Benchmark

Tujuan:

Membandingkan metode berdasarkan:

precision,

recall,

F1,

coverage,

candidate pairs,

runtime,

memory,

complexity.

12 — Final Comparison

Tujuan:

Menentukan pendekatan terbaik berdasarkan evidence dan trade-off, bukan berdasarkan satu metric saja.

8. Matching Strategy

Strategi matching tidak ditentukan sejak awal.

Potential approaches:

Exact Matching

email
phone
customer_id

Normalized Exact Matching

normalized email
normalized phone
normalized name

Multi-field Deterministic Matching

email + phone
name + dob
name + address

Fuzzy Matching

Potential library:

RapidFuzz

Entity Resolution Libraries

Potential options:

Splink
Dedupe
recordlinkage

Library digunakan hanya apabila eksperimen sebelumnya menunjukkan bahwa library tersebut diperlukan.

9. Scalability Consideration

Naive pairwise comparison memiliki jumlah pasangan:

n(n - 1) / 2

Contoh:

1,000 records
≈ 500,000 pairs

100,000 records
≈ 5 billion pairs

1,000,000 records
≈ 500 billion pairs

Karena itu project juga mempelajari:

blocking,

candidate generation,

indexing,

computational complexity,

runtime,

memory usage.

Tujuan akhirnya bukan hanya mendapatkan matching yang akurat, tetapi juga memahami apakah pendekatan tersebut masuk akal ketika data bertambah besar.

10. Evaluation

Jika tersedia ground truth:

TP
FP
TN
FN

Metric:

Precision
Recall
F1-score

Selain metric kualitas, project juga memperhatikan:

Runtime
Memory
Candidate Pairs
Coverage
Complexity
Scalability

Jika ground truth tidak tersedia, project tidak akan mengklaim precision/recall/F1 sebagai hasil definitif tanpa dasar evaluasi yang valid.

11. Business Risk

Entity resolution memiliki dua jenis kesalahan utama.

False Positive

Dua customer berbeda dianggap sama.

Contoh risiko:

Customer A
+
Customer B
↓
Incorrectly merged

Ini dapat menghasilkan customer profile yang salah.

False Negative

Dua record customer yang sebenarnya sama tidak berhasil digabung.

Contoh:

Customer A — Record 1
Customer A — Record 2
        ↓
Tidak terdeteksi sebagai entity yang sama

Akibatnya customer profile menjadi terfragmentasi.

12. Research Principles

Project mengikuti prinsip:

Data First

Jangan membuat asumsi sebelum melihat data.

Baseline First

Mulai dari metode sederhana.

Experiment First

Uji metode sebelum mengambil keputusan.

Evidence First

Keputusan harus berdasarkan hasil.

Scalability Matters

Metode harus dipertimbangkan untuk skala yang lebih besar.

No Fabricated Results

Tidak ada angka yang dibuat-buat.

13. Agent

Project ini menggunakan AI Agent sebagai Data Science Research & Experimentation Partner.

Agent memiliki dua dokumen utama:

PRD.md
skill.md

PRD.md

Menjelaskan:

tujuan project,

scope,

workflow,

deliverables,

definition of done.

skill.md

Menjelaskan:

bagaimana agent harus berpikir,

bagaimana agent menjalankan eksperimen,

aturan analisis,

aturan evaluasi,

aturan coding,

aturan pengambilan keputusan.

Agent harus membaca kedua file tersebut sebelum memulai pekerjaan.

14. Current Status

Project masih berada pada tahap awal laboratory.

Fokus saat ini:

Data Understanding
        ↓
Data Quality
        ↓
Duplicate Pattern Analysis

Tahap matching belum boleh dianggap final sebelum data quality dan duplicate pattern dipahami.

15. Expected Final Output

Pada akhir project diharapkan tersedia:

Profil dataset.

Data quality report.

Duplicate pattern analysis.

Standardization strategy.

Deterministic matching baseline.

Fuzzy matching experiment jika diperlukan.

Blocking/candidate-generation experiment.

Probabilistic ER experiment jika relevan.

Evaluation.

Error analysis.

Benchmark.

Final comparison.

Rekomendasi pendekatan yang paling masuk akal.

Pipeline entity resolution yang dapat dikembangkan lebih lanjut.

16. Key Takeaway

Project ini tidak bertujuan mencari:

"Metode paling canggih."

Tetapi mencari:

"Metode yang paling tepat berdasarkan karakteristik data, kualitas matching, computational cost, scalability, dan business risk."

Mental model utama:

Understand
    ↓
Measure
    ↓
Experiment
    ↓
Analyze
    ↓
Compare
    ↓
Decide

17. Project Status

Status: Research / Laboratory — Work in Progress

Environment: VS Code + Jupyter Notebook

Language: Python

Primary Task: Customer 360 Deduplication / Entity Resolution

Current Focus: Data Understanding → Data Quality → Duplicate Pattern Analysis