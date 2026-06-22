# Phase {{ phase }} Repair Prompt -- Attempt {{ attempt }}

## Context
The adapt skill loop is repairing a validator failure for phase {{ phase }}, attempt {{ attempt }}.

## Failure Signature
| Field     | Value |
|-----------|-------|
| Validator | {{ validator_name }} |
| Kind      | {{ failure_kind }} |
| Location  | {{ failure_location }} |
| Expected  | {{ expected }} |
| Actual    | {{ actual }} |

## Previous Attempts
{{ attempts_summary }}

## Diff Summary
{{ diff_summary }}

## Escape Hatch
If after 3 attempts no progress is observed, write `phases/phase{{ phase }}/escalation.md` and exit `human_needed`.
Do NOT continue attempting the same fix if the validator shows no improvement.
