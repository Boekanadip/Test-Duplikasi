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
```
---
 # 🛠️ Teknologi

Project ini menggunakan beberapa teknologi dan library Python untuk mendukung proses eksperimen:
- Python
- Pandas
- NumPy
- Splink
- RapidFuzz / fuzzy matching
- Pytest
- Jupyter Notebook

---
# 🧪 Testing

Project menyediakan pengujian terhadap komponen-komponen penting dari pipeline.
Testing digunakan untuk memastikan bahwa perubahan pada satu komponen tidak menyebabkan proses lain menghasilkan output yang tidak sesuai.
Contoh komponen yang dapat diuji:
```BASH
    standardization
    blocking
    comparison
    decision
    pipeline
```
Dengan adanya testing, workflow deduplikasi dapat dikembangkan secara lebih aman dan reproducible.
---
# 🚀 Instalasi

Clone repository:
```BASH
git clone https://github.com/Boekanadip/Test-Duplikasi.git
```
Masuk ke directory:
```BASH
cd Test-Duplikasi
```
Buat virtual environment:
```BASH
python -m venv .venv
```
Aktifkan environment pada Windows:
```BASH
.venv\Scripts\activate
```
Install dependencies:
```BASH
pip install -r requirements.txt
```
---
# ▶️ Menjalankan Eksperimen

Eksperimen dapat dijalankan melalui notebook yang tersedia pada directory:
```BASH
notebooks/
```
Sedangkan implementasi reusable dari pipeline berada pada:
```BASH
src/
```
Pendekatan ini memisahkan eksplorasi eksperimen dengan kode yang digunakan kembali oleh pipeline.
