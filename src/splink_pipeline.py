"""Optional Splink adapter built on the project's standardization contract."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from .io import load_customer_csv
from .standardization import standardize_customers

REVIEWED_LABEL_COLUMNS = {
    'record_id_l', 'record_id_r', 'clerical_match_score',
}


def build_splink_settings():
    """Create a conservative Splink settings object for dedupe-only linkage."""
    try:
        from splink import SettingsCreator, block_on
        from splink.comparison_library import (
            ExactMatch,
            JaroWinklerAtThresholds,
            LevenshteinAtThresholds,
        )
    except ImportError as error:
        raise RuntimeError(
            'Splink is optional. Install it with: python -m pip install -e ".[splink]"'
        ) from error

    return SettingsCreator(
        link_type='dedupe_only',
        unique_id_column_name='record_id',
        comparisons=[
            JaroWinklerAtThresholds('email_std', [0.95, 0.88]),
            JaroWinklerAtThresholds('phone_digits_std', [0.95, 0.88]),
            LevenshteinAtThresholds('name_key_std', [1, 2]),
            LevenshteinAtThresholds('address_std', [2, 4]),
            ExactMatch('city_std'),
            ExactMatch('dob_std'),
        ],
        blocking_rules_to_generate_predictions=[
            block_on('email_std'),
            block_on('phone_digits_std'),
            block_on('name_key_std', 'dob_std'),
            block_on('city_std', 'dob_std'),
        ],
    )


SPLINK_TEXT_COLUMNS = (
    'email_std',
    'phone_digits_std',
    'name_key_std',
    'address_std',
    'city_std',
    'dob_std',
)

QUEUE_LABEL_COLUMNS = {
    'left_row_index', 'right_row_index', 'review_label',
}


def _splink_normalize_identity(standardized: pd.DataFrame) -> pd.DataFrame:
    """Canonicalize email/phone identifiers for Splink comparison.

    Fixes false-negatives that standardization alone misses:
      - googlemail.com is gmail.com (same mailbox, different domain alias)
      - Indonesian country code: +62NNN... ≈ 0NNN...
    Applies to Splink-derived columns only; raw columns stay untouched.
    """
    result = standardized.copy()
    if 'email_std' in result.columns:
        result['email_std'] = result['email_std'].astype('string').str.replace(
            r'@googlemail\.com$', '@gmail.com', regex=True, case=False)
    if 'phone_digits_std' in result.columns:
        phone = result['phone_digits_std'].astype('string')
        starts_country_code = phone.str.fullmatch(r'62\d{9,}')
        result.loc[starts_country_code, 'phone_digits_std'] = (
            '0' + phone.loc[starts_country_code].str.replace(r'^62', '', regex=True)
        )
    return result


def prepare_splink_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardize customer data and add the unique id required by Splink."""
    if 'record_id' in frame.columns:
        standardized = frame.copy()
    else:
        standardized = standardize_customers(frame).reset_index(drop=True)
        standardized.insert(0, 'record_id', standardized.index.astype('string'))
    for column in SPLINK_TEXT_COLUMNS:
        if column in standardized.columns:
            standardized[column] = standardized[column].astype('string')
    return _splink_normalize_identity(standardized)


def _read_labels_csv(path: str | Path) -> pd.DataFrame:
    """Read a label CSV with comma or semicolon delimiter."""
    path = Path(path)
    with path.open('r', encoding='utf-8') as handle:
        header = handle.readline()
    sep = ';' if header.count(';') > header.count(',') else ','
    return pd.read_csv(path, sep=sep)


def reviewed_queue_to_splink_labels(
    queue_path: str | Path,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Bridge manual_review_queue.csv to Splink pairwise-label format."""
    queue = _read_labels_csv(queue_path)
    missing = sorted(QUEUE_LABEL_COLUMNS - set(queue.columns))
    if missing:
        raise ValueError(f'Missing review-queue columns: {missing}')
    reviewed = queue.dropna(subset=['review_label']).copy()
    result = pd.DataFrame({
        'record_id_l': reviewed['left_row_index'].astype('int64').astype('string'),
        'record_id_r': reviewed['right_row_index'].astype('int64').astype('string'),
        'clerical_match_score': pd.to_numeric(reviewed['review_label'], errors='coerce'),
    })
    result = load_reviewed_labels(result)
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
    return result


def load_reviewed_labels(path: str | Path | pd.DataFrame) -> pd.DataFrame:
    """Load reviewed pair labels without using customer_id as ground truth."""
    if isinstance(path, pd.DataFrame):
        labels = path.copy()
    else:
        labels = _read_labels_csv(path)
    if QUEUE_LABEL_COLUMNS.issubset(set(labels.columns)):
        labels = pd.DataFrame({
            'record_id_l': labels['left_row_index'].astype('int64').astype('string'),
            'record_id_r': labels['right_row_index'].astype('int64').astype('string'),
            'clerical_match_score': pd.to_numeric(labels['review_label'], errors='coerce'),
        })
    missing = sorted(REVIEWED_LABEL_COLUMNS - set(labels.columns))
    if missing:
        raise ValueError(f'Missing reviewed-label columns: {missing}')

    result = labels[list(REVIEWED_LABEL_COLUMNS)].copy()
    result['record_id_l'] = result['record_id_l'].astype('string')
    result['record_id_r'] = result['record_id_r'].astype('string')
    result['clerical_match_score'] = pd.to_numeric(
        result['clerical_match_score'], errors='coerce'
    )
    if result[['record_id_l', 'record_id_r', 'clerical_match_score']].isna().any().any():
        raise ValueError('Reviewed labels contain missing values.')
    if not result['clerical_match_score'].isin([0, 1]).all():
        raise ValueError('clerical_match_score must contain only 0 or 1.')
    if (result['record_id_l'] == result['record_id_r']).any():
        raise ValueError('Reviewed labels cannot contain self-pairs.')
    return result


def _build_linker(standardized: pd.DataFrame):
    try:
        from splink import DuckDBAPI, Linker
    except ImportError as error:
        raise RuntimeError(
            'Splink is optional. Install it with: python -m pip install -e ".[splink]"'
        ) from error
    return Linker(standardized, build_splink_settings(), db_api=DuckDBAPI())


def train_splink_pipeline(
    input_path: str | Path,
    labels_path: str | Path,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Train Splink m/u parameters from reviewed pair labels and predict."""
    standardized = prepare_splink_input(load_customer_csv(input_path))
    labels = load_reviewed_labels(labels_path)
    record_ids = set(standardized['record_id'])
    label_ids = set(labels['record_id_l']) | set(labels['record_id_r'])
    unknown_ids = sorted(label_ids - record_ids)
    if unknown_ids:
        raise ValueError(f'Reviewed labels reference unknown record ids: {unknown_ids}')

    from splink import block_on

    linker = _build_linker(standardized)
    linker._db_api.register_table(labels, 'reviewed_labels', overwrite=True)
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000, seed=42)
    linker.training.estimate_probability_two_random_records_match(
        deterministic_matching_rules=[block_on('email_std'), block_on('phone_digits_std')],
        recall=0.8,
    )
    linker.training.estimate_m_from_pairwise_labels('reviewed_labels')
    predictions = linker.inference.predict().as_pandas_dataframe()
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        predictions.to_csv(output, index=False)
    return predictions


IDENTITY_COLUMNS = ('email_std', 'phone_digits_std', 'name_key_std')


def split_labels(
    labels: str | Path | pd.DataFrame,
    *,
    train_frac: float = 0.7,
    seed: int = 42,
    stratify: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stratified (or random) train/holdout split. Never returns an empty fold."""
    assert 0 < train_frac < 1
    frame = load_reviewed_labels(labels)
    if len(frame) < 2:
        raise ValueError('split_labels needs at least 2 labelled pairs.')
    frame = frame.sample(frac=1, random_state=seed).reset_index(drop=True)
    if stratify and frame['clerical_match_score'].nunique() > 1:
        pos = frame[frame['clerical_match_score'] == 1].reset_index(drop=True)
        neg = frame[frame['clerical_match_score'] == 0].reset_index(drop=True)
        split_pos = max(1, int(len(pos) * train_frac))
        split_neg = max(1, int(len(neg) * train_frac))
        split_pos = min(split_pos, len(pos) - 1)
        split_neg = min(split_neg, len(neg) - 1)
        train = pd.concat([pos.iloc[:split_pos], neg.iloc[:split_neg]], ignore_index=True)
        holdout = pd.concat([pos.iloc[split_pos:], neg.iloc[split_neg:]], ignore_index=True)
        train = train.sample(frac=1, random_state=seed).reset_index(drop=True)
        holdout = holdout.sample(frac=1, random_state=seed + 1).reset_index(drop=True)
        return train, holdout
    n_train = max(1, min(int(len(frame) * train_frac), len(frame) - 1))
    return frame.iloc[:n_train].copy(), frame.iloc[n_train:].copy()


def evaluate_splink_holdout(
    predictions: pd.DataFrame,
    holdout: str | Path | pd.DataFrame,
    *,
    threshold: float = 0.5,
    standardized: pd.DataFrame | None = None,
    min_identity_agreement: int = 0,
) -> dict[str, float | int]:
    """Evaluate only on a holdout fold that was never used for m-estimation."""
    if isinstance(holdout, (str, Path)):
        h = load_reviewed_labels(holdout)
        if h.empty:
            raise ValueError('holdout set is empty.')
    else:
        h = holdout
    h = h.reset_index(drop=True)
    if len(h) == 0:
        raise ValueError('holdout set is empty.')
    return evaluate_splink_predictions(predictions, h, threshold=threshold,
                                       standardized=standardized,
                                       min_identity_agreement=min_identity_agreement)


def evaluate_splink_predictions(
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    threshold: float = 0.5,
    standardized: pd.DataFrame | None = None,
    min_identity_agreement: int = 0,
) -> dict[str, float | int]:
    """Evaluate a probability threshold against reviewed pair labels only.

    When ``standardized`` is provided the identity-field agreement guard
    ``min_identity_agreement`` is enforced: a prediction counts as positive
    only if the probability threshold is satisfied **and** at least that
    many of (email, phone, name) agree exactly between the two records.
    This guards against singleton weak-field (dob / city) over-confidence.
    """
    if not 0 <= threshold <= 1:
        raise ValueError('threshold must be between 0 and 1.')
    required_predictions = {'record_id_l', 'record_id_r', 'match_probability'}
    missing = sorted(required_predictions - set(predictions.columns))
    if missing:
        raise ValueError(f'Missing prediction columns: {missing}')

    reviewed = load_reviewed_labels(labels) if isinstance(labels, (str, Path)) else labels.copy()
    predictions = predictions.copy()
    reviewed = reviewed.copy()
    predictions['pair_key'] = predictions.apply(
        lambda row: tuple(sorted((str(row['record_id_l']), str(row['record_id_r'])))),
        axis=1,
    )
    reviewed['pair_key'] = reviewed.apply(
        lambda row: tuple(sorted((str(row['record_id_l']), str(row['record_id_r'])))),
        axis=1,
    )
    prediction_pairs = predictions[['pair_key', 'match_probability']].drop_duplicates('pair_key')
    reviewed_pairs = reviewed[['pair_key', 'clerical_match_score', 'record_id_l', 'record_id_r']]
    evaluated = reviewed_pairs.merge(prediction_pairs, on='pair_key', how='left')
    evaluated['match_probability'] = evaluated['match_probability'].fillna(0.0)

    use_guard = standardized is not None and min_identity_agreement > 0
    if use_guard:
        std = standardized
        id_left = std.set_index('record_id')[list(IDENTITY_COLUMNS)].rename(columns=lambda c: f'{c}_l')
        id_right = std.set_index('record_id')[list(IDENTITY_COLUMNS)].rename(columns=lambda c: f'{c}_r')
        evaluated['record_id_l'] = evaluated['record_id_l'].astype('string')
        evaluated['record_id_r'] = evaluated['record_id_r'].astype('string')
        evaluated = evaluated.merge(id_left, left_on='record_id_l', right_index=True, how='left')
        evaluated = evaluated.merge(id_right, left_on='record_id_r', right_index=True, how='left')
        identity_agreement = pd.Series(0, index=evaluated.index)
        for col in IDENTITY_COLUMNS:
            l = evaluated[f'{col}_l'].astype('string')
            r = evaluated[f'{col}_r'].astype('string')
            identity_agreement = identity_agreement + (l.eq(r) & l.notna() & r.notna()).astype(int)
        evaluated['identity_agreement'] = identity_agreement
    else:
        evaluated['identity_agreement'] = 0

    actual = evaluated['clerical_match_score'].astype(int)
    prob_ok = evaluated['match_probability'].ge(threshold)
    id_ok = evaluated['identity_agreement'].ge(min_identity_agreement) if use_guard else True
    predicted = (prob_ok & id_ok).astype(int)

    true_positive = int(((actual == 1) & (predicted == 1)).sum())
    false_positive = int(((actual == 0) & (predicted == 1)).sum())
    false_negative = int(((actual == 1) & (predicted == 0)).sum())
    true_negative = int(((actual == 0) & (predicted == 0)).sum())
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        'reviewed_pairs': int(len(evaluated)),
        'true_positive': true_positive,
        'false_positive': false_positive,
        'false_negative': false_negative,
        'true_negative': true_negative,
        'precision': precision,
        'recall': recall,
        'f1': f1,
    }


def cluster_predictions(
    standardized: pd.DataFrame,
    predictions: pd.DataFrame,
    threshold: float = 0.5,
) -> pd.DataFrame:
    """Cluster pairwise predictions into entity groups using connected components."""
    from splink.clustering import cluster_pairwise_predictions_at_threshold
    from splink import DuckDBAPI
    edges = predictions[['record_id_l', 'record_id_r', 'match_probability']].copy()
    nodes = standardized[['record_id']].copy()
    clustered = cluster_pairwise_predictions_at_threshold(
        nodes=nodes,
        edges=edges,
        db_api=DuckDBAPI(),
        node_id_column_name='record_id',
        edge_id_column_name_left='record_id_l',
        edge_id_column_name_right='record_id_r',
        threshold_match_probability=threshold,
    )
    return clustered.as_pandas_dataframe()


def tune_splink_threshold(
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    thresholds: list[float] | None = None,
    standardized: pd.DataFrame | None = None,
    min_identity_agreement: int = 0,
) -> tuple[float, pd.DataFrame]:
    """Find the probability threshold that maximizes F1 on reviewed labels."""
    if thresholds is None:
        thresholds = [round(x * 0.1, 1) for x in range(1, 10)]
    rows: list[dict[str, float | int]] = []
    for threshold in thresholds:
        metrics = evaluate_splink_predictions(
            predictions,
            labels,
            threshold=threshold,
            standardized=standardized,
            min_identity_agreement=min_identity_agreement,
        )
        metrics['threshold'] = threshold
        rows.append(metrics)
    summary = pd.DataFrame(rows)
    summary = summary.sort_values(['f1', 'precision'], ascending=[False, False])
    best = summary.iloc[0]
    return float(best['threshold']), summary


def run_splink_pipeline(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Run Splink predictions and optionally write the prediction artifact."""
    try:
        from splink import DuckDBAPI, Linker
    except ImportError as error:
        raise RuntimeError(
            'Splink is optional. Install it with: python -m pip install -e ".[splink]"'
        ) from error

    standardized = prepare_splink_input(load_customer_csv(input_path))
    linker = Linker(standardized, build_splink_settings(), db_api=DuckDBAPI())
    predictions = linker.inference.predict().as_pandas_dataframe()
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        predictions.to_csv(output, index=False)
    return predictions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run the optional Splink adapter.')
    parser.add_argument('--input', required=True, help='Path to customer CSV.')
    parser.add_argument('--output', required=True, help='Path for Splink predictions.')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    predictions = run_splink_pipeline(args.input, args.output)
    print(f'splink_predictions={len(predictions)} output={args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())