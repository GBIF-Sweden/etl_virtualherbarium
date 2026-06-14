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

    extract = config["extract"]
    load = config["load"]

    required_extract = ["delimiter", "quotechar", "lineterminator", "verbatimFilePath", "herbarium"]
    for key in required_extract:
        if key not in extract:
            errors.append(f"Missing required extract field: '{key}'.")

    if "database_table_pk_column" not in load:
        errors.append("Missing required load field: 'database_table_pk_column'.")

    # Backward-compatible output path aliasing.
    target_path = load.get("targetFilePath") or load.get("targeFilePath")
    if load.get("write_to_file") and not target_path:
        errors.append("write_to_file=true requires either 'targetFilePath' or 'targeFilePath'.")

    duplicate_policy = load.get("duplicatePolicy", "drop_all_duplicates")
    valid_policies = {"drop_all_duplicates", "keep_first", "keep_last", "write_only"}
    if duplicate_policy not in valid_policies:
        errors.append(
            f"Invalid duplicatePolicy '{duplicate_policy}'. Valid values: {sorted(valid_policies)}."
        )

    if load.get("write_to_db"):
        required_db_keys = ["database_hostname", "database_port", "database_name", "database_table"]
        for key in required_db_keys:
            if key not in load or str(load.get(key)).strip() == "":
                errors.append(f"write_to_db=true requires load.{key}.")

        db_mode = load.get("database_mode", "upsert")
        if db_mode not in {"ignore", "upsert"}:
            errors.append("load.database_mode must be 'ignore' or 'upsert'.")

        batch_size = load.get("database_batch_size", 1000)
        try:
            if int(batch_size) <= 0:
                errors.append("load.database_batch_size must be a positive integer.")
        except Exception:
            errors.append("load.database_batch_size must be an integer.")

    try:
        from transformation.registry import available_transformations, resolve_transformation_name

        known_transformations = set(available_transformations())
        transformations = config.get("transformations", [])
        if transformations is not None and not isinstance(transformations, list):
            errors.append("'transformations' section must be a list if present.")
        for idx, transformation in enumerate(transformations or []):
            if not isinstance(transformation, dict):
                errors.append(f"Transformation entry at index {idx} must be a mapping/object.")
                continue
            func_name = transformation.get("function")
            if not isinstance(func_name, str) or not func_name.strip():
                errors.append(f"Transformation entry at index {idx} requires a non-empty 'function' name.")
                continue
            resolved = resolve_transformation_name(func_name)
            if resolved not in known_transformations:
                errors.append(
                    f"Unknown transformation function '{func_name}'. "
                    f"Valid values: {sorted(known_transformations)}."
                )
            params = transformation.get("params", {})
            if params is not None and not isinstance(params, dict):
                errors.append(f"Transformation '{func_name}' params must be a mapping/object.")
    except Exception as exc:
        errors.append(f"Failed to validate transformation registry: {exc}")

    return len(errors) == 0, errors
