# tests/test_pedido_form_envio_fetch.py
"""Task 4 del form de alta de pedidos (2026-08-30): el envío pasa de un POST
clásico a `fetch`, para que un corte de señal en la calle (la pantalla vive
en la calle, ver `pedido_cliente.html`) no muestre la página de error del
navegador y se pierda el pedido.

Estos tests cubren el lado SERVIDOR del cambio:
  - la ruta sigue respondiendo igual (flash + redirect) a un POST clásico —
    hay tests viejos (`test_pedido_form_fixes.py`, `test_cajas_fraccionarias.py`,
    etc.) que ejercen exactamente ese camino y no pueden romperse;
  - con el header `X-Requested-With: XMLHttpRequest` (el mismo que ya usa el
    resto de la app para AJAX) responde JSON en vez de redirigir, en
    `nuevo_pedido` Y `editar_pedido` — las dos comparten el mismo
    `pedido_form.html`/JS;
  - el flash de éxito deja de mentir sobre "precios registrados" cuando
    alguna línea no tiene precio de lista.

El lado cliente (JS: fetch, banner de error, confirmación, borrador) está en
`test_pedido_form_no_perder_pedido.py` y en la verificación de navegador del
informe de esta tarea.
"""
import os
import pytest
from decimal import Decimal

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
        from app import (Rol, Territorio, Vendedor, Cliente, Producto,
                         ListaPrecio, PrecioProducto)

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username='admin', email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)

        cliente = Cliente(nombre='Van den Tweel', territorio_id=territorio.id)
        _db.session.add(cliente)

        # Un producto CON precio de lista y otro SIN ninguno: la mezcla es lo
        # que ejercita `sin_precio` por línea, no un pedido todo-o-nada.
        con_precio = Producto(
            nombre='Chuleta de cerdo ahumada 5 kg', descripcion='x',
            temperatura='Congelado', se_pesa=True, tax_rate=10.0,
        )
        sin_precio = Producto(
            nombre='Producto huérfano de precio', descripcion='x',
            temperatura='Congelado', se_pesa=True, tax_rate=10.0,
        )
        _db.session.add_all([con_precio, sin_precio])
        _db.session.flush()

        lista = ListaPrecio(nombre='Default', es_default=True, activa=True)
        _db.session.add(lista)
        _db.session.flush()
        _db.session.add(PrecioProducto(
            lista_precio_id=lista.id, producto_id=con_precio.id,
            precio_base=25.50, activo=True,
        ))
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin', 'password': 'testpass',
    }, follow_redirects=True)
    return client


def _ids():
    from app import Cliente, Producto
    cliente = Cliente.query.filter_by(nombre='Van den Tweel').first()
    con_precio = Producto.query.filter_by(nombre='Chuleta de cerdo ahumada 5 kg').first()
    sin_precio = Producto.query.filter_by(nombre='Producto huérfano de precio').first()
    return cliente.id, con_precio.id, sin_precio.id


# ── El POST clásico no se rompe ──────────────────────────────────────────

def test_post_clasico_sigue_redirigiendo_con_flash(app, logged_client):
    """Sin el header de fetch, la ruta se comporta EXACTAMENTE como antes:
    hay tests viejos (`test_pedido_form_fixes.py` y otros) que dependen de
    este camino con `client.post(...)` a secas."""
    cliente_id, con_precio_id, _ = _ids()
    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '2',
        'productos[0][precio]': '25.50',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert resp.headers.get('Content-Type', '').startswith('text/html')
    html = resp.get_data(as_text=True)
    assert 'Pedido creado con precios registrados.' in html


def test_post_clasico_con_error_sigue_redirigiendo_al_form(app, logged_client):
    cliente_id, _, _ = _ids()
    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Agrega al menos un producto al pedido' in html


# ── fetch pide JSON ───────────────────────────────────────────────────────

def _post_fetch(client, url, data):
    return client.post(url, data=data,
                       headers={'X-Requested-With': 'XMLHttpRequest'})


def test_fetch_exitoso_devuelve_confirmacion_json(app, logged_client):
    cliente_id, con_precio_id, _ = _ids()
    resp = _post_fetch(logged_client, '/pedidos/nuevo', {
        'cliente_id': cliente_id, 'notas': 'Entregar en la puerta',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '2',
        'productos[0][precio]': '25.50',
    })
    assert resp.status_code == 200
    assert resp.headers.get('Content-Type', '').startswith('application/json')
    datos = resp.get_json()
    assert datos['ok'] is True
    assert isinstance(datos['pedido_id'], int)
    assert datos['cliente_nombre'] == 'Van den Tweel'
    assert datos['notas'] == 'Entregar en la puerta'
    assert datos['sin_precio'] is False
    assert len(datos['lineas']) == 1
    linea = datos['lineas'][0]
    assert linea['producto_id'] == con_precio_id
    assert linea['sin_precio'] is False
    assert linea['precio'] == pytest.approx(25.50)
    assert linea['cajas'] == pytest.approx(2)
    assert linea['subtotal'] == pytest.approx(51.00)
    assert datos['subtotal'] == pytest.approx(51.00)

    from app import Pedido
    assert Pedido.query.get(datos['pedido_id']) is not None


def test_fetch_no_deja_flash_colgado_en_la_sesion(app, logged_client):
    """El JSON no navega a ninguna otra pantalla: si igual encolara un
    flash, aparecería sin venir a cuento en la SIGUIENTE página que el
    vendedor mirara (p.ej. "Volver a la lista")."""
    cliente_id, con_precio_id, _ = _ids()
    _post_fetch(logged_client, '/pedidos/nuevo', {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '1',
        'productos[0][precio]': '25.50',
    })
    siguiente = logged_client.get('/pedidos')
    html = siguiente.get_data(as_text=True)
    assert 'Pedido creado con precios registrados.' not in html


def test_fetch_marca_sin_precio_por_linea_y_en_general(app, logged_client):
    cliente_id, con_precio_id, sin_precio_id = _ids()
    resp = _post_fetch(logged_client, '/pedidos/nuevo', {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '1',
        'productos[0][precio]': '25.50',
        'productos[1][id]': sin_precio_id,
        'productos[1][cajas]': '3',
        'productos[1][precio]': '',
    })
    assert resp.status_code == 200
    datos = resp.get_json()
    assert datos['ok'] is True
    assert datos['sin_precio'] is True
    por_id = {l['producto_id']: l for l in datos['lineas']}
    assert por_id[con_precio_id]['sin_precio'] is False
    assert por_id[sin_precio_id]['sin_precio'] is True
    # Sin precio en ninguna lista: el servidor resuelve a 0, no a lo que
    # trajera el form (mismo argumento que `_resolver_precio_unitario_pedido`).
    assert por_id[sin_precio_id]['precio'] == pytest.approx(0)


def test_flash_clasico_es_condicional_segun_sin_precio(app, logged_client):
    """`app.py` decía SIEMPRE "con precios registrados", también sobre un
    pedido con líneas sin precio de lista — acá es donde eso se mentía."""
    cliente_id, _, sin_precio_id = _ids()
    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': sin_precio_id,
        'productos[0][cajas]': '1',
        'productos[0][precio]': '',
    }, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'Pedido creado con precios registrados.' not in html
    assert 'sin precio de lista' in html


def test_fetch_error_devuelve_json_con_status_no_redirect(app, logged_client):
    cliente_id, _, _ = _ids()
    resp = _post_fetch(logged_client, '/pedidos/nuevo', {
        'cliente_id': cliente_id, 'notas': '',
    })
    assert resp.status_code == 400
    datos = resp.get_json()
    assert datos['ok'] is False
    assert 'Agrega al menos un producto' in datos['error']


def test_fetch_cliente_invalido_devuelve_json_400(app, logged_client):
    resp = _post_fetch(logged_client, '/pedidos/nuevo', {
        'cliente_id': '999999', 'notas': '',
        'productos[0][id]': '1',
        'productos[0][cajas]': '1',
    })
    assert resp.status_code == 400
    datos = resp.get_json()
    assert datos['ok'] is False


# ── editar_pedido comparte el mismo template/JS: mismo gate ────────────────

def _crear_pedido(logged_client, cliente_id, producto_id):
    resp = _post_fetch(logged_client, '/pedidos/nuevo', {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': producto_id,
        'productos[0][cajas]': '2',
        'productos[0][precio]': '25.50',
    })
    return resp.get_json()['pedido_id']


def test_editar_por_fetch_tambien_devuelve_json(app, logged_client):
    cliente_id, con_precio_id, _ = _ids()
    pedido_id = _crear_pedido(logged_client, cliente_id, con_precio_id)

    resp = _post_fetch(logged_client, f'/pedidos/{pedido_id}/editar', {
        'cliente_id': cliente_id, 'notas': 'nota editada',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '4',
        'productos[0][precio]': '25.50',
    })
    assert resp.status_code == 200
    datos = resp.get_json()
    assert datos['ok'] is True
    assert datos['pedido_id'] == pedido_id
    assert datos['notas'] == 'nota editada'
    assert datos['lineas'][0]['cajas'] == pytest.approx(4)


def test_editar_pedido_facturado_por_fetch_devuelve_409(app, logged_client):
    cliente_id, con_precio_id, _ = _ids()
    pedido_id = _crear_pedido(logged_client, cliente_id, con_precio_id)
    from app import Pedido
    with app.app_context():
        pedido = Pedido.query.get(pedido_id)
        pedido.estado = 'facturado'
        _db.session.commit()

    resp = _post_fetch(logged_client, f'/pedidos/{pedido_id}/editar', {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '4',
        'productos[0][precio]': '25.50',
    })
    assert resp.status_code == 409
    datos = resp.get_json()
    assert datos['ok'] is False


def test_editar_por_post_clasico_sigue_igual(app, logged_client):
    cliente_id, con_precio_id, _ = _ids()
    pedido_id = _crear_pedido(logged_client, cliente_id, con_precio_id)

    resp = logged_client.post(f'/pedidos/{pedido_id}/editar', data={
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '5',
        'productos[0][precio]': '25.50',
    }, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Pedido actualizado.' in html


# ── Ronda de corrección 1: idempotencia con intento_id ─────────────────────
#
# El reintento que agregó esta tarea (fetch + botón "Reintentar") puede
# tocar un pedido que el servidor YA comiteó — el H12 de Heroku relanzando
# la request a los 30s mientras el dyno original sigue vivo, un 502/504 de
# Cloudflare sobre una request que el origen completó, o la señal
# cortándose literalmente entre el POST y la respuesta (el escenario del
# brief). Sin idempotencia, "Reintentar" crea un SEGUNDO pedido con sus
# líneas de preparación y una segunda factura en QuickBooks. `intento_id`
# (columna única en `Pedido`, generada en el navegador una sola vez por
# pedido-en-curso) cierra eso: un segundo POST con el MISMO intento_id no
# crea nada, devuelve la confirmación del que ya existe.

def test_reintento_con_mismo_intento_id_no_crea_segundo_pedido(app, logged_client):
    cliente_id, con_precio_id, _ = _ids()
    payload = {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '2',
        'productos[0][precio]': '25.50',
        'intento_id': 'intento-idempotente-1',
    }
    resp1 = _post_fetch(logged_client, '/pedidos/nuevo', payload)
    assert resp1.status_code == 200
    datos1 = resp1.get_json()
    assert datos1['ok'] is True

    resp2 = _post_fetch(logged_client, '/pedidos/nuevo', payload)
    assert resp2.status_code == 200
    datos2 = resp2.get_json()
    assert datos2['ok'] is True

    # Misma confirmación — mismo pedido, no uno nuevo.
    assert datos2['pedido_id'] == datos1['pedido_id']

    from app import Pedido
    with app.app_context():
        pedidos_con_ese_intento = Pedido.query.filter_by(
            intento_id='intento-idempotente-1').all()
        assert len(pedidos_con_ese_intento) == 1
        total_pedidos_cliente = Pedido.query.filter_by(
            cliente_id=cliente_id).count()
        assert total_pedidos_cliente == 1, (
            'el reintento con el mismo intento_id creó un segundo pedido'
        )


def test_reintento_post_clasico_con_mismo_intento_id_tampoco_crea_segundo(app, logged_client):
    """El mismo mecanismo, sin el header de fetch — por si algún camino
    manda el hidden sin pasar por AJAX (no debería, pero el índice único no
    depende de eso para proteger)."""
    cliente_id, con_precio_id, _ = _ids()
    payload = {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '2',
        'productos[0][precio]': '25.50',
        'intento_id': 'intento-idempotente-clasico',
    }
    logged_client.post('/pedidos/nuevo', data=payload, follow_redirects=True)
    logged_client.post('/pedidos/nuevo', data=payload, follow_redirects=True)

    from app import Pedido
    with app.app_context():
        assert Pedido.query.filter_by(
            intento_id='intento-idempotente-clasico').count() == 1


def test_intento_id_distinto_crea_pedido_distinto(app, logged_client):
    cliente_id, con_precio_id, _ = _ids()

    def _payload(intento):
        return {
            'cliente_id': cliente_id, 'notas': '',
            'productos[0][id]': con_precio_id,
            'productos[0][cajas]': '1',
            'productos[0][precio]': '25.50',
            'intento_id': intento,
        }

    r1 = _post_fetch(logged_client, '/pedidos/nuevo', _payload('intento-a'))
    r2 = _post_fetch(logged_client, '/pedidos/nuevo', _payload('intento-b'))
    assert r1.get_json()['pedido_id'] != r2.get_json()['pedido_id'], (
        'dos intento_id distintos tienen que crear dos pedidos distintos '
        '— dos pedidos-en-curso genuinos no pueden fusionarse en uno'
    )


def test_sin_intento_id_se_comporta_como_siempre(app, logged_client):
    """Sin el hidden (un cliente viejo, o el form sin JS) cada POST crea su
    propio pedido — nunca se activa la idempotencia sobre la nada."""
    cliente_id, con_precio_id, _ = _ids()
    payload = {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '1',
        'productos[0][precio]': '25.50',
    }
    r1 = _post_fetch(logged_client, '/pedidos/nuevo', payload)
    r2 = _post_fetch(logged_client, '/pedidos/nuevo', payload)
    assert r1.get_json()['pedido_id'] != r2.get_json()['pedido_id']


def test_editar_reintento_con_mismo_intento_id_no_reaplica(app, logged_client):
    """Un reintento de la MISMA edición (mismo intento_id) no se vuelve a
    aplicar — si lo hiciera dos veces con datos DISTINTOS (el escenario más
    revelador: el segundo toque llega con basura, o con un valor que el
    vendedor ya cambió de vuelta), la segunda aplicación pisaría la
    primera."""
    cliente_id, con_precio_id, _ = _ids()
    pedido_id = _crear_pedido(logged_client, cliente_id, con_precio_id)

    payload_1 = {
        'cliente_id': cliente_id, 'notas': 'primera edición',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '4',
        'productos[0][precio]': '25.50',
        'intento_id': 'intento-edicion-1',
    }
    resp1 = _post_fetch(logged_client, f'/pedidos/{pedido_id}/editar', payload_1)
    assert resp1.get_json()['lineas'][0]['cajas'] == pytest.approx(4)

    # "Reintento" con el MISMO intento_id pero cajas/notas DISTINTAS —si el
    # servidor lo reaplicara, ganaría 999 y "reintento espurio".
    payload_2 = dict(payload_1)
    payload_2['productos[0][cajas]'] = '999'
    payload_2['notas'] = 'reintento espurio'
    resp2 = _post_fetch(logged_client, f'/pedidos/{pedido_id}/editar', payload_2)
    datos2 = resp2.get_json()
    assert datos2['ok'] is True
    assert datos2['lineas'][0]['cajas'] == pytest.approx(4), (
        'el reintento con el mismo intento_id volvió a aplicar la edición '
        '— con datos distintos, la segunda aplicación pisó la primera'
    )
    assert datos2['notas'] == 'primera edición'

    from app import DetallePedido
    with app.app_context():
        detalle = DetallePedido.query.filter_by(
            pedido_id=pedido_id, es_linea_pedido=True).first()
        assert float(detalle.cajas) == pytest.approx(4), (
            'la DB terminó con las cajas del reintento espurio, no las de '
            'la edición original'
        )


def test_intento_id_distinto_si_permite_una_segunda_edicion_real(app, logged_client):
    """Dos ediciones GENUINAS (intento_id distinto cada vez, como dos
    cargas de página distintas) tienen que aplicarse las dos — la
    idempotencia es sobre el MISMO intento, no un candado que trabe seguir
    editando."""
    cliente_id, con_precio_id, _ = _ids()
    pedido_id = _crear_pedido(logged_client, cliente_id, con_precio_id)

    _post_fetch(logged_client, f'/pedidos/{pedido_id}/editar', {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '4',
        'productos[0][precio]': '25.50',
        'intento_id': 'intento-edicion-a',
    })
    resp2 = _post_fetch(logged_client, f'/pedidos/{pedido_id}/editar', {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '6',
        'productos[0][precio]': '25.50',
        'intento_id': 'intento-edicion-b',
    })
    assert resp2.get_json()['lineas'][0]['cajas'] == pytest.approx(6), (
        'una edición genuina con OTRO intento_id no se aplicó — la '
        'idempotencia está trabando ediciones reales, no solo reintentos'
    )


def test_intento_id_largo_no_revienta_el_guardado(app, logged_client):
    """Un intento_id absurdamente largo (la columna es VARCHAR(36)) se
    trunca y sigue el flujo normal en vez de un 500 por overflow de
    columna."""
    cliente_id, con_precio_id, _ = _ids()
    resp = _post_fetch(logged_client, '/pedidos/nuevo', {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': con_precio_id,
        'productos[0][cajas]': '1',
        'productos[0][precio]': '25.50',
        'intento_id': 'x' * 500,
    })
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True
