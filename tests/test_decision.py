import pandas as pd
import pytest

from src.decision import apply_match_policy


def test_decision_is_conservative_and_requires_review():
    comparison = pd.DataFrame({'agreement_count': [1, 2, 4]})
    result = apply_match_policy(comparison)
    assert result['match_decision'].tolist() == [
        'not_match', 'candidate', 'high_confidence_candidate',
    ]
    assert result['review_required'].tolist() == [False, True, True]


def test_threshold_order_is_validated():
    with pytest.raises(ValueError):
        apply_match_policy(pd.DataFrame({'agreement_count': [1]}), high_confidence_threshold=2, candidate_threshold=3)
