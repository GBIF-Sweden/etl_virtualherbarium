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


def _write_quality_report(config, config_path, action, source_files, extraction_quality, input_rows, rows_after_transform, final_rows, run_context):
    extract_cfg = config.get("extract", {})
    load_cfg = config.get("load", {})
    herbarium = str(extract_cfg.get("herbarium", "unknown")).lower()
    run_id = run_context.get("run_id")

    processed_path = _get_target_file_path(load_cfg) or ""
    output_dir = os.path.dirname(processed_path) if processed_path else os.path.join("data", "processed")
    os.makedirs(output_dir, exist_ok=True)

    report_path = os.path.join(output_dir, f"quality_report_{herbarium}_{run_id}.json")
    latest_path = os.path.join(output_dir, f"quality_report_{herbarium}.json")

    malformed_total = int(sum(item.get("malformed_rows", 0) for item in extraction_quality))
    repaired_total = int(sum(item.get("repaired_rows", 0) for item in extraction_quality))
    duplicates = run_context.get("quality", {}).get("duplicates", {})

    report = {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_path": config_path,
        "action": action,
        "herbarium": extract_cfg.get("herbarium"),
        "files_processed": len(source_files),
        "source_files": source_files,
        "extraction": {
            "input_rows_after_repair": input_rows,
            "repaired_rows_total": repaired_total,
            "malformed_rows_total": malformed_total,
            "by_file": extraction_quality,
            "detail": run_context.get("quality", {}).get("extraction_detail", []),
        },
        "transformation": {
            "rows_after_transformation": rows_after_transform,
            "duplicates": duplicates,
        },
        "output": {
            "final_rows": final_rows,
            "rows_dropped_total": int(input_rows - final_rows),
            "processed_file": _get_target_file_path(load_cfg),
            "column_quality": _column_quality_stats(run_context["final_df"]),
        },
    }

    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=True, indent=2)
    with open(latest_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=True, indent=2)
    return report_path


def _log_run_summary(config_path, action, report_path, run_context):
    q = run_context.get("quality", {})
    d = q.get("duplicates", {})
    logging.info(
        "SUMMARY config=%s action=%s repaired=%s malformed=%s dup_detected=%s dup_dropped=%s report=%s",
        config_path,
        action,
        q.get("repaired_rows_total", 0),
        q.get("malformed_rows_total", 0),
        d.get("duplicate_rows_detected", 0),
        d.get("duplicate_rows_dropped", 0),
        report_path,
    )
