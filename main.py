import argparse
import glob
import json
import logging
import os
from datetime import datetime, timezone

from config.config_loader import load_yaml_config, validate_pipeline_config
from extraction.extract import download_files_iteratively, read_csv_into_dataframe
from loading.load import save_to_database
from transformation.transform import apply_transformations
from utils.logging_utils import configure_logging


configure_logging()


def _find_existing_verbatim_files(extract_config):
    herbarium = extract_config.get("herbarium")
    verbatim_dir = extract_config.get("verbatimFilePath")
    if not herbarium or not verbatim_dir:
        return []
    pattern = os.path.join(verbatim_dir, f"{herbarium}_*.csv")
    return sorted(glob.glob(pattern))


def _get_target_file_path(load_config):
    return load_config.get("targetFilePath") or load_config.get("targeFilePath")


def _column_quality_stats(df):
    out = {}
    for col in ["catalogNumber", "scientificName", "decimalLatitude", "decimalLongitude"]:
        if col in df.columns:
            nulls = int(df[col].isna().sum())
            empties = int((df[col] == "").sum()) if df[col].dtype == "object" else 0
            out[col] = {"null": nulls, "empty": empties}
    return out


def _enforce_strict_quality(run_context, strict):
    if not strict:
        return
    quality = run_context.get("quality", {})
    repaired = int(quality.get("repaired_rows_total", 0))
    malformed = int(quality.get("malformed_rows_total", 0))
    dup_dropped = int(quality.get("duplicates", {}).get("duplicate_rows_dropped", 0))
    violations = []
    if malformed > 0:
        violations.append(f"malformed_rows_total={malformed}")
    if dup_dropped > 0:
        violations.append(f"duplicate_rows_dropped={dup_dropped}")
    if violations:
        raise RuntimeError("Strict quality checks failed: " + "; ".join(violations))
    if repaired > 0:
        logging.warning("Strict mode: repaired_rows_total=%s (allowed, but monitor data quality).", repaired)
