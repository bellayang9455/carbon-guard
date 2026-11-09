"""年度半導體模型整合；使用 annual_model.py 產生的參考 JSON。"""
import hashlib,hmac,json,math,threading
from datetime import datetime,timezone
from pathlib import Path
import sklearn
from sklearn.ensemble import IsolationForest
from pydantic import BaseModel,Field,ConfigDict,field_validator
from fastapi import APIRouter,Depends,HTTPException,Query
from .config import ROOT
from .database import connect
from .security import current_user,admin
from .integrity import TABLES,canonical,signature,append,verify,ensure_valid

router=APIRouter(prefix='/api/semiconductor')
FACILITIES=json.loads((Path(__file__).parent/'semiconductor_facilities.json').read_text(encoding='utf-8'))
FACILITY_BY_ID={r['controlno']:r for r in FACILITIES}
lock=threading.RLock(); model=None; document=None; model_id=None
CODES={'2611':'積體電路製造業','2612':'分離式元件製造業','2613':'半導體封裝及測試業'}
class AnnualRecord(BaseModel):
    model_config=ConfigDict(extra='forbid')
    supplier:str=Field(min_length=1,max_length=100)
    controlno:str=Field(min_length=1,max_length=100)
    industry:str=Field(pattern=r'^261[123]$')
    year:int=Field(ge=2000,le=2100,strict=True)
    direct:float=Field(ge=0,le=1e12,allow_inf_nan=False)
    indirect:float=Field(ge=0,le=1e12,allow_inf_nan=False)
    @field_validator('supplier','controlno')
    @classmethod
    def trim(cls,v):
        v=v.strip()
        if not v:raise ValueError('名稱及管制編號不可空白')
        return v
class AnnualBatch(BaseModel):
    records:list[AnnualRecord]=Field(min_length=1,max_length=1000)
class ModelImport(BaseModel):
    industry:str=Field(pattern=r'^261[123]$')
    train_year:int=Field(ge=2000,le=2100)
    contamination:float=Field(gt=0,le=.5,allow_inf_nan=False)
    samples:list[dict]=Field(min_length=32,max_length=10000)
    sklearn:str
    feature_version:str
    created_at_utc:str=''
    source_csv_sha256:str=''
class Review(BaseModel):
    decision:str=Field(pattern=r'^(confirmed|rejected|pending)$')
    note:str=Field(min_length=1,max_length=500)

def features(d,i):return [math.log1p(d),math.log1p(i),d/(d+i) if d+i else 0.]
def now():return datetime.now(timezone.utc).isoformat()
def event(db,user,action,detail):return append(db,'audit',dict(time=now(),user=user,action=action,detail=detail))
def build(value):
    if value.sklearn!=sklearn.__version__:raise HTTPException(409,'scikit-learn 版本不同，請使用訓練時相同版本')
    if value.feature_version!='annual-direct-indirect-share-v1':raise HTTPException(422,'年度特徵版本不符')
    x=[];seen=set()
    for row in value.samples:
        try:
            y=int(row['app_year']);y=y+1911 if y<1911 else y
            r=AnnualRecord(supplier=row['companyname'],controlno=row['controlno'],industry=row['ccksicco1'],year=y,direct=row['tot1_value'],indirect=row['tot2_value'])
            if r.industry!=value.industry or r.year!=value.train_year or row['check_yn']!='是' or row['sicname1']!=CODES[r.industry] or r.controlno in seen:raise ValueError()
            seen.add(r.controlno);x.append(features(r.direct,r.indirect))
        except (KeyError,ValueError,TypeError):raise HTTPException(422,'模型參考樣本格式、行業、年度或唯一鍵不符')
    candidate=IsolationForest(n_estimators=200,max_samples=min(256,len(x)),contamination=value.contamination,random_state=42,n_jobs=1)
    candidate.fit(x)
    return candidate

def load_saved():
    global model,document,model_id
    with connect() as db:row=db.execute('SELECT * FROM semiconductor_models ORDER BY rowid DESC LIMIT 1').fetchone()
    if row:
        if not hmac.compare_digest(row['mac'],signature('semiconductor-model:'+row['payload'])):raise RuntimeError('半導體模型 HMAC 不一致')
        value=ModelImport.model_validate_json(row['payload'])
        model=build(value);document=value.model_dump();model_id=row['id']

def initialize():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS semiconductor_records(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,previous_hash TEXT NOT NULL,digest TEXT NOT NULL,mac TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS semiconductor_models(id TEXT PRIMARY KEY,payload TEXT NOT NULL,mac TEXT NOT NULL)')
    TABLES.add('semiconductor_records')
    load_saved()
    local=ROOT/'ic-2023.json'
    if model is None and local.exists():
        if local.stat().st_size>2*1024*1024:raise RuntimeError('年度模型 JSON 超過 2 MB')
        import_model(ModelImport.model_validate_json(local.read_text(encoding='utf-8')),{'role':'admin','username':'startup-local-model'})

@router.get('/facilities')
def facilities(user=Depends(current_user)):
    return FACILITIES if user['role']=='admin' else [r for r in FACILITIES if r['supplier']==user['supplier']]

@router.get('/model')
def status(user=Depends(current_user)):
    with lock:
        return dict(loaded=model is not None,model_id=model_id,industry=document['industry'] if document else None,train_year=document['train_year'] if document else None,samples=len(document['samples']) if document else 0)

@router.post('/model/import')
def import_model(value:ModelImport,user=Depends(current_user)):
    global model,document,model_id
    admin(user)
    candidate=build(value);payload=canonical(value.model_dump());identifier=hashlib.sha256(payload.encode()).hexdigest()
    with lock:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE');ensure_valid(db)
            db.execute('INSERT OR IGNORE INTO semiconductor_models VALUES (?,?,?)',(identifier,payload,signature('semiconductor-model:'+payload)))
            event(db,user['username'],'semiconductor_model_import',dict(model_id=identifier,train_year=value.train_year,industry=value.industry))
        model=candidate;document=value.model_dump();model_id=identifier
    return status(user)

@router.post('/records',status_code=201)
def create(body:AnnualBatch,user=Depends(current_user)):
    if user['role']!='admin' and any(r.supplier!=user['supplier'] for r in body.records):raise HTTPException(403,'只能新增所屬供應商')
    for r in body.records:
        facility=FACILITY_BY_ID.get(r.controlno)
        if not facility or facility['supplier']!=r.supplier or facility['industry']!=r.industry:
            raise HTTPException(422,'請選擇清單中的廠別，供應商與行業必須一致')
    with lock:
        if model is None:raise HTTPException(409,'請先載入年度模型 JSON')
        if any(r.industry!=document['industry'] or r.year<=document['train_year'] for r in body.records):raise HTTPException(422,'資料行業必須符合模型，評分年度需晚於訓練年度')
        x=[features(r.direct,r.indirect) for r in body.records];scores=-model.score_samples(x);flags=model.predict(x)
        values=[{**r.model_dump(),'total':r.direct+r.indirect,'score':float(s),'anomaly':bool(f==-1),'model_id':model_id,'created_at':now(),'uploaded_by':user['username']} for r,s,f in zip(body.records,scores,flags)]
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');ensure_valid(db)
        result=[append(db,'semiconductor_records',v) for v in values]
        event(db,user['username'],'semiconductor_upload',{'record_ids':[r['id'] for r in result]})
    return {'records':result}

@router.get('/records')
def records(offset:int=Query(0,ge=0),user=Depends(current_user)):
    with connect() as db:
        latest={}
        for event_row in db.execute('SELECT payload FROM audit ORDER BY id DESC'):
            value=json.loads(event_row['payload'])
            if value.get('action')=='semiconductor_review':
                number=value['detail']['record_id']
                if number not in latest:latest[number]={'decision':value['detail']['decision'],'note':value['detail']['note'],'reviewed_by':value['user'],'reviewed_at':value['time']}
        values=[dict(id=r['id'],**json.loads(r['payload']),hash=r['digest'],review=latest.get(r['id'])) for r in db.execute('SELECT * FROM semiconductor_records ORDER BY id DESC')]
    if user['role']!='admin':values=[v for v in values if v['supplier']==user['supplier']]
    return {'total':len(values),'records':values[offset:offset+100]}

@router.get('/integrity')
def integrity(user=Depends(current_user)):
    admin(user)
    with connect() as db:return verify(db,'semiconductor_records')

@router.post('/records/{number}/review')
def review(number:int,body:Review,user=Depends(current_user)):
    admin(user)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');ensure_valid(db)
        if not db.execute('SELECT id FROM semiconductor_records WHERE id=?',(number,)).fetchone():raise HTTPException(404,'紀錄不存在')
        return event(db,user['username'],'semiconductor_review',dict(record_id=number,**body.model_dump()))

class SupplierBinding(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    controlno:str=Field(min_length=1,max_length=100)

@router.get('/supplier-accounts')
def supplier_accounts(user=Depends(current_user)):
    admin(user)
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT username,supplier FROM users WHERE role='supplier' ORDER BY username")]

@router.post('/supplier-binding')
def supplier_binding(body:SupplierBinding,user=Depends(current_user)):
    admin(user)
    facility=FACILITY_BY_ID.get(body.controlno)
    if not facility:raise HTTPException(422,'請選擇清單中的廠別')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');ensure_valid(db)
        target=db.execute("SELECT supplier FROM users WHERE username=? AND role='supplier'",(body.username,)).fetchone()
        if not target:raise HTTPException(404,'供應商帳號不存在')
        db.execute('UPDATE users SET supplier=? WHERE username=?',(facility['supplier'],body.username))
        db.execute('DELETE FROM sessions WHERE username=?',(body.username,))
        event(db,user['username'],'supplier_binding',dict(username=body.username,previous_supplier=target['supplier'],supplier=facility['supplier'],controlno=body.controlno))
    return {'ok':True,'supplier':facility['supplier']}
