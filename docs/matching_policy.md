# Matching Policy

## Scope

This policy describes the laboratory baseline extracted from notebooks 04-12. It is not a production merge policy.

## Standardization

Apply Unicode NFKC normalization, casefolding, whitespace collapse, and trimming to text fields. Keep raw columns unchanged. Keep only digits for phone comparison; do not invent country codes.

## Candidate generation

Use the union of valid blocking keys:

- exact normalized email;
- exact normalized phone digits;
- exact normalized name plus DOB;
- exact normalized email plus phone;
- phone prefix of at least seven digits;
- DOB;
- surname prefix plus DOB;
- city plus DOB.

Email-domain-only blocking is intentionally excluded from the default pipeline because the experiment produced candidate explosion.

A blocking key is valid only when all of its components are present. A blocking collision is candidate evidence, not a match decision.

## Comparison

Agreement is counted only when both values are present and equal after standardization. Missing values do not agree.

## Decision policy

- `agreement_count >= 4`: high-confidence review candidate; never an automatic merge by default.
- `agreement_count >= 2`: candidate only; known false-positive risk from DOB/city collisions.
- fewer than 2 agreements: reject as an automatic candidate or send to a separate review queue.

## Safety and evaluation

- `customer_id` is not a label unless independently validated as a master entity identifier.
- Precision, recall, and F1 are reported only against reviewed labels.
- A validation result from 107 reviewed pairs is sample evidence, not a population guarantee.
- Any automatic merge workflow requires a larger, stratified validation set and explicit business approval.
