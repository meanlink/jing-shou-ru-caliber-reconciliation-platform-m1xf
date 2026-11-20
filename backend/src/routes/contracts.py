from fastapi import APIRouter, Depends
from src.config.database import get_db
from src.middlewares.auth import current_user, admin_only
from src.services.contracts import catalog, revalidate_datasets
from src.services.audit import record
router=APIRouter(prefix='/contracts')
@router.get('')
def listing(u=Depends(current_user)):
    # 列契约目录：各版本字段、版本间差异、默认版本与默认依据。
    return catalog()
@router.post('/revalidate')
def revalidate(db=Depends(get_db),u=Depends(admin_only)):
    # 升级复核幂等：仅状态变化时写入，重试不重复隔离、不放出半批。
    changed=revalidate_datasets(db)
    if changed: record(db,u.email,'contracts.revalidate',{'quarantined':changed})
    db.commit()
    return {'quarantined':changed,'checked':True}
