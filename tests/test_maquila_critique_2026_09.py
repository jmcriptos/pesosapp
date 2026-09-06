"""Ronda de critique del módulo de maquila (2026-09-06).

Cada test fija un hallazgo medido en el navegador para que no vuelva:

- P1-1 · el piso táctil del módulo es 48px, y 56px lo que se opera con guante.
- P1-2 · la pantalla de cierre no lleva su explicación larga por delante.
- P2-1 · el riel de secciones lleva cuatro destinos; el resto va tras «Más».
- P2-2 · el estado de una recepción mira todas las unidades, no solo los kilos.
- P2-3 · el tipo de movimiento no se pinta con colores de estado.
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

IDS = {}
CSS = os.path.join(os.path.dirname(__file__), '..', 'static', 'css', 'maquila.css')


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
        carne = Ingrediente(nombre='Carne de res', unidad='kg')
        tripa = Ingrediente(nombre='Tripa natural', unidad='ud')
        _db.session.add_all([v, cli, prod, carne, tripa])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id,
                   carne=carne.id, tripa=tripa.id)
        yield flask_app
        _db.drop_all()


def _login(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'pw'},
           follow_redirects=True)
    return c


def _css():
    with open(CSS, encoding='utf-8') as fh:
        return fh.read()


def _nav(html):
    """El nav de maquila. `html.index('</nav>')` tomaba el de la topbar."""
    i = html.index('<nav class="maquila-nav-fila"')
    return html[i:html.index('</nav>', i)]


def _min_height(css, selector):
    """El min-height efectivo de `selector`, mirando TODAS sus reglas.

    Una sola no alcanza: `.maquila-sub summary` aparece tres veces —una de
    tipografía, sin alto, y dos que sí lo fijan— y el CSS cascadea. Se toma el
    mayor de los declarados, que es lo que termina midiendo el destino.
    """
    altos = []
    i = css.find(selector)
    assert i != -1, f'no existe la regla {selector}'
    while i != -1:
        abre = css.index('{', i)
        cuerpo = css[abre:css.index('}', abre)]
        encontrado = re.search(r'min-height:\s*(\d+)px', cuerpo)
        if encontrado:
            altos.append(int(encontrado.group(1)))
        i = css.find(selector, abre)
    assert altos, f'{selector} no fija min-height en ninguna regla'
    return max(altos)


# ---------------------------------------------------------------- P1-1

def test_ninguna_regla_del_modulo_fija_un_destino_tactil_en_44px():
    """El sistema manda 48px de mínimo (design.json, `ds-btn-primary`).

    44px es el número genérico de iOS y el módulo lo usaba en el 65 % de sus
    destinos medidos, argumentando el guante en el propio comentario —cuando
    el guante, en este sistema, pide 56.
    """
    sobrantes = [linea for linea in _css().splitlines()
                 if re.search(r'min-height:\s*44px', linea)]
    assert sobrantes == [], (
        'quedan destinos táctiles en 44px:\n  ' + '\n  '.join(sobrantes))


@pytest.mark.parametrize('selector', [
    '.maquila-nav a',
    '.maquila-wrap .ops-firma-clear',
    '.maquila-wrap .rec-quitar',
    '.maquila-sub summary',
    '.maquila-wrap details.maquila-detalles > summary',
    '.maquila-wrap .maquila-tarjeta-cab h2 a',
])
def test_los_destinos_tactiles_llegan_al_minimo_del_sistema(selector):
    alto = _min_height(_css(), selector)
    assert alto >= 48, f'{selector} mide {alto}px'


@pytest.mark.parametrize('selector', [
    '.maquila-tabla-consumo input[type="number"]',
    '.maquila-wrap .maquila-cajas-editar input[type="number"]',
])
def test_los_campos_que_se_teclean_con_guante_miden_56px(selector):
    """El consumo real y el peso de caja mueven inventario ajeno y se teclean
    con el guante puesto: van a la altura de «Acción con guante», no al
    mínimo táctil."""
    alto = _min_height(_css(), selector)
    assert alto >= 56, f'{selector} mide {alto}px'


# ---------------------------------------------------------------- P1-2

def _corrida_abierta_con_cajas():
    from maquila import servicios
    servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': IDS['carne'], 'peso_total': Decimal('100')},
                {'ingrediente_id': IDS['tripa'], 'peso_total': Decimal('200')}])
    c = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-1',
        fecha_produccion=date(2026, 9, 2), vendedor_id=IDS['vendedor'])
    servicios.agregar_caja_producida(c, Decimal('12.5'))
    _db.session.commit()
    return c


def test_el_cierre_no_lleva_la_explicacion_larga_por_delante(app):
    """Medido antes: 162 palabras de prosa y el primer campo «Real» a y=745 en
    un viewport de 844. La explicación sigue estando, plegada."""
    with app.app_context():
        corrida = _corrida_abierta_con_cajas()
        cid = corrida.id
    html = _login(app).get(f'/maquila/corridas/{cid}/cerrar').get_data(as_text=True)

    assert 'no viene precargado a propósito' in html, 'la explicación no se borra'
    i_details = html.index('maquila-porque')
    i_texto = html.index('no viene precargado a propósito')
    assert i_details < i_texto, 'la explicación tiene que vivir dentro del details'

    # El párrafo de la cabecera («Declará, recalculá, revisá el total y
    # firmá») lo dice el pie, pegado al botón que se bloquea.
    assert 'Declará, recalculá, revisá el total y firmá' not in html
    # Y la salida deja de ser un enlace de 16px dentro de una frase.
    assert 'maquila-salida' in html


def test_el_primer_campo_real_llega_antes_que_la_explicacion(app):
    with app.app_context():
        corrida = _corrida_abierta_con_cajas()
        cid = corrida.id
    html = _login(app).get(f'/maquila/corridas/{cid}/cerrar').get_data(as_text=True)
    assert html.index('name="consumo_real"') < html.index('id="firma_png"')


# ---------------------------------------------------------------- P2-1

def test_el_panel_de_mas_no_vive_dentro_del_riel_que_scrollea(app):
    """El bug de la primera versión: el menú se renderizaba y no se veía.

    `.maquila-nav` scrollea en horizontal (`overflow-x:auto`), esconde el
    desborde vertical (`overflow-y:hidden`) y lleva una `mask-image`. Cada una
    de las tres recorta por su cuenta un panel absoluto que cae por debajo del
    riel, así que «Más» abría un panel invisible. El `<details>` tiene que ser
    HERMANO del riel, no descendiente.
    """
    html = _login(app).get('/maquila').get_data(as_text=True)
    nav = _nav(html)
    riel = nav[nav.index('<div class="maquila-nav">'):]
    riel = riel[:riel.index('</div>')]
    assert 'maquila-nav-mas' not in riel, (
        'el disclosure dentro del riel queda recortado por su overflow')

    # Y la fila que sí lo contiene no puede recortar.
    css = _css()
    fila = css[css.index('.maquila-nav-fila {'):]
    fila = fila[:fila.index('}')]
    assert 'overflow: visible' in fila, 'la fila no puede recortar el panel'


def test_los_enlaces_del_panel_llegan_al_piso_de_48px():
    """Al salir del riel dejaron de heredar `.maquila-nav a`: sin regla propia
    salían como enlaces crudos de 19px, subrayados."""
    css = _css()
    assert _min_height(css, '.maquila-nav-panel a') >= 48
    bloque = css[css.index('.maquila-nav-panel a {'):]
    bloque = bloque[:bloque.index('}')]
    assert 'text-decoration: none' in bloque


def test_el_riel_lleva_cuatro_destinos_y_el_resto_va_tras_mas(app):
    """Medido: diez destinos daban 1.063px de riel en 356px útiles, con tres a
    la vista. Los seis de configurar y consultar pasan a un disclosure."""
    html = _login(app).get('/maquila').get_data(as_text=True)
    nav = _nav(html)
    panel = nav[nav.index('maquila-nav-panel'):]
    riel = nav[:nav.index('<details')]

    assert riel.count('<a ') == 4, 'el riel lleva solo los destinos de operación'
    for rotulo in ('Resumen', 'Recepciones', 'Producción', 'Ajustes'):
        assert f'>{rotulo}</a>' in riel
    for rotulo in ('Ingredientes', 'Recetas', 'Saldos', 'Kardex',
                   'Rendimiento', 'Trazabilidad'):
        assert f'>{rotulo}</a>' in panel, f'{rotulo} tiene que seguir alcanzable'


def test_el_panel_marca_donde_estas_pero_no_se_abre_solo(app):
    html = _login(app).get('/maquila/reportes/kardex').get_data(as_text=True)
    assert 'maquila-nav-mas is-active' in html, 'el disclosure marca la sección'
    nav = _nav(html)
    assert '<details class="maquila-nav-mas is-active">' in nav, (
        'abierto al cargar taparía el contenido que se vino a leer')
    assert 'aria-current="page"' in nav


# ---------------------------------------------------------------- P2-2

def _recibir(kg, ud):
    from maquila import servicios
    return servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': IDS['carne'], 'peso_total': Decimal(str(kg))},
                {'ingrediente_id': IDS['tripa'], 'peso_total': Decimal(str(ud))}])


def test_una_recepcion_con_la_tripa_agotada_no_dice_sin_consumir(app):
    """El caso que salía en verde: 240 kg de carne intactos y 600 ud de tripa
    consumidas enteras. El chip miraba solo los kilos.

    El consumo va por un cierre de corrida de verdad —no por un ajuste
    manual—: solo el reparto FIFO ata la salida a la línea de la recepción, y
    es el saldo POR LÍNEA el que alimenta esta columna.
    """
    from maquila import servicios
    with app.app_context():
        _recibir(240, 600)
        _db.session.commit()
        corrida = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-9',
            fecha_produccion=date(2026, 9, 2), vendedor_id=IDS['vendedor'])
        servicios.agregar_caja_producida(corrida, Decimal('20'))
        _db.session.commit()
        servicios.cerrar_corrida(corrida, {IDS['tripa']: Decimal('600')},
                                 IDS['vendedor'], firma=b'\x89PNG\r\n\x1a\n',
                                 firma_mimetype='image/png')
        _db.session.commit()

    html = _login(app).get('/maquila/recepciones').get_data(as_text=True)
    assert 'Sin consumir' not in html, (
        'con una unidad agotada la recepción no está «sin consumir»')
    assert 'Sin ud' in html, 'el chip tiene que nombrar la unidad que se agotó'
    # Y la carne, que no se tocó, sigue estando entera en la columna.
    assert '240 kg' in html


def test_una_recepcion_intacta_sigue_diciendo_sin_consumir(app):
    with app.app_context():
        _recibir(240, 600)
        _db.session.commit()
    html = _login(app).get('/maquila/recepciones').get_data(as_text=True)
    assert 'Sin consumir' in html


def test_la_columna_queda_muestra_cada_unidad_por_separado(app):
    """Sumar kg con ud sigue prohibido: da un número que no es nada."""
    with app.app_context():
        _recibir(240, 600)
        _db.session.commit()
    html = _login(app).get('/maquila/recepciones').get_data(as_text=True)
    fila = html[html.index('data-label="Queda"'):]
    fila = fila[:fila.index('</td>')]
    assert '240 kg' in fila and '600 ud' in fila


# ---------------------------------------------------------------- P2-3

@pytest.mark.parametrize('tipo,tono_prohibido', [
    ('entrada', 'is-conforme'),
    ('ajuste', 'is-aviso'),
])
def test_el_tipo_de_movimiento_no_usa_colores_de_estado(app, tipo, tono_prohibido):
    """Verde y ámbar significan estado y nada más. Una entrada no está
    «conforme» y un ajuste no es un «aviso»: son tipos, no estados."""
    with app.app_context():
        render = flask_app.jinja_env.get_template('maquila/_macros.html').module
        html = str(render.chip_tipo_movimiento(tipo))
    assert tono_prohibido not in html, f'«{tipo}» se pinta con un color de estado'
    assert tipo.capitalize() in html, 'el chip sigue diciendo la palabra'
