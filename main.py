import argparse
import logging
from pipeline import run_pipeline
from utils.logging_utils import configure_logging


configure_logging()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Swedish Virtual Herbarium Data Harvester.")
    parser.add_argument("config_path", nargs="?", type=str, help="Positional config path (legacy compatibility).")
    parser.add_argument("--config", nargs="+", dest="config_paths", help="One or more config paths.")
    parser.add_argument("--action", choices=["download", "process", "all"], default="all", help="Action to perform.")
    parser.add_argument("--strict", action="store_true", help="Enable strict quality thresholds.")
    args = parser.parse_args()

    config_paths = args.config_paths or ([args.config_path] if args.config_path else [])
    if not config_paths:
        parser.error("Provide config path(s) using --config or positional config_path.")

    for cfg in config_paths:
        logging.info("Running action '%s' for config: %s", args.action, cfg)
        run_pipeline(
            cfg,
            args.action,
            strict=args.strict,
        )
