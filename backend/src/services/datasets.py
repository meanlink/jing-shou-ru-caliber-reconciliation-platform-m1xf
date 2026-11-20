from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.contracts import classify
from src.utils.serialization import checksum
import time
def prepare(records):
    """判定整批契约版本；不通过时返回隔离原因，调用方不得部分放行。"""
    version, outcome = classify(records)
    if version is None:
        return {'contract_version': '', 'status': 'quarantined', 'quarantine_reason': outcome, 'records': records}
    return {'contract_version': version, 'status': 'active', 'quarantine_reason': '', 'records': outcome}
def create(db, data):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    plan=prepare(data.records)
    # 单事务整批落库：要么整批有效，要么整批隔离，绝不放出半批。
    d=Dataset(name=name, source=data.source, checksum=checksum(plan['records']), created_at=time.time(), **plan)
    db.add(d); db.flush()
    return d
