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
    metrics = evaluate_splink_predictions(predictions, labels_path, threshold=0.1)

    assert metrics['reviewed_pairs'] == 3
    assert metrics['true_positive'] == 1
    assert metrics['false_positive'] == 0
    assert metrics['false_negative'] == 0
    assert metrics['true_negative'] == 2
    assert 0.0 <= metrics['precision'] <= 1.0
    assert 0.0 <= metrics['recall'] <= 1.0
