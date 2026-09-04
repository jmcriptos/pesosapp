"""Los reportes de auditoría: saldo, kardex, rendimiento y trazabilidad."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([v, cli, prod, ing])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id,
                   ingrediente=ing.id)
        yield flask_app
        _db.drop_all()


def _cadena_completa():
    """Recepción → corrida → caja → pedido facturado. Devuelve las piezas."""
    from maquila import servicios
    from app import Pedido, DetallePedido
    rec = servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
        vendedor_id=IDS['vendedor'], documento_cliente='GUIA-77',
        lineas=[{'ingrediente_id': IDS['ingrediente'],
                 'peso_total': Decimal('200')}])
    corrida = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-0903',
        fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['vendedor'],
        fecha_vencimiento=date(2026, 12, 3))
    servicios.agregar_caja_producida(corrida, Decimal('40'))
    _db.session.commit()
    servicios.cerrar_corrida(corrida, {IDS['ingrediente']: Decimal('50')},
                             IDS['vendedor'])
    pedido = Pedido(cliente_id=IDS['cliente'], estado='facturado',
                    doc_number_qbo='1234')
    _db.session.add(pedido)
    _db.session.flush()
    detalle = DetallePedido(pedido_id=pedido.id, producto_id=IDS['producto'],
                            cajas=1, cajas_pedidas=1, peso=0,
                            precio_unitario=0, subtotal=0, es_linea_pedido=True)
    _db.session.add(detalle)
    _db.session.commit()
    servicios.asignar_cajas(detalle, [corrida.cajas[0]], IDS['vendedor'])
    return rec, corrida, pedido


def test_saldos_lista_las_lineas_todavia_abiertas(app):
    from maquila import reportes
    with app.app_context():
        _cadena_completa()
        filas = reportes.saldos(IDS['cliente'])
        assert len(filas) == 1
        assert filas[0]['saldo'] == Decimal('150')
        abiertas = filas[0]['lineas_abiertas']
        assert len(abiertas) == 1
        assert abiertas[0]['codigo'] == 'R-2026-0001'
        assert abiertas[0]['saldo'] == Decimal('150')


def test_el_kardex_acumula_el_saldo_en_orden(app):
    from maquila import reportes
    with app.app_context():
        _cadena_completa()
        filas = reportes.kardex(IDS['cliente'])
        assert [f['tipo'] for f in filas] == ['entrada', 'salida']
        assert filas[0]['saldo_acumulado'] == Decimal('200')
        assert filas[1]['saldo_acumulado'] == Decimal('150')
        assert filas[0]['responsable'] == 'Admin'


def test_el_rendimiento_calcula_merma_y_porcentaje(app):
    from maquila import reportes
    with app.app_context():
        _cadena_completa()
        filas = reportes.rendimiento(IDS['cliente'])
        assert len(filas) == 1
        fila = filas[0]
        assert fila['consumido'] == Decimal('50.000')
        assert fila['producido'] == Decimal('40.000')
        assert fila['merma'] == Decimal('10.000')
        assert fila['merma_pct'] == Decimal('20.0')


def test_trazar_un_lote_llega_hasta_la_factura(app):
    from maquila import reportes
    with app.app_context():
        rec, corrida, pedido = _cadena_completa()
        r = reportes.trazar('L-0903')
        assert r['encontrado'] is True
        assert r['tipo'] == 'corrida'
        assert rec.codigo in [x['codigo'] for x in r['hacia_atras']]
        adelante = r['hacia_adelante']
        assert adelante[0]['pedido_id'] == pedido.id
        assert adelante[0]['doc_number_qbo'] == '1234'


def test_trazar_por_codigo_de_recepcion_avanza_hasta_el_pedido(app):
    from maquila import reportes
    with app.app_context():
        _rec, _corrida, pedido = _cadena_completa()
        r = reportes.trazar('R-2026-0001')
        assert r['encontrado'] is True
        assert r['tipo'] == 'recepcion'
        assert r['hacia_adelante'][0]['pedido_id'] == pedido.id


def test_trazar_algo_que_no_existe_no_revienta(app):
    from maquila import reportes
    with app.app_context():
        r = reportes.trazar('NO-EXISTE')
        assert r['encontrado'] is False
        assert r['ambiguo'] is False
        assert r['hacia_atras'] == []
        assert r['hacia_adelante'] == []


def test_una_caja_pesada_a_mano_se_marca_sin_origen(app):
    from maquila import reportes
    from app import Pedido, DetallePedido, CajaPesada
    with app.app_context():
        _cadena_completa()
        pedido = Pedido(cliente_id=IDS['cliente'], estado='pendiente')
        _db.session.add(pedido)
        _db.session.flush()
        detalle = DetallePedido(pedido_id=pedido.id, producto_id=IDS['producto'],
                                cajas=1, cajas_pedidas=1, peso=0,
                                precio_unitario=0, subtotal=0,
                                es_linea_pedido=True)
        _db.session.add(detalle)
        _db.session.flush()
        _db.session.add(CajaPesada(detalle_pedido_id=detalle.id, numero=1,
                                   peso=Decimal('9'), lote='A-MANO',
                                   fecha_elaboracion=date(2026, 9, 3),
                                   fecha_vencimiento=date(2026, 12, 3)))
        _db.session.commit()
        r = reportes.trazar(str(pedido.id))
        assert r['encontrado'] is True
        assert r['ambiguo'] is False
        assert r['hacia_atras'][0]['sin_origen'] is True
        # La fila "a mano" no puede hacerse pasar por un ingrediente real: el
        # nombre del producto va en su propia clave, no pisa 'ingrediente'.
        assert r['hacia_atras'][0]['ingrediente'] is None
        assert r['hacia_atras'][0]['producto'] == 'Chorizo'


def test_trazar_docnumber_que_choca_con_id_de_otro_pedido_es_ambiguo(app):
    """Un DocNumber puede coincidir numéricamente con el id de OTRO pedido.

    `trazar` no puede elegir uno en silencio: tiene que devolver los dos y
    marcar `ambiguo`.
    """
    from maquila import reportes
    from app import Pedido
    with app.app_context():
        p1 = Pedido(cliente_id=IDS['cliente'], estado='pendiente')
        _db.session.add(p1)
        _db.session.commit()
        p2 = Pedido(cliente_id=IDS['cliente'], estado='facturado',
                    doc_number_qbo=str(p1.id))
        _db.session.add(p2)
        _db.session.commit()

        r = reportes.trazar(str(p1.id))
        assert r['encontrado'] is True
        assert r['ambiguo'] is True
        ids_encontrados = {fila['pedido_id'] for fila in r['hacia_adelante']}
        assert ids_encontrados == {p1.id, p2.id}


def test_trazar_lote_compartido_por_dos_clientes_es_ambiguo(app):
    """El lote solo es único por (cliente_id, lote), no globalmente."""
    from maquila import servicios, reportes
    from app import Cliente
    with app.app_context():
        cli2 = Cliente(nombre='Otra Maquila')
        _db.session.add(cli2)
        _db.session.commit()

        c1 = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'],
            lote='COMPARTIDO', fecha_produccion=date(2026, 9, 3),
            vendedor_id=IDS['vendedor'])
        c2 = servicios.abrir_corrida(
            cliente_id=cli2.id, producto_id=IDS['producto'],
            lote='COMPARTIDO', fecha_produccion=date(2026, 9, 3),
            vendedor_id=IDS['vendedor'])

        r = reportes.trazar('COMPARTIDO')
        assert r['encontrado'] is True
        assert r['ambiguo'] is True
        assert {c.id for c in r['corridas']} == {c1.id, c2.id}


def test_trazar_por_recepcion_agrega_el_mismo_pedido_de_dos_corridas(app):
    """Una recepción que alimentó dos corridas y las dos salieron por el
    mismo pedido: tiene que aparecer UNA vez, con el total real."""
    from maquila import servicios, reportes
    from app import Pedido, DetallePedido
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'], documento_cliente='GUIA-88',
            lineas=[{'ingrediente_id': IDS['ingrediente'],
                     'peso_total': Decimal('300')}])

        corrida1 = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'],
            lote='LOTE-A', fecha_produccion=date(2026, 9, 3),
            vendedor_id=IDS['vendedor'])
        servicios.agregar_caja_producida(corrida1, Decimal('40'))
        _db.session.commit()
        servicios.cerrar_corrida(corrida1, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])

        corrida2 = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'],
            lote='LOTE-B', fecha_produccion=date(2026, 9, 3),
            vendedor_id=IDS['vendedor'])
        servicios.agregar_caja_producida(corrida2, Decimal('30'))
        _db.session.commit()
        servicios.cerrar_corrida(corrida2, {IDS['ingrediente']: Decimal('40')},
                                 IDS['vendedor'])

        pedido = Pedido(cliente_id=IDS['cliente'], estado='facturado',
                        doc_number_qbo='9999')
        _db.session.add(pedido)
        _db.session.flush()
        detalle = DetallePedido(pedido_id=pedido.id, producto_id=IDS['producto'],
                                cajas=2, cajas_pedidas=2, peso=0,
                                precio_unitario=0, subtotal=0,
                                es_linea_pedido=True)
        _db.session.add(detalle)
        _db.session.commit()
        servicios.asignar_cajas(detalle, [corrida1.cajas[0], corrida2.cajas[0]],
                                IDS['vendedor'])

        r = reportes.trazar(rec.codigo)
        assert r['encontrado'] is True
        assert r['ambiguo'] is False
        assert len(r['hacia_adelante']) == 1
        entrada = r['hacia_adelante'][0]
        assert entrada['pedido_id'] == pedido.id
        assert entrada['cajas'] == 2
        assert entrada['peso'] == Decimal('70')
