"""Con el logo del cliente, la etiqueta no repite su nombre en «Client».

El logo ya dice de quién es la mercadería, así que la fila «Client» sobra y
gasta una de las cinco líneas del bloque. Solo se quita cuando el cliente tiene
logo propio: con el logo de Jomar (cliente sin logo) la fila se queda, o la
etiqueta no diría para quién es.

Decisión de JM, 2026-08-28. Las cuatro filas restantes SUBEN: el bloque
arranca donde arrancaba y termina una fila más arriba.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')


def _dibujar(**extra):
    """Dibuja una etiqueta sobre un canvas falso y devuelve (rótulo -> y)."""
    from utils import label_utils

    canvas = MagicMock()
    label_utils.draw_order_label(
        canvas, None, client='DeliNova', product='Cooked Chicken Wings',
        temperature='-18 °C', lot='L-1', mfg_date='2026-08-27',
        exp_date='2027-08-27', medida_rotulo='Net Weight:',
        medida_valor='12.55 kg', **extra,
    )
    return {
        llamada.args[2]: llamada.args[1]
        for llamada in canvas.drawRightString.call_args_list
    }


def _dibujar_a4(**extra):
    from utils import label_utils

    canvas = MagicMock()
    label_utils.draw_order_label_a4(
        canvas, None, 'DeliNova', 'Cooked Chicken Wings', '-18 °C', 'L-1',
        '2026-08-27', '2027-08-27', 'Net Weight:', '12.55 kg', 0, 0, **extra,
    )
    return {
        llamada.args[2]: llamada.args[1]
        for llamada in canvas.drawRightString.call_args_list
    }


# ------------------------------------------------------- 4x2 (una por página)


def test_sin_fila_cliente_no_se_dibuja_el_rotulo():
    filas = _dibujar(mostrar_cliente=False)

    assert 'Client:' not in filas
    assert 'Lot:' in filas


def test_sin_fila_cliente_las_demas_suben_una_posicion():
    """El bloque arranca donde arrancaba: «Lot» ocupa el lugar de «Client»."""
    from utils.label_utils import Y_CLIENT, Y_LOT, Y_MFG, Y_EXP

    filas = _dibujar(mostrar_cliente=False)

    assert filas['Lot:'] == pytest.approx(Y_CLIENT)
    assert filas['Manufactured:'] == pytest.approx(Y_LOT)
    assert filas['Expiration:'] == pytest.approx(Y_MFG)
    assert filas['When Kept at:'] == pytest.approx(Y_EXP)


def test_por_defecto_la_etiqueta_no_cambia():
    """Regresión: sin el parámetro, todo queda exactamente como estaba."""
    from utils.label_utils import Y_CLIENT, Y_LOT, Y_MFG, Y_EXP, Y_KEEP

    filas = _dibujar()

    assert filas['Client:'] == pytest.approx(Y_CLIENT)
    assert filas['Lot:'] == pytest.approx(Y_LOT)
    assert filas['Manufactured:'] == pytest.approx(Y_MFG)
    assert filas['Expiration:'] == pytest.approx(Y_EXP)
    assert filas['When Kept at:'] == pytest.approx(Y_KEEP)


def test_el_valor_del_cliente_tampoco_se_dibuja():
    """No alcanza con sacar el rótulo: el nombre iba en la columna de valores."""
    from utils import label_utils

    canvas = MagicMock()
    label_utils.draw_order_label(
        canvas, None, client='DeliNova', product='X', temperature='-18 °C',
        lot='L-1', mfg_date='2026-08-27', exp_date='2027-08-27',
        medida_rotulo='Net Weight:', medida_valor='1 kg',
        mostrar_cliente=False,
    )
    valores = [c.args[2] for c in canvas.drawString.call_args_list]
    assert 'DeliNova' not in valores


# ----------------------------------------------------------------- A4 (2 por hoja)


def test_a4_tambien_respeta_el_parametro():
    filas = _dibujar_a4(mostrar_cliente=False)

    assert 'Client:' not in filas
    assert 'Lot:' in filas


def test_a4_por_defecto_no_cambia():
    filas = _dibujar_a4()

    assert 'Client:' in filas


# ------------------------------------------- lo que deciden las rutas


@pytest.fixture
def app():
    from app import app as flask_app, db as _db
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


def _pedido_con_logo(app, con_logo):
    from datetime import date
    from decimal import Decimal
    from app import (db as _db, Rol, Territorio, Vendedor, Cliente, Producto,
                     Pedido, DetallePedido)

    rol = Rol(nombre='super_admin', descripcion='A')
    terr = Territorio(nombre='t', descripcion='T')
    _db.session.add_all([rol, terr]); _db.session.flush()
    v = Vendedor(username='admin', email='a@t.com', nombre_completo='A',
                 rol_id=rol.id, territorio_id=terr.id, activo=True)
    v.set_password('testpass')
    logo = None
    if con_logo:
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new('RGBA', (8, 8), (0, 0, 0, 255)).save(buf, format='PNG')
        logo = buf.getvalue()
    cli = Cliente(nombre='DeliNova', moneda='XCG', territorio_id=terr.id,
                  logo_etiqueta=logo, logo_mimetype='image/png' if logo else None)
    prod = Producto(nombre='Wings', se_pesa=False, tax_rate=10.0,
                    unidades_por_caja=36, temperatura='-18 °C')
    _db.session.add_all([v, cli, prod]); _db.session.flush()
    p = Pedido(cliente_id=cli.id, estado='preparado', tipo_cambio=1.0,
               fecha_entrega=date(2026, 8, 29))
    _db.session.add(p); _db.session.flush()
    for original in (True, False):
        d = DetallePedido(pedido_id=p.id, producto_id=prod.id,
                          cajas=Decimal('1'), cajas_pedidas=Decimal('1'), peso=0,
                          precio_unitario=Decimal('10'), subtotal=Decimal('10'),
                          es_linea_pedido=original)
        if not original:
            d.lote = 'L-1'
            d.fecha_fabricacion = date(2026, 8, 27)
            d.fecha_expiracion = date(2027, 8, 27)
        _db.session.add(d)
    _db.session.commit()
    return p.id


@pytest.mark.parametrize('con_logo,esperado', [(True, False), (False, True)])
def test_la_ruta_decide_segun_el_logo_del_cliente(app, con_logo, esperado):
    """Con logo propio la fila se quita; con el logo de Jomar se conserva."""
    import app as app_mod

    with app.app_context():
        pedido_id = _pedido_con_logo(app, con_logo)

    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)

    with patch.object(app_mod, 'draw_order_label') as dibujo:
        client.get(f'/generar_etiqueta_detalle/{pedido_id}'
                   '?fecha_inicio=2026-08-01&fecha_fin=2026-08-31')

    assert dibujo.called, 'no se dibujó ninguna etiqueta'
    assert dibujo.call_args.kwargs.get('mostrar_cliente') is esperado
