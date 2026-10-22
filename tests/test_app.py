import importlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['DATA_DIR'] = cls.tmp.name
        os.environ['SECRET_KEY'] = 'testing-secret'
        os.environ['ADMIN_PASSWORD'] = 'test-admin-password'
        cls.module = importlib.import_module('app')
        cls.client = cls.module.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_seeded_display_and_api(self):
        self.assertEqual(self.client.get('/display/lobby').status_code, 200)
        self.assertEqual(self.client.get('/api/display/dining').json['display']['name'], 'Dining')
        page = self.client.get('/display/lobby').data.decode()
        self.assertIn('window.SIGNAGE_TIMEZONE=', page)
        self.assertIn('window.SIGNAGE_TIME=', page)
        self.assertEqual(self.client.get('/display/absent').status_code, 404)

    def test_first_run_creates_and_seeds_database(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / 'new-data'
            database = data_dir / 'dashboard.sqlite3'
            environment = dict(os.environ, DATA_DIR=str(data_dir))
            self.assertFalse(database.exists())
            for run in range(2):
                subprocess.run([sys.executable, '-c', 'import app'], env=environment,
                               cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True)
                with closing(sqlite3.connect(database)) as db, db:
                    self.assertEqual(db.execute('SELECT slug FROM displays ORDER BY slug').fetchall(),
                                     [('activities',), ('dining',), ('lobby',)])
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM activities').fetchone()[0], 0)
                    if run == 0:
                        db.execute("UPDATE displays SET welcome='Saved welcome' WHERE slug='lobby'")
                    else:
                        self.assertEqual(db.execute("SELECT welcome FROM displays WHERE slug='lobby'").fetchone()[0],
                                         'Saved welcome')

    def test_login_and_create_event(self):
        with self.client:
            token = self.client.get('/login').data.decode().split('name="csrf_token" value="')[1].split('"')[0]
            result = self.client.post('/login', data={'csrf_token':token, 'password':'test-admin-password'})
            self.assertEqual(result.status_code, 302)
            token = self.client.get('/admin').data.decode().split('name="csrf_token" value="')[1].split('"')[0]
            result = self.client.post('/admin/events', data={'csrf_token':token,'title':'Test Dinner','start_time':'17:00','location':'Main Hall','category':'Dining','weekdays':[str(i) for i in range(7)],'enabled':'on'})
            self.assertEqual(result.status_code, 302)
            events = self.client.get('/api/display/dining').json['events']
            self.assertTrue(any(e['title']=='Test Dinner' for e in events))
            lobby_events = self.client.get('/api/display/lobby').json['events']
            self.assertTrue(any(e['title']=='Test Dinner' for e in lobby_events))

    def test_csrf_required(self):
        self.assertEqual(self.client.post('/login',data={'password':'anything'}).status_code,400)

    def test_custom_display_heading(self):
        with self.client.session_transaction() as session:
            session['admin'] = True
            session['csrf'] = 'heading-test-token'
        self.assertIn('id="displayBannerHeading"', self.client.get('/admin').data.decode())
        self.assertIn('id="displayEmptyMessage"', self.client.get('/admin').data.decode())
        form = {'csrf_token': 'heading-test-token', 'name': 'Menu', 'slug': 'menu-test',
                'heading': "TODAY'S MENU & SPECIALS", 'empty_message': 'Kitchen closed & resting today.'}
        try:
            self.assertEqual(self.client.post('/admin/displays', data=form).status_code, 302)
            display = self.client.get('/api/display/menu-test').json['display']
            self.assertEqual(display['heading'], form['heading'])
            self.assertEqual(display['empty_message'], form['empty_message'])
            self.assertIn('<div class="empty-tv">Kitchen closed &amp; resting today.</div>',
                          self.client.get('/display/menu-test').data.decode())
            self.assertIn('id="bannerHeading">TODAY&#39;S MENU &amp; SPECIALS</h1>',
                          self.client.get('/display/menu-test').data.decode())
            self.assertEqual(self.client.get('/api/display/lobby').json['display']['heading'], "TODAY'S ACTIVITIES")
            self.assertEqual(self.client.get('/api/display/lobby').json['display']['empty_message'], 'No activities scheduled for today.')
            form.update(id=str(display['id']), heading='Welcome everyone', empty_message='Please check back tomorrow.')
            self.assertEqual(self.client.post('/admin/displays', data=form).status_code, 302)
            self.assertEqual(self.client.get('/api/display/menu-test').json['display']['heading'], 'Welcome everyone')
            self.assertEqual(self.client.get('/api/display/menu-test').json['display']['empty_message'], 'Please check back tomorrow.')
            form['heading'] = '   '
            form['empty_message'] = '   '
            self.assertEqual(self.client.post('/admin/displays', data=form).status_code, 302)
            self.assertEqual(self.client.get('/api/display/menu-test').json['display']['heading'], "TODAY'S ACTIVITIES")
            self.assertEqual(self.client.get('/api/display/menu-test').json['display']['empty_message'], 'No activities scheduled for today.')
        finally:
            with self.module.connect() as db:
                db.execute("DELETE FROM displays WHERE slug='menu-test'")

    def test_activity_display_assignment(self):
        with self.client.session_transaction() as session:
            session['admin'] = True
            session['csrf'] = 'display-test-token'
        with self.module.connect() as db:
            target = db.execute("SELECT id FROM displays WHERE slug='dining'").fetchone()['id']
        page = self.client.get('/admin').data.decode()
        self.assertIn('select name="display_id" id="eventDisplay"', page)
        self.assertIn(f'<option value="{target}">Dining</option>', page)
        self.assertNotIn('name="category"', page)
        self.assertNotIn('<th>Category</th>', page)
        # Old category settings no longer affect which displays show an activity.
        with self.module.connect() as db:
            db.execute("UPDATE displays SET category='Dining' WHERE id=?", (target,))
        form = {'csrf_token': 'display-test-token', 'title': 'Assigned Activity',
                'start_time': '10:00', 'weekdays': [str(i) for i in range(7)],
                'category': 'Activities', 'enabled': 'on', 'display_id': str(target)}
        try:
            self.assertEqual(self.client.post('/admin/events', data=form).status_code, 302)
            self.assertTrue(any(e['title'] == form['title'] for e in self.client.get('/api/display/dining').json['events']))
            self.assertFalse(any(e['title'] == form['title'] for e in self.client.get('/api/display/lobby').json['events']))
            self.assertFalse(any(e['title'] == form['title'] for e in self.client.get('/api/display/activities').json['events']))
            # Deleting an assigned display must not broadcast its activities elsewhere.
            self.client.post(f'/admin/displays/{target}/delete', data={'csrf_token': form['csrf_token']})
            self.assertEqual(self.client.get('/api/display/dining').status_code, 200)
            with self.module.connect() as db:
                event_id = db.execute('SELECT id FROM activities WHERE title=?', (form['title'],)).fetchone()['id']
            form.update(id=str(event_id), display_id='')
            self.assertEqual(self.client.post('/admin/events', data=form).status_code, 302)
            self.assertTrue(any(e['title'] == form['title'] for e in self.client.get('/api/display/lobby').json['events']))
            self.assertTrue(any(e['title'] == form['title'] for e in self.client.get('/api/display/activities').json['events']))
            self.assertTrue(any(e['title'] == form['title'] for e in self.client.get('/api/display/dining').json['events']))
            for invalid in ('missing', '999999'):
                form['display_id'] = invalid
                self.assertEqual(self.client.post('/admin/events', data=form).status_code, 400)
        finally:
            with self.module.connect() as db:
                db.execute('DELETE FROM activities WHERE title=?', (form['title'],))


if __name__ == '__main__':
    unittest.main()
