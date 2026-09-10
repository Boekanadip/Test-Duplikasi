"""End-to-end Splink demo: train -> predict -> cluster -> evaluate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from .splink_pipeline import (
    _build_linker,
    cluster_predictions,
    load_reviewed_labels,
    load_customer_csv,
    prepare_splink_input,
    tune_splink_threshold,
)


def _cluster_id_column(clusters: pd.DataFrame) -> str:
    for column in ('cluster_id', 'cluster'):
        if column in clusters.columns:
            return column
    raise KeyError(f'Cluster column not found in: {list(clusters.columns)}')


def run_full_demo(
    input_path: str | Path,
    labels_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    thresholds: list[float] | None = None,
) -> dict[str, object]:
    """Run train, predict, cluster, evaluate and return all artefacts."""
    input_path = Path(input_path)
    if output_dir is None:
        output_dir = input_path.parent / 'processed'

    standardized = prepare_splink_input(load_customer_csv(input_path))
    linker = _build_linker(standardized)

    labels = None
    if labels_path is not None:
        from splink import block_on

        labels = load_reviewed_labels(labels_path)
        linker._db_api.register_table(labels, 'reviewed_labels', overwrite=True)
        linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000, seed=42)
        linker.training.estimate_probability_two_random_records_match(
            deterministic_matching_rules=[block_on('email_std'), block_on('phone_digits_std')],
            recall=0.8,
        )
        linker.training.estimate_m_from_pairwise_labels('reviewed_labels')
    else:
        linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000, seed=42)
    predictions = linker.inference.predict().as_pandas_dataframe()

    eval_summary: pd.DataFrame | None = None
    best_threshold = 0.5
    if labels is not None and len(labels) > 0:
        best_threshold, eval_summary = tune_splink_threshold(
            predictions, labels, thresholds=thresholds
        )

    clusters = cluster_predictions(standardized, predictions, threshold=best_threshold)

    outputs: dict[str, Path] = {}
    output_dir = Path(output_dir)
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        pred_path = output_dir / 'splink_predictions.csv'
        predictions.to_csv(pred_path, index=False)
        outputs['predictions'] = pred_path

        cluster_path = output_dir / 'splink_clusters.csv'
        clusters.to_csv(cluster_path, index=False)
        outputs['clusters'] = cluster_path

        if eval_summary is not None:
            eval_path = output_dir / 'splink_evaluation.csv'
            eval_summary.to_csv(eval_path, index=False)
            outputs['evaluation'] = eval_path

            cluster_column = _cluster_id_column(clusters)
            meta = {
                'best_threshold': best_threshold,
                'reviewed_pairs': int(eval_summary['reviewed_pairs'].iloc[0]),
                'best_f1': float(eval_summary['f1'].iloc[0]),
                'best_precision': float(eval_summary['precision'].iloc[0]),
                'best_recall': float(eval_summary['recall'].iloc[0]),
                'prediction_count': int(len(predictions)),
                'cluster_count': int(clusters[cluster_column].nunique()),
            }
            meta_path = output_dir / 'splink_summary.json'
            meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
            outputs['summary'] = meta_path

    return {
        'standardized': standardized,
        'predictions': predictions,
        'clusters': clusters,
        'eval_summary': eval_summary,
        'best_threshold': best_threshold,
        'output_dir': output_dir,
        'outputs': outputs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='splink-demo',
        description='Run Splink train -> predict -> cluster -> evaluate end-to-end.',
    )
    parser.add_argument('--input', required=True, help='Path to raw customer CSV.')
    parser.add_argument(
        '--labels',
        default=None,
        help='Path to reviewed labels (queue CSV or Splink-format CSV). Optional.',
    )
    parser.add_argument('--output-dir', default=None, help='Directory for all output artefacts.')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_full_demo(args.input, args.labels, args.output_dir)
    print(f'predictions={len(result["predictions"])}')
    print(f'best_threshold={result["best_threshold"]}')
    cluster_column = _cluster_id_column(result['clusters'])
    print(f'clusters={result["clusters"][cluster_column].nunique()}')
    summary = result['eval_summary']
    if summary is not None:
        best = summary.iloc[0]
        print(
            f'f1={best["f1"]:.4f} precision={best["precision"]:.4f} recall={best["recall"]:.4f}'
        )
    for key, path in result['outputs'].items():
        print(f'{key}={path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())