"""Etiqueta con listado de ingredientes.

El producto guarda sus ingredientes como texto libre (tal como deben salir
en la etiqueta) y el formulario de etiquetas ofrece, además de la de
vencimiento, una variante que los imprime.
"""
import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db  # noqa: E402

INGREDIENTES = ('Pork, water, salt, sugar, spices, sodium nitrite. '
                'CONTAINS: SOY, MILK.')


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Producto
        rol = Rol(nombre='super_admin', descripcion='Admin')
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add_all([rol, territorio])
        _db.session.flush()
        vendedor = Vendedor(username='admin', email='admin@test.com',
                            nombre_completo='Admin Test', rol_id=rol.id,
                            territorio_id=territorio.id, activo=True)
        vendedor.set_password('testpass')
        con = Producto(nombre='Chorizo Criollo', temperatura='-18°C', tax_rate=6.0,
                       ingredientes=INGREDIENTES)
        sin = Producto(nombre='Jamón', temperatura='4°C', tax_rate=6.0)
        _db.session.add_all([vendedor, con, sin])
        _db.session.commit()
        flask_app.config['_IDS'] = {'con': con.id, 'sin': sin.id}
        yield flask_app
        _db.drop_all()


@pytest.fixture
def client(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'testpass'})
    return c


# ---------------------------------------------------------------- producto

def test_producto_guarda_ingredientes_al_crear_y_editar(client, app):
    r = client.post('/productos', data={'nombre': 'Salami', 'temperatura': '4°C',
                                        'tax_rate': '6', 'ingredientes': '  Pork, salt.  '})
    assert r.status_code == 302
    with app.app_context():
        from app import Producto
        p = Producto.query.filter_by(nombre='Salami').one()
        assert p.ingredientes == 'Pork, salt.'
        pid = p.id
    r = client.post(f'/productos/{pid}/editar',
                    data={'nombre': 'Salami', 'temperatura': '4°C', 'tax_rate': '6',
                          'ingredientes': 'Pork, salt, pepper.'})
    assert r.status_code == 302
    with app.app_context():
        from app import Producto
        assert _db.session.get(Producto, pid).ingredientes == 'Pork, salt, pepper.'
    # Vaciarlo lo deja en NULL, no en cadena vacía.
    client.post(f'/productos/{pid}/editar',
                data={'nombre': 'Salami', 'temperatura': '4°C', 'tax_rate': '6', 'ingredientes': '  '})
    with app.app_context():
        from app import Producto
        assert _db.session.get(Producto, pid).ingredientes is None


def test_formularios_de_producto_tienen_campo_ingredientes(client, app):
    html = client.get('/productos').get_data(as_text=True)
    assert 'name="ingredientes"' in html
    pid = app.config['_IDS']['con']
    html = client.get(f'/productos/{pid}/editar').get_data(as_text=True)
    assert 'name="ingredientes"' in html
    assert 'CONTAINS: SOY, MILK.' in html


# ---------------------------------------------------------------- formulario

def test_form_etiquetas_ofrece_tipo_y_marca_productos_con_ingredientes(client, app):
    html = client.get('/etiquetas_vencimiento').get_data(as_text=True)
    assert 'name="tipo"' in html
    assert 'value="vencimiento"' in html and 'value="ingredientes"' in html
    ids = app.config['_IDS']
    assert f'<option value="{ids["con"]}" data-ingredientes="1"' in html
    assert f'<option value="{ids["sin"]}" data-ingredientes="0"' in html


# ---------------------------------------------------------------- datos

def test_build_datos_incluye_ingredientes(app):
    with app.app_context():
        from app import _build_datos_etiqueta_vencimiento
        datos, n = _build_datos_etiqueta_vencimiento({
            'producto_id': str(app.config['_IDS']['con']), 'fecha_fabricacion': '2026-10-01',
            'lote': 'L-1', 'cantidad_etiquetas': '2'})
        assert datos['ingredientes'] == INGREDIENTES
        assert n == 2


@pytest.mark.parametrize('ruta,nombre', [
    ('/etiquetas_vencimiento', 'etiquetas_ingredientes.pdf'),
    ('/etiquetas_vencimiento_4x2', 'etiquetas_ingredientes_4x2.pdf'),
])
def test_etiqueta_ingredientes_genera_pdf(client, app, ruta, nombre):
    r = client.post(ruta, data={'tipo': 'ingredientes', 'producto_id': str(app.config['_IDS']['con']),
                                'fecha_fabricacion': '2026-10-01', 'lote': 'L-1',
                                'cantidad_etiquetas': '3'})
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert r.data.startswith(b'%PDF')
    assert nombre in r.headers['Content-Disposition']


def test_etiqueta_ingredientes_rechaza_producto_sin_ingredientes(client, app):
    r = client.post('/etiquetas_vencimiento_4x2',
                    data={'tipo': 'ingredientes', 'producto_id': str(app.config['_IDS']['sin']),
                          'fecha_fabricacion': '2026-10-01', 'lote': 'L-1', 'cantidad_etiquetas': '1'})
    assert r.status_code == 400
    assert 'ingredientes' in r.get_data(as_text=True).lower()


def test_tipo_vencimiento_sigue_igual(client, app):
    """Sin `tipo` (o con vencimiento) la etiqueta de siempre, aunque el
    producto no tenga ingredientes."""
    for data in ({}, {'tipo': 'vencimiento'}):
        r = client.post('/etiquetas_vencimiento_4x2',
                        data={'producto_id': str(app.config['_IDS']['sin']),
                              'fecha_fabricacion': '2026-10-01', 'lote': 'L-1',
                              'cantidad_etiquetas': '1', **data})
        assert r.status_code == 200 and r.mimetype == 'application/pdf'
        assert 'etiquetas_vencimiento_4x2.pdf' in r.headers['Content-Disposition']


# ---------------------------------------------------------------- dibujo

def test_draw_wrap_paragraph_ajusta_y_encoge():
    from utils.label_utils import draw_wrap_paragraph
    c = MagicMock()
    corto = 'Pork, salt.'
    font, lines = draw_wrap_paragraph(c, corto, x=0, y_bottom=0, y_top=60, max_width=270,
                                      max_font=7.5, min_font=5.5)
    assert font == 7.5 and lines == [corto]
    assert c.drawString.call_count == 1
    c.reset_mock()
    largo = ' '.join(['ingredient'] * 60)
    font, lines = draw_wrap_paragraph(c, largo, x=0, y_bottom=0, y_top=60, max_width=270,
                                      max_font=7.5, min_font=5.5)
    assert font < 7.5 and len(lines) > 1
    assert ' '.join(lines) == largo
    # Una llamada drawString por línea, en orden.
    assert c.drawString.call_count == len(lines)
    assert c.drawString.call_args_list[0].args[2] == lines[0]


def test_draw_wrap_paragraph_recorta_con_elipsis_si_no_cabe():
    from utils.label_utils import draw_wrap_paragraph
    c = MagicMock()
    enorme = ' '.join(['ingredient'] * 2000)
    font, lines = draw_wrap_paragraph(c, enorme, x=0, y_bottom=0, y_top=60, max_width=270,
                                      max_font=7.5, min_font=5.5)
    assert font == 5.5
    assert lines[-1].endswith('…')


def test_draw_ingredients_label_dibuja_todo():
    from utils.label_utils import draw_ingredients_label
    c = MagicMock()
    datos = {'nombre_producto': 'Chorizo Criollo', 'lote': 'L-1', 'fecha_fabricacion': '01/10/2026',
             'fecha_expiracion': '01/10/2027', 'temperatura': '-18°C', 'ingredientes': INGREDIENTES}
    draw_ingredients_label(c, None, datos, 0, 0)
    textos = [call.args[-1] for call in c.drawString.call_args_list
              + c.drawRightString.call_args_list + c.drawCentredString.call_args_list]
    joined = ' '.join(str(t) for t in textos)
    for esperado in ('Chorizo Criollo', 'L-1', '01/10/2026', '01/10/2027', '-18°C', 'Ingredients', 'CONTAINS: SOY'):
        assert esperado in joined, esperado
