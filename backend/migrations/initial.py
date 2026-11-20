from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models

# 列契约版本升级引入的列；逐项检查后再 ALTER，中断重试不会重复写入。
NEW_COLUMNS = [
    ('datasets', 'contract_version', "VARCHAR(10) NOT NULL DEFAULT 'v1'"),
    ('datasets', 'status', "VARCHAR(20) NOT NULL DEFAULT 'active'"),
    ('datasets', 'quarantine_reason', "VARCHAR(500) NOT NULL DEFAULT ''"),
    ('jobs', 'contract_version', "VARCHAR(10) NOT NULL DEFAULT ''"),
    ('deliveries', 'contract_version', "VARCHAR(10) NOT NULL DEFAULT ''"),
]

def _ensure_columns(conn):
    existing = {t: {c['name'] for c in inspect(conn).get_columns(t)} for t, _, _ in NEW_COLUMNS}
    for table, column, ddl in NEW_COLUMNS:
        if column not in existing[table]:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))

def _backfill(conn):
    # 幂等回填：只更新占位空值，重复执行为零写入。
    conn.execute(text("UPDATE datasets SET contract_version='v1' WHERE contract_version=''"))
    conn.execute(text("UPDATE datasets SET status='active' WHERE status=''"))
    conn.execute(text("UPDATE jobs SET contract_version=(SELECT d.contract_version FROM datasets d WHERE d.id=jobs.dataset_id) WHERE contract_version=''"))
    conn.execute(text("UPDATE deliveries SET contract_version=(SELECT j.contract_version FROM reports r JOIN jobs j ON j.id=r.job_id WHERE r.id=deliveries.report_id) WHERE contract_version=''"))

def migrate():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        _ensure_columns(conn)
        _backfill(conn)
if __name__=='__main__':migrate()
