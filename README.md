# etl_virtualherbarium

ETL pipeline for Swedish Virtual Herbarium data.

## What it does
- Downloads verbatim CSV pages per herbarium (`GB`, `OHN`, `UME`, `UPS`).
- Repairs common exporter row-shape issues during extraction.
- Applies configured transformations and mapping to Darwin Core-like output.
- Writes processed files and quality reports.
- Optionally writes to MySQL (`ignore`/`upsert` modes).

## Requirements
- Python 3.12+
- Dependencies: `pip install -r requirements.txt`

## Run
```bash
python main.py --config config-mappings/ume.yml --action all
```

Actions:
- `download`: only download verbatim files
- `process`: process existing verbatim files
- `all`: download + process

Optional:
- `--strict`: fail if malformed rows or dropped duplicates are non-zero (repaired rows are logged as warning)

## Output
- Processed files: `data/processed/dwc_<herbarium>.csv`
- Quality reports:
  - `data/processed/quality_report_<herbarium>_<runid>.json`
  - `data/processed/quality_report_<herbarium>.json` (latest)
- Duplicate audit (if duplicates exist): `data/processed/duplicates_<herbarium>.csv`
- Malformed rows (if any): `data/malformed/<source>_malformed.csv`

## Docker
Build and run with Compose:
```bash
docker compose up --build
```

Environment overrides:
- `CONFIG_PATH` (default `config-mappings/ume.yml`)
- `ACTION` (default `process`)

Image notes:
- Docker image includes only runtime files (no tests, logs, reference materials, or local env files).

## Make targets
- `make build`
- `make up`
- `make process CONFIG=config-mappings/ups.yml`
- `make strict CONFIG=config-mappings/ume.yml ACTION=process`
- `make clean-generated`

## Tests
Use interpreter-bound pytest to avoid system/venv mismatch:
```bash
python -m pytest
```

## Database loading
Enable in config (`load.write_to_db: true`) and set env vars:
```bash
export ETL_DB_USER=...
export ETL_DB_PASSWORD=...
```

Supported load config keys:
- `database_hostname`
- `database_port`
- `database_name`
- `database_table`
- `database_table_pk_column`
- optional: `database_mode` (`ignore` or `upsert`)
- optional: `database_batch_size` (default `1000`)

## CI/CD
- CI runs lint + tests on push/PR.
- Docker image is published to GHCR on version tags (`v*`).
- See operational guidance in [PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md).
