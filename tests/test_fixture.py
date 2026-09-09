from pathlib import Path

import pandas as pd


def test_validation_fixture_contains_no_full_pii_columns():
    path = Path(__file__).parent / 'fixtures' / 'validation_pairs.csv'
    frame = pd.read_csv(path)
    forbidden = {'name', 'email', 'phone', 'address', 'customer_id'}
    assert forbidden.isdisjoint(frame.columns)
    assert frame['review_label'].isin([0, 1]).all()
