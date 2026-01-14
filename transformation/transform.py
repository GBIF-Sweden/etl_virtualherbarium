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


def clean_whitespace(df):
    """
    Clean unwanted whitespaces, tabs, and carriage returns from all string columns in the DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame.

    Returns:
        pd.DataFrame: Cleaned DataFrame.
    """
    try:
        # Apply whitespace cleaning to each column
        df_cleaned = df.map(
            lambda x: ' '.join(str(x).split()).replace('\t', '').replace('\v', '') if isinstance(x, str) else x
        )
        logging.info(f"Whitespace cleaning transformation completed successfully.")
        return df_cleaned

    except Exception as e:
        logging.exception(f"An error occurred during clean_whitespace: {e}")
        raise


def generate_occ_id_triplet(df):
    """
    Apply transformations creating occurrence IDs.

    Args:
        df (pd.DataFrame): Input DataFrame.

    Returns:
        pd.DataFrame: Transformed DataFrame.
    """
    try:
        # Create occurrenceID by combining multiple fields
        df['occurrenceID'] = df['institutionCode'] + ':' + df['collectionCode'] + ':' + df['catalogNumber'].astype(str)
        # Reorder columns to move 'occurrenceID' to the first position
        cols = ['occurrenceID'] + [col for col in df.columns if col != 'occurrenceID']
        df = df[cols]
    except Exception as e:
        logging.exception(f"An unexpected error occurred in generate_occ_id_triplet: {e}")
        raise

    return df
