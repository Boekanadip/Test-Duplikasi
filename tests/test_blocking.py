import pandas as pd

from src.blocking import build_blocking_keys, generate_candidate_pairs


def test_missing_components_do_not_create_composite_block():
    frame = pd.DataFrame({
        'email_std': [pd.NA, pd.NA],
        'phone_digits_std': ['111', '222'],
        'name_key_std': ['alexsmith', 'alexsmith'],
        'dob_std': [pd.NA, pd.NA],
    })
    keys = build_blocking_keys(frame)
    assert keys['name_plus_dob'].isna().all()
    assert generate_candidate_pairs(frame).empty


def test_union_blocking_deduplicates_pair_and_preserves_provenance():
    frame = pd.DataFrame({
        'email_std': ['same@example.com', 'same@example.com'],
        'phone_digits_std': ['111', '111'],
        'name_key_std': ['alexsmith', 'alexsmith'],
        'dob_std': ['1990-01-01', '1990-01-01'],
    })
    pairs = generate_candidate_pairs(frame)
    assert len(pairs) == 1
    assert pairs.loc[0, 'blocking_strategy_count'] == 5
    assert 'dob' in pairs.loc[0, 'supporting_blocking_strategies']
    assert 'phone_prefix_7' not in pairs.loc[0, 'supporting_blocking_strategies']
    assert 'email_domain' not in pairs.loc[0, 'supporting_blocking_strategies']
