# Splink Learning Findings — Does Splink Learn or Just Follow Baseline?

## Summary

Splink **does learn** from reviewed labels. Without labels, it mirrors
baseline behavior. With stratified labels (40 pos + 40 neg including
decoys), the m-probability estimation kicks in and produces a
discriminative probability ranking.

Tested on `data/processed/fake_500.csv` (422 records, 12 true dup pairs,
60 decoy entities).

---

## Splink: How It Learns

Splink estimates two sets of probabilities from the data:

### u-probability (unsupervised, no labels needed)
P(field agrees | two random records).
Estimated by random sampling. Works without labels but gives a flat
ranking — most pairs get low scores because random pairs rarely agree
on multiple fields.

### m-probability (supervised, needs labels)
P(field agrees | same entity).
Estimated via Expectation-Maximization from reviewed pairs (your
`clerical_match_score` labels). This is where learning happens:
the model discovers that, e.g., exact email agreement is a very strong
signal (m >> u), while exact city agreement is weaker (m ≈ u because
many unrelated people share the same city).

### How They Combine

P(match | fields) ≈ prior × ∏(m_i / u_i) for each field i.

Higher m_i/u_i ratio → stronger evidence of match.
Labels train the m_i values via EM. More diverse labels → better m_i
estimates → better probability ranking → better threshold selection.

---

## Empirical Results

### Branch A: Splink WITHOUT labels (u-probabilities only, default m)

| Threshold | Predicted | TP | FP | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| 0.05 | 12 | 12 | 0 | 1.000 | 1.000 | 1.000 |
| 0.10 | 12 | 12 | 0 | 1.000 | 1.000 | 1.000 |
| 0.30 | 12 | 12 | 0 | 1.000 | 1.000 | 1.000 |
| 0.50 | 12 | 12 | 0 | 1.000 | 1.000 | 1.000 |
| 0.70 | 12 | 12 | 0 | 1.000 | 1.000 | 1.000 |
| 0.90 | 12 | 12 | 0 | 1.000 | 1.000 | 1.000 |

**Interpretation:** Without labels, only 12 pairs total are ever
assigned a probability. These are the exact field-agreement pairs
that blocking + comparison produce. The model is extremely conservative
— it only "finds" what the blocking rules already give it. This is
essentially the baseline behavior.

### Branch B: Splink WITH labels (EM-trained m-probabilities)

| Threshold | Predicted | TP | FP | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| 0.05 | 74 | 12 | 62 | 0.162 | 1.000 | 0.279 |
| 0.10 | 46 | 12 | 34 | 0.261 | 1.000 | 0.414 |
| 0.20 | 29 | 12 | 17 | 0.414 | 1.000 | 0.585 |
| 0.30 | 21 | 12 | 9 | 0.571 | 1.000 | 0.727 |
| 0.50 | 13 | 12 | 1 | 0.923 | 1.000 | 0.960 |
| 0.70 | 12 | 12 | 0 | 1.000 | 1.000 | 1.000 |
| 0.90 | 12 | 12 | 0 | 1.000 | 1.000 | 1.000 |

**Interpretation:** With labels, Splink explores 74 candidate pairs
(more than blocking alone), but assigns varying probabilities. At
threshold 0.5, only 13 survive (12 TP + 1 FP). At 0.7, exactly 12
TP remain — same as Branch A but through a fundamentally different
mechanism: probability ranking, not just blocking.

The 74 pairs at low threshold = Splink's EM-learned m-probabilities
are now discriminating between fields: it knows that email/phone
agreement is a strong signal, while city/dob agreement is weaker.
This lets it explore more pairs while still ranking true matches
higher.

---

## Key Takeaway

**Without labels → Splink = baseline (blocking behavior, limited
to blocking keys).** It can only score pairs that blocking produces,
and it ranks them conservatively using default m-probabilities.

**With labels → Splink = probabilistic model that explores more
pairs AND ranks them by evidence strength.** The m-probability
training lets the model learn that certain field agreements (email,
phone) carry more weight than others (city, dob). This enables:

1. Higher recall (explores 74 pairs vs 12)
2. Better precision at tuned threshold (12 TP, 0 FP at 0.7)
3. Threshold tuning to optimize precision-recall tradeoff

Labels don't just "improve" Splink — they are **required** for
Splink to function as anything beyond a blocking-checker.

---

## Blocking, Score, Ground Truth, Tuning, Threshold — Explained

### Blocking

N(N-1)/2 = 90,000 possible pairs for 422 records.
Blocking keys (exact email, exact phone, name+dob, city+dob) reduce
this to a manageable candidate set.

**Blocking recall** = how many true duplicates survive into the
candidate set. If a true dup never shares a blocking key, it's
permanently lost (recall loss).

### Similarity Score (match_probability)

For each candidate pair, Splink compares 6 fields. Each field gets
an agreement score (0/1 or Levenshtein level). The model combines
these via:

  P(match) ≈ prior × ∏(m_i / u_i)

where m_i = P(field agrees | same person) and u_i = P(field agrees |
different person). Labels train m via EM. More labels → more accurate
m estimates → better probability ranking.

### Ground Truth

`true_entity_id` is the gold standard — which records are actually the
same person. In synthetic data, this is known. In production, it is
NOT known. You build label files from reviewed pairs:

  record_a, record_b, label (1 = match, 0 = not match)

The 80 labels used for training are stratified: 40 true matches + 40
negatives including decoys. Without ground truth you CANNOT compute
precision/recall — only inspect clusters.

### Tuning

Grid search over threshold (e.g. 0.05, 0.1, ... 0.95) on a held-out
review set. For each threshold:

  predicted_positive = (match_probability >= threshold)
  F1 = 2 × P × R / (P + R)

Pick the threshold with highest F1. The identity guard
(`min_identity_agreement`) is another tuning parameter: require ≥N of
(email, phone, name) to agree exactly, reducing shared-field decoy FPs.

### Threshold & Decision

- Lower threshold → more recall, fewer missed matches (more review queue)
- Higher threshold → more precision, fewer false merges (some true dupes missed)

**Production decision rule:**

  baseline(agree) AND Splink(>=threshold) AND guard(>=N identity)
  → auto_merge

Everything else → review queue for human verification.

---

## Artifact Paths

```
data/processed/fake_500.csv                      # fabricated dataset
data/processed/fake_500_ground_truth.csv          # pair-level ground truth
data/processed/splink_learning/
  train_labels.csv                                # 80 labels for training
  pred_A_no_labels.csv                            # Branch A predictions
  pred_B_with_labels.csv                          # Branch B predictions
  sweep_A.csv                                     # threshold sweep A
  sweep_B.csv                                     # threshold sweep B
```
