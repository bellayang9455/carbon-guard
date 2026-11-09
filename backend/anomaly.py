import json
import math
import threading
from datetime import datetime, timezone
from uuid import uuid4
import hmac
import sklearn
from sklearn.ensemble import IsolationForest
from .database import connect
from .integrity import canonical, signature

lock = threading.RLock()
model = None
metadata = None

def features(row):
    return [math.log1p(row['emission']), math.log1p(row['production']),
            math.log1p(row['emission'] / row['production']), row['scope']]

def fit(samples, contamination):
    candidate = IsolationForest(n_estimators=200, max_samples=min(256, len(samples)),
                               contamination=contamination, random_state=42, n_jobs=1)
    candidate.fit([features(row) for row in samples])
    return candidate

def prepare(body, username):
    samples = [s.model_dump() for s in body.samples]
    candidate = fit(samples, body.contamination)
    document = {'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(),
                'samples': samples, 'contamination': body.contamination,
                'note': body.note, 'username': username, 'sklearn': sklearn.__version__}
    return candidate, document

def activate(candidate, document):
    global model, metadata
    with lock:
        model, metadata = candidate, document

def restore():
    with connect() as db:
        row = db.execute('SELECT payload,mac FROM models ORDER BY saved_order DESC,id DESC LIMIT 1').fetchone()
    if row:
        if not hmac.compare_digest(row['mac'], signature('model:' + row['payload'])):
            raise RuntimeError('模型參考資料驗證失敗')
        document = json.loads(row['payload'])
        if document['sklearn'] != sklearn.__version__:
            raise RuntimeError('scikit-learn 版本與模型紀錄不符，請使用原版本或重新訓練')
        activate(fit(document['samples'], document['contamination']), document)

def status():
    with lock:
        if metadata is None:
            return {'trained': False}
        return {'trained': True, **{k: v for k, v in metadata.items() if k != 'samples'},
                'sample_count': len(metadata['samples'])}

def predict(row):
    with lock:
        if model is None:
            return {'score': None, 'anomaly': None, 'model_id': None}
        values = [features(row)]
        return {'score': float(-model.score_samples(values)[0]),
                'anomaly': bool(model.predict(values)[0] == -1), 'model_id': metadata['id']}
