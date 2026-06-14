import pandas as pd
import logging
import os

from transformation.registry import get_transformation, is_config_aware, resolve_transformation_name


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
            resolved_name = resolve_transformation_name(func_name)
            logging.info("Running Transformation function %s", resolved_name)
            transform_fn = get_transformation(func_name)
            if transform_fn is None:
                raise ValueError(f"Transformation function '{func_name}' not found.")
            if is_config_aware(func_name):
                df = transform_fn(df, config, run_context=run_context)
            else:
                df = transform_fn(df, **params)

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
        logging.info("Whitespace cleaning transformation completed successfully.")
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

def drop_duplicate_rows(df, config, run_context=None):
    """
    Removes duplicate rows from the DataFrame based on the specified primary key column.

    Args:
        df (pd.DataFrame): Input DataFrame.
        config (dict): Configuration dictionary.

    Returns:
        pd.DataFrame: DataFrame with duplicate rows removed based on the primary key column.
    """
    load_config = config.get('load', {})
    pk_column = load_config.get('database_table_pk_column')
    if pk_column not in df.columns:
        raise ValueError(f"Primary key column '{pk_column}' not found in DataFrame.")

    duplicate_policy = load_config.get("duplicatePolicy", "drop_all_duplicates")

    duplicate_mask = df.duplicated(subset=pk_column, keep=False)
    duplicates_df = df[duplicate_mask].copy()
    duplicate_keys = int(duplicates_df[pk_column].nunique()) if not duplicates_df.empty else 0

    # Write dropped duplicate rows to an audit file.
    duplicates_file = None
    if not duplicates_df.empty:
        processed_path = load_config.get('targetFilePath') or load_config.get('targeFilePath', '')
        output_dir = os.path.dirname(processed_path) if processed_path else os.path.join('data', 'processed')
        os.makedirs(output_dir, exist_ok=True)

        herbarium = config.get('extract', {}).get('herbarium', 'unknown')
        duplicates_file = os.path.join(output_dir, f"duplicates_{str(herbarium).lower()}.csv")
        duplicates_df.to_csv(duplicates_file, sep=load_config.get('delimiter', '\t'), index=False)
        logging.info(f"Wrote {len(duplicates_df)} duplicate rows to {duplicates_file}.")

    if duplicate_policy == "drop_all_duplicates":
        df_result = df[~df[pk_column].isin(duplicates_df[pk_column])].reset_index(drop=True)
    elif duplicate_policy == "keep_first":
        df_result = df.drop_duplicates(subset=pk_column, keep="first").reset_index(drop=True)
    elif duplicate_policy == "keep_last":
        df_result = df.drop_duplicates(subset=pk_column, keep="last").reset_index(drop=True)
    elif duplicate_policy == "write_only":
        df_result = df.reset_index(drop=True)
    else:
        raise ValueError(f"Unsupported duplicatePolicy: {duplicate_policy}")

    if run_context is not None:
        run_context.setdefault("quality", {})["duplicates"] = {
            "pk_column": pk_column,
            "policy": duplicate_policy,
            "duplicate_rows_detected": int(len(duplicates_df)),
            "duplicate_keys": duplicate_keys,
            "duplicate_rows_dropped": int(len(df) - len(df_result)),
            "duplicates_file": duplicates_file,
        }

    logging.info("drop_duplicate_rows transformation completed successfully.")
    return df_result
