"""Un pedido recién facturado tiene que poder encontrarse, y un pedido
borrado tiene que dejar rastro.

Los dos problemas salieron del mismo reporte ("se perdió el pedido después de
facturarlo"): el pedido estaba, pero el orden del listado lo mandaba al fondo
—dentro de los facturados se ordenaba por fecha de entrega ASCENDENTE, o sea
lo más viejo primero— y encima no había forma de auditar qué había pasado.
"""
import os
import re
from datetime import date, datetime
from decimal import Decimal

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
        from app import Rol, Territorio, Vendedor, Cliente

        rol = Rol(nombre='super_admin', descripcion='Admin')
        territorio = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([rol, territorio])
        _db.session.flush()
        vendedor = Vendedor(
            username='admin', email='a@test.com', nombre_completo='Admin',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add_all([vendedor, Cliente(nombre='DeliNova', moneda='XCG')])
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _pedido(estado, entrega, invoice=None):
    from app import Pedido, DetallePedido, Producto

    producto = Producto.query.first()
    if producto is None:
        producto = Producto(nombre='Wings', tax_rate=10.0, se_pesa=False)
        _db.session.add(producto)
        _db.session.flush()

    p = Pedido(cliente_id=1, estado=estado, tipo_cambio=1.0,
               fecha_entrega=entrega, invoice_id_qbo=invoice)
    _db.session.add(p)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=p.id, producto_id=producto.id, cajas=1, cajas_pedidas=1,
        peso=0, precio_unitario=Decimal('10.00'), subtotal=Decimal('10.00'),
        es_linea_pedido=True,
    ))
    _db.session.commit()
    return p.id


def _ids_en_pantalla(respuesta):
    """Ids de pedido en el orden en que los muestra el listado."""
    cuerpo = respuesta.get_data(as_text=True)
    return [int(n) for n in re.findall(r'data-href="/pedidos/(\d+)/detalles"', cuerpo)]


# ------------------------------------------------------------------- orden


def test_el_ultimo_facturado_va_primero(app, logged_client):
    """Dentro de los facturados no hay urgencia que ordenar: lo que se busca es
    lo último. Ordenarlos por fecha de entrega ascendente mandaba el recién
    facturado al fondo (posición 28 de 28 en producción)."""
    with app.app_context():
        viejo = _pedido('facturado', date(2026, 8, 10), invoice='1')
        medio = _pedido('facturado', date(2026, 8, 20), invoice='2')
        nuevo = _pedido('facturado', date(2026, 8, 29), invoice='3')

    ids = _ids_en_pantalla(logged_client.get('/pedidos?estado=facturado'))

    assert ids[:3] == [nuevo, medio, viejo], (
        f'Esperaba el más reciente primero; el listado devolvió {ids[:3]}'
    )


def test_los_activos_siguen_ordenados_por_urgencia(app, logged_client):
    """Lo no facturado no cambia: la entrega más urgente arriba."""
    with app.app_context():
        lejano = _pedido('pendiente', date(2026, 9, 30))
        urgente = _pedido('pendiente', date(2026, 8, 29))

    ids = _ids_en_pantalla(logged_client.get('/pedidos?estado=todos'))

    assert ids[:2] == [urgente, lejano], f'Orden de activos incorrecto: {ids[:2]}'


def test_los_facturados_siguen_debajo_de_los_activos(app, logged_client):
    with app.app_context():
        activo = _pedido('pendiente', date(2026, 9, 30))
        facturado = _pedido('facturado', date(2026, 8, 1), invoice='9')

    ids = _ids_en_pantalla(logged_client.get('/pedidos?estado=todos'))

    assert ids.index(activo) < ids.index(facturado)


def test_un_facturado_sin_fecha_no_le_gana_a_uno_con_fecha(app, logged_client):
    """Los 910 pedidos históricos no tienen fecha_entrega y no deben treparse
    por encima de los facturados recientes."""
    with app.app_context():
        historico = _pedido('facturado', None, invoice='1')
        reciente = _pedido('facturado', date(2026, 8, 29), invoice='2')

    ids = _ids_en_pantalla(logged_client.get('/pedidos?estado=facturado'))

    assert ids.index(reciente) < ids.index(historico)


# -------------------------------------------------------------- auditoría


def test_borrar_un_pedido_deja_rastro_que_sobrevive(app, logged_client):
    """`pedido_evento` tiene ON DELETE CASCADE: el evento que escribe
    `eliminar_pedido` lo borra el propio DELETE del pedido. El rastro tiene que
    quedar en una tabla que no cascadee."""
    from app import EventoAuditoria, PedidoEvento

    with app.app_context():
        pedido_id = _pedido('pendiente', date(2026, 8, 29))

    logged_client.post(f'/pedidos/{pedido_id}/eliminar', follow_redirects=True)

    with app.app_context():
        assert PedidoEvento.query.filter_by(pedido_id=pedido_id).count() == 0, (
            'El cascade borra pedido_evento — el rastro no puede vivir ahí'
        )
        eventos = EventoAuditoria.query.all()
        rastro = [e for e in eventos if str(pedido_id) in (e.detalle or '')
                  or str(pedido_id) in (e.accion or '')]
        assert rastro, (
            f'No quedó rastro del borrado del pedido {pedido_id}. '
            f'Eventos: {[(e.accion, e.detalle) for e in eventos]}'
        )


def test_el_rastro_dice_que_se_perdio(app, logged_client):
    """Sirve para reconstruir: estado, líneas y cajas pesadas."""
    from app import EventoAuditoria

    with app.app_context():
        pedido_id = _pedido('preparado', date(2026, 8, 29))

    logged_client.post(f'/pedidos/{pedido_id}/eliminar', follow_redirects=True)

    with app.app_context():
        detalle = ' '.join(
            (e.detalle or '') for e in EventoAuditoria.query.all()
        )
        assert 'preparado' in detalle, f'Falta el estado en el rastro: {detalle!r}'
        assert 'líneas=1' in detalle, f'Faltan las líneas en el rastro: {detalle!r}'
