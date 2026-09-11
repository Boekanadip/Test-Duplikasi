"""Import a Google-Form-style CSV export into the pipeline-ready format.

A default Google Form response sheet starts with a 'Timestamp' column and keeps
the raw question labels as headers. This helper maps common form labels onto the
pipeline's required columns (first_name, last_name, email, phone_number, dob,
address, city) and drops any duplicate column caused by 'multiple choice checkboxes'.
Everything else (gender, signup date, source...) is kept as-is; unknown columns are
kept so no information is lost silently.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

FIELD_ALIASES = {
    "nama depan": "first_name",
    "nama pertama": "first_name",
    "first name": "first_name",
    "nama belakang": "last_name",
    "last name": "last_name",
    "email": "email",
    "email address": "email",
    "nomor telepon": "phone_number",
    "nomor hp": "phone_number",
    "telepon": "phone_number",
    "phone": "phone_number",
    "phone number": "phone_number",
    "tanggal lahir": "dob",
    "tgl lahir": "dob",
    "birth date": "dob",
    "date of birth": "dob",
    "alamat": "address",
    "address": "address",
    "kota": "city",
    "city": "city",
}

HEADER_SEPARATOR = " - "


def _canonical_header(column: str) -> str:
    key = column.strip().casefold()
    if HEADER_SEPARATOR in key:
        key = key.split(HEADER_SEPARATOR)[-1].strip()
    return key


def import_form_csv(path: str | Path, *, timestamp_column: str = "Timestamp") -> pd.DataFrame:
    """Normalize a form-response CSV into the pipeline column contract.

    ``timestamp_column`` is dropped if present (it is bookkeeping, not identity).
    Raises ``ValueError`` when a required field has no mapped alias so the caller
    knows exactly which header is missing.
    """
    frame = pd.read_csv(path)
    missing = [c for c in (frame.columns) if c.strip().casefold() == timestamp_column.strip().casefold()]
    if missing:
        frame = frame.drop(columns=missing)

    rename: dict[str, str] = {}
    for column in frame.columns:
        target = FIELD_ALIASES.get(_canonical_header(column))
        if target is not None:
            rename[column] = target
    frame = frame.rename(columns=rename)

    frame = frame.loc[:, ~frame.columns.duplicated(keep="last")]

    required = {"first_name", "last_name", "email", "phone_number", "dob", "address", "city"}
    present = required & set(frame.columns)
    if present != required:
        raise ValueError(f"Missing required fields after mapping: {sorted(required - present)}")
    return frame


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import-form",
        description="Normalize a Google-Form CSV export into the pipeline column contract.",
    )
    parser.add_argument("--input", required=True, help="Path to the raw form-export CSV.")
    parser.add_argument("--output", required=True, help="Path for the normalized CSV.")
    parser.add_argument(
        "--timestamp-column", default="Timestamp",
        help="Header of the submission timestamp column to drop (default: Timestamp).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    normalized = import_form_csv(args.input, timestamp_column=args.timestamp_column)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output, index=False)
    print(f"rows={len(normalized)} columns={list(normalized.columns)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())