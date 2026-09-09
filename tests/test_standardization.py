import pandas as pd

from src.standardization import standardize_customers


def test_standardization_preserves_raw_columns_and_normalizes_identity_fields():
    frame = pd.DataFrame([{
        'first_name': ' Ana ', 'last_name': 'SANTOS',
        'email': ' Ana.Santos@Example.COM ', 'phone_number': '(123) 456-7890',
        'dob': '1990-01-02', 'address': '  Main   Street ', 'city': ' New York ',
    }])
    result = standardize_customers(frame)
    assert result.loc[0, 'email'] == ' Ana.Santos@Example.COM '
    assert result.loc[0, 'email_std'] == 'ana.santos@example.com'
    assert result.loc[0, 'phone_digits_std'] == '1234567890'
    assert result.loc[0, 'name_key_std'] == 'anasantos'
    assert result.loc[0, 'address_std'] == 'main street'
    assert result.loc[0, 'city_std'] == 'new york'
    assert result.loc[0, 'dob_std'] == '1990-01-02'
