import os
import requests
import pandas as pd
import logging
import csv
import tempfile
import time


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
            header = next(reader, None)

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
