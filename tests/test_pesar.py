# tests/test_pesar.py
import os
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
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto, Pedido, DetallePedido

        rol = Rol(nombre='super_admin', descripcion='Admin')
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add_all([rol, territorio])
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

        cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id, qbo_id='QBO-C001')
        _db.session.add(cliente)
        _db.session.flush()

        prod_pesa = Producto(
            nombre='Chuleta de Cerdo',
            descripcion='Carne',
            temperatura='-18°C',
            se_pesa=True,
            tax_rate=6.0,
            qbo_id='QBO-P001',
        )
        prod_import = Producto(
            nombre='Atún Van Camps',
            descripcion='Conserva',
            temperatura='Ambiente',
            se_pesa=False,
            tax_rate=6.0,
            qbo_id='QBO-P002',
        )
        _db.session.add_all([prod_pesa, prod_import])
        _db.session.flush()

        pedido = Pedido(cliente_id=cliente.id, estado='pendiente')
        _db.session.add(pedido)
        _db.session.flush()

        _db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_pesa.id,
            cajas=3,
            cajas_pedidas=3,
            peso=0,
            precio_unitario=Decimal('25.00'),
            subtotal=Decimal('75.00'),
            es_linea_pedido=True,
        ))
        _db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_import.id,
            cajas=5,
            cajas_pedidas=5,
            peso=0,
            precio_unitario=Decimal('10.00'),
            subtotal=Decimal('50.00'),
            es_linea_pedido=True,
        ))
        _db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_import.id,
            cajas=5,
            cajas_pedidas=0,
            peso=0,
            precio_unitario=Decimal('10.00'),
            subtotal=Decimal('50.00'),
            es_linea_pedido=False,
            fecha_expiracion='2027-06-01',
        ))

        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'}, follow_redirects=True)
    return client


def test_pesar_screen_loads(logged_client, app):
    with app.app_context():
        from app import Pedido

        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/pesar')
        html = resp.data.decode('utf-8')

        assert resp.status_code == 200
        assert 'Pesar PED-' in html
        assert 'Chuleta de Cerdo' in html
        assert 'cajas-list-producto-' in html


def test_registrar_caja_pesada(logged_client, app):
    with app.app_context():
        from app import Pedido, DetallePedido, CajaPesada

        pedido = Pedido.query.first()
        detalle = DetallePedido.query.filter_by(pedido_id=pedido.id, es_linea_pedido=True).join(DetallePedido.producto).filter_by(se_pesa=True).first()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/pesar/caja',
            data={
                'detalle_pedido_id': detalle.id,
                'peso': '12.450',
                'lote': 'L-2643',
                'fecha_elaboracion': '2026-04-18',
                'fecha_vencimiento': '2027-04-18',
            },
            headers={'HX-Request': 'true'},
        )

        assert resp.status_code == 200
        caja = CajaPesada.query.filter_by(detalle_pedido_id=detalle.id).one()
        assert caja.numero == 1
        assert caja.lote == 'L-2643'
        assert float(caja.peso) == pytest.approx(12.45)


def test_finalizar_pesaje_marca_pedido_preparado(logged_client, app):
    with app.app_context():
        from app import Pedido, DetallePedido, CajaPesada

        pedido = Pedido.query.first()
        detalle = DetallePedido.query.filter_by(pedido_id=pedido.id, es_linea_pedido=True).join(DetallePedido.producto).filter_by(se_pesa=True).first()

        for idx, peso in enumerate([11.1, 12.2, 13.3], start=1):
            _db.session.add(CajaPesada(
                detalle_pedido_id=detalle.id,
                numero=idx,
                peso=Decimal(str(peso)),
                lote='L-2643',
                fecha_elaboracion=date(2026, 4, 18),
                fecha_vencimiento=date(2027, 4, 18),
            ))
        _db.session.commit()

        resp = logged_client.post(f'/pedidos/{pedido.id}/pesar/finalizar', follow_redirects=True)
        assert resp.status_code == 200

        pedido = Pedido.query.first()
        assert pedido.estado == 'preparado'


def test_registrar_caja_confirma_producto_y_peso(logged_client, app):
    """Pedido 1357: la caja registrada se confirma nombrando el producto, para
    que un chip equivocado se note al momento y no en la etiqueta."""
    with app.app_context():
        from app import Pedido, DetallePedido

        pedido = Pedido.query.first()
        detalle = DetallePedido.query.filter_by(pedido_id=pedido.id, es_linea_pedido=True).join(DetallePedido.producto).filter_by(se_pesa=True).first()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/pesar/caja',
            data={
                'detalle_pedido_id': detalle.id,
                'peso': '16.9',
                'lote': 'L-2309202601',
                'fecha_elaboracion': '2026-09-23',
                'fecha_vencimiento': '2027-09-23',
            },
            headers={'HX-Request': 'true'},
        )
        html = resp.data.decode('utf-8')

        assert resp.status_code == 200
        assert 'pesar-feedback is-ok' in html
        assert 'Caja #01 · 16.90 kg' in html
        assert '<strong>Chuleta de Cerdo</strong>' in html
        # El panel lleva el lote de su última caja para no arrastrar el de
        # otro producto al cambiar de chip.
        assert 'data-ultimo-lote="L-2309202601"' in html
        assert 'data-ultima-elab="2026-09-23"' in html
        # El chip que vuelve por OOB sigue marcado como activo.
        assert f'id="pesar-chip-{detalle.id}"' in html
        chip = html.split(f'id="pesar-chip-{detalle.id}"', 1)[1].split('>', 1)[0]
        assert 'is-active' in chip


def test_pantalla_pesar_panel_sin_cajas_no_trae_lote(logged_client, app):
    with app.app_context():
        from app import Pedido

        pedido = Pedido.query.first()
        html = logged_client.get(f'/pedidos/{pedido.id}/pesar').data.decode('utf-8')
        assert 'data-ultimo-lote=""' in html
        assert 'pesar-feedback is-ok' not in html


def _registrar_caja(logged_client, app, peso='16.9'):
    from app import Pedido, DetallePedido, CajaPesada

    pedido = Pedido.query.first()
    detalle = DetallePedido.query.filter_by(pedido_id=pedido.id, es_linea_pedido=True).join(DetallePedido.producto).filter_by(se_pesa=True).first()
    resp = logged_client.post(
        f'/pedidos/{pedido.id}/pesar/caja',
        data={
            'detalle_pedido_id': detalle.id,
            'peso': peso,
            'lote': 'L-2309202601',
            'fecha_elaboracion': '2026-09-23',
            'fecha_vencimiento': '2027-09-23',
        },
        headers={'HX-Request': 'true'},
    )
    assert resp.status_code == 200
    caja = CajaPesada.query.filter_by(detalle_pedido_id=detalle.id).order_by(CajaPesada.numero.desc()).first()
    return pedido, detalle, caja, resp.data.decode('utf-8')


def test_confirmacion_de_caja_trae_boton_imprimir_etiqueta(logged_client, app):
    """Pedido 1357: la etiqueta se imprime al pie de la báscula, caja por caja,
    en vez de las 31 juntas al final para pegarlas buscando la caja por peso."""
    with app.app_context():
        pedido, detalle, caja, html = _registrar_caja(logged_client, app)
        assert f'/cajas/{caja.id}/etiqueta' in html
        assert 'data-etiqueta-caja' in html
        assert 'Imprimir etiqueta' in html
        assert f'data-filename="etiqueta_{pedido.id}_01.pdf"' in html


def test_modal_de_caja_trae_boton_imprimir_etiqueta(logged_client, app):
    with app.app_context():
        pedido, detalle, caja, _ = _registrar_caja(logged_client, app)
        html = logged_client.get(f'/cajas/{caja.id}/edit').data.decode('utf-8')
        assert f'/cajas/{caja.id}/etiqueta' in html
        assert 'Imprimir etiqueta de esta caja' in html


def test_etiqueta_de_una_caja_devuelve_pdf_con_producto_y_peso(logged_client, app):
    with app.app_context():
        pedido, detalle, caja, _ = _registrar_caja(logged_client, app, peso='16.9')
        resp = logged_client.get(f'/cajas/{caja.id}/etiqueta')

        assert resp.status_code == 200
        assert resp.mimetype == 'application/pdf'
        assert resp.data.startswith(b'%PDF')
        assert 'attachment' in resp.headers['Content-Disposition']
        assert f'etiqueta_{pedido.id}_Chuleta_de_Cerdo_01.pdf' in resp.headers['Content-Disposition']

        # pypdf no es dependencia de la app: sin él se verifica solo el sobre.
        pypdf = pytest.importorskip('pypdf')
        from io import BytesIO
        reader = pypdf.PdfReader(BytesIO(resp.data))
        assert len(reader.pages) == 1
        texto = reader.pages[0].extract_text()
        assert 'Chuleta de Cerdo' in texto
        assert '16.90 kg' in texto
        assert 'L-2309202601' in texto


def test_etiqueta_de_una_caja_en_ios_va_inline(logged_client, app):
    ua = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
          'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
    with app.app_context():
        pedido, detalle, caja, _ = _registrar_caja(logged_client, app)
        resp = logged_client.get(f'/cajas/{caja.id}/etiqueta', headers={'User-Agent': ua})
        assert resp.status_code == 200
        assert resp.headers['Content-Disposition'].startswith('inline;')


def test_etiqueta_de_una_caja_se_reimprime_con_pedido_facturado(logged_client, app):
    """Reimprimir es solo lectura: no lo bloquea la inmutabilidad del facturado."""
    with app.app_context():
        from app import db, Pedido

        pedido, detalle, caja, _ = _registrar_caja(logged_client, app)
        pedido = db.session.get(Pedido, pedido.id)
        pedido.estado = 'facturado'
        db.session.commit()

        resp = logged_client.get(f'/cajas/{caja.id}/etiqueta')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/pdf'


def test_etiqueta_de_caja_inexistente_da_404(logged_client, app):
    with app.app_context():
        resp = logged_client.get('/cajas/999999/etiqueta')
        assert resp.status_code == 404


def test_pesar_incluye_helper_de_compartir_ios(logged_client, app):
    with app.app_context():
        from app import Pedido

        pedido = Pedido.query.first()
        html = logged_client.get(f'/pedidos/{pedido.id}/pesar').data.decode('utf-8')
        assert 'etiquetas_ios_share.js' in html


def test_etiqueta_zpl_de_una_caja(logged_client, app):
    """La pantalla de pesar manda esta etiqueta por Bluetooth a la Zebra."""
    with app.app_context():
        pedido, detalle, caja, _ = _registrar_caja(logged_client, app, peso='16.9')
        resp = logged_client.get(f'/cajas/{caja.id}/etiqueta.zpl')
        assert resp.status_code == 200
        datos = resp.get_json()
        assert datos['caja_id'] == caja.id
        assert datos['numero'] == 1
        assert datos['producto'] == 'Chuleta de Cerdo'
        assert datos['zpl'].startswith('^XA') and datos['zpl'].endswith('^XZ')
        assert 'Chuleta de Cerdo' in datos['zpl']
        assert '16.90 kg' in datos['zpl']
        assert 'L-2309202601' in datos['zpl']
        assert 'Cliente Test' in datos['zpl']        # sin logo propio: fila Client
        # Logo de Jomar cargado aparte, invocado por nombre en la etiqueta.
        assert datos['logo']['zpl'].startswith('~DG')
        assert f"^XG{datos['logo']['nombre']},1,1^FS" in datos['zpl']


def test_etiqueta_zpl_inline_guarda_el_logo_en_ram(logged_client, app):
    """Browser Print pide `?logo=inline`: el logo va con cada etiqueta y se
    guarda en R: (RAM), no en la flash. Sin el parámetro, E: como siempre."""
    with app.app_context():
        pedido, detalle, caja, _ = _registrar_caja(logged_client, app, peso='16.9')
        datos = logged_client.get(f'/cajas/{caja.id}/etiqueta.zpl?logo=inline').get_json()
        assert datos['logo']['nombre'].startswith('R:J')
        assert datos['logo']['zpl'].startswith('~DGR:J')
        assert f"^XG{datos['logo']['nombre']},1,1^FS" in datos['zpl']
        normal = logged_client.get(f'/cajas/{caja.id}/etiqueta.zpl').get_json()
        assert normal['logo']['nombre'].startswith('E:J')
        assert normal['logo']['nombre'][2:] == datos['logo']['nombre'][2:]


def test_etiqueta_zpl_caja_inexistente_da_404(logged_client, app):
    with app.app_context():
        assert logged_client.get('/cajas/999999/etiqueta.zpl').status_code == 404


def test_pesar_trae_barra_de_impresora_bluetooth(logged_client, app):
    with app.app_context():
        from app import Pedido

        pedido = Pedido.query.first()
        html = logged_client.get(f'/pedidos/{pedido.id}/pesar').data.decode('utf-8')
        assert 'zebra_ble.js' in html
        assert 'id="pesar-printer"' in html
        assert 'id="pesar-printer-connect"' in html
        assert 'Imprimir al pesar' in html


def test_confirmacion_y_modal_llevan_el_id_de_la_caja(logged_client, app):
    with app.app_context():
        pedido, detalle, caja, html = _registrar_caja(logged_client, app)
        assert f'data-caja-id="{caja.id}"' in html
        modal = logged_client.get(f'/cajas/{caja.id}/edit').data.decode('utf-8')
        assert f'data-caja-id="{caja.id}"' in modal


def test_pesar_incluye_zebra_browser_print(logged_client, app):
    """La ZQ520 del almacén no expone Bluetooth de baja energía: el camino
    soportado por Zebra es Browser Print, y la pantalla lo intenta primero."""
    with app.app_context():
        from app import Pedido

        pedido = Pedido.query.first()
        html = logged_client.get(f'/pedidos/{pedido.id}/pesar').data.decode('utf-8')
        assert 'zebra_browser_print.js' in html
        # Orden de carga: Browser Print antes que pesar.js, que los consume.
        assert html.index('zebra_browser_print.js') < html.index('js/pesar.js')


def test_csp_permite_los_puertos_locales_de_browser_print():
    """En producción la CSP (connect-src) bloqueaba la petición de la página a
    Zebra Browser Print en localhost:9100 antes de que saliera del navegador."""
    import re
    from app import BROWSER_PRINT_ORIGENES

    assert 'http://localhost:9100' in BROWSER_PRINT_ORIGENES
    assert 'https://localhost:9101' in BROWSER_PRINT_ORIGENES
    assert 'http://127.0.0.1:9100' in BROWSER_PRINT_ORIGENES

    # El JS prueba las mismas direcciones que la CSP permite.
    with open(os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'zebra_browser_print.js'), encoding='utf-8') as fh:
        js = fh.read()
    bases = re.search(r"const BASES = \[(.*?)\];", js).group(1)
    for base in re.findall(r"'([^']+)'", bases):
        assert base.rstrip('/') in BROWSER_PRINT_ORIGENES, base


def test_deshacer_apunta_a_la_caja_de_numero_mas_alto(logged_client, app):
    """Con dos lotes en un producto, «Deshacer» borraba la última caja del
    primer grupo de lote. Cada chip lleva su número y el JS elige el mayor."""
    with app.app_context():
        from app import Pedido, DetallePedido

        pedido = Pedido.query.first()
        detalle = DetallePedido.query.filter_by(pedido_id=pedido.id, es_linea_pedido=True).join(DetallePedido.producto).filter_by(se_pesa=True).first()
        for peso, lote in (('16.9', 'L-0001'), ('17.1', 'L-0001'), ('5.2', 'L-0002')):
            resp = logged_client.post(
                f'/pedidos/{pedido.id}/pesar/caja',
                data={'detalle_pedido_id': detalle.id, 'peso': peso, 'lote': lote,
                      'fecha_elaboracion': '2026-09-23', 'fecha_vencimiento': '2027-09-23'},
                headers={'HX-Request': 'true'},
            )
            assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        # Dos grupos de lote, y el chip de cada caja lleva su número.
        assert html.count('pesar-group-card') == 2
        for numero in (1, 2, 3):
            assert f'data-numero="{numero}"' in html

    with open(os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'pesar.js'), encoding='utf-8') as fh:
        js = fh.read()
    assert ':last-of-type' not in js
    assert 'function ultimaCajaChip' in js
    assert 'dataset.numero' in js


def test_diagnostico_de_impresora_zpl(logged_client, app):
    """La barra de impresora imprime cuatro etiquetas de prueba, una por
    variante del formato, para ver en el almacén cuál arrastra el medio."""
    with app.app_context():
        resp = logged_client.get('/impresora/diagnostico.zpl')
        assert resp.status_code == 200
        datos = resp.get_json()
        assert [v['letra'] for v in datos['variantes']] == ['A', 'B', 'C', 'D']
        assert all(v['zpl'].startswith('^XA') for v in datos['variantes'])


def test_pesar_trae_boton_diagnostico(logged_client, app):
    with app.app_context():
        from app import Pedido

        pedido = Pedido.query.first()
        html = logged_client.get(f'/pedidos/{pedido.id}/pesar').data.decode('utf-8')
        assert 'id="pesar-printer-diag"' in html


def test_pesar_ofrece_modo_rapido_sin_desenfoque(logged_client, app):
    """Un Samsung viejo tardaba segundos en mostrar la caja registrada
    (2026-10-22) con el servidor en 33 ms: el desenfoque de fondo de las
    tarjetas le cuesta a la GPU en cada repintado. «Modo rápido» lo quita y
    se recuerda por navegador."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        html = logged_client.get(f'/pedidos/{pedido.id}/pesar').data.decode('utf-8')
    assert 'id="pesar-modo-rapido"' in html
    raiz = os.path.join(os.path.dirname(__file__), '..', 'static')
    with open(os.path.join(raiz, 'js', 'pesar.js'), encoding='utf-8') as fh:
        js = fh.read()
    assert "'pesar.modoRapido'" in js and 'data-modo-rapido' in js
    with open(os.path.join(raiz, 'css', 'pesar_redesign.css'), encoding='utf-8') as fh:
        css = fh.read()
    bloque = css[css.index('[data-modo-rapido="1"]'):]
    assert 'backdrop-filter: none !important' in bloque
    assert '.pesar-modal-overlay' in bloque and '#pesar-summary' in bloque


def test_tecla_caja_da_sensacion_de_accion():
    """La tecla «Caja» se toca decenas de veces al día: feedback sutil e
    inmediato (vibración, hundido de 120 ms, estado «registrando» con el
    peso) en vez de pasar a gris como apagada mientras responde el servidor."""
    raiz = os.path.join(os.path.dirname(__file__), '..', 'static')
    with open(os.path.join(raiz, 'js', 'pesar.js'), encoding='utf-8') as fh:
        js = fh.read()
    assert 'navigator.vibrate' in js
    assert "'is-sending'" in js and 'Registrando' in js
    with open(os.path.join(raiz, 'css', 'pesar_redesign.css'), encoding='utf-8') as fh:
        css = fh.read()
    assert 'body[data-pesar-screen] .pesar-key:active {\n  transform: scale(0.96);' in css
    assert '.pesar-key.is-submit.is-sending' in css
    assert 'pesar-key-spinner' in css
    reducido = css[css.index('prefers-reduced-motion'):]
    assert '.pesar-key:active' in reducido and 'transform: none' in reducido


def test_pesar_traza_de_tiempos_solo_con_parametro(logged_client, app):
    """`?tiempos=1` muestra cuánto tardó cada tramo de la última caja (toque,
    red, swap, settle, etiqueta) para diagnosticar en el almacén con la Zebra
    conectada (Galaxy A12, 2026-10-22). Sin el parámetro, el panel ni se ve."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        html = logged_client.get(f'/pedidos/{pedido.id}/pesar').data.decode('utf-8')
    assert 'id="pesar-tiempos"' in html
    panel = html[html.index('id="pesar-tiempos"') - 80:html.index('id="pesar-tiempos"') + 80]
    assert ' hidden' in panel
    # En la PWA no hay barra de direcciones: casilla «Medir tiempos».
    assert 'id="pesar-medir-tiempos"' in html
    raiz = os.path.join(os.path.dirname(__file__), '..', 'static')
    with open(os.path.join(raiz, 'js', 'pesar.js'), encoding='utf-8') as fh:
        js = fh.read()
    assert "get('tiempos') === '1'" in js and "'pesar.tiempos'" in js
    for tramo in ('toque→envío', 'red (servidor)', 'swap', 'settle', 'etiqueta'):
        assert tramo in js, tramo
