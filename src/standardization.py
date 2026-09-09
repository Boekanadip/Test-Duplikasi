import pandas as pd


def standardize_text(series: pd.Series) -> pd.Series:
    return (
        series.astype('string')
        .str.normalize('NFKC')
        .str.casefold()
        .str.replace(r'\s+', ' ', regex=True)
        .str.strip()
        .replace('', pd.NA)
    )


def standardize_customers(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with deterministic derived identity columns."""
    result = frame.copy()
    result['email_std'] = standardize_text(result['email'])
    result['phone_digits_std'] = (
        result['phone_number'].astype('string')
        .str.normalize('NFKC')
        .str.replace(r'\D', '', regex=True)
        .replace('', pd.NA)
    )
    result['first_name_std'] = standardize_text(result['first_name'])
    result['last_name_std'] = standardize_text(result['last_name'])
    result['name_key_std'] = (
        result['first_name_std'].fillna('') + result['last_name_std'].fillna('')
    ).str.replace(r'[^a-z0-9]', '', regex=True).replace('', pd.NA)
    result['address_std'] = standardize_text(result['address'])
    result['city_std'] = standardize_text(result['city'])
    result['dob_std'] = pd.to_datetime(result['dob'], errors='coerce').dt.strftime('%Y-%m-%d')
    return result
