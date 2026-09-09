"""Optional Splink adapter built on the project's standardization contract."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from .io import load_customer_csv
from .standardization import standardize_customers


def build_splink_settings():
    """Create a conservative Splink settings object for dedupe-only linkage."""
    try:
        from splink import SettingsCreator, block_on
        from splink.comparison_library import (
            exact_match,
            levenshtein_at_thresholds,
        )
    except ImportError as error:
        raise RuntimeError(
            'Splink is optional. Install it with: python -m pip install -e ".[splink]"'
        ) from error

    return SettingsCreator(
        link_type='dedupe_only',
        unique_id_column_name='record_id',
        comparisons=[
            exact_match('email_std'),
            exact_match('phone_digits_std'),
            levenshtein_at_thresholds('name_key_std', [1, 2]),
            levenshtein_at_thresholds('address_std', [2, 4]),
            exact_match('city_std'),
            exact_match('dob_std'),
        ],
        blocking_rules_to_generate_predictions=[
            block_on('email_std'),
            block_on('phone_digits_std'),
            block_on(['name_key_std', 'dob_std']),
            block_on(['city_std', 'dob_std']),
        ],
    )


def prepare_splink_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardize customer data and add the unique id required by Splink."""
    standardized = standardize_customers(frame).reset_index(drop=True)
    standardized.insert(0, 'record_id', standardized.index.astype('string'))
    return standardized


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