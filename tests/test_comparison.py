import pandas as pd

from src.comparison import build_comparison_vectors


def test_missing_values_do_not_count_as_agreement():
    frame = pd.DataFrame({
        'email_std': [pd.NA, pd.NA],
        'phone_digits_std': ['111', '222'],
        'name_key_std': ['alexsmith', 'alexsmith'],
        'address_std': ['one', 'one'],
        'city_std': ['city', 'city'],
        'dob_std': ['1990-01-01', '1990-01-01'],
    })
    pairs = pd.DataFrame({'left_row_index': [0], 'right_row_index': [1]})
    result = build_comparison_vectors(frame, pairs)
    assert result.loc[0, 'email_agree'] == 0
    assert result.loc[0, 'phone_agree'] == 0
    assert result.loc[0, 'agreement_count'] == 4
    assert result.loc[0, 'available_field_count'] == 5
