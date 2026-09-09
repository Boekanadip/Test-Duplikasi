from pathlib import Path

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
