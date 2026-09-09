from itertools import combinations

import pandas as pd


def _valid_composite_key(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    valid = frame[columns].notna().all(axis=1)
    key = pd.Series(pd.NA, index=frame.index, dtype='string')
    if valid.any():
        key.loc[valid] = frame.loc[valid, columns].astype('string').agg('|'.join, axis=1)
    return key


def _prefix_key(series: pd.Series, length: int) -> pd.Series:
    values = series.astype('string')
    return values.where(values.str.len().ge(length)).str.slice(0, length)


def _first_character(series: pd.Series) -> pd.Series:
    values = series.astype('string').str.strip()
    return values.where(values.str.len().gt(0)).str.slice(0, 1)


def build_blocking_keys(frame: pd.DataFrame) -> dict[str, pd.Series]:
    """Build blocking keys used by the validated candidate-generation baseline.

    ``email_domain`` is intentionally excluded because the notebook benchmark
    showed that it creates an impractically large candidate set.
    """
    keys = {
        'exact_email': frame['email_std'],
        'exact_phone': frame['phone_digits_std'],
        'name_plus_dob': _valid_composite_key(frame, ['name_key_std', 'dob_std']),
        'email_plus_phone': _valid_composite_key(frame, ['email_std', 'phone_digits_std']),
    }
    if 'last_name_std' in frame and 'dob_std' in frame:
        keys['surname_prefix_dob'] = _valid_composite_key(
            pd.DataFrame({
                'surname_prefix': _first_character(frame['last_name_std']),
                'dob_std': frame['dob_std'],
            }),
            ['surname_prefix', 'dob_std'],
        )
    if 'city_std' in frame and 'dob_std' in frame:
        keys['city_dob'] = _valid_composite_key(frame, ['city_std', 'dob_std'])
    if 'dob_std' in frame:
        keys['dob'] = frame['dob_std']
    keys['phone_prefix_7'] = _prefix_key(frame['phone_digits_std'], 7)
    return keys


def generate_candidate_pairs(frame: pd.DataFrame) -> pd.DataFrame:
    """Generate the deduplicated union of pairs from all blocking keys."""
    row_indices = pd.Series(frame.index, index=frame.index, dtype='int64')
    pair_rules: dict[tuple[int, int], set[str]] = {}
    for strategy, key_series in build_blocking_keys(frame).items():
        eligible = pd.DataFrame({'row_index': row_indices, 'block_key': key_series}).dropna()
        for _, block in eligible.groupby('block_key', sort=False):
            indices = sorted(block['row_index'].tolist())
            for left_index, right_index in combinations(indices, 2):
                pair_rules.setdefault((left_index, right_index), set()).add(strategy)

    rows = [
        {
            'left_row_index': left_index,
            'right_row_index': right_index,
            'supporting_blocking_strategies': '|'.join(sorted(strategies)),
            'blocking_strategy_count': len(strategies),
        }
        for (left_index, right_index), strategies in sorted(pair_rules.items())
    ]
    return pd.DataFrame(rows, columns=[
        'left_row_index', 'right_row_index',
        'supporting_blocking_strategies', 'blocking_strategy_count',
    ])
