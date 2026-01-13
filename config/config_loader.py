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


def load_yaml_config(config_path):
    try:
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logging.exception(f"Error: Configuration file not found at {config_path}.")
        raise
    except yaml.YAMLError:
        logging.exception("Error: Failed to parse YAML from the configuration file.")
        raise


def validate_pipeline_config(config: dict) -> Tuple[bool, List[str]]:
    errors = []
    if not isinstance(config, dict):
        return False, ["Configuration root must be a mapping/object."]

    if "extract" not in config or not isinstance(config["extract"], dict):
        errors.append("Missing required 'extract' section.")
    if "mappings" not in config or not isinstance(config["mappings"], dict):
        errors.append("Missing required 'mappings' section.")
    if "load" not in config or not isinstance(config["load"], dict):
        errors.append("Missing required 'load' section.")

    if errors:
        return False, errors

    return len(errors) == 0, errors
