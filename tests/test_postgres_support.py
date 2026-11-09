import os
from unittest.mock import patch
import unittest
import test_system
from backend import database
from backend.integrity import verify

class BootstrapTests(unittest.TestCase):
    setUp=test_system.SystemTests.setUp
    tearDown=test_system.SystemTests.tearDown
    def test_bootstrap_first_admin_only(self):
        with database.connect() as db:
            db.execute('DELETE FROM sessions')
            db.execute('DELETE FROM users')
        settings={'BOOTSTRAP_ADMIN_USERNAME':'first-admin','BOOTSTRAP_ADMIN_PASSWORD':'first-long-password'}
        with patch.dict(os.environ,settings):database.bootstrap_admin()
        with database.connect() as db:
            first=db.execute("SELECT password FROM users WHERE username='first-admin'").fetchone()['password']
        with patch.dict(os.environ,{**settings,'BOOTSTRAP_ADMIN_PASSWORD':'different-long-password'}):database.bootstrap_admin()
        with database.connect() as db:
            self.assertEqual(db.execute("SELECT password FROM users WHERE username='first-admin'").fetchone()['password'],first)
            self.assertTrue(verify(db,'audit')['valid'])
    def test_failed_postgres_never_falls_back_to_sqlite(self):
        try:import psycopg
        except ImportError:self.skipTest('Install requirements.txt to test PostgreSQL driver')
        with patch.object(database,'DATABASE_URL','postgresql://test:fake@db.example/test'):
            with patch('psycopg.connect',side_effect=RuntimeError('connection failed')) as pg,patch('sqlite3.connect') as local:
                with self.assertRaises(RuntimeError):
                    with database.connect():pass
                self.assertFalse(local.called)
                self.assertEqual(pg.call_args.kwargs['sslmode'],'require')
