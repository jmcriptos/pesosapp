# tests/conftest.py
import os, sys, pytest

# Vars para que app.py no falle al importarse
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("WTF_CSRF_SECRET_KEY", "test-csrf-secret")
os.environ.setdefault("DEFAULT_USERNAME", "testuser")
os.environ.setdefault("DEFAULT_PASSWORD", "testpass")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app as flask_app, db as _db

@pytest.fixture  # Sin scope="session" para que se recree en cada test
def app():
    flask_app.config.update(TESTING=True)
    with flask_app.app_context():
        _db.create_all()   # Crear todas las tablas
        
        # Crear datos mínimos requeridos para los tests
        from app import Rol, Territorio
        
        try:
            # Crear rol de prueba
            rol_test = Rol(nombre='test_role', descripcion='Rol de prueba')
            _db.session.add(rol_test)
            
            # Crear territorio de prueba (opcional)
            territorio_test = Territorio(nombre='test_territorio', descripcion='Territorio de prueba')
            _db.session.add(territorio_test)
            
            _db.session.commit()
            print("Datos de prueba creados exitosamente")  # Debug
            
        except Exception as e:
            print(f"Error creando datos de prueba: {e}")  # Debug
            _db.session.rollback()
        
        # Verificar que las tablas se crearon
        tables = _db.engine.table_names()
        print(f"Tablas creadas: {tables}")  # Debug para ver qué se creó
        
        yield flask_app
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def csrf_token(app):
    from flask_wtf.csrf import generate_csrf
    with app.test_request_context():
        return generate_csrf()
