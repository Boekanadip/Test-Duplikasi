import pandas as pd

COMPARISON_FIELDS = {
    'email': 'email_std',
    'phone': 'phone_digits_std',
    'name': 'name_key_std',
    'address': 'address_std',
    'city': 'city_std',
    'dob': 'dob_std',
}


def build_comparison_vectors(frame: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Add binary agreement indicators for each candidate pair."""
    result = pairs.copy()
    indexed = frame
    for label, column in COMPARISON_FIELDS.items():
        left = indexed.loc[result['left_row_index'], column].reset_index(drop=True)
        right = indexed.loc[result['right_row_index'], column].reset_index(drop=True)
        available = left.notna() & right.notna()
        left_comparable = left.astype('string').fillna('__MISSING_LEFT__')
        right_comparable = right.astype('string').fillna('__MISSING_RIGHT__')
        equal = left_comparable.eq(right_comparable)
        result[f'{label}_agree'] = (available & equal).astype('int8')

    agreement_columns = [f'{label}_agree' for label in COMPARISON_FIELDS]
    result['agreement_count'] = result[agreement_columns].sum(axis=1)
    result['available_field_count'] = sum(
        indexed.loc[result['left_row_index'], column].reset_index(drop=True).notna()
        & indexed.loc[result['right_row_index'], column].reset_index(drop=True).notna()
        for column in COMPARISON_FIELDS.values()
    )
    return result
