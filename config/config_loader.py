import json
import yaml
import logging
from typing import Tuple, List

def load_json_config(config_path):
    try:
        with open(config_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        logging.exception(f"Error: Configuration file not found at {config_path}.")
        raise
    except json.JSONDecodeError:
        logging.exception("Error: Failed to decode JSON from the configuration file.")
        raise
