import time
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services.business import metadata
from src.services.contracts import contract, supports
def create(db, data, user):
    d=db.get(Dataset,data.dataset_id)
    if not d: raise HTTPException(404,'数据批次不存在')
    if d.status!='active': raise HTTPException(409,f'数据批次已被隔离，不能用于分析：{d.quarantine_reason}')
    allowed={p['key']:p for p in metadata().get('parameters',[])}
    if set(data.params)-set(allowed): raise HTTPException(422,'包含未知分析参数')
    params={k:p['default'] for k,p in allowed.items()}
    params.update(data.params)
    for key,p in allowed.items():
        v=params[key]
        if p['type']=='number':
            try:
                v=float(v)
                if not (p.get('min',-1e9)<=v<=p.get('max',1e9)): raise ValueError()
                params[key]=v
            except (ValueError,TypeError): raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options',[])]:
            raise HTTPException(422,f'{p["label"]} 不是有效选项')
    version=d.contract_version
    grouping=params.get('group_by')
    if grouping and grouping not in ('channel','week') and not supports(version,grouping):
        c=contract(version)
        raise HTTPException(422,f'所选对账维度需要更新的源账契约；该批次固定为 {version}（{c["label"]}），不含字段 {grouping}')
    # 分析固定完整契约版本：分组含义不随后续契约升级悄悄变化。
    j=Job(name=data.name, dataset_id=data.dataset_id, params=params, contract_version=version, created_by=user.id, created_at=time.time(), status='queued')
    db.add(j); db.flush()
    return j
def enqueue(job_id):
    try:
        r=Redis.from_url(REDIS_URL); r.rpush('analysis:queue',job_id); r.close()
    except Exception:
        pass # SQL queued status is the durable fallback
