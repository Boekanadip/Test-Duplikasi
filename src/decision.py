import pandas as pd


def apply_match_policy(
    comparison: pd.DataFrame,
    *,
    high_confidence_threshold: int = 4,
    candidate_threshold: int = 2,
) -> pd.DataFrame:
    """Apply conservative decisions without merging records."""
    if high_confidence_threshold < candidate_threshold:
        raise ValueError('High-confidence threshold must be >= candidate threshold.')

    result = comparison.copy()
    result['match_decision'] = 'not_match'
    result['decision_reason'] = 'insufficient_identity_evidence'
    result['review_required'] = False

    candidate_mask = result['agreement_count'].ge(candidate_threshold)
    high_confidence_mask = result['agreement_count'].ge(high_confidence_threshold)
    result.loc[candidate_mask, 'match_decision'] = 'candidate'
    result.loc[candidate_mask, 'decision_reason'] = 'multi_field_agreement_requires_review'
    result.loc[candidate_mask, 'review_required'] = True
    result.loc[high_confidence_mask, 'match_decision'] = 'high_confidence_candidate'
    result.loc[high_confidence_mask, 'decision_reason'] = 'strong_multi_field_agreement_requires_review'
    return result
