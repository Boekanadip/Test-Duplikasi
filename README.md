# Customer 360 Entity Resolution Lab

> Research laboratory untuk mempelajari deduplication dan entity resolution pada data customer.

Project ini membangun baseline transparan dari eksperimen notebook menuju pipeline Python yang dapat diuji. Pipeline menghasilkan kandidat untuk review dan **tidak melakukan automatic merge**.

## Fokus Project

Laboratory workflow:

```text
data understanding -> data quality -> duplicate patterns -> standardization
-> deterministic matching -> fuzzy matching -> blocking
-> probabilistic readiness -> evaluation -> error analysis
-> benchmark -> final comparison -> optional Splink migration
```

Pertanyaan utamanya: kapan dua record customer dapat dianggap merepresentasikan entity yang sama meskipun nama, email, telepon, alamat, atau DOB memiliki variasi?

## Baseline Python

Implementasi di `src/` menggunakan pandas dan memiliki tahapan berikut:

- **Standardization**: Unicode NFKC, casefold, normalisasi whitespace, phone digits-only, dan parsing DOB.
- **Blocking**: exact email, exact phone, name+DOB, email+phone, phone prefix, DOB, surname prefix+DOB, dan city+DOB.
- **Comparison**: agreement indicators untuk email, phone, name, address, city, dan DOB.
- **Decision policy**: `agreement_count >= 4` menjadi `high_confidence_candidate`, `>= 2` menjadi `candidate`, dan sisanya `not_match`.
- **Review boundary**: kandidat membutuhkan review; tidak ada status `merged`.

Email-domain-only blocking tidak digunakan pada baseline karena menghasilkan candidate explosion. Detail aturan ada di [docs/matching_policy.md](docs/matching_policy.md).

## Repository Map

```text
docs/           Data contract, matching policy, dan panduan migrasi Splink
notebook/       Eksperimen 01-12 tanpa stored output atau PII pada commit publik
src/            Baseline pipeline, CLI, konfigurasi, logging, dan adapter Splink
tests/          Unit/integration tests dengan synthetic fixtures
data/raw/       Local-only; dataset asli tidak di-commit
data/processed/ Local-only; artifact eksperimen tidak di-commit
```

## Quick Start

Project membutuhkan Python 3.11 atau lebih baru.

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

Input CSV minimal harus memiliki kolom berikut:

```text
first_name,last_name,email,phone_number,dob,address,city
```

Jalankan baseline dari root repository:

```powershell
python -m src.cli `
  --input data/raw/customers.csv `
  --output data/processed/candidate_decisions.csv
```

Atau gunakan Python API:

```python
from src.pipeline import run_candidate_pipeline

decisions = run_candidate_pipeline(
    "data/raw/customers.csv",
    "data/processed/candidate_decisions.csv",
)
```

## Optional: Splink

Splink digunakan sebagai jalur probabilistic record linkage yang dapat dibandingkan dengan baseline:

```powershell
python -m pip install -e ".[splink]"
python -m src.splink_pipeline `
  --input data/raw/customers.csv `
  --output data/processed/splink_predictions.csv
```

Panduan migrasi bertahap tersedia di [docs/splink_migration.md](docs/splink_migration.md). Prediction Splink tetap harus divalidasi menggunakan reviewed labels sebelum dipertimbangkan untuk workflow merge.

## Data Governance

- `data/raw/` bersifat read-only dan tidak boleh masuk repository publik.
- `data/processed/` berisi artifact lokal dan juga di-ignore oleh Git.
- Notebook publik tidak menyimpan execution output atau customer rows.
- `customer_id` bukan ground truth otomatis.
- Precision, recall, dan F1 hanya valid terhadap reviewed labels.
- Candidate score bukan keputusan merge.
- Threshold bisnis membutuhkan validasi lebih besar, stratified, dan persetujuan stakeholder.

## Status dan Batasan

Status project: **research laboratory / baseline engineering**.

Belum termasuk automatic merge, entity survivorship, persistence production, monitoring drift, threshold approval bisnis, atau privacy review deployment. Tujuan utamanya adalah menghasilkan baseline yang dapat dijelaskan dan menjadi dasar perbandingan metode.

## Public Repository Checklist

- raw dan processed customer data tidak ter-stage;
- notebook sudah memakai relative path;
- notebook tidak memiliki stored output atau PII;
- `.env`, credential, `.venv`, cache, dan generated package metadata tidak ikut commit;
- hanya synthetic fixtures yang digunakan untuk test publik.
