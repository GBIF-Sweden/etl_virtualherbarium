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


def drop_columns(df, columns_to_drop):
    """
    Drops specified columns from the DataFrame if they exist.

    Args:
        df (pd.DataFrame): Input DataFrame.
        columns_to_drop (str or list): Column name or list of column names to drop.

    Returns:
        pd.DataFrame: DataFrame after dropping specified columns.
    """
    df = df.copy()
    try:
        # Convert single column name (string) to a list
        if isinstance(columns_to_drop, str):
            columns_to_drop = [columns_to_drop] or []
        if columns_to_drop:
            # Only drop columns that exist in the DataFrame
            columns_to_drop = [col for col in (columns_to_drop or []) if col in df.columns]
            df.drop(columns=columns_to_drop, inplace=True)
        return df
    except KeyError as e:
        logging.error(f"Error: One or more unmapped columns not found in DataFrame: {e}")
        raise
    except Exception as e:
        logging.exception(f"An unexpected error occurred in drop_unmapped_columns: {e}")
        raise


def drop_unmapped_columns(df, config, run_context=None):
    """
    Drop specified columns from the DataFrame based on the configuration.

    Args:
        df (pd.DataFrame): Input DataFrame.
        config (dict): Configuration dictionary.

    Returns:
        pd.DataFrame: DataFrame after dropping specified columns.
    """
    unmapped_columns = config.get('unmapped', [])
    df = df.copy()
    try:
        drop_columns(df, unmapped_columns)
        df.drop(columns=[col for col in unmapped_columns if col in df.columns], inplace=True)
        logging.info("drop_unmapped_columns transformation completed successfully.")
        return df
    except Exception as e:
        logging.error(f"An error occurred while dropping unmapped columns: {e}")
        raise


def clean_extra_quotes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Removes extra single or double quotes enclosing values in a pandas DataFrame.

    Args:
        df: The input DataFrame to clean.

    Returns:
        A DataFrame with extra quotes removed.
    """

    def remove_quotes(value: str) -> str:
        """
        Removes surrounding single or double quotes from a string.

        Args:
            value: The input string.

        Returns:
            The string with quotes removed.
        """

        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            return value[1:-1]
        else:
            return value

    # Apply the function to all string columns
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].apply(remove_quotes)

    return df


def copyColumn(df, srcColumn, targetColumn):
    # Copy values from srcColumn to targetColumn
    df[targetColumn] = df[srcColumn]
    return df


def drop_empty_rows(df, column_to_check):
    """
    Drop rows where the specified column is empty or null.

    Args:
        df (pd.DataFrame): The input DataFrame.
        column_to_check (str): The column name to check for empty or null values.

    Returns:
        pd.DataFrame: The updated DataFrame with the rows dropped.
    """
    try:
        if column_to_check not in df.columns:
            raise ValueError(f"Column '{column_to_check}' does not exist in the DataFrame.")

        # Drop rows where the specified column is null
        df = df.dropna(subset=[column_to_check])

        num_empty_rows = (df[column_to_check] == "").sum()
        # Drop rows where the specified column is an empty string
        df = df[df[column_to_check] != '']

        logging.info(f"Dropping '{num_empty_rows}' rows with empty '{column_to_check}' completed successfully.")
        return df

    except ValueError as ve:
        logging.error(f"ValueError: {ve}")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
