import logging
import os
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker


def _resolve_db_credentials(load_config: Dict[str, Any]) -> tuple[str, str, str, int, str]:
    host = load_config.get("database_hostname")
    port = int(load_config.get("database_port", 3306))
    dbname = load_config.get("database_name")

    # Primary env names aligned with reference repo.
    user = os.getenv("ETL_DB_USER") or os.getenv("DATABASE_USER")
    password = os.getenv("ETL_DB_PASSWORD") or os.getenv("DATABASE_PASSWORD")

    if not all([host, dbname, user, password]):
        raise KeyError(
            "Missing DB credentials/config. Required: load.database_hostname, load.database_name, "
            "and env vars ETL_DB_USER + ETL_DB_PASSWORD."
        )
    return host, dbname, user, port, password


def save_to_database(
    df: pd.DataFrame,
    load_config: Dict[str, Any],
    batch_size: Optional[int] = None,
    mode: Optional[str] = None,
) -> None:
    """
    Persist DataFrame to MySQL.

    mode="ignore": INSERT IGNORE
    mode="upsert": INSERT ... ON DUPLICATE KEY UPDATE
    """
    logger = logging.getLogger(__name__)
    write_to_db = bool(load_config.get("write_to_db", False))
    if not write_to_db:
        logger.info("write_to_db is False; skipping database write.")
        return

    host, dbname, user, port, password = _resolve_db_credentials(load_config)
    table_name = load_config.get("database_table")
    pk_column = load_config.get("database_table_pk_column")
    if not table_name:
        raise KeyError("Missing load.database_table")

    write_mode = mode or load_config.get("database_mode", "upsert")
    if write_mode not in {"ignore", "upsert"}:
        raise ValueError("database_mode must be 'ignore' or 'upsert'")

    effective_batch_size = int(batch_size or load_config.get("database_batch_size", 1000))
    if effective_batch_size <= 0:
        raise ValueError("database_batch_size must be a positive integer")

    connection_url = URL.create(
        drivername="mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=dbname,
        query={"charset": "utf8mb4"},
    )

    engine = create_engine(connection_url, pool_pre_ping=True, future=True)
    Session = sessionmaker(bind=engine, future=True)
