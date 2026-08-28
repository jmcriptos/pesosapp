"""Carga de `unidades_por_caja` desde el formulario de productos.

El dato ya existía en el modelo (etiquetas por unidades), pero solo se podía
cargar por SQL. Estos tests cubren el campo en los dos formularios: crear
(pantalla Productos) y editar.
"""
import os

import pytest

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
            username='admin', email='admin@test.com', nombre_completo='Admin Test',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _crear_producto(unidades_por_caja=None):
    from app import Producto
    producto = Producto(
        nombre='Croquetas', descripcion='Por caja', temperatura='-18°C',
        se_pesa=False, tax_rate=10.0, qbo_id='QBO-P1',
        unidades_por_caja=unidades_por_caja,
    )
    _db.session.add(producto)
    _db.session.commit()
    return producto


def _datos_edicion(**extra):
    datos = {
        'nombre': 'Croquetas', 'descripcion': 'Por caja',
        'temperatura': '-18°C', 'qbo_id': 'QBO-P1', 'tax_rate': '10',
        'proveedor': '',
    }
    datos.update(extra)
    return datos


# === Formulario de editar ===

def test_form_de_editar_producto_tiene_el_campo(logged_client, app):
    """El form de editar muestra el campo con el valor guardado."""
    with app.app_context():
        producto = _crear_producto(unidades_por_caja=24)

        resp = logged_client.get(f'/productos/{producto.id}/editar')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'name="unidades_por_caja"' in html
        assert 'value="24"' in html


def test_editar_producto_guarda_las_unidades(logged_client, app):
    with app.app_context():
        from app import Producto
        producto = _crear_producto()
        producto_id = producto.id

        resp = logged_client.post(
            f'/productos/{producto_id}/editar',
            data=_datos_edicion(unidades_por_caja='24'),
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert _db.session.get(Producto, producto_id).unidades_por_caja == 24


def test_editar_producto_permite_vaciar_las_unidades(logged_client, app):
    """Dejar el campo vacío vuelve el producto a `Boxes:` (NULL)."""
    with app.app_context():
        from app import Producto
        producto = _crear_producto(unidades_por_caja=24)
        producto_id = producto.id

        logged_client.post(
            f'/productos/{producto_id}/editar',
            data=_datos_edicion(unidades_por_caja=''),
            follow_redirects=True,
        )

        assert _db.session.get(Producto, producto_id).unidades_por_caja is None


def test_editar_producto_con_valor_invalido_conserva_el_anterior(logged_client, app):
    """Un valor que no es un entero no borra el que ya estaba, y avisa.

    Perder un 24 cargado por un typo sería justo el tipo de pérdida silenciosa
    que no se nota hasta que sale mal la etiqueta impresa.
    """
    with app.app_context():
        from app import Producto
        producto = _crear_producto(unidades_por_caja=24)
        producto_id = producto.id

        resp = logged_client.post(
            f'/productos/{producto_id}/editar',
            data=_datos_edicion(unidades_por_caja='24 uds'),
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert _db.session.get(Producto, producto_id).unidades_por_caja == 24
        assert 'unidades por caja' in resp.get_data(as_text=True).lower()


def test_editar_producto_rechaza_cero_y_negativos(logged_client, app):
    """0 unidades por caja no significa nada: se trata como valor inválido."""
    with app.app_context():
        from app import Producto
        producto = _crear_producto(unidades_por_caja=24)
        producto_id = producto.id

        for invalido in ('0', '-5'):
            logged_client.post(
                f'/productos/{producto_id}/editar',
                data=_datos_edicion(unidades_por_caja=invalido),
                follow_redirects=True,
            )
            assert _db.session.get(Producto, producto_id).unidades_por_caja == 24, invalido


# === Formulario de crear ===

def test_form_de_crear_producto_tiene_el_campo(logged_client, app):
    with app.app_context():
        resp = logged_client.get('/productos')
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'name="unidades_por_caja"' in html


def test_crear_producto_guarda_las_unidades(logged_client, app):
    with app.app_context():
        from app import Producto

        resp = logged_client.post('/productos', data={
            'nombre': 'Croquetas', 'descripcion': 'Por caja',
            'temperatura': '-18°C', 'qbo_id': 'QBO-NEW', 'tax_rate': '10',
            'proveedor': '', 'unidades_por_caja': '24',
        }, follow_redirects=True)

        assert resp.status_code == 200
        creado = Producto.query.filter_by(qbo_id='QBO-NEW').first()
        assert creado is not None
        assert creado.unidades_por_caja == 24


def test_crear_producto_sin_unidades_las_deja_en_null(logged_client, app):
    with app.app_context():
        from app import Producto

        logged_client.post('/productos', data={
            'nombre': 'Pollo', 'descripcion': '', 'temperatura': '',
            'qbo_id': 'QBO-NEW2', 'tax_rate': '10', 'proveedor': '',
            'unidades_por_caja': '',
        }, follow_redirects=True)

        creado = Producto.query.filter_by(qbo_id='QBO-NEW2').first()
        assert creado is not None
        assert creado.unidades_por_caja is None
