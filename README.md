# Test-Duplikasi

Eksperimen sistem deduplikasi dan entity resolution dengan menggabungkan pendekatan manual/deterministic matching, fuzzy matching, blocking, serta probabilistic record linkage menggunakan Splink.

Project ini dibuat untuk mempelajari bagaimana data yang memiliki kemungkinan merepresentasikan entity yang sama dapat diidentifikasi, dibandingkan, dievaluasi, dan diproses secara sistematis sebelum dilakukan penggabungan record.

---

## 🎯 Tujuan Project

Tujuan utama project ini adalah mempelajari dan membangun workflow deduplikasi data yang:

- mampu mendeteksi record yang identik maupun memiliki variasi penulisan;
- membedakan antara exact duplicate dan potential duplicate;
- mengurangi jumlah perbandingan record menggunakan blocking;
- menggabungkan deterministic matching dengan fuzzy matching;
- mengeksplorasi probabilistic record linkage menggunakan Splink;
- menyediakan proses review sebelum record benar-benar di-merge;
- dapat dievaluasi menggunakan data yang telah direview;
- dapat diuji dan dikembangkan menjadi pipeline yang lebih scalable.

Project ini lebih berfokus pada **entity resolution** daripada sekadar menghapus baris yang memiliki nilai sama.

---

# 🧩 Konsep Utama

Secara umum, workflow project dapat digambarkan sebagai berikut:

```text
Raw Data
   │
   ▼
Data Understanding
   │
   ▼
Data Quality Analysis
   │
   ▼
Standardization
   │
   ▼
Deterministic Matching
   │
   ▼
Fuzzy Matching
   │
   ▼
Blocking / Candidate Generation
   │
   ├───────────────┐
   ▼               ▼
Manual Review   Splink
   │               │
   └───────┬───────┘
           ▼
     Match Decision
           │
           ▼
      Evaluation
           │
           ▼
    Error Analysis
           │
           ▼
     Merge / Output


📁 Struktur Project

Struktur project secara umum:

Test-Duplikasi/
│
├── data/
│   └── ...
│
├── notebooks/
│   └── ...
│
├── src/
│   ├── standardization.py
│   ├── blocking.py
│   ├── comparison.py
│   ├── decision.py
│   ├── pipeline.py
│   └── splink_pipeline.py
│
├── tests/
│   ├── test_standardization.py
│   ├── test_blocking.py
│   ├── test_comparison.py
│   ├── test_decision.py
│   └── test_pipeline.py
│
├── requirements.txt
│
└── README.md

Struktur dapat berubah mengikuti perkembangan eksperimen.