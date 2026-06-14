import glob
import json
import logging
import os
from datetime import datetime, timezone

from config.config_loader import load_yaml_config, validate_pipeline_config
from extraction.extract import download_files_iteratively, read_csv_into_dataframe
from loading.load import save_to_database
from transformation.transform import apply_transformations


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
    if violations:
        raise RuntimeError("Strict quality checks failed: " + "; ".join(violations))
    if dup_dropped > 0:
        logging.warning(
            "Strict mode: duplicate_rows_dropped=%s (allowed, but monitor data quality).",
            dup_dropped,
        )
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


def run_pipeline(config_path, action, strict=False):
    config = load_yaml_config(config_path)
    valid, errors = validate_pipeline_config(config)
    if not valid:
        raise ValueError(f"Invalid config {config_path}: " + " | ".join(errors))

    extract_config = config["extract"]
    load_config = config["load"]
    run_context = {"run_id": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"), "quality": {}}

    downloaded_files = []
    if action in ["download", "all"]:
        downloaded_files = download_files_iteratively(
            extract_config.get("sourcerURL"),
            extract_config.get("herbarium"),
            extract_config.get("verbatimFilePath"),
            max_page_retries=int(extract_config.get("download_page_max_retries", 3)),
            retry_sleep_seconds=int(extract_config.get("download_retry_sleep_seconds", 2)),
        )
        logging.info("Downloaded %s files for %s.", len(downloaded_files), extract_config.get("herbarium"))

    if action == "download":
        logging.info("Download step completed.")
        return

    source_files = downloaded_files if downloaded_files else _find_existing_verbatim_files(extract_config)
    if not source_files:
        logging.warning(
            "No source files found for herbarium '%s' in '%s'.",
            extract_config.get("herbarium"),
            extract_config.get("verbatimFilePath"),
        )
        return

    df, extraction_quality = read_csv_into_dataframe(source_files, extract_config, run_context=run_context)
    input_rows = int(len(df))
    run_context["quality"]["repaired_rows_total"] = int(sum(item.get("repaired_rows", 0) for item in extraction_quality))
    run_context["quality"]["malformed_rows_total"] = int(sum(item.get("malformed_rows", 0) for item in extraction_quality))

    if len(df) == 0:
        logging.warning("No rows available after extraction.")
        return

    df = apply_transformations(df, config, run_context=run_context)
    rows_after_transform = int(len(df))
    logging.info("Number of rows after transformation: %s.", df.shape[0])
    logging.info("Number of columns after transformation: %s.", df.shape[1])

    dwc_fields = load_config.get("dwc_fields", [])
    if dwc_fields:
        df = df[dwc_fields]
    run_context["final_df"] = df
    _enforce_strict_quality(run_context, strict)

    processed_file_path = _get_target_file_path(load_config)
    if load_config.get("write_to_file") and processed_file_path:
        os.makedirs(os.path.dirname(processed_file_path), exist_ok=True)
        df.to_csv(
            processed_file_path,
            sep=load_config.get("delimiter", "\t"),
            encoding=load_config.get("encoding", "utf-8"),
            index=False,
        )

    if load_config.get("write_to_db"):
        save_to_database(df, load_config)

    report_path = _write_quality_report(
        config=config,
        config_path=config_path,
        action=action,
        source_files=source_files,
        extraction_quality=extraction_quality,
        input_rows=input_rows,
        rows_after_transform=rows_after_transform,
        final_rows=int(len(df)),
        run_context=run_context,
    )
    _log_run_summary(config_path, action, report_path, run_context)
    logging.info("ETL process completed successfully!")

