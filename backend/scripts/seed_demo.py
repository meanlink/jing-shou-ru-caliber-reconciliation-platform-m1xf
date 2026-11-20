import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit
from src.services.business import metadata, seed_records, seed_records_v2, analyze
from src.services.datasets import prepare
from src.services.reports import deliver
from src.utils.security import hash_password
from src.utils.serialization import checksum
def add_dataset(db, name, source, rows):
    d=db.scalar(select(Dataset).where(Dataset.name==name))
    if not d:
        plan=prepare(rows)
        d=Dataset(name=name,source=source,checksum=checksum(plan['records']),created_at=time.time(),**plan)
        db.add(d); db.flush()
    return d
def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=add_dataset(db,m['dataset_name'],m['short']+'-202609.csv',seed_records())
        d2=add_dataset(db,m['dataset_name_v2'],m['short']+'-202611.csv',seed_records_v2())
        # 隔离示例：前半含结算标签、后半缺失，同批混用契约被整批隔离。
        mixed=seed_records_v2()[:6]+seed_records()[:6]
        add_dataset(db,m['dataset_name_quarantine'],m['short']+'-mixed.csv',mixed)
        admin=db.scalar(select(User).where(User.role=='admin'))
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params,d.contract_version)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,contract_version=d.contract_version,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        if not db.scalar(select(Job).where(Job.name=='结算标签分组复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            params['group_by']='settlement_tag'
            result=analyze(d2.records,params,d2.contract_version)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            j=Job(name='结算标签分组复核 · '+m['name'],dataset_id=d2.id,params=params,contract_version=d2.contract_version,status='completed',result=result,created_by=admin.id,created_at=time.time()-1800,finished_at=time.time()-1795,approved=False)
            db.add(j);db.flush()
            db.add(Audit(actor='seed',action='demo.settlement_tag',detail={'dataset':d2.id,'job':j.id},at=time.time()))
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
