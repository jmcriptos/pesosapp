"""El logo del cliente se imprime en blanco y negro sin perder lo que va claro.

Las etiquetas salen por una impresora térmica: 1 bit, sin grises. Si la app
manda el logo a color, el driver lo binariza por luminancia y un logo con
marcas claras sobre un fondo de color medio pierde las marcas — fondo y marcas
caen del mismo lado del umbral. Le pasó al logo de Deli Nova, que se imprimía
sin el "Deli" (verde 155 y blanco 224, umbral 128: los dos sin tinta).

La conversión de la app usa el COLOR y no el brillo: el color dominante (el
campo del logo) pasa a tinta y todo lo demás a papel.
"""
import os
from io import BytesIO

import pytest
from PIL import Image

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

VERDE = (144, 192, 48)
BLANCO = (255, 255, 255)
AZUL = (10, 100, 170)


def _png(construir, size=(60, 60)):
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    construir(img)
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _logo_knockout():
    """Campo verde con una barra blanca y otra azul encima — como Deli Nova."""
    def construir(img):
        for x in range(60):
            for y in range(60):
                img.putpixel((x, y), VERDE + (255,))
        for x in range(10, 50):          # barra blanca ("Deli")
            for y in range(15, 25):
                img.putpixel((x, y), BLANCO + (255,))
        for x in range(10, 50):          # barra azul ("nova")
            for y in range(35, 45):
                img.putpixel((x, y), AZUL + (255,))
    return _png(construir)


def _logo_negro():
    """Artwork negro sobre transparente, como el logo por defecto de Jomar."""
    def construir(img):
        for x in range(20, 40):
            for y in range(20, 40):
                img.putpixel((x, y), (0, 0, 0, 255))
    return _png(construir)


def _clasificar(png_bytes):
    """Devuelve (es_tinta) por píxel: True = tinta, False = papel."""
    img = Image.open(BytesIO(png_bytes)).convert('RGBA')
    def tinta(p):
        r, g, b, a = p
        return a >= 128 and (0.299 * r + 0.587 * g + 0.114 * b) < 128
    return img, {(x, y): tinta(img.getpixel((x, y)))
                 for x in range(img.width) for y in range(img.height)}


# ------------------------------------------------------------- la conversión


def test_las_marcas_claras_sobreviven_la_conversion():
    """Lo que va en blanco sobre el fondo de color tiene que quedar SIN tinta,
    y el fondo CON tinta. Es justo al revés de lo que hace el driver."""
    from utils.label_utils import logo_monocromo_para_etiqueta

    _img, tinta = _clasificar(logo_monocromo_para_etiqueta(_logo_knockout()))

    assert tinta[(5, 5)], 'el campo del logo tiene que quedar en tinta'
    assert not tinta[(30, 20)], 'la marca blanca tiene que quedar en papel'


def test_las_marcas_de_otro_color_tambien_sobreviven():
    """El azul tampoco es el color dominante, así que también es marca: si se
    fuera a tinta se fundiría con el fondo y se perdería igual que el blanco."""
    from utils.label_utils import logo_monocromo_para_etiqueta

    _img, tinta = _clasificar(logo_monocromo_para_etiqueta(_logo_knockout()))

    assert not tinta[(30, 40)], 'la marca azul tiene que quedar en papel'


def test_un_logo_ya_monocromo_conserva_su_tinta():
    """El caso normal no se degrada: artwork negro sigue imprimiéndose negro."""
    from utils.label_utils import logo_monocromo_para_etiqueta

    _img, tinta = _clasificar(logo_monocromo_para_etiqueta(_logo_negro()))

    assert tinta[(30, 30)], 'el artwork negro tiene que quedar en tinta'
    assert not tinta[(2, 2)], 'el fondo transparente tiene que quedar en papel'


def test_la_salida_es_solo_tinta_o_papel():
    """Sin grises intermedios: la térmica no los imprime, los vuelve a binarizar."""
    from utils.label_utils import logo_monocromo_para_etiqueta

    img = Image.open(BytesIO(
        logo_monocromo_para_etiqueta(_logo_knockout())
    )).convert('RGBA')

    colores = {p for p in img.getdata()}
    assert colores <= {(0, 0, 0, 255), (0, 0, 0, 0)}, (
        f'Esperaba solo tinta y papel, encontré: {sorted(colores)[:5]}'
    )


# --------------------------------------------------------- detección al subir


def test_detecta_el_logo_con_fondo_de_color():
    from utils.label_utils import logo_tiene_fondo_de_color

    assert logo_tiene_fondo_de_color(_logo_knockout()) is True


def test_no_marca_un_logo_ya_monocromo():
    from utils.label_utils import logo_tiene_fondo_de_color

    assert logo_tiene_fondo_de_color(_logo_negro()) is False


# ------------------------------------------------------ integración con el PDF


def test_resolve_label_logo_convierte_el_logo_del_cliente():
    from reportlab.lib.utils import ImageReader
    from utils.label_utils import resolve_label_logo

    logo = resolve_label_logo('.', _logo_knockout())

    assert isinstance(logo, ImageReader)
    assert logo.getSize() == (60, 60)
    # Lo que se dibuja tiene que estar YA convertido: si llegara el logo
    # original a color, el driver volvería a perder las marcas claras.
    tonos = set(logo.getRGBData())
    assert tonos <= {0, 255}, f'Llegó color sin convertir al PDF: {sorted(tonos)[:6]}'


def test_el_logo_por_defecto_no_se_toca():
    """La decisión fue convertir SOLO logos de cliente."""
    from utils.label_utils import resolve_label_logo, get_logo_path

    assert resolve_label_logo('.', None) == get_logo_path('.')


def test_un_logo_ilegible_no_rompe_la_etiqueta():
    """Imprimir etiquetas es operativo: ante un logo que Pillow no puede leer,
    la etiqueta sale igual en vez de tirar 500."""
    from utils.label_utils import resolve_label_logo

    logo = resolve_label_logo('.', b'esto no es una imagen')

    assert logo is not None


# ------------------------------------------------- aviso al subir el logo


from app import app as flask_app, db as _db  # noqa: E402


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
        _db.session.add_all([vendedor, Cliente(nombre='Deli Nova', moneda='XCG')])
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _subir_logo(client, png_bytes):
    return client.post('/clientes/1/editar', data={
        'nombre': 'Deli Nova', 'moneda': 'XCG',
        'logo': (BytesIO(png_bytes), 'logo.png'),
    }, content_type='multipart/form-data', follow_redirects=True)


def test_avisa_al_subir_un_logo_con_fondo_de_color(app, logged_client):
    """El logo se guarda igual —la app lo convierte al imprimir—, pero el aviso
    explica por qué la etiqueta no va a verse como el archivo original."""
    respuesta = _subir_logo(logged_client, _logo_knockout())

    cuerpo = respuesta.get_data(as_text=True)
    assert 'fondo de color' in cuerpo, 'Falta el aviso al subir el logo'

    with app.app_context():
        from app import Cliente
        assert _db.session.get(Cliente, 1).logo_etiqueta, 'El logo debe guardarse igual'


def test_no_avisa_con_un_logo_ya_monocromo(app, logged_client):
    respuesta = _subir_logo(logged_client, _logo_negro())

    assert 'fondo de color' not in respuesta.get_data(as_text=True)
