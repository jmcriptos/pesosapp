"""P2 del critique del listado: las acciones no pueden moverse bajo el dedo.

En escritorio un `pendiente` mostraba [Pesar][Editar][Borrar] y un `preparado`
[Editar][Facturar][Borrar]: la acción principal se corría al medio y el editar
saltaba al primer puesto, con 100px de deriva entre filas adyacentes de 63px.
Quien baja por la columna haciendo clic sin releer toca otro control — y uno de
los candidatos es Facturar.

Además la tarjeta móvil nunca decía CUÁNTO se pasó un pedido: el escritorio
renderiza «3 d tarde» y el móvil solo la fecha, en el mismo gris que uno a
tiempo. La magnitud de la urgencia existía solo en el dispositivo que estos
usuarios no llevan.

Critique: .impeccable/critique/2026-08-28T08-22-35Z__templates-pedidos-html.md
"""
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin', email='admin@test.com', nombre_completo='Admin',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.add(Cliente(nombre='Distribuidora Norte', territorio_id=territorio.id,
                                moneda='XCG', qbo_id='C1'))
        _db.session.add(Producto(nombre='Producto', temperatura='4°C', se_pesa=False,
                                 tax_rate=10.0, qbo_id='P1'))
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _hoy_local():
    from app import DASHBOARD_TIMEZONE
    return datetime.now(DASHBOARD_TIMEZONE).date()


def _pedido(estado='pendiente', dias=1):
    from app import Pedido, Cliente, Producto, DetallePedido
    p = Pedido(cliente_id=Cliente.query.first().id, estado=estado, tipo_cambio=1.0)
    p.fecha_entrega = _hoy_local() + timedelta(days=dias)
    _db.session.add(p)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=p.id, producto_id=Producto.query.first().id,
        cajas=1, cajas_pedidas=1, peso=0,
        precio_unitario=Decimal('10'), subtotal=Decimal('10'), es_linea_pedido=True,
    ))
    _db.session.commit()
    return p


def _bloque_acciones_escritorio(html, pedido_id):
    """El grupo de acciones del <tr> de ese pedido."""
    for tr in re.findall(r'<tr[^>]*>.*?</tr>', html, re.S):
        if f'PED-{pedido_id}<' in tr:
            m = re.search(r'<div class="pedido-row-actions.*?</div>\s*</td>', tr, re.S)
            return m.group(0) if m else ''
    return ''


def _orden_de_acciones(bloque):
    """Los roles de acción en el orden en que aparecen en el markup."""
    orden = []
    for m in re.finditer(r'class="([^"]*(?:row-action|action)[^"]*)"', bloque):
        clases = m.group(1)
        if 'row-action-main' in clases:
            orden.append('principal')
        elif 'row-action-edit' in clases:
            orden.append('editar')
        elif 'row-action-danger' in clases:
            orden.append('borrar')
    return orden


# === Las acciones ocupan siempre el mismo puesto ===

def test_pendiente_y_preparado_ordenan_igual_sus_acciones(app, logged_client):
    """Principal, editar, borrar. En las dos filas, en el mismo orden."""
    with app.app_context():
        pendiente = _pedido('pendiente')
        preparado = _pedido('preparado')

        html = logged_client.get('/pedidos').get_data(as_text=True)

        esperado = ['principal', 'editar', 'borrar']
        assert _orden_de_acciones(_bloque_acciones_escritorio(html, pendiente.id)) == esperado
        assert _orden_de_acciones(_bloque_acciones_escritorio(html, preparado.id)) == esperado


def test_la_accion_principal_no_cambia_de_ancho_entre_filas(app, logged_client):
    """«Pesar» y «Facturar» tienen largos distintos: sin un ancho mínimo común,
    editar y borrar se corren de fila a fila aunque el orden sea el mismo."""
    with app.app_context():
        _pedido('pendiente')

        css = open('static/css/pedidos_list.css', encoding='utf-8').read()
        bloque = re.search(
            r'\.pedido-row-actions \.row-action-main \{[^}]*\}', css, re.S)

        assert bloque, 'no encontré la regla de la acción principal'
        assert 'min-width' in bloque.group(0), (
            'la acción principal necesita un ancho mínimo para no mover a las otras'
        )


# === La urgencia se ve en el teléfono ===

def test_la_tarjeta_movil_dice_cuantos_dias_de_atraso(app, logged_client):
    """El escritorio ya mostraba «3 d tarde»; el móvil, solo la fecha."""
    with app.app_context():
        _pedido('pendiente', dias=-3)

        html = logged_client.get('/pedidos').get_data(as_text=True)
        tarjeta = re.search(r'<div class="pedido-card".*?<!-- /pedido-card -->|<div class="pedido-card".*?</div>\s*</div>\s*</div>', html, re.S)

        assert tarjeta, 'no encontré la tarjeta móvil'
        assert '3 d tarde' in tarjeta.group(0)


def test_la_tarjeta_de_un_pedido_a_tiempo_no_habla_de_atraso(app, logged_client):
    with app.app_context():
        _pedido('pendiente', dias=4)

        html = logged_client.get('/pedidos').get_data(as_text=True)
        # La sección móvil entera: si «tarde» no está en ningún lado, no está
        # en la tarjeta.
        movil = html.split('tabla-pedidos-card')[0]

        assert 'tarde' not in movil


# === Una sola fuente de iconos ===

def test_font_awesome_se_carga_una_sola_vez(app, logged_client):
    """Se cargaban 6.7.2 (base) y 6.4.2 (pedidos): dos fuentes de iconos
    completas en un teléfono de campo, para el mismo juego de glifos."""
    with app.app_context():
        html = logged_client.get('/pedidos').get_data(as_text=True)

        assert len(re.findall(r'font-awesome/[\d.]+/css/all\.min\.css', html)) == 1
