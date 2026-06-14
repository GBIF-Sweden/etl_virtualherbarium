# etl_virtualherbarium

ETL pipeline for harvesting and transforming data from Swedish Virtual Herbarium (https://herbarium.emg.umu.se/) into DarwinCore standard.

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
- `--strict`: fail if malformed rows are non-zero; repaired rows and dropped duplicates are logged as warnings

## Extraction repair
The upstream exporter writes tab-separated data manually, so raw tabs inside text fields can shift later values into the wrong columns. During extraction, the pipeline normalizes each verbatim file before pandas reads it:

- Rows with trailing empty surplus columns are truncated back to the expected header width.
- Rows shifted by surplus empty fields are repaired only when validation keeps dates, coordinates, geography, scientific names, and georeference fields plausible.
- Rows with tabs inside known text fields such as `Locality`, `OriginalName`, `OriginalText`, `Notes`, `Comments`, or `georeferenceRemarks` are repaired by merging the split field when the result is the best validated candidate.
- Rows that cannot be repaired confidently are written to `data/malformed/<source>_malformed.csv` and counted as malformed.

Optional extract config keys:
```yaml
extract:
  repair_text_columns:
    - Locality
    - OriginalName
    - OriginalText
    - Notes
    - Comments
    - georeferenceRemarks
  repair_validation:
    WGS84N: numeric_or_empty
    WGS84S: numeric_or_empty
    DateCollected: date_or_empty
```

Supported validation rules are `non_empty`, `numeric_or_empty`, `date_or_empty`, `text_or_empty`, and `known_continent_or_empty`.

## Output
- Processed files: `data/processed/dwc_<herbarium>.csv`
- Quality reports:
  - `data/processed/quality_report_<herbarium>_<runid>.json`
  - `data/processed/quality_report_<herbarium>.json` (latest)
- Duplicate audit (if duplicates exist): `data/processed/duplicates_<herbarium>.csv`
- Malformed rows (if any): `data/malformed/<source>_malformed.csv`

## Docker

### Building the Image
The Docker image contains only the runtime files necessary to execute the pipeline. You can build it using the provided `Makefile` or the Docker CLI.

**Using Make:**
```bash
make build
```

**Using Docker CLI:**
```bash
docker build -t etl_virtualherbarium:latest .
```

### Running with Compose
The recommended way to run the pipeline in a container is via Docker Compose, which handles volume mounting for logs and data:

```bash
docker compose up --build
```

Environment overrides:
- `CONFIG_PATH` (default `config-mappings/ume.yml`)
- `ACTION` (default `process`)

Image notes:
- The image includes the application code and dependencies but excludes tests, local logs, and environment files.

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
