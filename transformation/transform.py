import pandas as pd
import logging
import os


def apply_transformations(df, config, run_context=None):
    try:
        # Rename columns
        df.rename(columns=config['mappings'], inplace=True)

        # Add default values
        for col, default_value in config.get('defaults', {}).items():
            df[col] = default_value

        # Apply transformations
        transformations = config.get('transformations', [])
        for transformation in transformations:
            func_name = transformation.get('function')
            params = transformation.get('params', {})
            logging.info(f"Running Transformation function {func_name}")
            # Call transformation function dynamically
            if func_name in globals():
                if func_name in ["add_dynamicProperties", "vernacular_to_scientificName", "drop_unmapped_columns", "drop_duplicate_rows"]:
                    df = globals()[func_name](df, config, run_context=run_context)
                else:
                    df = globals()[func_name](df, **params)
            else:
                logging.info(f"Transformation function {func_name} not found. Skipping.")

        return df
    except Exception as e:
        logging.error(f"An error occurred during transformation: {e}")
        raise
