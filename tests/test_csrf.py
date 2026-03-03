import os
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')

from app import app as flask_app
from app import db as _db


@pytest.fixture
def client():
    original_testing = flask_app.config.get('TESTING')
    original_csrf = flask_app.config.get('WTF_CSRF_ENABLED', True)
    original_db_uri = flask_app.config.get('SQLALCHEMY_DATABASE_URI')

    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )

    with flask_app.app_context():
        _db.create_all()
        with flask_app.test_client() as c:
            yield c
        _db.drop_all()

    flask_app.config.update(
        TESTING=original_testing,
        WTF_CSRF_ENABLED=original_csrf,
        SQLALCHEMY_DATABASE_URI=original_db_uri,
    )


def test_post_without_csrf_returns_400(client):
    resp = client.post('/_csrf_ping')
    assert resp.status_code == 400


def test_post_with_csrf_returns_200(client):
    # Obtiene cookie de sesión y token desde /login (GET)
    r = client.get('/login')
    # Extraer token de meta en la respuesta
    token = None
    if b'name="csrf-token"' in r.data:
        import re
        m = re.search(rb'<meta name="csrf-token" content="([^"]+)">', r.data)
        if m:
            token = m.group(1).decode('utf-8')

    assert token, 'No se encontró meta csrf-token en la respuesta'

    resp = client.post('/_csrf_ping', headers={'X-CSRFToken': token})
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True}


def test_login_post_requires_csrf(client):
    # Enviar POST al login sin csrf -> 400
    resp = client.post('/login', data={'username': 'u', 'password': 'p'})
    assert resp.status_code == 400


def test_login_post_with_hidden_csrf_ok(client):
    # Obtener token desde GET /login
    r = client.get('/login')
    token = None
    if b'name="csrf-token"' in r.data:
        import re
        m = re.search(rb'<meta name="csrf-token" content="([^"]+)">', r.data)
        if m:
            token = m.group(1).decode('utf-8')

    assert token, 'No se encontró meta csrf-token en la respuesta'

    # Enviar POST al login con campo hidden
    resp = client.post('/login', data={
        'username': 'wrong',
        'password': 'wrong',
        'csrf_token': token
    }, follow_redirects=False)
    # Debe procesar la vista (no 400 por CSRF). Estado 200 o 302 por redirect con flash
    assert resp.status_code in (200, 302)

