# tests/test_dashboard_verdad_y_enlaces.py
"""Lo que el dashboard promete con palabras tiene que cumplirlo con números.

Tres cosas que ya se rompieron una vez y que un refactor puede volver a romper:

1. El saludo salía de la hora del servidor. El dyno corre en UTC y Curaçao está
   a UTC−4, así que el turno de las ocho de la noche leía "Buenos días".
2. El "Prom/día" vivía bajo el título "Esta semana" y dividía los pedidos del
   MES por los días del mes. Un promedio mensual con encabezado semanal.
3. Las filas del Top de Clientes enlazan a los pedidos de ese cliente, pero
   SOLO cuando el nombre del ranking resuelve a un cliente local: el ranking
   puede venir de QuickBooks con su propio DisplayName, y un enlace que cae en
   una lista vacía es peor que texto plano.
"""
import os
import re
from datetime import datetime

import pytest
from zoneinfo import ZoneInfo

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db, _saludo_local, _enlazar_top_clientes


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
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
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


# === El saludo lo decide la hora de la planta ===

@pytest.mark.parametrize('hora, esperado', [
    (0, 'Buenos días'),
    (8, 'Buenos días'),
    (11, 'Buenos días'),
    (12, 'Buenas tardes'),
    (18, 'Buenas tardes'),
    (19, 'Buenas noches'),
    (23, 'Buenas noches'),
])
def test_saludo_sigue_la_hora_local(hora, esperado):
    ahora = datetime(2026, 8, 30, hora, 30, tzinfo=ZoneInfo('America/Curacao'))
    assert _saludo_local(ahora) == esperado


def test_saludo_no_usa_la_hora_del_servidor():
    """20:00 en Curaçao son las 00:00 UTC del día siguiente.

    Con `datetime.now().hour` sobre UTC eso da 0 y saluda "Buenos días" a un
    turno de noche. El helper tiene que decir "Buenas noches".
    """
    ahora_local = datetime(2026, 8, 30, 20, 0, tzinfo=ZoneInfo('America/Curacao'))
    assert ahora_local.astimezone(ZoneInfo('UTC')).hour == 0
    assert _saludo_local(ahora_local) == 'Buenas noches'


def test_dashboard_no_trae_el_saludo_con_sol_fijo(logged_client):
    """El ☀ era incondicional: sol a las nueve de la noche."""
    html = logged_client.get('/dashboard').get_data(as_text=True)
    assert '☀' not in html


# === El promedio diario es el de ESTA semana ===

def test_prom_dia_divide_por_los_dias_de_la_semana(app):
    """12 pedidos en una semana de 3 días transcurridos son 4,0 por día.

    Con la fórmula vieja (pedidos del mes / día del mes) el mismo caso daba
    otra cifra bajo el mismo título.
    """
    with app.test_request_context():
        html = flask_app.jinja_env.get_template('dashboard.html').render(
            pedidos_semana=12,
            dias_semana=3,
            pedidos_mes=40,
            fecha_actual=datetime(2026, 8, 30).date(),
            current_user=type('U', (), {'is_authenticated': False, 'username': None})(),
        )
    # El valor vive en la tarjeta "Prom/día" de la sección "Esta semana".
    tarjeta = re.search(
        r'Prom/día</span>\s*<span class="week-mini-val">([^<]+)</span>', html
    )
    assert tarjeta, 'no se encontró la tarjeta Prom/día'
    assert tarjeta.group(1).strip() == '4.0'
    # Con la fórmula vieja (40 pedidos del mes / 30 del mes) habría dado 1,3.
    assert tarjeta.group(1).strip() != '1.3'


def test_ruta_pasa_los_dias_de_la_semana(logged_client):
    """Si la ruta deja de pasar `dias_semana`, la plantilla cae a 7 en silencio."""
    from app import dashboard  # noqa: F401  (la ruta existe)
    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    assert 'PROM/DÍA' in resp.get_data(as_text=True).upper()


# === El Top de Clientes solo enlaza lo que existe ===

def test_top_clientes_enlaza_solo_los_nombres_que_resuelven(app):
    from app import Cliente

    with app.app_context():
        _db.session.add(Cliente(nombre='Mangusa Hypermarket'))
        _db.session.commit()

        enlazadas = _enlazar_top_clientes([
            ('Mangusa Hypermarket', {'total': 100.0, 'pedidos': 2}),
            ('Cliente Solo De QuickBooks', {'total': 50.0, 'pedidos': 1}),
        ])

    por_nombre = {n: d for n, d in enlazadas}
    assert por_nombre['Mangusa Hypermarket']['buscar'] == 'Mangusa Hypermarket'
    assert 'buscar' not in por_nombre['Cliente Solo De QuickBooks']


def test_top_clientes_resuelve_sin_importar_mayusculas_ni_espacios(app):
    from app import Cliente

    with app.app_context():
        _db.session.add(Cliente(nombre='Van den Tweel Supermarket'))
        _db.session.commit()

        enlazadas = _enlazar_top_clientes([
            ('  VAN DEN TWEEL SUPERMARKET  ', {'total': 10.0, 'pedidos': 1}),
        ])

    # Se enlaza con el nombre LOCAL, que es el que la búsqueda de /pedidos
    # encuentra, no con la variante que trajo el ranking.
    assert enlazadas[0][1]['buscar'] == 'Van den Tweel Supermarket'


def test_fila_del_top_es_enlace_cuando_resuelve_y_div_cuando_no(app):
    """El envoltorio cambia de <a> a <div>: la afordancia no puede mentir."""
    with app.test_request_context():
        html = flask_app.jinja_env.get_template('dashboard.html').render(
            top_clientes=[
                ('Mangusa Hypermarket', {'total': 100.0, 'pedidos': 2,
                                         'buscar': 'Mangusa Hypermarket'}),
                ('Cliente Solo De QuickBooks', {'total': 50.0, 'pedidos': 1}),
            ],
            fecha_actual=datetime(2026, 8, 30).date(),
            current_user=type('U', (), {'is_authenticated': False, 'username': None})(),
        )

    assert 'href="/pedidos?q=Mangusa%20Hypermarket"' in html
    assert 'rank-link' in html
    # El que no resuelve no aparece dentro de ningún href.
    assert 'q=Cliente' not in html
    assert 'Cliente Solo De QuickBooks' in html


def test_top_productos_no_promete_un_destino(app):
    """No existe pantalla por producto que responda "¿dónde se vendió esto?".

    Mientras no exista, las filas de productos son texto. Si alguien las
    convierte en enlaces, este test obliga a decidir a dónde llevan.
    """
    with app.test_request_context():
        html = flask_app.jinja_env.get_template('dashboard.html').render(
            top_productos=[{'nombre': 'Boneless Chicken Breast', 'ingresos': 100.0,
                            'cajas': 4, 'peso': 0, 'pedidos': 1}],
            fecha_actual=datetime(2026, 8, 30).date(),
            current_user=type('U', (), {'is_authenticated': False, 'username': None})(),
        )

    seccion = html.split('sec-top-prod')[-1].split('sec-top-cli')[0]
    assert 'Boneless Chicken Breast' in seccion
    assert 'rank-link' not in seccion


# === El gráfico no usa colores de estado ===

def test_el_grafico_no_pinta_las_barras_con_verde_de_estado(app):
    """DESIGN.md: un color de estado nunca es la serie de un gráfico.

    Las barras estaban en `--mark-good` (verde de "conforme") y pintaban de
    verde una semana floja.
    """
    with app.test_request_context():
        html = flask_app.jinja_env.get_template('dashboard.html').render(
            fecha_actual=datetime(2026, 8, 30).date(),
            current_user=type('U', (), {'is_authenticated': False, 'username': None})(),
        )

    script = html.split('salesTrendChart')[-1]
    for prohibido in ('--mark-good', '--mark-warning', '--mark-critical',
                      '16,185,129', '#10b981'):
        assert prohibido not in script, f'color de estado {prohibido} en el gráfico'
    # Barras en el índigo de marca y línea de tendencia en tinta: dos índigos
    # separados solo por claridad no despegaban la línea de las barras.
    assert '--indigo-500' in html and '--gray-900' in html


# === El selector de periodo del Top ===

def test_selector_de_periodo_lleva_su_javascript(app):
    """El control dibujado sin su script son cuatro botones que no hacen nada.

    Pasó de verdad: `hay_selector` se calculaba con un `{% set %}` dentro de
    `{% block content %}` y se leía en `{% block scripts %}`, donde NO existe —
    los bloques de Jinja tienen ámbito propio—. El HTML salía con los chips y
    sin el manejador. Este test mira las dos mitades en la misma respuesta.
    """
    periodos = {
        clave: {
            'top_productos': [{'nombre': 'Ham di Pasku', 'ingresos': 4333.0,
                               'cajas': 15, 'peso': 223.45, 'pedidos': 3,
                               'cajas_txt': '15', 'peso_txt': '223.4'}],
            'top_clientes': [{'nombre': 'Mangusa Hypermarket', 'total': 4333.0,
                              'pedidos': 3, 'ultimo_pedido': '26/08',
                              'buscar': 'Mangusa Hypermarket'}],
            'max_ventas': 4333.0,
            'max_total_clientes': 4333.0,
        }
        for clave in ('month', '3m', '6m')
    }

    with app.test_request_context():
        html = flask_app.jinja_env.get_template('dashboard.html').render(
            rankings_periodos_json=periodos,
            fecha_actual=datetime(2026, 8, 30).date(),
            current_user=type('U', (), {'is_authenticated': False, 'username': None})(),
        )

    # La mitad visible: dos grupos de chips, uno por ranking.
    assert html.count('data-periodo-para=') == 2
    assert 'data-periodo="3m"' in html and 'data-periodo="6m"' in html
    # '4w' se retiró el 2026-08-30: a fin de mes esa ventana y 'month' son casi
    # la misma, y tres destinos separan mejor que cuatro que se pisan.
    assert 'data-periodo="4w"' not in html
    # La mitad que lo hace funcionar.
    assert 'function pintar' in html
    assert 'data-rank-lista="productos"' in html
    assert 'data-rank-lista="clientes"' in html


def test_sin_datos_de_mas_de_un_periodo_no_hay_selector(app):
    """Un control que ofrece vistas que no existen es ruido."""
    with app.test_request_context():
        html = flask_app.jinja_env.get_template('dashboard.html').render(
            rankings_periodos_json={'month': {'top_productos': [], 'top_clientes': []}},
            fecha_actual=datetime(2026, 8, 30).date(),
            current_user=type('U', (), {'is_authenticated': False, 'username': None})(),
        )
    assert 'data-periodo-para=' not in html
    assert 'function pintar' not in html


def test_la_pantalla_degradada_no_ofrece_otros_periodos(app):
    """Con los datos caídos, cambiar de periodo no puede traer nada mejor."""
    periodos = {c: {'top_productos': [], 'top_clientes': []}
                for c in ('month', '3m', '6m')}
    with app.test_request_context():
        html = flask_app.jinja_env.get_template('dashboard.html').render(
            rankings_periodos_json=periodos,
            degradado=True,
            fecha_actual=datetime(2026, 8, 30).date(),
            current_user=type('U', (), {'is_authenticated': False, 'username': None})(),
        )
    assert 'data-periodo-para=' not in html
    assert 'function pintar' not in html


def test_el_json_del_top_trae_los_textos_ya_formateados(app):
    """Cajas y kilos viajan formateados para que el redibujado no cambie dígitos.

    Python formatea 223,45 como "223.4" y JavaScript como "223.5": la misma
    fila mostraba un valor al cargar y otro al volver del selector. El servidor
    formatea una vez y el navegador solo imprime.
    """
    from app import _serialize_rankings_periodos

    with app.app_context():
        salida = _serialize_rankings_periodos({
            'month': {
                'top_productos': [{'nombre': 'Ham di Pasku', 'ingresos': 4333.0,
                                   'cajas': 15.0, 'peso': 223.45, 'pedidos': 3}],
                'top_clientes': [],
            }
        })

    producto = salida['month']['top_productos'][0]
    assert producto['peso_txt'] == '223.4'
    assert producto['cajas_txt'] == '15'
