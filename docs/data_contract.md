# Data Contract

## Input

The pipeline reads a CSV containing these required columns:

- `first_name`
- `last_name`
- `email`
- `phone_number`
- `dob`
- `address`
- `city`

Optional columns such as `customer_id`, `state`, `country`, and `source` may be preserved but are never used as automatic match evidence.

## Raw-data rules

- `data/raw/` is read-only.
- Standardization writes derived columns to a new dataframe or processed output.
- Empty strings and whitespace-only values are treated as missing.
- Missing values never form a blocking key and never count as agreement.

## Derived columns

- `email_std`: normalized casefolded email.
- `phone_digits_std`: digits-only phone representation.
- `first_name_std`, `last_name_std`: normalized text.
- `name_key_std`: normalized concatenated name key.
- `address_std`, `city_std`: normalized text.
- `dob_std`: ISO date string when parseable.

## Pipeline output

Candidate output contains:

- `left_row_index`
- `right_row_index`
- `supporting_blocking_strategies`
- field agreement indicators
- `agreement_count`
- `match_decision`
- `decision_reason`
- `review_required`

The output is a candidate decision artifact, not a merged customer table.

## Failure behavior

The pipeline fails fast when required columns are absent. Invalid dates become missing derived values and are reported by validation; they are not silently treated as matches.
