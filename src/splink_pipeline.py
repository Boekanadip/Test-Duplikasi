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
            ExactMatch('email_std'),
            ExactMatch('phone_digits_std'),
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


def prepare_splink_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardize customer data and add the unique id required by Splink."""
    standardized = standardize_customers(frame).reset_index(drop=True)
    standardized.insert(0, 'record_id', standardized.index.astype('string'))
    return standardized


def load_reviewed_labels(path: str | Path) -> pd.DataFrame:
    """Load reviewed pair labels without using customer_id as ground truth."""
    labels = pd.read_csv(path)
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

    linker = _build_linker(standardized)
    linker._db_api.register_table(labels, 'reviewed_labels', overwrite=True)
    linker.training.estimate_m_from_pairwise_labels('reviewed_labels')
    linker.training.estimate_u_using_random_sampling(seed=42)
    predictions = linker.inference.predict().as_pandas_dataframe()
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        predictions.to_csv(output, index=False)
    return predictions


def evaluate_splink_predictions(
    predictions: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    threshold: float = 0.5,
) -> dict[str, float | int]:
    """Evaluate a probability threshold against reviewed pair labels only."""
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
    reviewed_pairs = reviewed[['pair_key', 'clerical_match_score']]
    evaluated = reviewed_pairs.merge(prediction_pairs, on='pair_key', how='left')
    evaluated['match_probability'] = evaluated['match_probability'].fillna(0.0)
    actual = evaluated['clerical_match_score'].astype(int)
    predicted = evaluated['match_probability'].ge(threshold).astype(int)
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