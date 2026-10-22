import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-change-this')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
DATA_DIR = Path(os.environ.get('DATA_DIR', Path(__file__).parent / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'dashboard.sqlite3'
try:
    ZONE = ZoneInfo(os.environ.get('TZ', 'America/New_York'))
except ZoneInfoNotFoundError:
    ZONE = ZoneInfo('UTC')


def now():
    return datetime.now(ZONE)


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=10000')
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS displays (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
              subtitle TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
              welcome TEXT NOT NULL DEFAULT '', theme TEXT NOT NULL DEFAULT 'navy'
            );
            CREATE TABLE IF NOT EXISTS activities (
              id INTEGER PRIMARY KEY, title TEXT NOT NULL, location TEXT NOT NULL DEFAULT '',
              start_time TEXT NOT NULL, end_time TEXT NOT NULL DEFAULT '',
              event_date TEXT NOT NULL DEFAULT '', weekdays TEXT NOT NULL DEFAULT '',
              category TEXT NOT NULL DEFAULT '', details TEXT NOT NULL DEFAULT '',
              enabled INTEGER NOT NULL DEFAULT 1
            );
        ''')
        if 'display_id' not in {column['name'] for column in db.execute('PRAGMA table_info(activities)')}:
            db.execute('ALTER TABLE activities ADD COLUMN display_id INTEGER REFERENCES displays(id)')
        if 'heading' not in {column['name'] for column in db.execute('PRAGMA table_info(displays)')}:
            db.execute("ALTER TABLE displays ADD COLUMN heading TEXT NOT NULL DEFAULT 'TODAY''S ACTIVITIES'")
        if 'empty_message' not in {column['name'] for column in db.execute('PRAGMA table_info(displays)')}:
            db.execute("ALTER TABLE displays ADD COLUMN empty_message TEXT NOT NULL DEFAULT 'No activities scheduled for today.'")
        if not db.execute('SELECT 1 FROM displays LIMIT 1').fetchone():
            db.execute('INSERT INTO displays (name,slug,subtitle,welcome) VALUES (?,?,?,?)',
                       ('Main Lobby','lobby','Today at our community','Welcome!'))
            db.execute('INSERT INTO displays (name,slug,subtitle) VALUES (?,?,?)',
                       ('Activities','activities','Games, classes & events'))
            db.execute('INSERT INTO displays (name,slug,subtitle) VALUES (?,?,?)',
                       ('Dining','dining','Dining schedule'))


init_db()


@app.after_request
def secure_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response


def admin_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return inner


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


@app.context_processor
def inject_globals():
    return {'csrf_token': csrf_token, 'current_year': now().year}


@app.before_request
def validate_csrf():
    if request.method == 'POST':
        submitted = request.form.get('csrf_token', '')
        if not hmac.compare_digest(submitted, session.get('csrf', '')) or not submitted:
            abort(400, 'Invalid form token. Reload the page and try again.')


def clean(value, maximum=120):
    return (value or '').strip()[:maximum]


def checked_date(value):
    if not value:
        return ''
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        abort(400, 'Invalid date')


def checked_time(value, required=False):
    value = clean(value, 5)
    if not value and not required:
        return ''
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        abort(400, 'Invalid time')
    return value


def get_display(slug):
    with connect() as db:
        record = db.execute('SELECT * FROM displays WHERE slug=?', (slug,)).fetchone()
    if record is None:
        abort(404)
    return record


def filtered_events(display, target_date):
    day_index = target_date.weekday()  # Monday = 0
    with connect() as db:
        rows = db.execute('SELECT * FROM activities WHERE enabled=1 ORDER BY start_time, title').fetchall()
    results = []
    for event in rows:
        if event['display_id'] is not None:
            if event['display_id'] != display['id']:
                continue
        if event['event_date']:
            if event['event_date'] != target_date.isoformat():
                continue
        elif not event['weekdays'] or str(day_index) not in event['weekdays'].split(','):
            continue
        results.append(dict(event))
    return results


@app.route('/')
def index():
    with connect() as db:
        displays = db.execute('SELECT * FROM displays ORDER BY name').fetchall()
    return render_template('index.html', displays=displays)


@app.route('/display/<slug>')
def display(slug):
    item = get_display(slug)
    current_time = now()
    today = current_time.date()
    return render_template('display.html', display=item, events=filtered_events(item, today), today=today,
                           current_time=current_time, timezone=ZONE.key)


@app.route('/api/display/<slug>')
def display_api(slug):
    item = get_display(slug)
    current_time = now()
    today = current_time.date()
    return jsonify({'date': today.isoformat(), 'time': current_time.isoformat(), 'events': filtered_events(item, today),
                    'display': dict(item)})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        expected = os.environ.get('ADMIN_PASSWORD', '')
        if not expected or expected == 'replace-with-unique-long-password':
            flash('Set a secure ADMIN_PASSWORD in .env first.', 'error')
        elif hmac.compare_digest(request.form.get('password', ''), expected):
            session.clear()
            session['admin'] = True
            csrf_token()
            return redirect(url_for('admin'))
        else:
            flash('Incorrect password.', 'error')
    return render_template('login.html')


@app.post('/logout')
@admin_required
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin():
    with connect() as db:
        events = db.execute('SELECT activities.*, displays.name AS display_name FROM activities LEFT JOIN displays ON activities.display_id=displays.id ORDER BY event_date DESC, start_time, title').fetchall()
        displays = db.execute('SELECT * FROM displays ORDER BY name').fetchall()
    return render_template('admin.html', events=events, displays=displays, weekdays=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])


@app.post('/admin/events')
@admin_required
def save_event():
    form = request.form
    title = clean(form.get('title'))
    if not title:
        abort(400, 'Activity title required')
    event_date = checked_date(form.get('event_date'))
    weekdays = sorted({int(d) for d in form.getlist('weekdays') if d in {str(i) for i in range(7)}})
    if not event_date and not weekdays:
        abort(400, 'Choose a date or at least one recurring day')
    display_id = form.get('display_id', '').strip()
    if display_id:
        try:
            display_id = int(display_id)
        except ValueError:
            abort(400, 'Choose a valid display')
    else:
        display_id = None
    values = (title, clean(form.get('location')), checked_time(form.get('start_time'), True),
              checked_time(form.get('end_time')), event_date, ','.join(map(str, weekdays)) if not event_date else '',
              clean(form.get('details'), 400), 1 if form.get('enabled') else 0, display_id)
    event_id = form.get('id', '').strip()
    with connect() as db:
        if display_id is not None and not db.execute('SELECT 1 FROM displays WHERE id=?', (display_id,)).fetchone():
            abort(400, 'Choose a valid display')
        if event_id:
            record = db.execute('UPDATE activities SET title=?,location=?,start_time=?,end_time=?,event_date=?,weekdays=?,details=?,enabled=?,display_id=? WHERE id=?', values + (event_id,))
            if record.rowcount == 0:
                abort(404)
        else:
            db.execute('INSERT INTO activities (title,location,start_time,end_time,event_date,weekdays,details,enabled,display_id) VALUES (?,?,?,?,?,?,?,?,?)', values)
    flash('Activity saved.', 'success')
    return redirect(url_for('admin'))


@app.post('/admin/events/<int:event_id>/delete')
@admin_required
def delete_event(event_id):
    with connect() as db:
        db.execute('DELETE FROM activities WHERE id=?', (event_id,))
    flash('Activity deleted.', 'success')
    return redirect(url_for('admin'))


@app.post('/admin/displays')
@admin_required
def save_display():
    form = request.form
    name = clean(form.get('name'), 70)
    slug = clean(form.get('slug'), 70).lower()
    if not name or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        abort(400, 'Provide a display name and a URL slug (lowercase letters, numbers, hyphens).')
    values = (name, slug, clean(form.get('subtitle')), clean(form.get('welcome'),180),
              clean(form.get('heading'), 80) or "TODAY'S ACTIVITIES",
              clean(form.get('empty_message'), 180) or 'No activities scheduled for today.',
              form.get('theme') if form.get('theme') in ('navy','forest','plum') else 'navy')
    display_id = form.get('id', '').strip()
    try:
        with connect() as db:
            if display_id:
                result = db.execute('UPDATE displays SET name=?,slug=?,subtitle=?,welcome=?,heading=?,empty_message=?,theme=? WHERE id=?', values + (display_id,))
                if result.rowcount == 0:
                    abort(404)
            else:
                db.execute('INSERT INTO displays (name,slug,subtitle,welcome,heading,empty_message,theme) VALUES (?,?,?,?,?,?,?)', values)
    except sqlite3.IntegrityError:
        abort(400, 'That display URL is already in use.')
    flash('Display saved.', 'success')
    return redirect(url_for('admin') + '#displays')


@app.post('/admin/displays/<int:display_id>/delete')
@admin_required
def delete_display(display_id):
    with connect() as db:
        if db.execute('SELECT 1 FROM activities WHERE display_id=? LIMIT 1', (display_id,)).fetchone():
            flash('Move activities assigned to this display to another display or All displays before deleting it.', 'error')
            return redirect(url_for('admin') + '#displays')
        db.execute('DELETE FROM displays WHERE id=?', (display_id,))
    flash('Display deleted.', 'success')
    return redirect(url_for('admin') + '#displays')


if __name__ == '__main__':
    app.run('127.0.0.1', 8080, debug=False)
