import os
import tempfile
import unittest
import json

TEST_DATA = tempfile.TemporaryDirectory()
os.environ['CARBON_DATA_DIR'] = TEST_DATA.name
os.environ['CARBON_SECRET'] = 'testing-only-secret-' * 4
os.environ['CARBON_SECURE_COOKIE'] = 'false'
os.environ['DATABASE_URL'] = ''
os.environ.pop('BOOTSTRAP_ADMIN_USERNAME',None)
os.environ.pop('BOOTSTRAP_ADMIN_PASSWORD',None)
from fastapi.testclient import TestClient
from backend.main import app, attempts
from backend.database import connect
from backend.config import DB
from backend.security import password_hash
from backend import anomaly
from backend.integrity import canonical, fingerprint

class SystemTests(unittest.TestCase):
    def setUp(self):
        if DB.exists(): DB.unlink()
        anomaly.activate(None, None)
        attempts.clear()
        self.client = TestClient(app)
        self.client.__enter__()
        with connect() as db:
            for username, role, supplier in [('root','admin',''),('alice','supplier','A'),('bob','supplier','B')]:
                db.execute('INSERT INTO users VALUES (?,?,?,?)',
                           (username,password_hash('long-test-password'),role,supplier))

    def tearDown(self):
        self.client.__exit__(None,None,None)

    def login(self, name='root'):
        response=self.client.post('/api/login',json={'username':name,'password':'long-test-password'})
        self.assertEqual(response.status_code,200,response.text)
        return {'X-CSRF-Token':response.json()['csrf']}

    def record(self, supplier='A', emission=100):
        return {'supplier':supplier,'month':'2026-11','scope':1,'emission':emission,'production':1000}

    def add(self, headers, **kwargs):
        return self.client.post('/api/records',headers=headers,json={'records':[self.record(**kwargs)]})

    def test_auth_csrf_and_tenant_isolation(self):
        self.assertEqual(self.client.get('/api/records').status_code,401)
        headers=self.login('alice')
        self.assertEqual(self.add({}).status_code,403)
        self.assertEqual(self.add(headers,supplier='B').status_code,403)
        self.assertEqual(self.add(headers).status_code,201)
        self.assertEqual(self.client.get('/api/integrity').status_code,403)
        self.login('bob')
        self.assertEqual(self.client.get('/api/records').json()['total'],0)
        self.assertNotIn(',A,',self.client.get('/api/export').text)
        self.assertEqual(self.client.get('/api/audit').status_code,403)

    def test_training_prediction_and_restart_restore(self):
        headers=self.login()
        samples=[self.record(emission=80+i) for i in range(40)]
        response=self.client.post('/api/model/train',headers=headers,json={
            'samples':samples,'note':'合成參考樣本','contamination':.05})
        self.assertEqual(response.status_code,200,response.text)
        version=response.json()['id']
        normal=self.client.post('/api/predict',headers=headers,json=self.record()).json()
        extreme=self.client.post('/api/predict',headers=headers,json=self.record(emission=100000)).json()
        self.assertGreater(extreme['score'],normal['score'])
        result=self.add(headers).json()['records'][0]
        self.assertEqual(result['model_id'],version)
        anomaly.activate(None,None)
        anomaly.restore()
        self.assertEqual(anomaly.status()['id'],version)
        self.assertEqual(anomaly.predict(self.record())['score'],normal['score'])

    def test_chain_hmac_and_block_corrupt_writes(self):
        headers=self.login()
        self.assertEqual(self.add(headers).status_code,201)
        self.assertTrue(self.client.get('/api/integrity').json()['records']['valid'])
        with connect() as db:
            row=db.execute('SELECT * FROM records WHERE id=1').fetchone()
            payload=json.loads(row['payload']);payload['emission']=999
            payload=canonical(payload)
            forged=fingerprint('records',1,payload,'GENESIS')
            db.execute('UPDATE records SET payload=?,digest=? WHERE id=1',(payload,forged))
        self.assertFalse(self.client.get('/api/integrity').json()['records']['valid'])
        self.assertEqual(self.add(headers).status_code,409)

    def test_review_and_atomic_batch(self):
        headers=self.login()
        self.add(headers)
        response=self.client.post('/api/records/1/review',headers=headers,
                                  json={'decision':'confirmed','note':'核對完成'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/api/audit').json()[0]['action'],'review')
        self.assertTrue(self.client.get('/api/integrity').json()['audit']['valid'])
        self.assertEqual(self.add(headers,emission=-1).status_code,422)
        before=self.client.get('/api/records').json()['total']
        response=self.client.post('/api/records',headers=headers,json={
            'records':[self.record(),self.record(emission=-5)]})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.client.get('/api/records').json()['total'],before)
        self.client.post('/api/logout',headers=headers)
        self.assertEqual(self.client.get('/api/me').status_code,401)

    def test_size_headers_formula_export_and_throttle(self):
        headers=self.login()
        self.add(headers,supplier='=1+1')
        self.assertIn("'=1+1",self.client.get('/api/export').text)
        response=self.client.get('/')
        self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
        self.assertIn('httponly',self.client.cookies.get('carbon_session') and
                      self.client.post('/api/login',json={'username':'root','password':'long-test-password'}).headers['set-cookie'].lower())
        self.assertEqual(self.client.post('/api/records',content=b'x'*(2*1024*1024+1)).status_code,413)
        for _ in range(10):
            self.assertEqual(self.client.post('/api/login',json={'username':'x','password':'wrong'}).status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'username':'x','password':'wrong'}).status_code,429)

if __name__=='__main__': unittest.main()
