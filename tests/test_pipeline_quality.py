import json
from pathlib import Path

import pandas as pd
import yaml

from config.config_loader import validate_pipeline_config
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


def test_strict_allows_repaired_rows(tmp_path):
    header = ["institutionCode", "CatalogNumber", "ScientificName"]
    rows = [["TST", "A1", "Name1"], ["TST", "A2"]]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)
    cfg_path = _make_config(tmp_path, duplicate_policy="drop_all_duplicates")

    run_pipeline(str(cfg_path), "process", strict=True)

    report = json.loads((tmp_path / "processed" / "quality_report_tst.json").read_text(encoding="utf-8"))
    assert report["extraction"]["repaired_rows_total"] == 1
    assert report["output"]["final_rows"] == 2


def test_strict_allows_duplicate_cleanup(tmp_path):
    header = ["institutionCode", "CatalogNumber", "ScientificName"]
    rows = [["TST", "A1", "Name1"], ["TST", "A1", "Name1-dup"]]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)
    cfg_path = _make_config(tmp_path, duplicate_policy="drop_all_duplicates")

    run_pipeline(str(cfg_path), "process", strict=True)

    report = json.loads((tmp_path / "processed" / "quality_report_tst.json").read_text(encoding="utf-8"))
    assert report["transformation"]["duplicates"]["duplicate_rows_dropped"] == 2


def test_regression_output_snapshot(tmp_path):
    header = ["institutionCode", "CatalogNumber", "ScientificName"]
    rows = [["TST", "A1", "Name1"], ["TST", "A1", "Name1-dup"], ["TST", "A2", "Name2"]]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)
    cfg_path = _make_config(tmp_path, duplicate_policy="keep_first")

    run_pipeline(str(cfg_path), "process")

    produced = (tmp_path / "processed" / "dwc_tst.csv").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    expected = (Path(__file__).parent / "fixtures" / "expected_dwc_tst.tsv").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    assert produced == expected


def test_unescaped_quotes_and_newlines_in_notes(tmp_path):
    header = ["institutionCode", "CatalogNumber", "ScientificName", "Notes"]
    # Write a row where Notes contains unescaped quotes and a newline \n, wrapped in outer quotes
    rows = [
        ["TST", "A1", "Name1", '"1. Note with "unescaped" quotes\n2. And a newline"'],
        ["TST", "A2", "Name2", '"Normal note with no newline"'],
    ]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)

    # We need to make a custom config that includes Notes / occurrenceRemarks
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
        "mappings": {"CatalogNumber": "catalogNumber", "ScientificName": "scientificName", "Notes": "occurrenceRemarks"},
        "unmapped": [],
        "transformations": [
            {"function": "generate_occ_id_triplet", "params": {}},
            {"function": "drop_duplicate_rows", "params": {}},
            {"function": "drop_empty_rows", "params": {"column_to_check": "catalogNumber"}},
            {"function": "drop_unmapped_columns", "params": {}},
        ],
        "load": {
            "database_table_pk_column": "occurrenceID",
            "duplicatePolicy": "keep_first",
            "delimiter": "\t",
            "encoding": "utf-8",
            "targetFilePath": str(tmp_path / "processed" / "dwc_tst.csv"),
            "write_to_file": True,
            "write_to_db": False,
            "dwc_fields": ["occurrenceID", "catalogNumber", "scientificName", "occurrenceRemarks"],
        },
    }
    cfg_path = tmp_path / "config.yml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh)

    run_pipeline(str(cfg_path), "process")

    out = pd.read_csv(tmp_path / "processed" / "dwc_tst.csv", sep="\t")
    assert len(out) == 2
    assert out.iloc[0]["occurrenceRemarks"] == '1. Note with "unescaped" quotes\n2. And a newline'
    assert out.iloc[1]["occurrenceRemarks"] == 'Normal note with no newline'


def test_repairs_unescaped_tab_in_locality_without_shifting_columns(tmp_path):
    header = ["institutionCode", "CatalogNumber", "Locality", "WGS84N", "WGS84S", "ScientificName"]
    rows = [
        ["TST", "A1", "North slope", "59.1", "18.2", "Name1"],
        ["TST", "A2", "South", "slope", "60.1", "19.2", "Name2"],
    ]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)

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
            "repair_text_columns": ["Locality"],
        },
        "defaults": {"basisOfRecord": "PreservedSpecimen", "collectionCode": "BOT", "institutionCode": "TST"},
        "mappings": {
            "CatalogNumber": "catalogNumber",
            "Locality": "locality",
            "WGS84N": "decimalLatitude",
            "WGS84S": "decimalLongitude",
            "ScientificName": "scientificName",
        },
        "unmapped": [],
        "transformations": [
            {"function": "generate_occ_id_triplet", "params": {}},
            {"function": "drop_duplicate_rows", "params": {}},
            {"function": "drop_empty_rows", "params": {"column_to_check": "catalogNumber"}},
            {"function": "drop_unmapped_columns", "params": {}},
        ],
        "load": {
            "database_table_pk_column": "occurrenceID",
            "duplicatePolicy": "keep_first",
            "delimiter": "\t",
            "encoding": "utf-8",
            "targetFilePath": str(tmp_path / "processed" / "dwc_tst.csv"),
            "write_to_file": True,
            "write_to_db": False,
            "dwc_fields": ["occurrenceID", "catalogNumber", "locality", "decimalLatitude", "decimalLongitude", "scientificName"],
        },
    }
    cfg_path = tmp_path / "config.yml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh)

    run_pipeline(str(cfg_path), "process")

    out = pd.read_csv(tmp_path / "processed" / "dwc_tst.csv", sep="\t")
    repaired = out[out["catalogNumber"] == "A2"].iloc[0]
    assert repaired["locality"] == "South slope"
    assert str(repaired["decimalLatitude"]) == "60.1"
    assert str(repaired["decimalLongitude"]) == "19.2"

    report = json.loads((tmp_path / "processed" / "quality_report_tst.json").read_text(encoding="utf-8"))
    assert report["extraction"]["repaired_rows_total"] == 1
    assert report["extraction"]["malformed_rows_total"] == 0
    assert report["extraction"]["detail"][0]["targeted_repairs"] == 1


def test_config_rejects_unknown_transformation(tmp_path):
    cfg = {
        "extract": {
            "delimiter": "\\t",
            "quotechar": '"',
            "lineterminator": "\\r",
            "encoding": "utf-8",
            "verbatimFilePath": str(tmp_path / "verbatim"),
            "sourcerURL": "http://example.invalid",
            "herbarium": "TST",
        },
        "defaults": {"basisOfRecord": "PreservedSpecimen", "collectionCode": "BOT", "institutionCode": "TST"},
        "mappings": {"CatalogNumber": "catalogNumber"},
        "unmapped": [],
        "transformations": [{"function": "does_not_exist", "params": {}}],
        "load": {
            "database_table_pk_column": "occurrenceID",
            "delimiter": "\t",
            "encoding": "utf-8",
            "targetFilePath": str(tmp_path / "processed" / "dwc_tst.csv"),
            "write_to_file": True,
            "write_to_db": False,
        },
    }
    valid, errors = validate_pipeline_config(cfg)
    assert not valid
    assert any("does_not_exist" in error for error in errors)


def test_overwide_row_without_confident_repair_is_audited_as_malformed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    header = ["institutionCode", "CatalogNumber", "Locality", "WGS84N", "WGS84S", "ScientificName"]
    rows = [
        ["TST", "A1", "North slope", "59.1", "18.2", "Name1"],
        ["TST", "A2", "South", "slope", "not-a-latitude", "19.2", "Name2"],
    ]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)

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
            "repair_text_columns": ["Locality"],
        },
        "defaults": {"basisOfRecord": "PreservedSpecimen", "collectionCode": "BOT", "institutionCode": "TST"},
        "mappings": {
            "CatalogNumber": "catalogNumber",
            "Locality": "locality",
            "WGS84N": "decimalLatitude",
            "WGS84S": "decimalLongitude",
            "ScientificName": "scientificName",
        },
        "unmapped": [],
        "transformations": [
            {"function": "generate_occ_id_triplet", "params": {}},
            {"function": "drop_duplicate_rows", "params": {}},
            {"function": "drop_empty_rows", "params": {"column_to_check": "catalogNumber"}},
            {"function": "drop_unmapped_columns", "params": {}},
        ],
        "load": {
            "database_table_pk_column": "occurrenceID",
            "duplicatePolicy": "keep_first",
            "delimiter": "\t",
            "encoding": "utf-8",
            "targetFilePath": str(tmp_path / "processed" / "dwc_tst.csv"),
            "write_to_file": True,
            "write_to_db": False,
            "dwc_fields": ["occurrenceID", "catalogNumber", "locality", "decimalLatitude", "decimalLongitude", "scientificName"],
        },
    }
    cfg_path = tmp_path / "config.yml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh)

    run_pipeline(str(cfg_path), "process")

    out = pd.read_csv(tmp_path / "processed" / "dwc_tst.csv", sep="\t")
    assert len(out) == 1
    assert set(out["catalogNumber"]) == {"A1"}

    report = json.loads((tmp_path / "processed" / "quality_report_tst.json").read_text(encoding="utf-8"))
    assert report["extraction"]["repaired_rows_total"] == 0
    assert report["extraction"]["malformed_rows_total"] == 1
    assert Path("data/malformed/TST_1_malformed.csv").exists()


def test_repairs_extra_empty_shift_before_date_collected(tmp_path):
    header = [
        "institutionCode",
        "CatalogNumber",
        "Collector",
        "collectornumber",
        "DateCollected",
        "Notes",
        "Comments",
        "Continent",
        "Country",
        "Province",
        "District",
        "Locality",
        "WGS84N",
        "WGS84S",
        "CSource",
        "coordinateUncertaintyInMeters",
        "CValue",
        "ScientificName",
        "Genus",
        "SpecificEpithet",
        "IntraspecificEpithet",
        "RT90-N",
        "RT90-E",
        "RUBIN",
        "OriginalName",
        "OriginalText",
        "Type-status",
        "TAuctor",
        "Basionym",
        "georeferenceRemarks",
        "ImageLinks",
        "ImageThumbLinks",
    ]
    rows = [
        [
            "UME",
            "26481",
            "C. P. Laestadius",
            "",
            "",
            "",
            "",
            "1910-5-6",
            '""',
            '"Matrix: Arctostaphylos"',
            "Europe",
            "Sweden",
            "Västerbotten",
            "Umeå",
            "Skravelsjöberget",
            "63.791697667939",
            "20.15122323041",
            "Locality",
            "1000",
            "Skravelsjöberget",
            "Lembosina gontardii",
            "Lembosina",
            "gontardii",
            "",
            "",
            "",
            "",
            '"Gloeosporium alpinum"',
            '"VÄSTERBOTTEN: Umeå, Skravelsjöberget. På Arctostaphylos."',
            "",
            '""',
            "",
            '"Coordinate generated from Locality: Skravelsjöberget Precision: 1000m"',
            "",
            "",
        ],
    ]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)

    cfg_path = _make_config(tmp_path, duplicate_policy="keep_first")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["mappings"] = {
        "CatalogNumber": "catalogNumber",
        "DateCollected": "eventDate",
        "Comments": "occurrenceRemarks",
        "Locality": "locality",
        "WGS84N": "decimalLatitude",
        "WGS84S": "decimalLongitude",
        "ScientificName": "scientificName",
    }
    cfg["unmapped"] = [col for col in header if col not in cfg["mappings"] and col != "institutionCode"]
    cfg["load"]["dwc_fields"] = [
        "occurrenceID",
        "catalogNumber",
        "eventDate",
        "occurrenceRemarks",
        "locality",
        "decimalLatitude",
        "decimalLongitude",
        "scientificName",
    ]
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    run_pipeline(str(cfg_path), "process", strict=True)

    out = pd.read_csv(tmp_path / "processed" / "dwc_tst.csv", sep="\t")
    row = out.iloc[0]
    assert row["eventDate"] == "1910-5-6"
    assert row["occurrenceRemarks"] == "Matrix: Arctostaphylos"
    assert row["locality"] == "Skravelsjöberget"
    assert str(row["decimalLatitude"]) == "63.791697667939"
    assert str(row["decimalLongitude"]) == "20.15122323041"

    report = json.loads((tmp_path / "processed" / "quality_report_tst.json").read_text(encoding="utf-8"))
    assert report["extraction"]["repaired_rows_total"] == 1
    assert report["extraction"]["malformed_rows_total"] == 0


def test_repairs_extra_empty_shift_before_coordinates_even_with_empty_tail(tmp_path):
    header = [
        "institutionCode",
        "CatalogNumber",
        "Collector",
        "collectornumber",
        "DateCollected",
        "Notes",
        "Comments",
        "Continent",
        "Country",
        "Province",
        "District",
        "Locality",
        "WGS84N",
        "WGS84S",
        "CSource",
        "coordinateUncertaintyInMeters",
        "CValue",
        "ScientificName",
        "Genus",
        "SpecificEpithet",
        "IntraspecificEpithet",
        "RT90-N",
        "RT90-E",
        "RUBIN",
        "OriginalName",
        "OriginalText",
        "Type-status",
        "TAuctor",
        "Basionym",
        "georeferenceRemarks",
        "ImageLinks",
        "ImageThumbLinks",
    ]
    rows = [
        [
            "UME",
            "115274",
            "Niklas Lönnell",
            "",
            "1996-9-11",
            '""',
            '""',
            "Europe",
            "Sweden",
            "Medelpad",
            "Torp",
            "Bäråsbäcken N om Öratjärnsåsen, 800 m N om V Vattutjärnen",
            "",
            "",
            "62.315617215801",
            "16.248566713558",
            "RT90-coordinates",
            "100",
            "6911554N, 1522999E",
            "Scapania undulata",
            "Scapania",
            "undulata",
            "",
            "6911554",
            "1522999",
            "",
            '"Scapania undulata"',
            '"Bäråsbäcken N om Öratjärnsåsen, 800 m N om V Vattutjärnen, RT90: 6911554 - 1522999"',
            "",
            '""',
            "",
            '"Coordinate generated from RT90-coordinates: 6911554N, 1522999E Precision: 100m"',
            "",
            "",
        ],
    ]
    _write_tsv(tmp_path / "verbatim" / "TST_1.csv", header, rows)

    cfg_path = _make_config(tmp_path, duplicate_policy="keep_first")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["mappings"] = {
        "CatalogNumber": "catalogNumber",
        "DateCollected": "eventDate",
        "Locality": "locality",
        "WGS84N": "decimalLatitude",
        "WGS84S": "decimalLongitude",
        "CSource": "georeferenceSources",
        "coordinateUncertaintyInMeters": "coordinateUncertaintyInMeters",
        "CValue": "verbatimCoordinates",
        "ScientificName": "scientificName",
        "Genus": "genus",
        "SpecificEpithet": "specificEpithet",
        "RT90-N": "verbatimLatitude",
        "RT90-E": "verbatimLongitude",
    }
    cfg["unmapped"] = [col for col in header if col not in cfg["mappings"] and col != "institutionCode"]
    cfg["load"]["dwc_fields"] = [
        "occurrenceID",
        "catalogNumber",
        "eventDate",
        "locality",
        "decimalLatitude",
        "decimalLongitude",
        "georeferenceSources",
        "coordinateUncertaintyInMeters",
        "verbatimCoordinates",
        "scientificName",
        "genus",
        "specificEpithet",
        "verbatimLatitude",
        "verbatimLongitude",
    ]
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    run_pipeline(str(cfg_path), "process", strict=True)

    out = pd.read_csv(tmp_path / "processed" / "dwc_tst.csv", sep="\t")
    row = out.iloc[0]
    assert str(row["decimalLatitude"]) == "62.315617215801"
    assert str(row["decimalLongitude"]) == "16.248566713558"
    assert row["georeferenceSources"] == "RT90-coordinates"
    assert str(row["coordinateUncertaintyInMeters"]) == "100"
    assert row["scientificName"] == "Scapania undulata"
    assert row["genus"] == "Scapania"
    assert row["specificEpithet"] == "undulata"
    assert str(row["verbatimLatitude"]) == "6911554"
    assert str(row["verbatimLongitude"]) == "1522999"

    report = json.loads((tmp_path / "processed" / "quality_report_tst.json").read_text(encoding="utf-8"))
    assert report["extraction"]["repaired_rows_total"] == 1
    assert report["extraction"]["malformed_rows_total"] == 0
