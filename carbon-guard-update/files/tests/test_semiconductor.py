import unittest
import test_system
from backend import semiconductor as semi
from backend.database import connect

class SemiconductorTests(unittest.TestCase):
    login=test_system.SystemTests.login
    tearDown=test_system.SystemTests.tearDown
    def setUp(self):
        semi.model=None;semi.document=None;semi.model_id=None
        test_system.SystemTests.setUp(self)
    def test_annual_integration(self):
        import sklearn
        h=self.login()
        doc={'industry':'2611','train_year':2023,'contamination':.05,'sklearn':sklearn.__version__,'feature_version':'annual-direct-indirect-share-v1','samples':[
            dict(app_year='112',companyname='A',controlno='X'+str(i),ccksicco1='2611',sicname1='積體電路製造業',check_yn='是',tot1_value=str(100+i),tot2_value=str(300+i)) for i in range(40)]}
        r=self.client.post('/api/semiconductor/model/import',headers=h,json=doc)
        self.assertEqual(r.status_code,200,r.text)
        facility=next(f for f in semi.FACILITIES if f['industry']=='2611')
        record=dict(supplier=facility['supplier'],controlno=facility['controlno'],industry='2611',year=2024,direct=500,indirect=600)
        r=self.client.post('/api/semiconductor/records',headers=h,json={'records':[record]})
        self.assertEqual(r.status_code,201,r.text)
        original_score=r.json()['records'][0]['score']
        reviewed=self.client.post('/api/semiconductor/records/1/review',headers=h,json={'decision':'confirmed','note':'已核對佐證'})
        self.assertEqual(reviewed.status_code,200)
        displayed=self.client.get('/api/semiconductor/records').json()['records'][0]
        self.assertEqual(displayed['review']['decision'],'confirmed')
        self.assertEqual(displayed['score'],original_score)
        self.assertTrue(self.client.get('/api/semiconductor/integrity').json()['valid'])
        semi.model=None;semi.load_saved();self.assertIsNotNone(semi.model)
        bad={**record,'industry':'2613'}
        self.assertEqual(self.client.post('/api/semiconductor/records',headers=h,json={'records':[bad]}).status_code,422)
        unknown={**record,'controlno':'NOT-IN-PUBLIC-LIST'}
        self.assertEqual(self.client.post('/api/semiconductor/records',headers=h,json={'records':[unknown]}).status_code,422)
        with connect() as db:db.execute('UPDATE users SET supplier=? WHERE username=?',(facility['supplier'],'alice'))
        self.login('alice')
        allowed=self.client.get('/api/semiconductor/facilities').json()
        self.assertTrue(allowed)
        self.assertTrue(all(f['supplier']==facility['supplier'] for f in allowed))
        h=self.login('bob');self.assertEqual(self.client.get('/api/semiconductor/records').json()['total'],0)
        self.assertEqual(self.client.post('/api/semiconductor/model/import',headers=h,json=doc).status_code,403)
        self.assertEqual(self.client.post('/api/semiconductor/records',headers=h,json={'records':[record]}).status_code,403)
        h=self.login()
        with connect() as db:db.execute("UPDATE semiconductor_records SET payload='{}' WHERE id=1")
        self.assertFalse(self.client.get('/api/semiconductor/integrity').json()['valid'])
        self.assertEqual(self.client.post('/api/semiconductor/records',headers=h,json={'records':[record]}).status_code,409)

    def test_supplier_binding(self):
        headers=self.login('alice')
        alice_token=self.client.cookies.get('carbon_session')
        self.assertEqual(self.client.get('/api/semiconductor/supplier-accounts').status_code,403)
        facility=next(f for f in semi.FACILITIES if f['industry']=='2611')
        self.assertEqual(self.client.post('/api/semiconductor/supplier-binding',headers=headers,json={'username':'bob','controlno':facility['controlno']}).status_code,403)
        headers=self.login()
        response=self.client.post('/api/semiconductor/supplier-binding',headers=headers,json={'username':'alice','controlno':facility['controlno']})
        self.assertEqual(response.status_code,200,response.text)
        with connect() as db:
            self.assertEqual(db.execute('SELECT supplier FROM users WHERE username=?',('alice',)).fetchone()['supplier'],facility['supplier'])
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE username=?',('alice',)).fetchone()[0],0)
        self.assertTrue(self.client.get('/api/integrity').json()['audit']['valid'])
        self.login('alice')
        self.assertTrue(self.client.get('/api/semiconductor/facilities').json())
