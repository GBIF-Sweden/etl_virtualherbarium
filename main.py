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
