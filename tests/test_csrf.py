import os
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


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


