import os
import requests
import pandas as pd
import logging
import csv
import tempfile
import time

from extraction.row_repair import repair_overwide_row


def download_csv_file(url_template, target_folder_path):
    """
    Downloads a CSV file from a URL template and saves it in a specified folder with a structured name.
    Validates that the file contains more than just a header.

    Args:
        url_template (str): URL template of the form
                            "http://herbarium.emg.umu.se/export/CSV.php?InstitutionCode={institutionCode}&Page={page_number}".
        target_folder_path (str): Path to the folder where the file should be saved.

    Returns:
        tuple[str, str | None]:
            ("downloaded", path) on success,
            ("empty", None) for header-only page,
            ("request_error", None) for HTTP/network errors,
            ("invalid_url", None) for malformed URL template.
    """
    # Ensure the target folder exists
    os.makedirs(target_folder_path, exist_ok=True)

    # Extract InstitutionCode and Page from the URL template
    try:
        base_url, params = url_template.split('?')
        params = {key: value for key, value in (param.split('=') for param in params.split('&'))}
        institution_code = params.get('InstitutionCode', '{institutionCode}')
        page_number = params.get('Page', '{page_number}')

        if '{institutionCode}' in institution_code or '{page_number}' in page_number:
            raise ValueError("Please provide valid values for 'InstitutionCode' and 'Page'.")
    except Exception as e:
        logging.error(f"Invalid URL template format: {e}")
        return "invalid_url", None

    # Fetch and save the file
    file_name = f"{institution_code}_{page_number}.csv"
    save_path = os.path.join(target_folder_path, file_name)

    try:
        response = requests.get(url_template, timeout=120)
        response.raise_for_status()

        with open(save_path, "wb") as file:
            file.write(response.content)

        # Check if CSV has any data rows beyond the header
        has_data = False
        with open(save_path, "r", encoding="utf-8", newline="") as file:
            reader = csv.reader(file)
            next(reader, None)

            for row in reader:
                if any(cell.strip() for cell in row):
                    has_data = True
                    break

        if not has_data:
            os.remove(save_path)
            logging.info(f"File at {save_path} contains only header row. Deleted.")
            return "empty", None

        logging.info(f"File saved as {save_path}")
        return "downloaded", save_path

    except requests.RequestException as e:
        logging.error(f"Failed to download the file: {e}")
        return "request_error", None
    return "request_error", None


def download_files_iteratively(base_url, institution_code, target_folder_path, max_page_retries=3, retry_sleep_seconds=2):
    """
    Downloads CSV files for a given institution code iteratively by increasing the page number
    until no more files can be downloaded or valid data is found.

    Args:
        base_url (str): Base URL without query parameters, e.g., "http://herbarium.emg.umu.se/export/CSV.php".
        institution_code (str): The institution code to include in the URL.
        target_folder_path (str): Path to the folder where the files should be saved.

    Returns:
        list: A list of paths to successfully downloaded files.
    """
    os.makedirs(target_folder_path, exist_ok=True)
    page_number = 1
    downloaded_files = []

    while True:
        # Construct the URL for the current page
        url = f"{base_url}?InstitutionCode={institution_code}&Page={page_number}"

        logging.info(f"Attempting to download page {page_number}...")
        retries = 0
        while True:
            status, file_path = download_csv_file(url, target_folder_path)
            if status == "downloaded":
                downloaded_files.append(file_path)
                page_number += 1
                break
            if status == "empty":
                logging.info(f"No more valid files found after page {page_number - 1}.")
                return downloaded_files
            if status in {"request_error", "invalid_url"}:
                retries += 1
                if retries > max_page_retries:
                    raise RuntimeError(
                        f"Stopping due to repeated download failures on page {page_number} "
                        f"after {max_page_retries} retries."
                    )
                logging.warning(
                    "Retrying page %s after error (%s/%s)...",
                    page_number,
                    retries,
                    max_page_retries,
                )
                time.sleep(retry_sleep_seconds)
                continue

    return downloaded_files

def _normalize_escaped_value(value):
    escape_map = {
        r'\t': '\t',
        r'\r': '\r',
        r'\n': '\n',
    }
    return escape_map.get(value, value)


def _split_valid_and_malformed_rows(file_path, delimiter, quotechar, lineterminator, encoding="utf-8", extract_config=None, run_context=None):
    """
    Splits input CSV into a cleaned CSV and a malformed rows CSV based on header column count.
    Returns path to cleaned temp file and row quality stats.
    """
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    malformed_dir = os.path.join("data", "malformed")
    os.makedirs(malformed_dir, exist_ok=True)
    malformed_path = os.path.join(malformed_dir, f"{base_name}_malformed.csv")

    cleaned_temp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", suffix=".csv", delete=False)
    malformed_file = open(malformed_path, "w", encoding="utf-8", newline="")

    malformed_count = 0
    repaired_count = 0
    targeted_repair_count = 0
    ambiguous_count = 0
    line_too_short_count = 0
    line_too_long_count = 0

    # Ensure delimiter and lineterminator are bytes for binary reading
    delimiter_bytes = delimiter.encode('utf-8') if isinstance(delimiter, str) else delimiter
    lineterminator_bytes = lineterminator.encode('utf-8') if isinstance(lineterminator, str) else lineterminator

    try:
        with open(file_path, "rb") as src:
            content = src.read()

        if lineterminator_bytes:
            raw_records = content.split(lineterminator_bytes)
        else:
            raw_records = [content]

        # Filter out trailing empty record
        if raw_records and len(raw_records[-1]) == 0:
            raw_records.pop()

        encodings = [encoding, "utf-8-sig", "latin-1"]
        decoded_records = None
        for enc in encodings:
            try:
                # Test decode on a sample of records
                for r in raw_records[:100]:
                    r.decode(enc)
                decoded_records = [r.decode(enc) for r in raw_records]
                break
            except UnicodeDecodeError:
                continue

        if decoded_records is None:
            raise UnicodeDecodeError("unknown", b"", 0, 1, "Unable to decode source with tried encodings")

        cleaned_writer = csv.writer(cleaned_temp, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)
        malformed_writer = csv.writer(malformed_file, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)

        if not decoded_records:
            return cleaned_temp.name, {"expected_columns": 0, "repaired_rows": 0, "malformed_rows": 0}

        header = decoded_records[0].split(delimiter)
        # Clean header values from surrounding quotes if present
        if quotechar:
            header = [
                val[1:-1].replace(quotechar + quotechar, quotechar)
                if len(val) >= 2 and val.startswith(quotechar) and val.endswith(quotechar)
                else val
                for val in header
            ]

        expected_cols = len(header)
        cleaned_writer.writerow(header)
        malformed_writer.writerow(header)

        for record in decoded_records[1:]:
            if len(record) == 0:
                continue

            row = record.split(delimiter)
            if quotechar:
                cleaned_row = []
                for val in row:
                    if len(val) >= 2 and val.startswith(quotechar) and val.endswith(quotechar):
                        val = val[1:-1]
                        val = val.replace(quotechar + quotechar, quotechar)
                    cleaned_row.append(val)
                row = cleaned_row

            row_len = len(row)
            if row_len == expected_cols:
                cleaned_writer.writerow(row)
                continue

            # Some exporter rows have trailing delimiter drift:
            # extra empty cells (or georef text shifted into tail cells).
            # Repair those rows by normalizing to expected column count.
            if row_len > expected_cols:
                line_too_long_count += 1
                repaired_row, repair_type = repair_overwide_row(row, header, extract_config or {})
                if repair_type in {"targeted", "drop_empty_shift", "truncate_empty_tail", "merge_last"}:
                    cleaned_writer.writerow(repaired_row)
                    repaired_count += 1
                    if repair_type == "targeted":
                        targeted_repair_count += 1
                    continue
                if repair_type == "ambiguous":
                    ambiguous_count += 1
                malformed_writer.writerow(row)
                malformed_count += 1
                continue

            # If row is short, right-pad with empty values.
            if row_len < expected_cols:
                line_too_short_count += 1
                cleaned_writer.writerow(row + ([""] * (expected_cols - row_len)))
                repaired_count += 1
                continue

            malformed_writer.writerow(row)
            malformed_count += 1

    finally:
        cleaned_temp.close()
        malformed_file.close()

    if malformed_count == 0:
        try:
            os.remove(malformed_path)
        except OSError:
            pass
    else:
        logging.warning(
            f"Found {malformed_count} malformed rows in {file_path}. Saved to {malformed_path}."
        )

    if repaired_count > 0:
        logging.info(
            f"Repaired {repaired_count} structurally inconsistent rows in {file_path}."
        )
    if run_context is not None:
        run_context.setdefault("quality", {}).setdefault("extraction_detail", []).append({
            "file": file_path,
            "too_long_rows": int(line_too_long_count),
            "too_short_rows": int(line_too_short_count),
            "targeted_repairs": int(targeted_repair_count),
            "ambiguous_repairs": int(ambiguous_count),
        })

    return cleaned_temp.name, {
        "expected_columns": expected_cols,
        "repaired_rows": repaired_count,
        "malformed_rows": malformed_count,
    }


def extract_from_csv(file_path, extract_config, run_context=None):
    dtype = extract_config.get('dtype_dict', {})
    quotechar = extract_config.get('quotechar')
    lineterminator = extract_config.get('lineterminator')
    delimiter = extract_config.get('delimiter')

    # YAML single-quoted values like '\t' and '\r' are literal backslash sequences.
    # Normalize them so pandas receives actual control characters.
    delimiter = _normalize_escaped_value(delimiter)
    lineterminator = _normalize_escaped_value(lineterminator)

    read_kwargs = {
        'sep': delimiter,
        'quotechar': quotechar,
        'dtype': dtype,
    }
    encodings = [extract_config.get("encoding", "utf-8"), "utf-8-sig", "latin-1"]
    chunksize = extract_config.get("chunksize")
    # C engine is faster and supports low_memory. Python engine does not.
    if isinstance(delimiter, str) and len(delimiter) > 1 and delimiter != r'\s+':
        read_kwargs['engine'] = 'python'
    else:
        read_kwargs['low_memory'] = False
    cleaned_file_path = None
    try:
        cleaned_file_path, quality_stats = _split_valid_and_malformed_rows(
            file_path,
            delimiter,
            quotechar,
            lineterminator,
            encoding=extract_config.get("encoding", "utf-8"),
            extract_config=extract_config,
            run_context=run_context,
        )
        df = None
        for enc in encodings:
            try:
                if chunksize:
                    chunk_iter = pd.read_csv(cleaned_file_path, encoding=enc, chunksize=int(chunksize), **read_kwargs)
                    df = pd.concat(list(chunk_iter), ignore_index=True)
                else:
                    df = pd.read_csv(cleaned_file_path, encoding=enc, **read_kwargs)
                break
            except UnicodeDecodeError:
                continue
        if df is None:
            raise UnicodeDecodeError("unknown", b"", 0, 1, "Unable to decode source with tried encodings")

        logging.info(f"Extracted {df.shape[0]} rows from source file.")
        return df, quality_stats

    except FileNotFoundError:
        logging.error(f"Error: Source file not found at {file_path}.")
        raise
    except pd.errors.EmptyDataError:
        logging.error("Error: The source file is empty.")
        raise
    finally:
        if cleaned_file_path and os.path.exists(cleaned_file_path):
            try:
                os.remove(cleaned_file_path)
            except OSError:
                pass


def read_csv_into_dataframe(downloaded_files, extract_config, run_context=None):
    """
    Reads all the CSV files from the given list of file paths into a single Pandas DataFrame.

    Args:
        downloaded_files (list): List of file paths to the downloaded CSV files.

    Returns:
        pd.DataFrame: Combined DataFrame containing data from all valid CSV files.
        :param downloaded_files:
        :param extract_config:
    """
    all_data = []
    extraction_quality = []
    for file_path in downloaded_files:
        try:
            # Read the CSV file into a DataFrame
            df, stats = extract_from_csv(file_path, extract_config, run_context=run_context)
            all_data.append(df)
            extraction_quality.append({
                "file": file_path,
                "rows_read": int(len(df)),
                "expected_columns": int(stats.get("expected_columns", 0)),
                "repaired_rows": int(stats.get("repaired_rows", 0)),
                "malformed_rows": int(stats.get("malformed_rows", 0)),
            })
            logging.info(f"Successfully read {file_path}, {len(df)} rows.")
        except Exception as e:
            logging.error(f"Error reading {file_path}: {e}")

    # Combine all the DataFrames into one
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        logging.info(f"Combined DataFrame created with {len(combined_df)} rows.")
    else:
        combined_df = pd.DataFrame()  # Return an empty DataFrame if no files were read successfully
        logging.warning("No valid data found in the downloaded files.")

    return combined_df, extraction_quality
