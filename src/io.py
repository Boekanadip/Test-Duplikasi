from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {
    'first_name', 'last_name', 'email', 'phone_number',
    'dob', 'address', 'city',
}


def load_customer_csv(path: str | Path) -> pd.DataFrame:
    """Load a customer CSV and fail fast when required columns are absent."""
    csv_path = Path(path)
    frame = pd.read_csv(csv_path)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f'Missing required columns: {missing}')
    return frame


def save_artifact(frame: pd.DataFrame, path: str | Path, *, sep: str = ',') -> None:
    """Save a derived artifact without mutating the input dataframe."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False, sep=sep)
