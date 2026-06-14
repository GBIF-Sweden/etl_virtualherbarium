from functools import lru_cache
from importlib import import_module


CONFIG_AWARE_TRANSFORMS = {
    "drop_unmapped_columns",
    "drop_duplicate_rows",
}

TRANSFORMATION_NAMES = {
    "clean_whitespace",
    "generate_occ_id_triplet",
    "drop_columns",
    "drop_unmapped_columns",
    "clean_extra_quotes",
    "copyColumn",
    "drop_empty_rows",
    "drop_duplicate_rows",
}

TRANSFORMATION_ALIASES = {
    "copy_column": "copyColumn",
}


@lru_cache(maxsize=1)
def _transform_module():
    return import_module("transformation.transform")


def resolve_transformation_name(name):
    return TRANSFORMATION_ALIASES.get(name, name)


def has_transformation(name):
    return resolve_transformation_name(name) in TRANSFORMATION_NAMES


def is_config_aware(name):
    return resolve_transformation_name(name) in CONFIG_AWARE_TRANSFORMS


def get_transformation(name):
    resolved = resolve_transformation_name(name)
    if resolved not in TRANSFORMATION_NAMES:
        return None
    return getattr(_transform_module(), resolved, None)


def available_transformations():
    return sorted(TRANSFORMATION_NAMES)

