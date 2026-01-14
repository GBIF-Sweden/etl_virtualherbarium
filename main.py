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
