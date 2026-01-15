# Production Runbook

## Pre-deploy checklist
- CI green on default branch.
- Latest image published to GHCR from a version tag (`v*`).
- DB credentials set in runtime environment (`ETL_DB_USER`, `ETL_DB_PASSWORD`).
- Config validated for target herbarium (`--config ... --action process` dry run in staging).

## Standard run
```bash
python main.py --config config-mappings/ups.yml --action all
```

## Strict gate run
Use this for release/staging verification:
```bash
python main.py --config config-mappings/ups.yml --action process --strict
```
Strict mode fails when:
- malformed rows > 0
- duplicate rows dropped > 0
Strict mode does not fail on repaired rows; it logs a warning.

## Operational checks after run
- Verify final output file exists in `data/processed/`.
- Verify latest quality report:
  - `data/processed/quality_report_<herbarium>.json`
- Inspect key metrics:
  - `extraction.repaired_rows_total`
  - `extraction.malformed_rows_total`
  - `transformation.duplicates.duplicate_rows_dropped`
  - `output.final_rows`

## Test command
Use interpreter-bound pytest:
```bash
python -m pytest
```

## Alert thresholds (recommended)
- `malformed_rows_total > 0`: high severity.
- `duplicate_rows_dropped` sudden increase > 20% versus previous run: medium severity.
- `final_rows` drop > 10% versus previous run: high severity.
- repeated downloader retry exhaustion/failure: high severity.

## Failure triage
1. Downloader failure:
   - check network/API reachability
   - retry run; inspect retry logs
2. Strict-mode quality failure:
   - inspect malformed files (`data/malformed/*`)
   - inspect duplicates file (`data/processed/duplicates_*.csv`)
3. DB load failure:
   - verify env credentials
   - verify table schema and PK/unique constraints
   - rerun with `write_to_db: false` to validate upstream stages

## Rollback approach
- Keep last known-good processed outputs archived by run ID.
- Re-run previous tagged image/config in container if regression is detected.
