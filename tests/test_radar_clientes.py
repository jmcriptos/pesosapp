"""El radar de clientes: ritmo propio, agrupación y contrato de la pantalla.

Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md
"""
import os
from datetime import date, datetime, timedelta, timezone

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import _ritmo_cliente, _RADAR_RITMO_NEGOCIO, _RADAR_RAFAGA_DIAS


HOY = date(2026, 8, 29)


def _fechas(*dias_atras):
    return [HOY - timedelta(days=d) for d in dias_atras]


def test_ritmo_propio_con_tres_fechas_o_mas():
    # Compra cada 7 días: 0, 7, 14, 21 atrás → intervalos [7,7,7]
    ritmo, propio = _ritmo_cliente(_fechas(0, 7, 14, 21))
    assert (ritmo, propio) == (7, True)


def test_ritmo_es_la_mediana_no_el_promedio():
    """Un intervalo raro no debe mover el ritmo: por eso mediana."""
    # intervalos [5, 5, 100] → mediana 5, promedio 36,7
    ritmo, propio = _ritmo_cliente(_fechas(0, 5, 10, 110))
    assert (ritmo, propio) == (5, True)


def test_con_menos_de_tres_fechas_usa_el_ritmo_del_negocio():
    for fechas in ([], _fechas(3), _fechas(3, 10)):
        ritmo, propio = _ritmo_cliente(fechas)
        assert ritmo == _RADAR_RITMO_NEGOCIO
        assert propio is False


def test_varios_pedidos_el_mismo_dia_no_dan_ritmo_cero():
    """LA regresión que motivó medir entre fechas y no entre pedidos.

    Best Buy carga varios pedidos la misma fecha. Midiendo entre PEDIDOS su
    mediana daba 0 días, lo que lo marcaba atrasado contra una división por
    cero y encima imprimía «ritmo 0d» en la fila. Midiendo entre fechas
    distintas, su ritmo es real.
    """
    fechas = _fechas(0, 0, 0, 14, 14, 28)     # tres fechas, no seis
    ritmo, propio = _ritmo_cliente(fechas)
    assert ritmo == 14
    assert propio is True
    assert ritmo > 0, 'un ritmo de 0 días divide por cero al calcular el atraso'


def test_datetimes_del_mismo_dia_cuentan_como_una_sola_fecha():
    """El contrato que impide que vuelva el bug de Best Buy.

    Si `_ritmo_cliente` no normaliza a día calendario, estos tres `datetime`
    del mismo día sobreviven como fechas distintas, los intervalos dan 0 y el
    ritmo sale 0 — que es división por cero al calcular el atraso.
    """
    base = datetime(2026, 8, 15, 9, 0)
    fechas = [
        base, base.replace(hour=11), base.replace(hour=16),   # un solo día
        datetime(2026, 8, 29, 10, 0),
        datetime(2026, 9, 12, 10, 0),
    ]
    ritmo, propio = _ritmo_cliente(fechas)
    assert ritmo == 14, 'los tres del 15/08 tienen que colapsar en una sola fecha'
    assert propio is True


from app import _agrupar_radar


def _fila(nombre, dias_desde_ultimo=None, ritmo=10, n_pedidos=5, propio=True):
    return {
        'id': abs(hash(nombre)) % 10000,
        'nombre': nombre,
        'ultimo': None if dias_desde_ultimo is None else HOY - timedelta(days=dias_desde_ultimo),
        'n_pedidos': n_pedidos,
        'ritmo': ritmo,
        'ritmo_propio': propio,
    }


def _grupo(grupos, clave):
    for c, _etiqueta, filas in grupos:
        if c == clave:
            return filas
    raise AssertionError(f'falta el grupo {clave}')


def test_las_cuatro_claves_siempre_estan_y_en_orden():
    grupos = _agrupar_radar([], HOY)
    assert [c for c, _e, _f in grupos] == ['atrasados', 'al_dia', 'dormidos', 'sin_pedidos']


def test_pasado_de_su_ritmo_va_a_atrasados():
    # ritmo 10, lleva 30 días → 3× su ritmo
    grupos = _agrupar_radar([_fila('Arco Iris', 30, ritmo=10)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'atrasados')] == ['Arco Iris']
    assert _grupo(grupos, 'al_dia') == []


def test_dentro_de_su_ritmo_va_a_al_dia():
    grupos = _agrupar_radar([_fila('Mangusa', 6, ritmo=7)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'al_dia')] == ['Mangusa']
    assert _grupo(grupos, 'atrasados') == []


def test_el_umbral_es_una_vez_y_media():
    """Justo en el límite NO está atrasado; apenas encima, sí."""
    assert _grupo(_agrupar_radar([_fila('Justo', 15, ritmo=10)], HOY), 'atrasados') == []
    assert len(_grupo(_agrupar_radar([_fila('Pasado', 16, ritmo=10)], HOY), 'atrasados')) == 1


def test_mas_de_noventa_dias_es_dormido_y_no_atrasado():
    """Disjuntos: un dormido está pasadísimo de su ritmo, pero va en un grupo solo."""
    grupos = _agrupar_radar([_fila('Everyday', 173, ritmo=10)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'dormidos')] == ['Everyday']
    assert _grupo(grupos, 'atrasados') == []


def test_sin_ningun_pedido_va_a_su_propio_grupo():
    grupos = _agrupar_radar([_fila('Alta Nueva', None, n_pedidos=0)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'sin_pedidos')] == ['Alta Nueva']
    assert _grupo(grupos, 'dormidos') == [], 'no compró nunca, no está dormido'


def test_atrasados_ordena_por_veces_su_ritmo():
    grupos = _agrupar_radar([
        _fila('poco', 20, ritmo=10),    # 2,0×
        _fila('mucho', 60, ritmo=10),   # 6,0×
        _fila('medio', 40, ritmo=10),   # 4,0×
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'atrasados')] == ['mucho', 'medio', 'poco']


def test_dormidos_ordena_por_cantidad_de_pedidos():
    """En un dormido importa cuánto se perdió, no cuánto hace."""
    grupos = _agrupar_radar([
        _fila('chico', 120, n_pedidos=2),
        _fila('grande', 100, n_pedidos=40),
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'dormidos')] == ['grande', 'chico']


def test_sin_pedidos_ordena_alfabetico():
    grupos = _agrupar_radar([
        _fila('Zeta', None, n_pedidos=0),
        _fila('alfa', None, n_pedidos=0),
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'sin_pedidos')] == ['alfa', 'Zeta']


def test_cada_cliente_cae_en_un_solo_grupo():
    filas = [_fila('a', 30, ritmo=10), _fila('b', 5, ritmo=10),
             _fila('c', 200, ritmo=10), _fila('d', None, n_pedidos=0)]
    grupos = _agrupar_radar(filas, HOY)
    vistos = [f['nombre'] for _c, _e, fs in grupos for f in fs]
    assert sorted(vistos) == ['a', 'b', 'c', 'd']
    assert len(vistos) == len(set(vistos))


def test_una_fila_con_ritmo_roto_no_divide_por_cero():
    """La defensa existe en el código, pero nada la estaba protegiendo.

    `_ritmo_cliente` ya no puede devolver 0, pero `_agrupar_radar` recibe
    dicts armados por el llamador y no puede confiar en eso: un `ritmo` en 0
    o en None tiene que caer al ritmo del negocio, no reventar.
    """
    for ritmo_roto in (0, None):
        fila = _fila('Roto', 30, ritmo=ritmo_roto)
        grupos = _agrupar_radar([fila], HOY)
        # cae al ritmo del negocio (13): 30 días son 2,3x → atrasado
        assert [f['nombre'] for f in _grupo(grupos, 'atrasados')] == ['Roto'], (
            f'con ritmo={ritmo_roto!r} el cliente no se clasificó'
        )
        assert fila['veces_su_ritmo'] > 0


def test_fila_con_pedidos_pero_sin_fecha_del_ultimo():
    """Dato inconsistente: afirma tener pedidos y no trae la última fecha.

    Sin fecha no hay atraso que calcular. Va a «sin pedidos» y NO a Dormidos:
    mandarlo a Dormidos por un dato faltante sería afirmar que hace más de 90
    días que no compra, que es una cosa que la pantalla no sabe.
    """
    grupos = _agrupar_radar([_fila('Sucio', None, n_pedidos=7)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'sin_pedidos')] == ['Sucio']
    assert _grupo(grupos, 'dormidos') == []


# ── El contexto de la pantalla: una sola consulta ─────────────────────────────
# Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md (Task 3)

import pytest

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Pedido

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username='admin', email='admin@test.com', nombre_completo='Admin',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)

        ahora = datetime.utcnow()

        # Ritmo estimado (prestado): 2 pedidos en fechas distintas. Hacen
        # falta 3 fechas distintas para que `_ritmo_cliente` calcule un ritmo
        # propio; con 2, la fila es «estimado».
        estimado = Cliente(nombre='Ritmo Estimado', territorio_id=territorio.id)
        _db.session.add(estimado)
        _db.session.flush()
        _db.session.add(Pedido(cliente_id=estimado.id,
                                fecha_pedido=ahora - timedelta(days=20)))
        _db.session.add(Pedido(cliente_id=estimado.id,
                                fecha_pedido=ahora - timedelta(days=6)))

        # Ritmo propio: 4 pedidos en fechas distintas.
        propio = Cliente(nombre='Ritmo Propio', territorio_id=territorio.id)
        _db.session.add(propio)
        _db.session.flush()
        for dias in (0, 7, 14, 21):
            _db.session.add(Pedido(cliente_id=propio.id,
                                    fecha_pedido=ahora - timedelta(days=dias)))

        # Sin ningún pedido.
        _db.session.add(Cliente(nombre='Sin Pedidos', territorio_id=territorio.id))

        # Dos pedidos el MISMO día calendario, más otros dos en días
        # distintos: la fila cuenta 4 pedidos (filas), pero el ritmo se mide
        # sobre 3 fechas distintas (15, 25 y 35 días atrás). Horas fijas al
        # mediodía UTC para no depender de a qué hora corre el test ni
        # arriesgar cruzar medianoche local.
        mismo_dia = Cliente(nombre='Mismo Día', territorio_id=territorio.id)
        _db.session.add(mismo_dia)
        _db.session.flush()
        dia_a = (ahora - timedelta(days=15)).date()
        _db.session.add(Pedido(cliente_id=mismo_dia.id,
                                fecha_pedido=datetime(dia_a.year, dia_a.month, dia_a.day, 12, 0)))
        _db.session.add(Pedido(cliente_id=mismo_dia.id,
                                fecha_pedido=datetime(dia_a.year, dia_a.month, dia_a.day, 15, 0)))
        dia_b = (ahora - timedelta(days=25)).date()
        _db.session.add(Pedido(cliente_id=mismo_dia.id,
                                fecha_pedido=datetime(dia_b.year, dia_b.month, dia_b.day, 12, 0)))
        dia_c = (ahora - timedelta(days=35)).date()
        _db.session.add(Pedido(cliente_id=mismo_dia.id,
                                fecha_pedido=datetime(dia_c.year, dia_c.month, dia_c.day, 12, 0)))

        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def test_el_radar_hace_una_sola_consulta_de_pedidos(logged_client, app):
    """Con 62 clientes, una query por cliente serían 62 viajes a la base."""
    from sqlalchemy import event
    from app import db

    consultas = []

    def espiar(conn, cursor, statement, params, context, many):
        if 'pedido' in statement.lower():
            consultas.append(statement)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', espiar)
        try:
            resp = logged_client.get('/clientes')
        finally:
            event.remove(db.engine, 'before_cursor_execute', espiar)

    assert resp.status_code == 200
    assert len(consultas) <= 1, (
        f'el radar hizo {len(consultas)} consultas a pedido: '
        'tiene que ser una sola agregada'
    )


def test_fecha_pedido_se_cuenta_en_la_zona_del_negocio(app):
    """`fecha_pedido` es UTC naive; el radar cuenta días calendario locales.

    Un pedido a las 02:00 UTC del día 10 es todavía el día 9 en Curaçao
    (UTC−4). Contarlo como del 10 corre el ritmo un día entero.
    """
    from app import _dia_local
    assert _dia_local(datetime(2026, 8, 10, 2, 0)) == date(2026, 8, 9)
    assert _dia_local(datetime(2026, 8, 10, 12, 0)) == date(2026, 8, 10)


def test_contexto_radar_agrupa_a_los_clientes_de_la_fixture(app):
    """`_contexto_radar` arma las cuatro claves y respeta ritmo propio/estimado."""
    from app import _contexto_radar, Cliente

    with app.app_context():
        clientes = Cliente.query.all()
        hoy_local = datetime.now(timezone.utc).date()
        grupos = _contexto_radar(clientes, hoy_local)

        claves = [c for c, _e, _f in grupos]
        assert claves == ['atrasados', 'al_dia', 'dormidos', 'sin_pedidos']

        todas = [f for _c, _e, filas in grupos for f in filas]
        nombres = {f['nombre']: f for f in todas}
        assert set(nombres) == {
            'Ritmo Estimado', 'Ritmo Propio', 'Sin Pedidos', 'Mismo Día',
        }

        assert nombres['Ritmo Estimado']['ritmo_propio'] is False
        assert nombres['Ritmo Propio']['ritmo_propio'] is True
        assert nombres['Sin Pedidos']['n_pedidos'] == 0

        # `n_pedidos` cuenta filas de pedido, no fechas distintas.
        assert nombres['Ritmo Estimado']['n_pedidos'] == 2
        assert nombres['Ritmo Propio']['n_pedidos'] == 4


def test_n_pedidos_cuenta_filas_mientras_el_ritmo_cuenta_dias(logged_client, app):
    """Las dos reglas conviven y se confunden fácil.

    Un cliente con DOS pedidos el mismo día compró dos veces —eso es lo que la
    fila promete— pero para el ritmo ese día es UNO solo. Ninguna fixture
    anterior tenía dos pedidos el mismo día, así que cambiar `len(fechas)` por
    `len(set(fechas))` dejaba los 21 tests en verde.
    """
    from app import _contexto_radar, Cliente

    with app.app_context():
        clientes = Cliente.query.all()
        hoy_local = datetime.now(timezone.utc).date()
        grupos = _contexto_radar(clientes, hoy_local)
        todas = [f for _c, _e, filas in grupos for f in filas]
        fila = next(f for f in todas if f['nombre'] == 'Mismo Día')

        # 4 filas de pedido (dos el mismo día + dos en días distintos), pero
        # solo 3 fechas calendario distintas: si `n_pedidos` contara fechas en
        # vez de filas, saldría 3, no 4.
        assert fila['n_pedidos'] == 4, (
            'n_pedidos tiene que contar CADA pedido, incluidos los dos del '
            'mismo día, no las fechas distintas'
        )

        # El ritmo se mide sobre las 3 fechas distintas (15/25/35 días
        # atrás): intervalos [10, 10] → mediana 10. Si el ritmo se calculara
        # sobre las filas en vez de las fechas, los dos pedidos del mismo día
        # meterían un intervalo de 0 días y correrían el resultado.
        assert fila['ritmo_propio'] is True
        assert fila['ritmo'] == 10, (
            f"ritmo salió {fila['ritmo']}, se esperaba 10 (mediana de fechas "
            'distintas, no de filas de pedido)'
        )
        assert fila['n_pedidos'] != fila['ritmo'], (
            'los dos números tienen que ser distintos para que el test '
            'distinga cuál regla se está afirmando'
        )


def test_mostrar_clientes_le_pasa_los_grupos_a_la_plantilla(logged_client, app):
    """`grupos=` no lo protegía nada.

    La plantilla todavía no usa `grupos` —se cablea en la tarea siguiente—, así
    que borrar `grupos=_contexto_radar(...)` del render dejaba la suite entera
    en verde. Este test mira el CONTEXTO que recibe la plantilla, que es lo que
    de verdad se quiere afirmar, y no el HTML que sale.
    """
    from flask import template_rendered

    capturado = []

    def registrar(sender, template, context, **extra):
        capturado.append(context)

    template_rendered.connect(registrar, app)
    try:
        resp = logged_client.get('/clientes')
    finally:
        template_rendered.disconnect(registrar, app)

    assert resp.status_code == 200
    assert capturado, 'no se renderizó ninguna plantilla'
    ctx = capturado[0]
    assert 'clientes' in ctx, 'el JS de alta y borrado depende de `clientes`'
    assert 'grupos' in ctx, 'la plantilla del radar necesita `grupos`'
    assert [clave for clave, _etiqueta, _filas in ctx['grupos']] == [
        'atrasados', 'al_dia', 'dormidos', 'sin_pedidos'
    ]


# ── Task 4: la plantilla dibuja el radar ───────────────────────────────────
# Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md (Task 4)

import re


def test_la_pantalla_dibuja_las_secciones_del_radar(logged_client):
    html = logged_client.get('/clientes').get_data(as_text=True)
    for clave in ['atrasados', 'al_dia', 'dormidos', 'sin_pedidos']:
        assert f'data-radar-grupo="{clave}"' in html


def test_la_fila_dice_dias_ritmo_y_pedidos(logged_client, app):
    """Afirma los NÚMEROS de la fila, no sólo los rótulos alrededor.

    Comprobado por mutación: borrar `{{ f.dias_sin_comprar }}` y
    `{{ f.n_pedidos }}` de `clientes.html:91,93` deja la fila diciendo
    « días sin comprar · su ritmo: 7 d · pedidos» —sin un solo número— y
    los DOS rótulos literales ('días sin comprar', 'su ritmo') siguen
    intactos en el HTML porque viven en el propio template, no en las
    variables borradas. La versión anterior de este test sólo buscaba esos
    rótulos sueltos en toda la página y seguía en verde con el dato
    borrado. Se ancla a la fila de «Ritmo Propio» (fixture de este archivo:
    4 pedidos en fechas 0/7/14/21 días atrás → dias_sin_comprar=0, ritmo
    propio=7, n_pedidos=4) y exige los números, no los rótulos.
    """
    with app.app_context():
        from app import Cliente
        cliente_id = Cliente.query.filter_by(nombre='Ritmo Propio').first().id
    html = logged_client.get('/clientes').get_data(as_text=True)
    fila = re.search(rf'id="cliente-{cliente_id}".*?</li>', html, re.S)
    assert fila, 'no se encontró la fila de Ritmo Propio'
    texto = fila.group(0)
    assert '0 días sin comprar' in texto
    assert 'su ritmo: 7 d' in texto
    assert '4 pedidos' in texto


def test_el_ritmo_prestado_se_declara_estimado(logged_client, app):
    """Un cliente sin ritmo propio lleva la marca; uno con ritmo propio no.

    OJO: el cliente de la fixture se llama «Ritmo Estimado» y su nombre
    lowercaseado ('ritmo estimado') termina en `data-buscar` de CUALQUIER
    forma, incluso sin la marca — así que buscar 'estimado' suelto en todo
    el HTML pasaría con una plantilla rota. Hay que anclar el texto entre
    paréntesis (la marca que la plantilla agrega, no el nombre del cliente)
    y, además, comprobar que la fila de «Ritmo Propio» NO la lleva.
    """
    with app.app_context():
        from app import Cliente
        id_estimado = Cliente.query.filter_by(nombre='Ritmo Estimado').first().id
        id_propio = Cliente.query.filter_by(nombre='Ritmo Propio').first().id
    html = logged_client.get('/clientes').get_data(as_text=True)

    assert '(estimado)' in html

    fila_estimado = re.search(rf'id="cliente-{id_estimado}".*?</li>', html, re.S)
    fila_propio = re.search(rf'id="cliente-{id_propio}".*?</li>', html, re.S)
    assert fila_estimado and '(estimado)' in fila_estimado.group(0)
    assert fila_propio and '(estimado)' not in fila_propio.group(0)


def test_la_accion_principal_es_crear_un_pedido_para_ese_cliente(logged_client, app):
    """Anclado con la comilla de cierre: sin ella, `?cliente=1` es substring
    de `?cliente=10`/`?cliente=11` en cuanto haya diez clientes o más."""
    with app.app_context():
        from app import Cliente
        cid = Cliente.query.first().id
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert f'/pedidos/nuevo?cliente={cid}"' in html


def test_la_fila_muestra_la_moneda_del_cliente(logged_client, app):
    """Un pedido en USD no es el mismo importe que uno en XCG (~78% de
    diferencia): la moneda es información operativa, no decorativa, y tiene
    que estar en la fila desde la que se arranca el pedido nuevo.

    Anclado a la fila del cliente concreto (no `'USD' in html` suelto, que
    se satisface con cualquier otra cosa en la página que diga USD).

    OJO de sesión: NO envolver esta mutación en un `with app.app_context()`
    propio. El fixture `app` deja su contexto pusheado durante todo el test
    (el `yield` está DENTRO del `with`), y `logged_client.get(...)` lo
    reutiliza (Flask reusa el app-context de arriba de la pila cuando ya es
    de la misma app). Mutar en un contexto nuevo aparte usa una sesión
    DISTINTA: el commit es real en la base, pero el objeto `Cliente` que la
    sesión del fixture ya tenía cacheado en su identity map no se refresca,
    y la fila sale con la moneda vieja aunque la base ya tenga la nueva.
    Mutando acá, en el contexto ambiente, se evita el problema.
    """
    from app import Cliente, db as _db
    estimado = Cliente.query.filter_by(nombre='Ritmo Estimado').first()
    estimado.moneda = 'USD'
    _db.session.commit()
    id_estimado = estimado.id
    propio_id = Cliente.query.filter_by(nombre='Ritmo Propio').first().id

    html = logged_client.get('/clientes').get_data(as_text=True)

    fila_estimado = re.search(rf'id="cliente-{id_estimado}".*?</li>', html, re.S)
    fila_propio = re.search(rf'id="cliente-{propio_id}".*?</li>', html, re.S)
    assert fila_estimado and '>USD<' in fila_estimado.group(0)
    assert fila_propio and '>USD<' not in fila_propio.group(0), (
        'el cliente en XCG no puede mostrar el chip de USD'
    )
    assert fila_propio and '>XCG<' in fila_propio.group(0)


def test_sigue_estando_el_id_de_fila_que_usa_el_borrado(logged_client, app):
    """`eliminar-cliente` hace getElementById('cliente-'+id) para sacar la fila."""
    with app.app_context():
        from app import Cliente
        cid = Cliente.query.first().id
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert f'id="cliente-{cid}"' in html
    assert 'data-buscar=' in html, 'la búsqueda client-side depende de este atributo'


def test_sin_atrasados_la_pantalla_lo_dice_con_calma(logged_client, app):
    """El vacío de «Atrasados» es un buen resultado, no una pantalla rota."""
    with app.app_context():
        from app import Pedido, db as _db
        _db.session.query(Pedido).delete()
        _db.session.commit()
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert 'Todos al día' in html
    assert 'data-radar-grupo="atrasados"' in html


# ── Task 5: plegado, búsqueda y estilos ─────────────────────────────────────
# Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md (Task 5)
#
# Sin navegador (eso es la Task 6): estas pruebas leen el HTML/JS que sirve
# `/clientes` y afirman patrones exactos de código, no comportamiento
# ejecutado. Cada assert está anclado a una substring que sólo puede venir
# de la pieza que se quiere proteger, no de otra parte de la página.


def test_la_busqueda_esconde_las_secciones_que_quedan_vacias(logged_client):
    """Si «Mangusa» sólo está en «Al día», no puede quedar un encabezado
    «Atrasados 5» encima de cero filas: la pantalla estaría mintiendo."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert 'radar-seccion' in html
    assert 'seccionesVacias' in html, (
        'el JS de búsqueda tiene que replegar las secciones sin coincidencias'
    )


def _cuerpo_seccionesVacias(html):
    m = re.search(r'function seccionesVacias\(q\) \{.*?\n  \}', html, re.S)
    assert m, (
        'seccionesVacias tiene que declarar `q` como parámetro: sin el '
        'término de búsqueda no puede distinguir "no hay búsqueda" de '
        '"buscando y sin resultados"'
    )
    return m.group(0)


def test_seccionesVacias_no_esconde_secciones_cuando_no_hay_busqueda(logged_client):
    """La enmienda del controlador (posterior al brief original): la versión
    que esconde TODA sección con cero `.radar-row` visibles rompe el ciclo
    buscar → borrar la búsqueda. `.radar-seccion[data-radar-grupo="atrasados"]`
    vacía no dibuja NINGUNA `.radar-row` (dibuja «Todos al día» en su lugar
    — ver `test_sin_atrasados_la_pantalla_lo_dice_con_calma`), así que con la
    versión ingenua esa sección desaparecería al escribir cualquier término y
    JAMÁS volvería al borrarlo, porque nunca tuvo filas que "reaparecer".

    Este test no ejecuta el JS (no hay navegador en esta tarea): afirma que
    el código trae la guarda `if (!q)` que hace que, sin término de
    búsqueda, TODAS las secciones vuelvan incondicionalmente — la única
    forma de que el ciclo completo (buscar → borrar) sea correcto.
    """
    html = logged_client.get('/clientes').get_data(as_text=True)
    cuerpo = _cuerpo_seccionesVacias(html)
    assert 'if (!q)' in cuerpo, (
        'falta la guarda que hace volver todas las secciones cuando el '
        'buscador está vacío'
    )
    assert 'sec.hidden = false' in cuerpo, (
        'la guarda de "sin búsqueda" tiene que reabrir la sección '
        '(sec.hidden = false), no dejarla como estaba'
    )


def test_seccionesVacias_solo_esconde_cuando_hay_termino_y_sin_coincidencias(logged_client):
    html = logged_client.get('/clientes').get_data(as_text=True)
    cuerpo = _cuerpo_seccionesVacias(html)
    assert (
        "sec.hidden = sec.querySelectorAll('.radar-row:not([hidden])')"
        ".length === 0" in cuerpo
    ), 'con término de búsqueda, la sección se esconde solo si no le quedan filas visibles'


def test_el_buscador_llama_seccionesVacias_con_el_termino_no_sin_argumentos(logged_client):
    """`seccionesVacias()` sin argumento no puede distinguir el caso "recién
    borré la búsqueda" del caso "busco algo y no hay resultados": ambos
    llegarían con la sección igual de vacía de filas. Ancla el LLAMADO
    (con `;` de cierre de sentencia), no la línea de la declaración de la
    función (que también contiene el substring `seccionesVacias(q)` pero
    seguido de `{`, nunca de `;`)."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert html.count('seccionesVacias(q)') >= 2, (
        'seccionesVacias(q) tiene que aparecer tanto en la declaración como '
        'en el llamado'
    )
    assert 'seccionesVacias(q);' in html, (
        'el buscador tiene que llamar a seccionesVacias pasándole el término '
        'de búsqueda, no seccionesVacias() a secas'
    )


# ── H5: la cuenta del encabezado no puede afirmar un número falso ─────────
# El propio comentario del JS (arriba de `seccionesVacias`) dice que un
# encabezado «Atrasados 5» encima de cero filas visibles «estaría afirmando
# algo falso» — pero eso sólo lo resolvía el caso CERO. Buscando «man» con
# 1 fila visible, la cuenta seguía fija en «5»: el mismo defecto, un caso
# más adentro. `actualizarContadores` cuenta `.radar-row:not([hidden])`
# dentro de cada `.radar-seccion` y reescribe el badge — así que sin
# búsqueda (nada queda oculto) el número es el total sin ninguna rama
# especial, y al borrar un cliente (`row.remove()`) también queda al día.

def _cuerpo_actualizarContadores(html):
    m = re.search(r'function actualizarContadores\(\) \{.*?\n  \}', html, re.S)
    assert m, 'no se encontró la función actualizarContadores'
    return m.group(0)


def test_actualizarContadores_cuenta_filas_visibles_por_seccion(logged_client):
    cuerpo = _cuerpo_actualizarContadores(logged_client.get('/clientes').get_data(as_text=True))
    assert ".querySelector('.radar-cuenta')" in cuerpo, (
        'tiene que ubicar el badge de la propia sección, no uno global'
    )
    assert (
        "cuenta.textContent = sec.querySelectorAll('.radar-row:not([hidden])')"
        ".length" in cuerpo
    ), 'el badge tiene que reflejar las filas VISIBLES de esa sección, no el total fijo'


def test_el_buscador_llama_actualizarContadores(logged_client):
    """Sin esto, buscar «man» deja «Atrasados 5» sobre 1 fila visible: el
    mismo defecto que `seccionesVacias` existe para prevenir, un caso más
    adentro (con resultados parciales, no sólo con cero)."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    m = re.search(
        r"buscar-cliente'\)\.addEventListener\('input', function \(\) \{.*?\n  \}\);",
        html, re.S,
    )
    assert m, 'no se encontró el listener de búsqueda'
    assert 'actualizarContadores();' in m.group(0), (
        'el buscador tiene que recalcular las cuentas de sección en cada tecleo'
    )


def test_borrar_un_cliente_llama_actualizarContadores(logged_client):
    """Hoy, borrar la última fila de «Al día» deja su encabezado con la
    cuenta vieja: `row.remove()` saca la fila del DOM pero nada recalcula
    el badge. Se ancla al manejador de `.eliminar-cliente`, después de que
    la fila se remueve."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    m = re.search(
        r"e\.target\.closest\('\.eliminar-cliente'\);.*?\n  \}\);",
        html, re.S,
    )
    assert m, 'no se encontró el manejador de borrado'
    cuerpo = m.group(0)
    assert 'row.remove();' in cuerpo
    assert cuerpo.index('row.remove();') < cuerpo.index('actualizarContadores();'), (
        'actualizarContadores tiene que correr DESPUÉS de sacar la fila del DOM'
    )


def test_borrar_la_busqueda_reabre_los_grupos_que_la_busqueda_dejo_visibles(logged_client):
    """Cuando `q` está vacío, el listener de búsqueda no toca `.radar-grupo`
    ni `aria-expanded` (sólo lo hace `if (q)`): el estado de plegado que deja
    el usuario (o que la búsqueda abrió) es responsabilidad del click en el
    encabezado, no del buscador — así que borrar la búsqueda no puede volver
    a plegar «Dormidos» si el usuario lo abrió a mano antes de buscar."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    m = re.search(
        r"buscar-cliente'\)\.addEventListener\('input', function \(\) \{.*?\n  \}\);",
        html, re.S,
    )
    assert m, 'no se encontró el listener de búsqueda'
    cuerpo = m.group(0)
    assert "if (q) g.hidden = false;" in cuerpo, (
        'abrir grupos plegados es condicional a que haya término de '
        'búsqueda, no incondicional'
    )
    assert "if (q) b.setAttribute('aria-expanded', 'true');" in cuerpo


def test_el_plegado_convive_con_el_borrado_sin_reemplazarlo(logged_client):
    """El listener de borrado (`.eliminar-cliente`) y el de plegado
    (`.radar-titulo-plegable`) van los DOS sobre `#lista-clientes`. Si
    alguien "simplifica" reemplazando uno por otro, el borrado de clientes
    —una función viva— deja de andar sin que ningún test de plegado lo note
    si no se cuentan ambos listeners explícitamente."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    listeners = re.findall(
        r"getElementById\('lista-clientes'\)\s*\.addEventListener\('click',",
        html,
    )
    assert len(listeners) == 2, (
        f"se esperaban 2 listeners de click en #lista-clientes (borrado y "
        f"plegado), se encontraron {len(listeners)}"
    )
    assert "e.target.closest('.eliminar-cliente')" in html
    assert "e.target.closest('.radar-titulo-plegable')" in html


def test_el_plegado_actualiza_aria_expanded_y_el_hidden_del_grupo(logged_client):
    html = logged_client.get('/clientes').get_data(as_text=True)
    m = re.search(
        r"e\.target\.closest\('\.radar-titulo-plegable'\);.*?\n  \}\);",
        html, re.S,
    )
    assert m, 'no se encontró el manejador de click del plegado'
    cuerpo = m.group(0)
    assert 'grupo.hidden = !abrir' in cuerpo
    assert "btn.setAttribute('aria-expanded', abrir ? 'true' : 'false')" in cuerpo


def test_dormidos_y_sin_pedidos_arrancan_plegados_pero_los_otros_dos_no(logged_client):
    """Los encabezados de «Dormidos»/«Nunca compraron» son botones plegables
    con `aria-expanded="false"`; «Atrasados»/«Al día» son `<h2>`, no botones,
    y no llevan `aria-expanded` en absoluto."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    for clave in ('dormidos', 'sin_pedidos'):
        seccion = re.search(
            rf'data-radar-grupo="{clave}".*?(?=data-radar-grupo="|\Z)',
            html, re.S,
        )
        assert seccion, f'no se encontró la sección {clave}'
        assert 'aria-expanded="false"' in seccion.group(0)
        assert 'class="radar-titulo radar-titulo-plegable"' in seccion.group(0)


def test_las_filas_usan_radar_row_para_que_la_busqueda_las_encuentre(logged_client):
    """La búsqueda (Task 5) consulta `#lista-clientes .radar-row`, no
    `.gestion-row` a secas: si la Task 4 alguna vez pierde la clase
    `radar-row` de la fila, `seccionesVacias` no puede contarlas y el
    ciclo buscar → borrar queda roto silenciosamente."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert re.search(r'class="gestion-row radar-row"', html)
    assert "querySelectorAll('#lista-clientes .radar-row')" in html


# ── Estilos: colores explícitos, no heredados ───────────────────────────────
# Esta pantalla ya sufrió el bleed de una regla global de color sobre
# elementos que no se esperaba que alcanzara (ver operaciones-css-bleed en la
# memoria del proyecto). Se lee el CSS del disco, no vía Flask: es un asset
# estático servido directo, sin plantilla de por medio.

import pathlib

_GESTION_CSS = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'css' / 'gestion.css'


def _css_radar():
    texto = _GESTION_CSS.read_text(encoding='utf-8')
    inicio = texto.index('El radar de clientes')
    return texto[inicio:]


def test_el_css_del_radar_no_usa_el_gris_de_bajo_contraste():
    """#94a3b8 sobre blanco da 2,56:1 (memoria del proyecto,
    operaciones-css-bleed); esta pantalla se usa a plena luz, en la calle.

    Ancla a un valor de propiedad (`: #94a3b8`), no a la substring suelta:
    el propio CSS lo NOMBRA en un comentario para explicar por qué no se
    usa, así que un `assert '#94a3b8' not in css` a secas se dispara con su
    propia documentación."""
    css = _css_radar()
    assert not re.search(r':\s*#94a3b8\b', css)


def _valor_regla(css, selector, propiedad):
    """Extrae `propiedad: #xxxxxx` del bloque `{...}` de `selector` en `css`.

    Lee el valor QUE ESTÁ HOY en el archivo, no uno copiado a mano: así, si
    alguien cambia el color de `.radar-cuenta` y no toca este test, el
    cálculo de contraste corre igual sobre el valor nuevo (y puede fallar de
    verdad), en vez de seguir comparando contra un literal viejo que ya no
    describe el CSS.
    """
    m = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', css, re.S)
    assert m, f'no se encontró la regla {selector!r} en el CSS'
    pm = re.search(propiedad + r'\s*:\s*(#[0-9a-fA-F]{6})', m.group(1))
    assert pm, f'{selector!r} no define {propiedad!r}'
    return pm.group(1)


def test_los_colores_del_radar_llegan_al_minimo_de_contraste():
    """Calcula la razón WCAG real, contra el fondo REAL de cada regla —
    leyendo los colores DEL ARCHIVO, no copiados a mano en el test.

    El test `..._no_usa_el_gris_de_bajo_contraste` de arriba sólo prohibía
    el literal `#94a3b8`. No habría cazado el fallo que motivó este test:
    `.radar-cuenta` en `#64748b` sobre `#f1f5f9` (su propio fondo) daba
    4,34:1 —por debajo del 4,5 de 12px bold— y el comentario del CSS
    afirmaba 4,76 porque estaba calculado contra BLANCO y no contra el
    fondo real del badge. Medir contra el fondo equivocado es el error que
    este test existe para impedir.

    Comprobado a mano que este test puede fallar: con `.radar-cuenta`
    devuelto a `color: #64748b` (el valor de antes de la corrección), esta
    misma función reporta `cuenta de sección (badge): #64748b sobre
    #f1f5f9 = 4.34:1 (mínimo 4.5)` y el assert final se dispara — porque
    lee el color de la regla en vivo, no un texto fijo en el test.
    """
    def luminancia(hex_color):
        h = hex_color.lstrip('#')
        canales = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]

        def lineal(v):
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

        r, g, b = (lineal(c) for c in canales)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def razon(fg, bg):
        l1, l2 = luminancia(fg), luminancia(bg)
        alto, bajo = max(l1, l2), min(l1, l2)
        return (alto + 0.05) / (bajo + 0.05)

    css_completo = _GESTION_CSS.read_text(encoding='utf-8')
    css = _css_radar()

    # Fondos compartidos, fuera del bloque `.radar-*` (los pinta el patrón
    # de gestión para toda pantalla, no el radar) — también leídos en vivo,
    # de las reglas que ya existían antes de esta tarea.
    pagina_bg = _valor_regla(css_completo, 'body[data-gestion-screen] .app-content,\nbody[data-gestion-screen] .mobile-form-container', 'background')
    fila_bg = _valor_regla(css_completo, 'body[data-gestion-screen] .gestion-row', 'background')

    # (qué es, color, fondo real, mínimo) — todo leído del CSS salvo el
    # nombre y el mínimo. Ninguno de estos textos califica como "texto
    # grande" de WCAG (18px normal o 14pt/~18,7px bold): todos van entre
    # 12px y 14.4px, así que el mínimo es 4,5:1 en todos los casos.
    pares = [
        # Encabezado de sección: sin fondo propio, se apoya en el área de
        # contenido (regla 1 de gestion.css).
        ('título de sección', _valor_regla(css, '.radar-titulo', 'color'), pagina_bg, 4.5),
        # El badge de cuenta SÍ trae fondo propio: éste es el par que
        # estaba mal, calculado antes contra blanco en vez de contra el
        # suyo.
        ('cuenta de sección (badge)',
         _valor_regla(css, '.radar-cuenta', 'color'),
         _valor_regla(css, '.radar-cuenta', 'background'), 4.5),
        ('título de atrasados',
         _valor_regla(css, '[data-radar-grupo="atrasados"] .radar-titulo', 'color'),
         pagina_bg, 4.5),
        ('cuenta de atrasados (badge)',
         _valor_regla(css, '[data-radar-grupo="atrasados"] .radar-cuenta', 'color'),
         _valor_regla(css, '[data-radar-grupo="atrasados"] .radar-cuenta', 'background'), 4.5),
        # La fila (.gestion-row) SÍ trae fondo propio blanco, así que estos
        # dos van contra ese blanco de verdad.
        ('meta de la fila (días/ritmo/pedidos)',
         _valor_regla(css, 'body[data-gestion-screen] .gestion-row-sub.radar-meta', 'color'),
         fila_bg, 4.5),
        ('meta de la fila, "(estimado)"',
         _valor_regla(css, '.radar-meta em', 'color'), fila_bg, 4.5),
        ('acción principal ("+ Pedido")',
         _valor_regla(css, '.radar-action-main', 'color'),
         _valor_regla(css, '.radar-action-main', 'background'), 4.5),
        ('acción principal, hover',
         _valor_regla(css, '.radar-action-main', 'color'),
         _valor_regla(css, '.radar-action-main:hover', 'background'), 4.5),
        # Mismo fondo que el encabezado de sección: #f8fafc explícito
        # dentro de la propia regla `.radar-vacio`.
        ('mensaje "Todos al día"',
         _valor_regla(css, '.radar-vacio', 'color'),
         _valor_regla(css, '.radar-vacio', 'background'), 4.5),
    ]

    flojos = [
        f'{que}: {fg} sobre {bg} = {razon(fg, bg):.2f}:1 (mínimo {minimo})'
        for que, fg, bg, minimo in pares
        if razon(fg, bg) < minimo
    ]
    assert not flojos, 'colores por debajo del mínimo: ' + '; '.join(flojos)


def test_radar_meta_gana_la_guerra_de_especificidad_contra_gestion_row_sub():
    """`body[data-gestion-screen] .gestion-row-sub` (arriba en este mismo
    archivo) ya trae un color propio con especificidad (0,2,1) — un
    `.radar-meta { color: ... }` suelto, con (0,1,0), perdería contra ella
    sin importar el orden en el archivo. El selector tiene que igualar (o
    superar) esa especificidad para que el color del radar gane siempre."""
    css = _css_radar()
    assert 'body[data-gestion-screen] .gestion-row-sub.radar-meta' in css, (
        'el color de .radar-meta necesita la misma especificidad que '
        '.gestion-row-sub para no depender del orden de las reglas'
    )


def test_las_areas_tactiles_del_radar_son_de_44px():
    css = _css_radar()
    assert re.search(r'\.radar-titulo-plegable\s*\{[^}]*min-height:\s*44px', css)
    assert re.search(r'\.radar-action-main\s*\{[^}]*min-height:\s*44px', css)


# ── Ráfagas de compra ────────────────────────────────────────────────────────

def test_una_rafaga_de_compras_es_UNA_visita():
    """El falso positivo de Roberto Da Silva, encontrado contra producción.

    Compró quince veces en una semana de octubre de 2025 y después desapareció
    diez meses. Contando FECHAS sueltas, la mediana de sus intervalos daba 3
    días —los de adentro de la ráfaga—, así que a los quince días de silencio
    figuraba como «5,0x su ritmo» y salía SEGUNDO en Atrasados, por encima de
    Arco Iris, que sí había dejado de comprar de verdad.

    Es el mismo error que el de Best Buy un escalón más arriba: si un día con
    varios pedidos es UNA compra, una semana con varios días también.
    """
    rafaga = [date(2025, 10, 6) + timedelta(days=d) for d in (0, 1, 2, 3, 4)]
    fechas = rafaga + [date(2026, 3, 15), date(2026, 8, 14)]

    ritmo, propio = _ritmo_cliente(fechas)

    assert propio is True
    assert ritmo > 100, (
        f'ritmo {ritmo}d: la ráfaga se está contando como cadencia. '
        'Su cadencia real entre visitas es de meses, no de días.'
    )


def test_el_cliente_regular_no_lo_toca_el_colapso():
    """Colapsar ráfagas no debe mover a quien compra con cadencia normal."""
    fechas = [HOY - timedelta(days=7 * i) for i in range(6)]
    assert _ritmo_cliente(fechas) == (7, True)


def test_el_limite_exacto_de_la_rafaga():
    """En el borde: hasta `_RADAR_RAFAGA_DIAS` es la misma visita; uno más, no."""
    base = date(2026, 1, 1)
    juntas = [base, base + timedelta(days=_RADAR_RAFAGA_DIAS),
              base + timedelta(days=20), base + timedelta(days=40)]
    separadas = [base, base + timedelta(days=_RADAR_RAFAGA_DIAS + 1),
                 base + timedelta(days=20), base + timedelta(days=40)]

    # juntas → 3 visitas, intervalos [20, 20]
    assert _ritmo_cliente(juntas) == (20, True)
    # separadas → 4 visitas, intervalos [4, 16, 20] → mediana 16
    assert _ritmo_cliente(separadas) == (16, True)


def test_una_rafaga_sola_no_alcanza_para_tener_ritmo_propio():
    """Quince compras en una semana y nada más: una visita, cero intervalos.

    No hay cadencia que medir, así que corresponde el ritmo del negocio
    marcado como estimado — no un ritmo propio de un día.
    """
    rafaga = [date(2026, 8, 1) + timedelta(days=d) for d in range(5)]
    ritmo, propio = _ritmo_cliente(rafaga)
    assert (ritmo, propio) == (_RADAR_RITMO_NEGOCIO, False)


def test_una_rafaga_LARGA_tampoco_se_lee_como_cadencia():
    """El contraejemplo que encontró la revisión del arreglo de ráfagas.

    La primera versión comparaba cada fecha contra el INICIO de la visita, o
    sea contra una ventana fija de 3 días. Una ráfaga más larga que la ventana
    se partía en visitas falsas separadas por 4 días, y el ritmo volvía a salir
    «4 días propio»: exactamente el fallo que colapsar ráfagas venía a cerrar,
    con una ráfaga más larga que la que se había probado.

    Encadenando contra la fecha anterior, tres semanas seguidas de compras son
    una visita, dure lo que dure la racha.
    """
    rafaga = [date(2025, 1, 1) + timedelta(days=d) for d in range(21)]
    fechas = rafaga + [date(2025, 7, 20), date(2026, 2, 5)]

    ritmo, propio = _ritmo_cliente(fechas)

    assert ritmo > 100, (
        f'ritmo {ritmo}d: una ráfaga de 21 días se está partiendo en visitas '
        'falsas. Comparar contra el inicio de la visita en vez de contra la '
        'fecha anterior reintroduce este bug.'
    )
    assert propio is True


def test_el_que_compra_siempre_seguido_queda_en_estimado_y_no_en_un_numero_falso():
    """De una compra continua no se puede leer una cadencia, y hay que decirlo.

    Un cliente que compra todos los días colapsa entero en una sola visita: no
    hay intervalos entre visitas, así que corresponde el ritmo del negocio
    marcado como estimado. La versión anclada al inicio le devolvía «4 días
    propio» —un número inventado con cara de dato— porque partía la racha en
    ventanas fijas.
    """
    diario = [date(2026, 1, 1) + timedelta(days=d) for d in range(30)]
    ritmo, propio = _ritmo_cliente(diario)
    assert (ritmo, propio) == (_RADAR_RITMO_NEGOCIO, False)
