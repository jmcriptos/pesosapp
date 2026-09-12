# tests/test_privacidad.py
"""La política de privacidad es pública: Google la tiene que poder abrir
para publicar la app OAuth de Drive."""
import pytest
from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


def test_privacidad_es_publica_sin_login(app):
    resp = app.test_client().get('/privacidad')
    assert resp.status_code == 200
    assert 'Política de privacidad'.encode() in resp.data
    assert b'Google Drive' in resp.data
    assert b'jomarfood@gmail.com' in resp.data
