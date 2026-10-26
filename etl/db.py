"""Open the release as a self-documenting DuckDB database.

    from etl.db import connect
    con = connect()
    con.sql("SELECT view_name, comment FROM duckdb_views() WHERE NOT internal")
    con.sql("SELECT column_name, comment FROM duckdb_columns() WHERE table_name = 'observations'")

Views read data/release/parquet/*.parquet; every table and column carries its
description as a comment (the same text as data/release/schema.json).
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def connect(database=':memory:'):
    import duckdb
    con = duckdb.connect(database)
    sql = open(os.path.join(ROOT, 'data', 'release', 'open.sql'), encoding='utf-8').read()
    sql = sql.replace("read_parquet('data/release/", f"read_parquet('{ROOT}/data/release/")
    con.execute(sql)
    return con
