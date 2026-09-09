# Splink Migration Guide

Dokumen ini menjelaskan migrasi bertahap dari baseline custom ke Splink. Migrasi bersifat opsional dan tidak menghapus pipeline di `src/pipeline.py`.

## 1. Install Optional Dependency

```powershell
python -m pip install -e ".[splink]"
```

Jika hanya ingin menjalankan baseline, Splink tidak perlu di-install.

## 2. Mapping Komponen

| Baseline | Splink |
| --- | --- |
| `standardize_customers` | Data preparation sebelum `Linker` |
| `build_blocking_keys` | `blocking_rules_to_generate_predictions` |
| `build_comparison_vectors` | `comparisons` dan comparison levels |
| `agreement_count` | match probability / match weight |
| `apply_match_policy` | threshold prediction + manual review |
| CSV candidate artifact | Splink prediction table |

Adapter awal tersedia di `src/splink_pipeline.py`.

## 3. Jalankan Adapter

```powershell
python -m src.splink_pipeline `
  --input data/raw/crm_50000_customers_dirty_v3.csv `
  --output data/processed/splink_predictions.csv
```

Adapter menggunakan `dedupe_only` dan membuat `record_id` internal. `customer_id` tidak dipakai sebagai label atau blocking key.

## 4. Bandingkan Candidate Generation

Bandingkan setidaknya:

- jumlah input records;
- jumlah generated pairs;
- jumlah unique pairs;
- blocking coverage;
- runtime dan memory;
- reviewed-pair recall.

Perbedaan jumlah pair tidak otomatis berarti salah. Splink dapat menghasilkan pair dan score berbeda karena comparison levels serta blocking rules berbeda.

## 5. Label dan Training

Gunakan `tests/fixtures/reviewed_pair_labels.csv` sebagai contoh format pair label non-PII. File `validation_pairs.csv` berisi ringkasan evidence dan metrik fixture, bukan input training Splink. Jangan menganggap fixture sintetis sebagai ground truth dataset produksi.

Untuk eksperimen nyata, siapkan reviewed labels yang terstratifikasi berdasarkan:

- score band;
- blocking strategy;
- missingness pattern;
- suspected duplicate dan non-duplicate;
- variasi sumber data.

Setelah label cukup, jalankan estimasi parameter Splink dan evaluasi ulang threshold. Jangan langsung mengubah prediction menjadi merge.

## 6. Training dari Reviewed Labels

Training pair labels harus menggunakan record IDs internal Splink, bukan `customer_id`:

```csv
record_id_l,record_id_r,clerical_match_score
0,1,1
2,3,0
```

Jalankan training dan prediction:

```powershell
python -c "from src.splink_pipeline import train_splink_pipeline; train_splink_pipeline('data/raw/customers.csv', 'data/processed/reviewed_pair_labels.csv', 'data/processed/splink_trained_predictions.csv')"
```

`clerical_match_score=1` berarti reviewer menilai pasangan sebagai entity yang sama, sedangkan `0` berarti berbeda. Label harus berasal dari manual review yang terstratifikasi dan tidak boleh dibuat dari `customer_id` tanpa validasi independen.

Evaluasi threshold dilakukan hanya pada reviewed pairs:

```python
from src.splink_pipeline import evaluate_splink_predictions

metrics = evaluate_splink_predictions(
  predictions,
  "data/processed/reviewed_pair_labels.csv",
  threshold=0.5,
)
```

Threshold `0.5` di atas hanya contoh API. Threshold final harus dipilih dari validation set yang cukup besar, seimbang, dan representatif. Fixture sintetis menggunakan threshold kecil hanya untuk membuktikan alur training secara deterministik.

## 7. Validasi terhadap Baseline

Pertahankan dua jalur selama migrasi:

```text
raw CSV
  ├── custom baseline -> candidate decisions
  └── Splink adapter   -> probabilistic predictions
```

Gunakan reviewed labels untuk membandingkan precision, recall, F1, false positives, dan false negatives. Investigasi perbedaan pair yang hanya muncul pada salah satu jalur.

## 8. Tahap Produksi yang Belum Selesai

Adapter ini belum melakukan:

- automatic merge;
- cluster/entity survivorship;
- production persistence;
- monitoring drift;
- threshold approval bisnis;
- privacy review untuk deployment.

Jalur yang disarankan: baseline reproducible -> Splink prediction -> reviewed evaluation -> threshold approval -> merge workflow terpisah.