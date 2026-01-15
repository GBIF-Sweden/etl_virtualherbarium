import json
from pathlib import Path

import pandas as pd
import yaml

from main import run_pipeline


def _write_tsv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("\t".join(header) + "\r")
        for row in rows:
            fh.write("\t".join(row) + "\r")


def _make_config(tmp_path: Path, duplicate_policy="drop_all_duplicates"):
    cfg = {
        "extract": {
            "delimiter": "\\t",
            "quotechar": '"',
            "lineterminator": "\\r",
            "encoding": "utf-8",
            "verbatimFilePath": str(tmp_path / "verbatim"),
            "sourcerURL": "http://example.invalid",
            "herbarium": "TST",
            "dtype_dict": {"CatalogNumber": "string"},
        },
        "defaults": {"basisOfRecord": "PreservedSpecimen", "collectionCode": "BOT", "institutionCode": "TST"},
        "mappings": {"CatalogNumber": "catalogNumber", "ScientificName": "scientificName"},
        "unmapped": [],
        "transformations": [
            {"function": "generate_occ_id_triplet", "params": {}},
            {"function": "drop_duplicate_rows", "params": {}},
            {"function": "drop_empty_rows", "params": {"column_to_check": "catalogNumber"}},
            {"function": "drop_unmapped_columns", "params": {}},
        ],
        "load": {
            "database_table_pk_column": "occurrenceID",
            "duplicatePolicy": duplicate_policy,
            "delimiter": "\t",
            "encoding": "utf-8",
            "targetFilePath": str(tmp_path / "processed" / "dwc_tst.csv"),
            "write_to_file": True,
            "write_to_db": False,
            "dwc_fields": ["occurrenceID", "catalogNumber", "scientificName"],
        },
    }
    cfg_path = tmp_path / "config.yml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh)
    return cfg_path


def test_quality_report_and_repair(tmp_path):
    header = ["institutionCode", "CatalogNumber", "ScientificName"]
    rows = [
        ["TST", "A1", "Name1"],
        ["TST", "A1", "Name1-dup"],
        ["TST", "A2", "Name2", ""],  # extra trailing field -> repaired
    ]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)
    cfg_path = _make_config(tmp_path, duplicate_policy="drop_all_duplicates")

    run_pipeline(str(cfg_path), "process")

    report = json.loads((tmp_path / "processed" / "quality_report_tst.json").read_text(encoding="utf-8"))
    assert report["extraction"]["repaired_rows_total"] == 1
    assert report["transformation"]["duplicates"]["duplicate_rows_detected"] == 2
    assert report["output"]["final_rows"] == 1


def test_duplicate_policy_keep_first(tmp_path):
    header = ["institutionCode", "CatalogNumber", "ScientificName"]
    rows = [["TST", "A1", "Name1"], ["TST", "A1", "Name1-dup"], ["TST", "A2", "Name2"]]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)
    cfg_path = _make_config(tmp_path, duplicate_policy="keep_first")

    run_pipeline(str(cfg_path), "process")
    out = pd.read_csv(tmp_path / "processed" / "dwc_tst.csv", sep="\t")
    assert len(out) == 2
    assert set(out["catalogNumber"]) == {"A1", "A2"}


def test_strict_thresholds_fail(tmp_path):
    header = ["institutionCode", "CatalogNumber", "ScientificName"]
    rows = [["TST", "A1", "Name1"], ["TST", "A1", "Name1-dup"]]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)
    cfg_path = _make_config(tmp_path, duplicate_policy="drop_all_duplicates")

    failed = False
    try:
        run_pipeline(str(cfg_path), "process", strict=True)
    except RuntimeError:
        failed = True
    assert failed


def test_regression_output_snapshot(tmp_path):
    header = ["institutionCode", "CatalogNumber", "ScientificName"]
    rows = [["TST", "A1", "Name1"], ["TST", "A1", "Name1-dup"], ["TST", "A2", "Name2"]]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)
    cfg_path = _make_config(tmp_path, duplicate_policy="keep_first")

    run_pipeline(str(cfg_path), "process")

    produced = (tmp_path / "processed" / "dwc_tst.csv").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    expected = (Path(__file__).parent / "fixtures" / "expected_dwc_tst.tsv").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    assert produced == expected
