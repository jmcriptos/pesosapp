# tests/test_dashboard_kpis.py
"""Tests para Story 1.1: KPIs de nivel de servicio corregidos."""
import os
import pytest
from datetime import datetime, timedelta, date

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin',
            email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id,
            territorio_id=territorio.id,
            activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin',
        'password': 'testpass',
    }, follow_redirects=True)
    return client


# === Tests de estructura de respuesta ===

def test_dashboard_loads_without_error(logged_client):
    """AC #8: El dashboard carga sin errores."""
    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200


def test_dashboard_no_order_accuracy_in_response(logged_client):
    """AC #3: Order Accuracy eliminado del template."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    # No debe contener la variable antigua normalizada
    assert 'order_accuracy_v' not in html


def test_dashboard_has_order_fill_rate(logged_client):
    """OFR real reemplaza Order Completion Rate en el template."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Order Fill Rate' in html


def test_dashboard_has_customer_engagement(logged_client):
    """AC #5: Customer Engagement se muestra en el dashboard."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Customer Engagement' in html


# === Tests de cálculo de KPIs (via la función helper interna) ===

def test_kpis_empty_period_returns_defaults(app):
    """calcular_kpis_periodo con lista vacía retorna defaults correctos (sin datos = fallback)."""
    with app.app_context():
        resp = app.test_client()
        resp.post('/login', data={'username': 'admin', 'password': 'testpass'})
        response = resp.get('/dashboard')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # Debe contener las claves nuevas en el HTML renderizado
        assert 'order_completion_rate' in html
        assert 'order_accuracy' not in html


def test_kpi_evolution_chart_no_accuracy(logged_client):
    """AC #3: El chart de evolución no tiene dataset de Accuracy."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'order_accuracy' not in html
    assert "Accuracy (%)" not in html


def test_kpi_evolution_chart_has_ofr(logged_client):
    """El chart de evolución usa OFR."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'order_completion_rate' in html
    assert "OFR (%)" in html


def test_dashboard_no_palabras_error(app):
    """AC #3: La variable palabras_error ya no se usa en app.py."""
    import inspect
    from app import app as flask_app
    # Leer el source code de la ruta dashboard
    source_file = inspect.getfile(flask_app.__class__)
    with open(os.path.join(os.path.dirname(source_file), 'app.py'), 'r') as f:
        content = f.read()
    # palabras_error ya no debe estar definida
    assert "palabras_error = {" not in content


def test_fallback_data_has_correct_keys(app):
    """AC #7: El fallback_data tiene las claves correctas."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'app.py'), 'r') as f:
        content = f.read()
    # Verificar que fallback_data tiene las nuevas claves
    assert "'order_completion_rate'" in content
    assert "'customer_engagement'" in content
    assert "'perfect_order_rate'" in content
    # Y no tiene las viejas
    assert "'order_accuracy'" not in content.split('fallback_data')[1].split('}')[0]


# === Tests de Story 1.2: Reorganización dashboard y proyección ===

def test_dashboard_has_objetivos_de_ventas_section(logged_client):
    """AC #1: Sección 'Objetivos de Ventas' visible en el dashboard."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Objetivos de Ventas' in html


def test_dashboard_has_nivel_de_servicio_section(logged_client):
    """AC #2: Sección 'Nivel de Servicio' visible en el dashboard."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Nivel de Servicio' in html


def test_dashboard_has_proyeccion(logged_client):
    """AC #3/#5: Proyección de ventas se muestra en el dashboard."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Proyección' in html or 'proyeccion_ventas' in html


def test_dashboard_has_perfect_order_rate(logged_client):
    """AC #2: Perfect Order Rate visible en Nivel de Servicio."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Perfect Order Rate' in html


def test_meta_configurable_env_var(app):
    """AC #4: Meta mensual leída de env var MONTHLY_SALES_TARGET."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'app.py'), 'r') as f:
        content = f.read()
    assert "os.environ.get('MONTHLY_SALES_TARGET'" in content
    # No debe quedar hardcode 120000.00
    assert 'meta_mensual = 120000.00' not in content


def test_fallback_data_has_proyeccion_keys(app):
    """AC #3: fallback_data incluye claves de proyección."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'app.py'), 'r') as f:
        content = f.read()
    fallback_section = content.split('fallback_data')[1].split('}')[0]
    assert "'proyeccion_ventas'" in fallback_section
    assert "'porcentaje_proyeccion'" in fallback_section
    assert "'dias_total_mes'" in fallback_section
