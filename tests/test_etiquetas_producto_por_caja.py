"""Los productos vendidos POR CAJA también llevan lote y fechas en su etiqueta.

El pedido 1305 salió con las etiquetas del producto pesable y sin las de los
dos productos por caja. La cadena era: el modal de edición ocultaba «Lote» y
«Fecha de fabricación» para los no pesables, así que quedaban en NULL; y
`_build_label_items_for_pedido` filtra por `fecha_fabricacion`, de modo que
esas líneas se descartaban — en silencio, porque el pesable sí generó las
suyas y la ruta solo avisa cuando NO hay ninguna etiqueta.
"""
import os
import re
from datetime import date
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
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([rol, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=rol.id, territorio_id=terr.id, activo=True)
        v.set_password('testpass')
        _db.session.add_all([
            v,
            Cliente(nombre='DeliNova', moneda='XCG', territorio_id=terr.id),
            # Por caja, 36 unidades — como «Cooked Shoulder 500 gr» del 1305.
            Producto(nombre='Cooked Shoulder 500 gr', se_pesa=False,
                     tax_rate=10.0, unidades_por_caja=36, temperatura='Refrigerado'),
        ])
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'testpass'},
           follow_redirects=True)
    return c


def _pedido_por_caja(cajas='0.25', con_trazabilidad=False):
    """Pedido con un producto por caja: línea original + línea de preparación."""
    from app import Pedido, DetallePedido

    p = Pedido(cliente_id=1, estado='preparado', tipo_cambio=1.0,
               fecha_entrega=date(2026, 8, 29))
    _db.session.add(p)
    _db.session.flush()
    for es_original in (True, False):
        d = DetallePedido(
            pedido_id=p.id, producto_id=1, cajas=Decimal(cajas),
            cajas_pedidas=Decimal(cajas), peso=0,
            precio_unitario=Decimal('10.00'), subtotal=Decimal('2.50'),
            es_linea_pedido=es_original,
        )
        if con_trazabilidad and not es_original:
            d.lote = 'L-2808202601'
            d.fecha_fabricacion = date(2026, 8, 28)
            d.fecha_expiracion = date(2027, 8, 28)
        _db.session.add(d)
    _db.session.commit()
    return p.id


# --------------------------------------------------- la etiqueta se genera


def test_un_producto_por_caja_con_trazabilidad_genera_su_etiqueta(app):
    from app import Pedido, _build_label_items_for_pedido

    with app.app_context():
        pedido_id = _pedido_por_caja(con_trazabilidad=True)
        pedido = _db.session.get(Pedido, pedido_id)

        items = _build_label_items_for_pedido(pedido, '2026-08-01', '2026-08-31')

        assert len(items) == 1, f'Esperaba 1 etiqueta, recibí {len(items)}'
        assert items[0]['lote'] == 'L-2808202601'
        # 0,25 caja x 36 unidades = 9
        assert items[0]['medida_rotulo'] == 'Units:'
        assert items[0]['medida_valor'] == '9'


# -------------------------------------- el formulario deja cargar los datos


def _editar(client, detalle_id, **campos):
    datos = {'producto_id': '1', 'peso': '0.25'}
    datos.update(campos)
    return client.post(f'/detalles_pedido/{detalle_id}/editar', data=datos,
                       follow_redirects=True)


def test_el_form_muestra_lote_y_fabricacion_para_los_productos_por_caja(app, logged_client):
    """El modal los ocultaba con `display:none` para los no pesables, así que
    no había forma de cargarlos."""
    with app.app_context():
        pedido_id = _pedido_por_caja()

    cuerpo = logged_client.get(f'/pedidos/{pedido_id}/detalles').get_data(as_text=True)

    # El bloque que decide qué se muestra ya no puede esconderlos.
    bloque = cuerpo[cuerpo.find('function openEditModal'):]
    bloque = bloque[:bloque.find('editModalOverlay.classList.add')]
    assert "editLoteGroup.style.display = 'none'" not in bloque, (
        'El modal sigue ocultando el Lote para los productos por caja'
    )
    assert "editFabGroup.style.display = 'none'" not in bloque, (
        'El modal sigue ocultando la Fecha de fabricación para los productos por caja'
    )


def test_el_servidor_rechaza_una_linea_por_caja_sin_trazabilidad(app, logged_client):
    """El `required` del navegador se puede saltear; la guarda tiene que estar
    también en el servidor."""
    from app import DetallePedido

    with app.app_context():
        # Arranca CON trazabilidad: así, si el guardado se acepta, los datos
        # se pierden — y eso es lo que el test tiene que detectar. Con la
        # línea vacía de entrada la aserción se cumpliría sola.
        _pedido_por_caja(con_trazabilidad=True)
        prep_id = DetallePedido.query.filter_by(es_linea_pedido=False).first().id

    _editar(logged_client, prep_id, lote='', fecha_fabricacion='', fecha_expiracion='')

    with app.app_context():
        prep = _db.session.get(DetallePedido, prep_id)
        assert prep.lote == 'L-2808202601', (
            'El servidor aceptó borrar la trazabilidad de una línea por caja'
        )
        assert str(prep.fecha_fabricacion) == '2026-08-28'


def test_el_servidor_guarda_la_trazabilidad_de_una_linea_por_caja(app, logged_client):
    from app import DetallePedido

    with app.app_context():
        _pedido_por_caja()
        prep_id = DetallePedido.query.filter_by(es_linea_pedido=False).first().id

    _editar(logged_client, prep_id, lote='L-99',
            fecha_fabricacion='2026-08-28', fecha_expiracion='2027-08-28')

    with app.app_context():
        prep = _db.session.get(DetallePedido, prep_id)
        assert prep.lote == 'L-99'
        assert str(prep.fecha_fabricacion) == '2026-08-28'
        assert str(prep.fecha_expiracion) == '2027-08-28'


# ------------------------------------------ la omisión deja de ser silenciosa


def test_avisa_cuando_deja_lineas_sin_etiqueta(app, logged_client):
    """Con una línea sin fecha de fabricación y otra con ella, el PDF sale con
    una sola etiqueta. Antes no se decía nada y parecía que estaban todas."""
    from app import Pedido, DetallePedido, Producto

    with app.app_context():
        pedido_id = _pedido_por_caja(con_trazabilidad=True)
        # Segundo producto por caja, SIN trazabilidad: el caso del 1305.
        otro = Producto(nombre='Cooked Chicken Ham 500 gr', se_pesa=False,
                        tax_rate=10.0, unidades_por_caja=36, temperatura='Refrigerado')
        _db.session.add(otro)
        _db.session.flush()
        for es_original in (True, False):
            _db.session.add(DetallePedido(
                pedido_id=pedido_id, producto_id=otro.id, cajas=Decimal('0.25'),
                cajas_pedidas=Decimal('0.25'), peso=0,
                precio_unitario=Decimal('10.00'), subtotal=Decimal('2.50'),
                es_linea_pedido=es_original))
        _db.session.commit()

    logged_client.get(
        f'/generar_etiqueta_detalle/{pedido_id}'
        '?fecha_inicio=2026-08-01&fecha_fin=2026-08-31'
    )
    cuerpo = logged_client.get(f'/pedidos/{pedido_id}/detalles').get_data(as_text=True)

    assert 'Cooked Chicken Ham 500 gr' in cuerpo
    assert 'sin fecha de fabricación' in cuerpo, (
        'Falta el aviso de las líneas que quedaron sin etiqueta'
    )
