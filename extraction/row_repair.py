import re


DEFAULT_REPAIR_TEXT_COLUMNS = [
    "Locality",
    "OriginalName",
    "OriginalText",
    "Original_text",
    "Notes",
    "Comments",
    "georeferenceRemarks",
]

DEFAULT_REPAIR_VALIDATION = {
    "CatalogNumber": "non_empty",
    "DateCollected": "date_or_empty",
    "Continent": "known_continent_or_empty",
    "WGS84N": "numeric_or_empty",
    "WGS84S": "numeric_or_empty",
    "CSource": "text_or_empty",
    "RT90-N": "numeric_or_empty",
    "RT90-E": "numeric_or_empty",
    "coordinateUncertaintyInMeters": "numeric_or_empty",
    "ScientificName": "text_or_empty",
}

KNOWN_CONTINENTS = {
    "africa",
    "antarctica",
    "asia",
    "europe",
    "north america",
    "oceania",
    "south america",
    "south & central america",
}


def _is_numeric_or_empty(value):
    value = str(value).strip()
    if value == "":
        return True
    try:
        float(value.replace(",", "."))
        return True
    except ValueError:
        return False


def _is_emptyish(value):
    return str(value).strip() in {"", '""'}


def _clean_validation_value(value):
    value = str(value).strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1].strip()
    return value


def _is_date_or_empty(value):
    value = _clean_validation_value(value)
    if value == "":
        return True
    return bool(re.fullmatch(r"\d{4}(-\d{1,2}){0,2}", value))


def _is_date_value(value):
    value = _clean_validation_value(value)
    return bool(re.fullmatch(r"\d{4}(-\d{1,2}){0,2}", value))


def _is_text_or_empty(value):
    value = _clean_validation_value(value)
    if value == "":
        return True
    return not _is_numeric_or_empty(value)


def _is_known_continent_or_empty(value):
    value = _clean_validation_value(value)
    if value == "":
        return True
    return value.lower() in KNOWN_CONTINENTS


def _has_balanced_quotes(value):
    return str(value).count('"') % 2 == 0


def _candidate_repair_score(candidate, header):
    values = dict(zip(header, candidate))
    score = 0

    if _is_date_value(values.get("DateCollected", "")):
        score += 4
    if _is_known_continent_or_empty(values.get("Continent", "")) and _clean_validation_value(values.get("Continent", "")):
        score += 2
    if _clean_validation_value(values.get("Country", "")):
        score += 1
    if _clean_validation_value(values.get("ScientificName", "")):
        score += 2
    if _clean_validation_value(values.get("Genus", "")):
        score += 1
    if (
        _clean_validation_value(values.get("WGS84N", ""))
        and _clean_validation_value(values.get("WGS84S", ""))
        and _is_numeric_or_empty(values.get("WGS84N", ""))
        and _is_numeric_or_empty(values.get("WGS84S", ""))
    ):
        score += 3

    georef = _clean_validation_value(values.get("georeferenceRemarks", "")).lower()
    if georef.startswith("coordinate generated"):
        score += 6

    for image_col in ["ImageLinks", "ImageThumbLinks"]:
        image_value = _clean_validation_value(values.get(image_col, "")).lower()
        if "coordinate generated" in image_value:
            score -= 6

    for text_col in ["Notes", "Comments"]:
        if _is_date_value(values.get(text_col, "")):
            score -= 4

    original_name = _clean_validation_value(values.get("OriginalName", "")).lower()
    genus = _clean_validation_value(values.get("Genus", "")).lower()
    specific_epithet = _clean_validation_value(values.get("SpecificEpithet", "")).lower()
    if original_name:
        if genus and genus in original_name:
            score += 2
        if specific_epithet and specific_epithet in original_name:
            score += 2
        if _has_balanced_quotes(values.get("OriginalName", "")):
            score += 1
        else:
            score -= 2

    original_text = values.get("OriginalText", "")
    if _clean_validation_value(original_text):
        if _has_balanced_quotes(original_text):
            score += 3
        else:
            score -= 2

    type_status = _clean_validation_value(values.get("Type-status", ""))
    if type_status and type_status.lower() not in {"holotype", "isotype", "lectotype", "syntype", "paratype"}:
        score -= 3

    return score


def _select_best_candidate(candidates, header):
    unique_candidates = []
    seen = set()
    for candidate in candidates:
        key = tuple(candidate)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)

    if not unique_candidates:
        return None, "none"
    if len(unique_candidates) == 1:
        return unique_candidates[0], "selected"

    scored = [(_candidate_repair_score(candidate, header), candidate) for candidate in unique_candidates]
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored[0][0] > scored[1][0]:
        return scored[0][1], "selected"
    return None, "ambiguous"


def _is_valid_repaired_row(row, header, validation_rules):
    values_by_column = dict(zip(header, row))
    for column, rule in validation_rules.items():
        if column not in values_by_column:
            continue

        value = values_by_column[column]
        if rule == "numeric_or_empty" and not _is_numeric_or_empty(value):
            return False
        if rule == "non_empty" and str(value).strip() == "":
            return False
        if rule == "date_or_empty" and not _is_date_or_empty(value):
            return False
        if rule == "text_or_empty" and not _is_text_or_empty(value):
            return False
        if rule == "known_continent_or_empty" and not _is_known_continent_or_empty(value):
            return False

    return True


def repair_overwide_row(row, header, extract_config):
    """
    Repairs rows where unescaped delimiters inside free-text fields shifted later columns.
    Returns (row, repair_type). repair_type is one of: targeted, drop_empty_shift, truncate_empty_tail, merge_last, ambiguous, none.
    """
    expected_cols = len(header)
    extra_cols = len(row) - expected_cols
    if extra_cols <= 0:
        return row, "none"

    extras = row[expected_cols:]
    extras_non_empty = [v for v in extras if str(v).strip()]
    validation_rules = dict(DEFAULT_REPAIR_VALIDATION)
    validation_rules.update(extract_config.get("repair_validation", {}))
    row_contains_date = any(_is_date_value(value) for value in row)

    repair_text_columns = extract_config.get("repair_text_columns", DEFAULT_REPAIR_TEXT_COLUMNS)
    candidates = []
    for column in repair_text_columns:
        if column not in header:
            continue

        idx = header.index(column)
        merge_end = idx + extra_cols + 1
        if merge_end > len(row):
            continue

        merged_value = " ".join(str(v).strip() for v in row[idx:merge_end] if str(v).strip())
        candidate = row[:idx] + [merged_value] + row[merge_end:]
        if len(candidate) != expected_cols:
            continue

        if _is_valid_repaired_row(candidate, header, validation_rules):
            values_by_column = dict(zip(header, candidate))
            if row_contains_date and not _is_date_value(values_by_column.get("DateCollected", "")):
                continue
            candidates.append(candidate)

    selected, selection_type = _select_best_candidate(candidates, header)
    if selection_type == "selected":
        return selected, "targeted"

    empty_shift_candidates = []
    for start in range(0, len(row) - extra_cols + 1):
        removed = row[start:start + extra_cols]
        if not all(_is_emptyish(v) for v in removed):
            continue

        candidate = row[:start] + row[start + extra_cols:]
        if len(candidate) != expected_cols:
            continue

        if _is_valid_repaired_row(candidate, header, validation_rules):
            values_by_column = dict(zip(header, candidate))
            if row_contains_date and not _is_date_value(values_by_column.get("DateCollected", "")):
                continue
            empty_shift_candidates.append(candidate)

    selected, empty_selection_type = _select_best_candidate(empty_shift_candidates, header)
    if empty_selection_type == "selected":
        return selected, "drop_empty_shift"
    if selection_type == "ambiguous" or empty_selection_type == "ambiguous":
        return row, "ambiguous"

    # Backward-compatible fallback: if the only surplus data is empty tail
    # cells and no validated shift candidate exists, discard the tail.
    if not extras_non_empty:
        return row[:expected_cols], "truncate_empty_tail"

    # Backward-compatible fallback for files without configured/known validation anchors.
    if not any(column in header for column in validation_rules):
        base = row[:expected_cols]
        last_value = str(base[-1]).strip()
        merged = " | ".join(extras_non_empty)
        base[-1] = f"{last_value} | {merged}" if last_value else merged
        return base, "merge_last"

    return row, "none"
