from pathlib import Path

import pytest

from src.pipeline import run_candidate_pipeline


FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'customers_sample.csv'


def test_pipeline_runs_fixture_without_merging_and_writes_artifact(tmp_path):
    output_path = tmp_path / 'candidate_decisions.csv'
    result = run_candidate_pipeline(FIXTURE_PATH, output_path, log_level='WARNING')

    assert output_path.exists()
    assert {'match_decision', 'decision_reason', 'review_required'}.issubset(result.columns)
    assert len(result) >= 1
    assert result['match_decision'].isin({
        'not_match', 'candidate', 'high_confidence_candidate',
    }).all()
    assert not result['match_decision'].eq('merged').any()


def test_splink_adapter_runs_on_fixture_when_installed(tmp_path):
    pytest.importorskip('splink')
    from src.splink_pipeline import run_splink_pipeline

    output_path = tmp_path / 'splink_predictions.csv'
    result = run_splink_pipeline(FIXTURE_PATH, output_path)

    assert output_path.exists()
    assert len(result) >= 1
    assert {'record_id_l', 'record_id_r', 'match_probability'}.issubset(result.columns)


def test_splink_training_uses_reviewed_labels_and_evaluates(tmp_path):
    pytest.importorskip('splink')
    from src.splink_pipeline import (
        evaluate_splink_predictions,
        train_splink_pipeline,
    )

    labels_path = tmp_path / 'reviewed_labels.csv'
    labels_path.write_text(
        'record_id_l,record_id_r,clerical_match_score\n'
        '0,1,1\n'
        '2,3,0\n'
        '0,2,0\n',
        encoding='utf-8',
    )
    predictions = train_splink_pipeline(FIXTURE_PATH, labels_path)
    metrics = evaluate_splink_predictions(predictions, labels_path, threshold=0.6)

    assert metrics['reviewed_pairs'] == 3
    assert metrics['true_positive'] == 1
    assert metrics['false_positive'] == 0
    assert metrics['false_negative'] == 0
    assert metrics['true_negative'] == 2
    assert 0.0 <= metrics['precision'] <= 1.0
    assert 0.0 <= metrics['recall'] <= 1.0


def test_queue_labels_bridge_writes_splink_format(tmp_path):
    pytest.importorskip('splink')
    from src.splink_pipeline import load_reviewed_labels, reviewed_queue_to_splink_labels
    queue = tmp_path / 'review_queue.csv'
    queue.write_text(
        'left_row_index;right_row_index;review_label\n'
        '0;1;1\n'
        '2;3;0\n',
        encoding='utf-8',
    )
    labels = load_reviewed_labels(queue)
    assert set(labels.columns) == {'record_id_l', 'record_id_r', 'clerical_match_score'}
    assert len(labels) == 2
    assert labels['clerical_match_score'].tolist() == [1, 0]
    out = tmp_path / 'out_labels.csv'
    reviewed_queue_to_splink_labels(queue, out)
    assert out.exists()


def test_tune_threshold_returns_best_and_summary(tmp_path):
    pytest.importorskip('splink')
    from src.splink_pipeline import tune_splink_threshold, train_splink_pipeline
    labels_path = tmp_path / 'labels.csv'
    labels_path.write_text(
        'record_id_l,record_id_r,clerical_match_score\n'
        '0,1,1\n'
        '2,3,0\n'
        '0,2,0\n',
        encoding='utf-8',
    )
    predictions = train_splink_pipeline(FIXTURE_PATH, labels_path)
    best, summary = tune_splink_threshold(predictions, labels_path, thresholds=[0.1, 0.5, 0.9])
    assert isinstance(best, float)
    assert 0.1 <= best <= 0.9
    assert set(summary.columns) >= {'threshold', 'f1', 'precision', 'recall'}
    assert len(summary) == 3


def test_cluster_predictions_groups_entities(tmp_path):
    pytest.importorskip('splink')
    from src.splink_pipeline import (
        prepare_splink_input,
        run_splink_pipeline,
        cluster_predictions,
    )
    from src.io import load_customer_csv
    standardized = prepare_splink_input(load_customer_csv(FIXTURE_PATH))
    predictions = run_splink_pipeline(FIXTURE_PATH)
    clusters = cluster_predictions(standardized, predictions, threshold=0.3)
    assert set(clusters.columns) >= {'record_id', 'cluster_id'}
    assert clusters['cluster_id'].nunique() <= len(standardized)
