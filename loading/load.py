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
