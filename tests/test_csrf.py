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
    # Obtiene cookie de sesión y token desde una vista GET que renderiza base
    # Forzamos a crear sesión accediendo a login
    r = client.get('/login')
    # Extraer token de meta en la respuesta
    token = None
    if b'name="csrf-token"' in r.data:
        # búsqueda simple del content
        import re
        m = re.search(rb'<meta name="csrf-token" content="([^"]+)">', r.data)
        if m:
            token = m.group(1).decode('utf-8')

    assert token, 'No se encontró meta csrf-token en la respuesta'

    resp = client.post('/_csrf_ping', headers={'X-CSRFToken': token})
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True}


