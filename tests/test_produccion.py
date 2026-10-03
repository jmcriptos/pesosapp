"""Producción propia: lotes, mermas y rendimiento SIN verificación de
disponibilidad de insumos, y sin compartir nada con maquila."""
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
        from app import Rol, Territorio, Vendedor, Producto
        from produccion.models import Insumo, Formula, FormulaInsumo
        ra = Rol(nombre='super_admin', descripcion='Admin')
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, rv, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                         rol_id=ra.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                        rol_id=rv.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        chorizo = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        jamon = Producto(nombre='Jamón', se_pesa=True, tax_rate=10)
        carne = Insumo(nombre='Carne de cerdo', unidad='kg')
        sal = Insumo(nombre='Sal', unidad='kg')
        tripa = Insumo(nombre='Tripa', unidad='ud')
        _db.session.add_all([admin, vend, chorizo, jamon, carne, sal, tripa])
        _db.session.flush()
        formula = Formula(producto_id=chorizo.id, nombre='Chorizo casa',
                          base_kg=Decimal('100'), activa=True)
        _db.session.add(formula)
        _db.session.flush()
        _db.session.add_all([
            FormulaInsumo(formula_id=formula.id, insumo_id=carne.id, cantidad=Decimal('80')),
            FormulaInsumo(formula_id=formula.id, insumo_id=sal.id, cantidad=Decimal('2')),
            FormulaInsumo(formula_id=formula.id, insumo_id=tripa.id, cantidad=Decimal('50')),
        ])
        _db.session.commit()
        IDS.update(admin=admin.id, vend=vend.id, chorizo=chorizo.id, jamon=jamon.id,
                   carne=carne.id, sal=sal.id, tripa=tripa.id, formula=formula.id)
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def _lote(**kw):
    from produccion import servicios
    base = dict(producto_id=IDS['chorizo'], lote='L-1001',
                fecha_produccion=date(2026, 10, 1), vendedor_id=IDS['admin'],
                peso_adicional=Decimal('85'),
                consumos={IDS['carne']: Decimal('100'), IDS['tripa']: Decimal('60')},
                mermas=[{'tipo': 'coccion', 'cantidad': Decimal('10'), 'motivo': ''}])
    base.update(kw)
    return servicios.crear_lote(**base)


# ---------------------------------------------------------------- andamiaje

def test_las_tablas_existen(app):
    with app.app_context():
        nombres = set(_db.inspect(_db.engine).get_table_names())
    assert {'lote_produccion', 'lote_consumo', 'lote_merma', 'produccion_insumo',
            'produccion_formula', 'produccion_formula_insumo'} <= nombres


def test_no_depende_de_maquila(app):
    """Separación total: ningún modelo de maquila entra en el módulo y las
    FK de los lotes apuntan solo a tablas propias (y producto/vendedor)."""
    import produccion.models, produccion.servicios, produccion.reportes, produccion.routes
    for mod in (produccion.models, produccion.servicios, produccion.reportes, produccion.routes):
        modulos = {(getattr(v, '__module__', '') or '').split('.')[0] for v in vars(mod).values()}
        assert 'maquila' not in modulos, mod.__name__
    with app.app_context():
        from produccion.models import LoteConsumo, LoteProduccion
        tablas = {fk.column.table.name for t in (LoteProduccion.__table__, LoteConsumo.__table__)
                  for fk in t.foreign_keys}
        assert tablas <= {'producto', 'vendedor', 'produccion_formula',
                          'produccion_insumo', 'lote_produccion'}


def test_las_tablas_se_crean_solas_si_faltan(app):
    """Heroku sin el script SQL: /produccion daba 500 por «no such table».
    Al arrancar, el módulo crea lo que falte, sin tocar lo que ya existe."""
    from produccion import asegurar_tablas
    from produccion.models import (LoteProduccion, LoteConsumo, LoteMerma, Insumo,
                                   Formula, FormulaInsumo)
    with app.app_context():
        for t in (LoteMerma.__table__, LoteConsumo.__table__, LoteProduccion.__table__,
                  FormulaInsumo.__table__, Formula.__table__, Insumo.__table__):
            t.drop(_db.engine)
        assert 'lote_produccion' not in set(_db.inspect(_db.engine).get_table_names())
        asegurar_tablas(app)
        asegurar_tablas(app)   # segunda vez: no revienta por «ya existe»
        assert {'lote_produccion', 'lote_consumo', 'lote_merma'} <= set(
            _db.inspect(_db.engine).get_table_names())
    c = _login(app, 'admin')
    assert c.get('/produccion').status_code == 200
    assert c.get('/produccion/lotes').status_code == 200


def test_las_tablas_de_la_primera_version_se_recrean(app):
    """La primera versión ató los lotes a maquila: `lote_consumo` tenía
    `ingrediente_id` y no `insumo_id`. Al arrancar se reconoce y se recrea."""
    from sqlalchemy import text
    from produccion import asegurar_tablas
    from produccion.models import LoteProduccion, LoteConsumo, LoteMerma
    with app.app_context():
        for t in (LoteMerma.__table__, LoteConsumo.__table__, LoteProduccion.__table__):
            t.drop(_db.engine)
        with _db.engine.begin() as conn:
            conn.execute(text('CREATE TABLE lote_produccion (id INTEGER PRIMARY KEY, receta_id INTEGER)'))
            conn.execute(text('CREATE TABLE lote_consumo (id INTEGER PRIMARY KEY, lote_id INTEGER, ingrediente_id INTEGER)'))
            conn.execute(text('CREATE TABLE lote_merma (id INTEGER PRIMARY KEY, lote_id INTEGER)'))
        asegurar_tablas(app)
        columnas = {c['name'] for c in _db.inspect(_db.engine).get_columns('lote_consumo')}
        assert 'insumo_id' in columnas and 'ingrediente_id' not in columnas
        assert 'formula_id' in {c['name'] for c in _db.inspect(_db.engine).get_columns('lote_produccion')}
        lote = _lote()
        assert lote.codigo == 'PR-2026-0001'


def test_el_recurso_produccion_esta_en_los_permisos_configurables(app):
    from app import PERMISOS_RECURSOS, _permiso_default
    assert 'produccion' in PERMISOS_RECURSOS
    assert _permiso_default('vendedor', 'produccion', 'crear') is True
    assert _permiso_default('vendedor', 'produccion', 'editar') is False
    assert _permiso_default('supervisor', 'produccion', 'editar') is True


# ----------------------------------------------------------------- servicios

def test_registrar_sin_recepciones_ni_saldo_no_bloquea(app):
    """La regla que da nombre al módulo: no hay ledger ni recepciones, y el
    consumo se anota tal cual."""
    with app.app_context():
        lote = _lote()
        assert lote.estado == 'abierta'
        assert lote.codigo == 'PR-2026-0001'
        assert {c.insumo_id: c.cantidad_real for c in lote.consumos} == {
            IDS['carne']: Decimal('100.000'), IDS['tripa']: Decimal('60.000')}


def test_el_codigo_es_correlativo_por_anio(app):
    with app.app_context():
        a = _lote(lote='A')
        b = _lote(lote='B')
        c = _lote(lote='C', fecha_produccion=date(2027, 1, 5))
        assert (a.codigo, b.codigo, c.codigo) == ('PR-2026-0001', 'PR-2026-0002', 'PR-2027-0001')


def test_balance_merma_identificada_y_sin_identificar(app):
    with app.app_context():
        from produccion import servicios
        b = servicios.balance(_lote())
        assert b['consumido'] == Decimal('100')          # la tripa (ud) no suma kilos
        assert b['otras_unidades'] == ['ud']
        assert b['producido'] == Decimal('85.000')
        assert b['merma_total'] == Decimal('15.000')
        assert b['merma_identificada'] == Decimal('10.000')
        assert b['merma_sin_identificar'] == Decimal('5.000')
        assert b['merma_pct'] == Decimal('15.0')
        assert b['rendimiento_pct'] == Decimal('85.0')
        assert b['merma_alta'] is True
        assert b['mermas_por_tipo'][0]['etiqueta'] == 'Cocción y ahumado'


def test_el_teorico_sale_de_la_formula_y_queda_como_snapshot(app):
    with app.app_context():
        from produccion import servicios
        from produccion.models import FormulaInsumo
        lote = _lote(peso_adicional=Decimal('50'))
        assert lote.formula_id == IDS['formula']
        teoricos = {c.insumo_id: c.cantidad_teorica for c in lote.consumos}
        assert teoricos[IDS['carne']] == Decimal('40.000')
        assert teoricos[IDS['tripa']] == Decimal('25.000')
        # Abierto, el teórico sigue al peso producido (que cambia con cada
        # caja pesada): cambiar la fórmula se ve en vivo.
        FormulaInsumo.query.filter_by(formula_id=IDS['formula'],
                                      insumo_id=IDS['carne']).update({'cantidad': 90})
        _db.session.commit()
        b = servicios.balance(_db.session.get(type(lote), lote.id))
        carne = next(v for v in b['varianzas'] if v['insumo_id'] == IDS['carne'])
        assert carne['teorica'] == Decimal('45.000')
        # Cerrado, queda la foto: cambiar la fórmula después no reescribe el lote.
        servicios.cerrar_lote(lote, IDS['admin'])
        FormulaInsumo.query.filter_by(formula_id=IDS['formula'],
                                      insumo_id=IDS['carne']).update({'cantidad': 80})
        _db.session.commit()
        b = servicios.balance(_db.session.get(type(lote), lote.id))
        carne = next(v for v in b['varianzas'] if v['insumo_id'] == IDS['carne'])
        assert carne['teorica'] == Decimal('45.000')
        assert carne['diferencia'] == Decimal('55.000')
        assert carne['pct'] == Decimal('122.2')
        return
        assert carne['teorica'] == Decimal('40.000')
        assert carne['diferencia'] == Decimal('60.000')
        assert carne['pct'] == Decimal('150.0')


def test_producto_sin_formula_registra_solo_el_real(app):
    with app.app_context():
        from produccion import servicios
        lote = _lote(producto_id=IDS['jamon'], consumos={IDS['carne']: Decimal('20')},
                     peso_adicional=Decimal('22'), mermas=[])
        assert lote.formula_id is None
        b = servicios.balance(lote)
        assert b['varianzas'][0]['teorica'] == Decimal('0')
        assert b['varianzas'][0]['pct'] is None
        assert b['merma_total'] == Decimal('-2.000')   # pesa más que lo que entró: se muestra
        assert b['rendimiento_pct'] == Decimal('110.0')


def test_lote_repetido_del_mismo_producto_se_rechaza_salvo_anulado(app):
    with app.app_context():
        from produccion import servicios
        primero = _lote()
        with pytest.raises(servicios.LoteInvalido):
            _lote()
        _lote(producto_id=IDS['jamon'], mermas=[])      # otro producto, mismo número: vale
        servicios.anular_lote(primero, IDS['admin'], 'tecleado dos veces')
        assert _lote().codigo == 'PR-2026-0003'


def test_validaciones_de_alta(app):
    with app.app_context():
        from produccion import servicios
        with pytest.raises(servicios.LoteInvalido):
            _lote(fecha_produccion=None)
        with pytest.raises(servicios.LoteInvalido):
            _lote(producto_id=9999)
        with pytest.raises(servicios.LoteInvalido):
            _lote(consumos={IDS['carne']: Decimal('-1')})
        with pytest.raises(servicios.LoteInvalido):
            _lote(mermas=[{'tipo': 'coccion', 'cantidad': Decimal('0'), 'motivo': 'x'}])
        with pytest.raises(servicios.LoteInvalido):
            _lote(mermas=[{'tipo': 'otro', 'cantidad': Decimal('1'), 'motivo': ''}])
        with pytest.raises(servicios.LoteInvalido):
            _lote(mermas=[{'tipo': 'inventado', 'cantidad': Decimal('1'), 'motivo': ''}])
        # Nada de lo rechazado quedó a medias.
        from produccion.models import LoteProduccion
        assert LoteProduccion.query.count() == 0


def test_consumo_cero_y_merma_vacia_se_omiten(app):
    with app.app_context():
        lote = _lote(consumos={IDS['carne']: Decimal('100'), IDS['sal']: Decimal('0')},
                     mermas=[{'tipo': 'coccion', 'cantidad': None, 'motivo': ''}])
        assert [c.insumo_id for c in lote.consumos] == [IDS['carne']]
        assert lote.mermas == []


def test_cerrar_exige_peso_y_consumo_en_kg(app):
    with app.app_context():
        from produccion import servicios
        sin_peso = _lote(lote='A', peso_adicional=None)
        with pytest.raises(servicios.LoteInvalido):
            servicios.cerrar_lote(sin_peso, IDS['admin'])
        solo_tripa = _lote(lote='B', consumos={IDS['tripa']: Decimal('10')}, mermas=[])
        with pytest.raises(servicios.LoteInvalido):
            servicios.cerrar_lote(solo_tripa, IDS['admin'])
        ok = _lote(lote='C')
        servicios.cerrar_lote(ok, IDS['admin'])
        assert ok.estado == 'cerrada'
        assert ok.cerrado_por == IDS['admin']
        assert ok.cerrado_en is not None
        with pytest.raises(servicios.LoteInvalido):
            servicios.cerrar_lote(ok, IDS['admin'])


def test_editar_solo_abierto_y_reabrir_con_motivo(app):
    with app.app_context():
        from produccion import servicios
        lote = _lote()
        servicios.cerrar_lote(lote, IDS['admin'])
        cab = dict(producto_id=IDS['chorizo'], lote='L-1001', fecha_produccion=date(2026, 10, 1),
                   peso_adicional=Decimal('90'))
        with pytest.raises(servicios.LoteNoEditable):
            servicios.editar_lote(lote, cabecera=cab, consumos={IDS['carne']: Decimal('100')})
        with pytest.raises(servicios.MotivoRequerido):
            servicios.reabrir_lote(lote, IDS['admin'], '  ')
        servicios.reabrir_lote(lote, IDS['admin'], 'se pesó mal la salida')
        assert lote.estado == 'abierta'
        assert lote.cerrado_en is None
        assert 'Reabierto: se pesó mal la salida' in lote.notas
        servicios.editar_lote(lote, cabecera=cab,
                              consumos={IDS['carne']: Decimal('100'), IDS['sal']: Decimal('2')},
                              mermas=[{'tipo': 'recorte', 'cantidad': Decimal('4'), 'motivo': ''}])
        assert lote.peso_producido == Decimal('90.000')
        assert {c.insumo_id for c in lote.consumos} == {IDS['carne'], IDS['sal']}
        # El teórico se recalcula con el peso nuevo.
        assert {c.insumo_id: c.cantidad_teorica for c in lote.consumos}[IDS['sal']] == Decimal('1.800')
        assert [m.tipo for m in lote.mermas] == ['recorte']
        b = servicios.balance(lote)
        assert b['consumido'] == Decimal('102')
        assert b['merma_sin_identificar'] == Decimal('8.000')


def test_editar_cambia_de_producto_y_resuelve_la_formula(app):
    with app.app_context():
        from produccion import servicios
        lote = _lote()
        cab = dict(producto_id=IDS['jamon'], lote='L-1001', fecha_produccion=date(2026, 10, 1),
                   peso_adicional=Decimal('85'))
        servicios.editar_lote(lote, cabecera=cab, consumos={IDS['carne']: Decimal('100')})
        assert lote.producto_id == IDS['jamon']
        assert lote.formula_id is None
        assert lote.consumos[0].cantidad_teorica == Decimal('0')


def test_anular_exige_motivo_y_saca_de_los_reportes(app):
    with app.app_context():
        from produccion import servicios, reportes
        lote = _lote()
        servicios.cerrar_lote(lote, IDS['admin'])
        assert len(reportes.rendimiento()[0]) == 1
        with pytest.raises(servicios.MotivoRequerido):
            servicios.anular_lote(lote, IDS['admin'], '')
        servicios.anular_lote(lote, IDS['admin'], 'lote de prueba')
        assert lote.estado == 'anulada'
        assert lote.motivo_anulacion == 'lote de prueba'
        assert reportes.rendimiento()[0] == []
        with pytest.raises(servicios.LoteInvalido):
            servicios.anular_lote(lote, IDS['admin'], 'otra vez')


# ------------------------------------------------------------------ reportes

def _cerrados():
    from produccion import servicios
    a = _lote(lote='A', peso_adicional=Decimal('85'),
              consumos={IDS['carne']: Decimal('100')},
              mermas=[{'tipo': 'coccion', 'cantidad': Decimal('10'), 'motivo': ''}])
    b = _lote(lote='B', fecha_produccion=date(2026, 10, 5), peso_adicional=Decimal('190'),
              consumos={IDS['carne']: Decimal('200')},
              mermas=[{'tipo': 'coccion', 'cantidad': Decimal('6'), 'motivo': ''},
                      {'tipo': 'recorte', 'cantidad': Decimal('2'), 'motivo': ''}])
    j = _lote(lote='J', producto_id=IDS['jamon'], fecha_produccion=date(2026, 9, 20),
              peso_adicional=Decimal('45'), consumos={IDS['carne']: Decimal('50')}, mermas=[])
    abierto = _lote(lote='X', peso_adicional=Decimal('1'), consumos={IDS['carne']: Decimal('99')})
    for l in (a, b, j):
        servicios.cerrar_lote(l, IDS['admin'])
    return a, b, j, abierto


def test_rendimiento_pondera_por_kilos_y_filtra(app):
    with app.app_context():
        from produccion import reportes
        _cerrados()
        filas, resumen = reportes.rendimiento()
        assert [f['lote'] for f in filas] == ['B', 'A', 'J']       # cerrados, más reciente primero
        chorizo = next(r for r in resumen if r['producto'] == 'Chorizo')
        assert chorizo['lotes'] == 2
        assert chorizo['consumido'] == Decimal('300')
        assert chorizo['producido'] == Decimal('275.000')
        assert chorizo['rendimiento_pct'] == Decimal('91.7')        # 275/300, no (85+95)/2
        assert chorizo['merma_pct'] == Decimal('8.3')
        assert chorizo['merma_identificada'] == Decimal('18.000')
        assert chorizo['merma_sin_identificar'] == Decimal('7.000')
        assert (chorizo['rend_min'], chorizo['rend_max']) == (Decimal('85.0'), Decimal('95.0'))
        assert chorizo['lotes_merma_alta'] == 1

        filas, resumen = reportes.rendimiento(producto_id=IDS['jamon'])
        assert [f['lote'] for f in filas] == ['J']
        filas, _ = reportes.rendimiento(desde=date(2026, 10, 2))
        assert [f['lote'] for f in filas] == ['B']
        filas, _ = reportes.rendimiento(hasta=date(2026, 10, 2))
        assert [f['lote'] for f in filas] == ['A', 'J']


def test_mermas_por_causa_y_por_producto(app):
    with app.app_context():
        from produccion import reportes
        _cerrados()
        d = reportes.mermas()
        assert d['lotes'] == 3
        assert d['consumido'] == Decimal('350')
        assert d['merma_total'] == Decimal('30.000')
        assert d['identificada'] == Decimal('18.000')
        assert d['sin_identificar'] == Decimal('12.000')
        assert d['pct_identificada'] == Decimal('60.0')
        por_tipo = {t['tipo']: t for t in d['por_tipo']}
        assert set(por_tipo) == {'coccion', 'recorte', 'descarte', 'proceso', 'muestras', 'otro'}
        assert por_tipo['coccion']['cantidad'] == Decimal('16.000')
        assert por_tipo['coccion']['lotes'] == 2
        assert por_tipo['coccion']['pct_merma'] == Decimal('53.3')
        assert por_tipo['descarte']['cantidad'] == Decimal('0')
        assert d['por_tipo'][0]['tipo'] == 'coccion'
        jamon = next(p for p in d['por_producto'] if p['producto'] == 'Jamón')
        assert jamon['merma_total'] == Decimal('5.000')
        assert jamon['sin_identificar'] == Decimal('5.000')
        assert jamon['tipos'] == []


def test_resumen_del_periodo(app):
    with app.app_context():
        from produccion import reportes
        _cerrados()
        r = reportes.resumen_periodo(date(2026, 10, 1), date(2026, 10, 31))
        assert r['lotes'] == 2
        assert r['producido'] == Decimal('275.000')
        assert r['rendimiento_pct'] == Decimal('91.7')
        assert r['lotes_merma_alta'] == 1


# --------------------------------------------------------------------- rutas

def test_sin_sesion_redirige_al_login(app):
    r = app.test_client().get('/produccion', follow_redirects=False)
    assert r.status_code == 302


def test_admin_ve_el_resumen(app):
    c = _login(app, 'admin')
    assert c.get('/produccion').status_code == 200


def test_vendedor_lee_y_crea_pero_no_cierra(app):
    """Un solo cliente por test: la fixture deja un app context activo y los
    requests lo reusan, así que Flask-Login cachea en `g` el primer usuario
    que carga. Dos clientes en el mismo test verían al mismo usuario."""
    v = _login(app, 'vend')
    assert v.get('/produccion').status_code == 200              # leer por defecto
    assert v.get('/produccion/lotes/nuevo').status_code == 200  # crear por defecto
    with app.app_context():
        lote_id = _lote().id
    r = v.post(f'/produccion/lotes/{lote_id}/cerrar', follow_redirects=False)
    assert r.status_code == 302 and r.headers['Location'].endswith('/')  # editar: no
    r = v.get(f'/produccion/lotes/{lote_id}/editar', follow_redirects=False)
    assert r.status_code == 302 and r.headers['Location'].endswith('/')
    r = v.post(f'/produccion/lotes/{lote_id}/anular', data={'motivo': 'x'}, follow_redirects=False)
    assert r.status_code == 302 and r.headers['Location'].endswith('/')
    with app.app_context():
        from produccion.models import LoteProduccion
        assert _db.session.get(LoteProduccion, lote_id).estado == 'abierta'
    # Sin permiso de editar, «Guardar y cerrar» guarda y avisa; no cierra.
    r = v.post('/produccion/lotes/nuevo', data={
        'producto_id': str(IDS['chorizo']), 'lote': 'V-1',
        'fecha_produccion': '2026-10-02', 'peso_adicional': '80',
        'consumo_insumo_id': [str(IDS['carne'])], 'consumo_real': ['100'],
        'accion': 'cerrar',
    }, follow_redirects=True)
    assert 'requiere permiso de editar' in r.get_data(as_text=True)
    with app.app_context():
        from produccion.models import LoteProduccion
        assert LoteProduccion.query.filter_by(lote='V-1').one().estado == 'abierta'


def test_alta_por_formulario_con_consumos_y_mermas(app):
    c = _login(app, 'admin')
    r = c.post('/produccion/lotes/nuevo', data={
        'producto_id': str(IDS['chorizo']), 'lote': 'W-42',
        'fecha_produccion': '2026-10-02', 'fecha_vencimiento': '',
        'peso_adicional': '84,5', 'unidades_producidas': '120', 'cajas_producidas': '',
        'consumo_insumo_id': [str(IDS['carne']), str(IDS['sal']), str(IDS['tripa'])],
        'consumo_real': ['100', '', '60'],
        'merma_tipo': ['coccion', 'otro'],
        'merma_cantidad': ['9', '1,5'],
        'merma_motivo': ['', 'se cayó una bandeja'],
        'accion': 'guardar',
    }, follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        from produccion.models import LoteProduccion
        from produccion import servicios
        lote = LoteProduccion.query.filter_by(lote='W-42').one()
        assert lote.peso_adicional == Decimal('84.500') and lote.peso_producido == Decimal('84.500')
        assert lote.unidades_producidas == 120 and lote.cajas_producidas is None
        assert {c.insumo_id for c in lote.consumos} == {IDS['carne'], IDS['tripa']}
        assert [(m.tipo, m.cantidad, m.motivo) for m in lote.mermas] == [
            ('coccion', Decimal('9.000'), None), ('otro', Decimal('1.500'), 'se cayó una bandeja')]
        assert servicios.balance(lote)['merma_sin_identificar'] == Decimal('5.000')
        assert r.headers['Location'].endswith(f'/produccion/lotes/{lote.id}')
    assert c.get(r.headers['Location']).status_code == 200


def test_alta_rechazada_conserva_lo_tecleado(app):
    c = _login(app, 'admin')
    r = c.post('/produccion/lotes/nuevo', data={
        'producto_id': str(IDS['chorizo']), 'lote': 'R-1',
        'fecha_produccion': '2026-10-02', 'peso_adicional': '84',
        'consumo_insumo_id': [str(IDS['carne'])], 'consumo_real': ['77'],
        'merma_tipo': ['otro'], 'merma_cantidad': ['3'], 'merma_motivo': [''],   # «Otra» sin detalle
    })
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'necesita decir qué fue' in html
    assert 'value="77"' in html
    assert 'value="84"' in html
    assert 'value="R-1"' in html
    with app.app_context():
        from produccion.models import LoteProduccion
        assert LoteProduccion.query.count() == 0


def test_guardar_y_cerrar_en_un_paso(app):
    c = _login(app, 'admin')
    r = c.post('/produccion/lotes/nuevo', data={
        'producto_id': str(IDS['chorizo']), 'lote': 'Z-1',
        'fecha_produccion': '2026-10-02', 'peso_adicional': '80',
        'consumo_insumo_id': [str(IDS['carne'])], 'consumo_real': ['100'],
        'accion': 'cerrar',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert 'Rendimiento 80.0 %' in r.get_data(as_text=True)
    with app.app_context():
        from produccion.models import LoteProduccion
        assert LoteProduccion.query.filter_by(lote='Z-1').one().estado == 'cerrada'


def test_guardar_y_cerrar_sin_peso_queda_abierto(app):
    c = _login(app, 'admin')
    r = c.post('/produccion/lotes/nuevo', data={
        'producto_id': str(IDS['chorizo']), 'lote': 'Z-2',
        'fecha_produccion': '2026-10-02', 'peso_adicional': '',
        'consumo_insumo_id': [str(IDS['carne'])], 'consumo_real': ['100'],
        'accion': 'cerrar',
    }, follow_redirects=True)
    assert 'Quedó guardado pero abierto' in r.get_data(as_text=True)
    with app.app_context():
        from produccion.models import LoteProduccion
        assert LoteProduccion.query.filter_by(lote='Z-2').one().estado == 'abierta'


def test_editar_cerrar_reabrir_y_anular_por_rutas(app):
    c = _login(app, 'admin')
    with app.app_context():
        lote_id = _lote().id
    assert c.get(f'/produccion/lotes/{lote_id}/editar').status_code == 200
    r = c.post(f'/produccion/lotes/{lote_id}/editar', data={
        'producto_id': str(IDS['chorizo']), 'lote': 'L-1001',
        'fecha_produccion': '2026-10-01', 'peso_adicional': '88',
        'consumo_insumo_id': [str(IDS['carne'])], 'consumo_real': ['100'],
    }, follow_redirects=False)
    assert r.status_code == 302
    assert c.post(f'/produccion/lotes/{lote_id}/cerrar', follow_redirects=False).status_code == 302
    with app.app_context():
        from produccion.models import LoteProduccion
        lote = _db.session.get(LoteProduccion, lote_id)
        assert lote.estado == 'cerrada' and lote.peso_producido == Decimal('88.000')
    # Cerrado: editar redirige al detalle con aviso.
    r = c.get(f'/produccion/lotes/{lote_id}/editar', follow_redirects=True)
    assert 'reabrilo' in r.get_data(as_text=True)
    assert c.get(f'/produccion/lotes/{lote_id}').status_code == 200
    r = c.post(f'/produccion/lotes/{lote_id}/reabrir', data={'motivo': ''}, follow_redirects=True)
    assert 'exige un motivo' in r.get_data(as_text=True)
    c.post(f'/produccion/lotes/{lote_id}/reabrir', data={'motivo': 'faltó una merma'})
    c.post(f'/produccion/lotes/{lote_id}/anular', data={'motivo': 'prueba'})
    with app.app_context():
        from produccion.models import LoteProduccion
        assert _db.session.get(LoteProduccion, lote_id).estado == 'anulada'
    assert c.get(f'/produccion/lotes/{lote_id}').status_code == 200


def test_listado_y_reportes_responden(app):
    c = _login(app, 'admin')
    with app.app_context():
        _cerrados()
    for url in ('/produccion', '/produccion/lotes', '/produccion/lotes?estado=abierta',
                f'/produccion/lotes?producto_id={IDS["chorizo"]}&desde=2026-10-01&hasta=2026-10-31',
                '/produccion/reportes/rendimiento',
                f'/produccion/reportes/rendimiento?producto_id={IDS["chorizo"]}',
                '/produccion/reportes/mermas',
                '/produccion/reportes/mermas?desde=2026-10-01'):
        r = c.get(url)
        assert r.status_code == 200, url
    html = c.get('/produccion/reportes/rendimiento').get_data(as_text=True)
    assert '91.7 %' in html
    html = c.get('/produccion/reportes/mermas').get_data(as_text=True)
    assert 'Cocción y ahumado' in html


def test_export_excel_del_rendimiento(app):
    c = _login(app, 'admin')
    with app.app_context():
        _cerrados()
    r = c.get('/produccion/reportes/rendimiento/export?desde=2026-10-01')
    assert r.status_code == 200
    assert r.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert r.data[:2] == b'PK'
    import io
    import openpyxl
    libro = openpyxl.load_workbook(io.BytesIO(r.data))
    assert libro.sheetnames == ['Lotes', 'Por producto', 'Consumo por insumo']
    filas = list(libro['Lotes'].iter_rows(values_only=True))
    assert filas[0][0] == 'Código'
    assert {f[1] for f in filas[1:]} == {'A', 'B'}
    resumen = list(libro['Por producto'].iter_rows(values_only=True))
    assert resumen[1][0] == 'Chorizo' and abs(resumen[1][4] - 91.7) < 0.01


def test_lote_inexistente_da_404(app):
    c = _login(app, 'admin')
    assert c.get('/produccion/lotes/9999').status_code == 404


def test_el_menu_muestra_produccion_a_quien_puede_leer(app):
    c = _login(app, 'vend')
    html = c.get('/produccion').get_data(as_text=True)
    assert 'href="/produccion"' in html


# ------------------------------------------------------- catálogo propio

def test_insumos_y_formulas_por_servicio(app):
    with app.app_context():
        from produccion import servicios
        from produccion.models import Formula
        hielo = servicios.crear_insumo(nombre='  Hielo ', unidad='kg')
        assert hielo.nombre == 'Hielo' and hielo.activo
        with pytest.raises(servicios.InsumoInvalido):
            servicios.crear_insumo(nombre='hielo')          # repetido, sin distinguir mayúsculas
        with pytest.raises(servicios.InsumoInvalido):
            servicios.crear_insumo(nombre='Agua', unidad='litros')
        tripa_m = servicios.crear_insumo(nombre='Tripa de cerdo 28-30', unidad='m')
        agua = servicios.crear_insumo(nombre='Agua', unidad='l')
        assert (tripa_m.unidad, agua.unidad) == ('m', 'l')
        with pytest.raises(servicios.InsumoInvalido):
            servicios.crear_insumo(nombre='')

        # Una sola fórmula activa por producto.
        with pytest.raises(servicios.FormulaInvalida):
            servicios.guardar_formula(None, producto_id=IDS['chorizo'], nombre='Otra',
                                      base_kg=100, activa=True, items={IDS['carne']: 50})
        inactiva = servicios.guardar_formula(None, producto_id=IDS['chorizo'], nombre='Prueba',
                                             base_kg=50, activa=False,
                                             items={IDS['carne']: 40, hielo.id: 0})
        assert [i.insumo_id for i in inactiva.insumos] == [IDS['carne']]
        with pytest.raises(servicios.FormulaInvalida):
            servicios.guardar_formula(None, producto_id=IDS['jamon'], nombre='Vacía',
                                      base_kg=100, activa=True, items={})
        with pytest.raises(servicios.FormulaInvalida):
            servicios.guardar_formula(None, producto_id=IDS['jamon'], nombre='Base 0',
                                      base_kg=0, activa=True, items={IDS['carne']: 1})
        jamon = servicios.guardar_formula(None, producto_id=IDS['jamon'], nombre='Jamón',
                                          base_kg=100, activa=True,
                                          items={IDS['carne']: 95, IDS['sal']: 2.5})
        assert servicios.formula_para(IDS['jamon']).id == jamon.id
        # Editar reemplaza los insumos.
        servicios.guardar_formula(jamon, producto_id=IDS['jamon'], nombre='Jamón v2',
                                  base_kg=100, activa=True, items={IDS['carne']: 90})
        assert [(i.insumo_id, i.cantidad) for i in jamon.insumos] == [(IDS['carne'], Decimal('90.000'))]
        assert Formula.query.count() == 3
        lote = _lote(producto_id=IDS['jamon'], consumos={IDS['carne']: 45}, peso_adicional=50, mermas=[])
        assert lote.formula_id == jamon.id
        assert lote.consumos[0].cantidad_teorica == Decimal('45.000')


def test_catalogo_por_rutas(app):
    c = _login(app, 'admin')
    assert c.get('/produccion/insumos').status_code == 200
    r = c.post('/produccion/insumos', data={'nombre': 'Grasa de cerdo', 'unidad': 'kg', 'notas': ''},
               follow_redirects=True)
    assert 'Grasa de cerdo' in r.get_data(as_text=True)
    with app.app_context():
        from produccion.models import Insumo
        grasa_id = Insumo.query.filter_by(nombre='Grasa de cerdo').one().id
    c.post(f'/produccion/insumos/{grasa_id}/toggle')
    with app.app_context():
        from produccion.models import Insumo
        assert _db.session.get(Insumo, grasa_id).activo is False

    assert c.get('/produccion/formulas').status_code == 200
    assert c.get('/produccion/formulas/nueva').status_code == 200
    # Insumo repetido: se rechaza y se conserva lo tecleado.
    r = c.post('/produccion/formulas/nueva', data={
        'producto_id': str(IDS['jamon']), 'nombre': 'Jamón', 'base_kg': '100', 'activa': '1',
        'item_insumo_id': [str(IDS['carne']), str(IDS['carne'])], 'item_cantidad': ['90', '5'],
    })
    assert r.status_code == 200 and 'repetido' in r.get_data(as_text=True)
    r = c.post('/produccion/formulas/nueva', data={
        'producto_id': str(IDS['jamon']), 'nombre': 'Jamón', 'base_kg': '100', 'activa': '1',
        'item_insumo_id': [str(IDS['carne']), str(IDS['sal'])], 'item_cantidad': ['90', '2,5'],
    }, follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        from produccion.models import Formula
        f = Formula.query.filter_by(producto_id=IDS['jamon']).one()
        assert {i.insumo_id: i.cantidad for i in f.insumos} == {
            IDS['carne']: Decimal('90.000'), IDS['sal']: Decimal('2.500')}
        f_id = f.id
    assert c.get(f'/produccion/formulas/{f_id}').status_code == 200
    assert c.get('/produccion/formulas/9999').status_code == 404
    # El formulario de lote ya lleva la fórmula nueva del jamón.
    html = c.get('/produccion/lotes/nuevo').get_data(as_text=True)
    assert 'data-formulas=' in html and 'Jam' in html


def test_vendedor_ve_el_catalogo_pero_no_lo_edita(app):
    v = _login(app, 'vend')
    assert v.get('/produccion/insumos').status_code == 200
    assert v.get('/produccion/formulas').status_code == 200
    r = v.post('/produccion/insumos', data={'nombre': 'Pimentón', 'unidad': 'kg'}, follow_redirects=True)
    assert 'requiere permiso de editar' in r.get_data(as_text=True)
    r = v.get('/produccion/formulas/nueva', follow_redirects=False)
    assert r.status_code == 302 and r.headers['Location'].endswith('/')
    with app.app_context():
        from produccion.models import Insumo
        assert Insumo.query.filter_by(nombre='Pimentón').first() is None


def test_la_navegacion_de_produccion_no_enlaza_a_maquila(app):
    c = _login(app, 'admin')
    html = c.get('/produccion').get_data(as_text=True)
    inicio = html.index('Secciones de producción')
    nav = html[inicio:html.index('</nav>', inicio)]
    assert '/maquila' not in nav
    assert '/produccion/formulas' in nav and '/produccion/insumos' in nav


def test_carga_masiva_de_insumos(app):
    with app.app_context():
        from produccion import servicios
        from produccion.models import Insumo
        creados, omitidos = servicios.cargar_insumos(
            "Recortes de pollo (Kippetrimmings)\n"
            "- Sal fina, kg\n"
            "Palatinata;kg\n"
            "\n"
            "Tripa natural de cerdo 28-30, ud\n"
            "carne de cerdo\n"          # ya existe (sin distinguir mayúsculas)
            "Palatinata\n")             # repetida en el mismo texto
        assert [(i.nombre, i.unidad) for i in creados] == [
            ('Recortes de pollo (Kippetrimmings)', 'kg'), ('Sal fina', 'kg'),
            ('Palatinata', 'kg'), ('Tripa natural de cerdo 28-30', 'ud')]
        assert omitidos == ['carne de cerdo', 'Palatinata']
        antes = Insumo.query.count()
        with pytest.raises(servicios.InsumoInvalido) as exc:
            servicios.cargar_insumos("Hielo\nAgua, litros\n")
        assert 'Línea 2' in str(exc.value)
        assert Insumo.query.count() == antes      # nada a medias


def test_carga_masiva_por_ruta(app):
    c = _login(app, 'admin')
    r = c.post('/produccion/insumos/carga', data={'lineas': 'Raprall\nSuper Stim\nTripa natural, ud'},
               follow_redirects=True)
    html = r.get_data(as_text=True)
    assert '3 insumos cargados' in html and 'Super Stim' in html
    r = c.post('/produccion/insumos/carga', data={'lineas': 'Raprall\nAgua, litros'})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Línea 2' in html and 'Agua, litros' in html      # el texto vuelve al textarea


def test_carga_masiva_requiere_editar(app):
    # Un solo cliente por test: ver test_vendedor_lee_y_crea_pero_no_cierra.
    v = _login(app, 'vend')
    r = v.post('/produccion/insumos/carga', data={'lineas': 'Pimentón'}, follow_redirects=False)
    assert r.status_code == 302 and r.headers['Location'].endswith('/')
    with app.app_context():
        from produccion.models import Insumo
        assert Insumo.query.filter_by(nombre='Pimentón').first() is None


def test_metros_y_litros_quedan_fuera_del_balance_de_kilos(app):
    """La tripa por metro y el agua por litro se registran y comparan
    contra su teórico, pero no suman al consumido en kg."""
    with app.app_context():
        from produccion import servicios
        tripa_m = servicios.crear_insumo(nombre='Tripa 28-30', unidad='m')
        agua = servicios.crear_insumo(nombre='Agua', unidad='l')
        lote = _lote(consumos={IDS['carne']: Decimal('100'), tripa_m.id: Decimal('42.5'),
                               agua.id: Decimal('8')}, mermas=[])
        b = servicios.balance(lote)
        assert b['consumido'] == Decimal('100')
        assert b['otras_unidades'] == ['l', 'm']
        assert b['rendimiento_pct'] == Decimal('85.0')
    c = _login(app, 'admin')
    html = c.get('/produccion/lotes/nuevo').get_data(as_text=True)
    assert 'data-unidad="m"' in html and 'placeholder="m"' in html


# ------------------------------------------- cajas pesadas en pedidos

def _pedido_con_detalle(producto_id, cliente_nombre='Cliente'):
    from app import Cliente, Pedido, DetallePedido
    cli = Cliente(nombre=cliente_nombre)
    _db.session.add(cli); _db.session.flush()
    pedido = Pedido(cliente_id=cli.id, estado='pendiente')
    _db.session.add(pedido); _db.session.flush()
    det = DetallePedido(pedido_id=pedido.id, producto_id=producto_id, cajas=3, cajas_pedidas=3,
                        peso=0, precio_unitario=Decimal('10'), subtotal=Decimal('30'),
                        es_linea_pedido=True)
    _db.session.add(det); _db.session.commit()
    return pedido, det


def _caja(detalle, numero, peso, lote='X'):
    from app import CajaPesada
    caja = CajaPesada(detalle_pedido_id=detalle.id, numero=numero, peso=Decimal(str(peso)), lote=lote,
                      fecha_elaboracion=date(2026, 10, 1), fecha_vencimiento=date(2027, 10, 1))
    _db.session.add(caja); _db.session.flush()
    return caja


def test_el_peso_producido_sale_de_las_cajas_pesadas(app):
    with app.app_context():
        from produccion import servicios
        from produccion.models import LoteCaja
        lote = _lote(peso_adicional=None, consumos={IDS['carne']: Decimal('100')}, mermas=[])
        assert lote.peso_producido == Decimal('0')
        with pytest.raises(servicios.LoteInvalido):
            servicios.cerrar_lote(lote, IDS['admin'])      # sin cajas ni adicional
        pedido, det = _pedido_con_detalle(IDS['chorizo'])
        c1 = _caja(det, 1, '10.5'); c2 = _caja(det, 2, '9.5')
        servicios.vincular_caja(lote, c1); servicios.vincular_caja(lote, c2)
        _db.session.commit()
        _db.session.expire_all()
        lote = _db.session.get(type(lote), lote.id)
        assert lote.peso_pesado == Decimal('20.000')
        assert lote.cajas_pesadas_count == 2
        # El teórico sigue al peso mientras está abierto.
        b = servicios.balance(lote)
        assert b['producido'] == Decimal('20.000') and b['rendimiento_pct'] == Decimal('20.0')
        carne = next(v for v in b['varianzas'] if v['insumo_id'] == IDS['carne'])
        assert carne['teorica'] == Decimal('16.000')
        # Peso adicional se suma.
        servicios.editar_lote(lote, cabecera=dict(producto_id=IDS['chorizo'], lote='L-1001',
                                                   fecha_produccion=date(2026, 10, 1),
                                                   peso_adicional=Decimal('5')),
                              consumos={IDS['carne']: Decimal('100')})
        assert lote.peso_producido == Decimal('25.000')
        # «Deshacer» una caja en el pedido: el vínculo cae solo y el lote deja de contarla.
        _db.session.delete(c2); _db.session.commit()
        _db.session.expire_all()
        lote = _db.session.get(type(lote), lote.id)
        assert LoteCaja.query.count() == 1
        assert lote.peso_producido == Decimal('15.500')
        servicios.cerrar_lote(lote, IDS['admin'])
        assert lote.estado == 'cerrada'
        assert lote.consumos[0].cantidad_teorica == Decimal('12.400')   # foto al cerrar: 15.5 × 0.8


def test_vincular_caja_rechaza_otro_producto_lote_cerrado_y_repetida(app):
    with app.app_context():
        from produccion import servicios
        lote = _lote(consumos={IDS['carne']: Decimal('100')}, mermas=[])
        pedido_j, det_j = _pedido_con_detalle(IDS['jamon'], 'J')
        caja_j = _caja(det_j, 1, '8')
        with pytest.raises(servicios.VinculoInvalido):
            servicios.vincular_caja(lote, caja_j)
        pedido, det = _pedido_con_detalle(IDS['chorizo'], 'C')
        caja = _caja(det, 1, '8')
        servicios.vincular_caja(lote, caja); _db.session.commit()
        otro = _lote(lote='OTRO', consumos={IDS['carne']: Decimal('10')}, mermas=[])
        with pytest.raises(servicios.VinculoInvalido):
            servicios.vincular_caja(otro, caja)             # ya atribuida
        _db.session.rollback()
        servicios.cerrar_lote(lote, IDS['admin'])
        with pytest.raises(servicios.VinculoInvalido):
            servicios.vincular_caja(lote, _caja(det, 2, '8'))  # cerrado


def test_lotes_disponibles_solo_abiertos_del_producto(app):
    with app.app_context():
        from produccion import servicios
        a = _lote(lote='A', peso_adicional=Decimal('1'), consumos={IDS['carne']: Decimal('1')}, mermas=[])
        b = _lote(lote='B', fecha_produccion=date(2026, 10, 5), consumos={}, mermas=[])
        j = _lote(lote='J', producto_id=IDS['jamon'], consumos={}, mermas=[])
        servicios.cerrar_lote(a, IDS['admin'])
        disp = servicios.lotes_disponibles([IDS['chorizo'], IDS['jamon'], None])
        assert [l.lote for l in disp[IDS['chorizo']]] == ['B']
        assert [l.lote for l in disp[IDS['jamon']]] == ['J']
        assert servicios.lotes_disponibles([]) == {}


def test_pesar_vincula_la_caja_al_lote_y_toma_su_numero(app):
    c = _login(app, 'admin')
    with app.app_context():
        from produccion import servicios
        lote = _lote(lote='CH-77', fecha_vencimiento=date(2027, 1, 15),
                     consumos={IDS['carne']: Decimal('100')}, mermas=[])
        lote_id = lote.id
        pedido, det = _pedido_con_detalle(IDS['chorizo'])
        pedido_id, det_id = pedido.id, det.id
        cerrado = _lote(lote='CERRADO', peso_adicional=Decimal('1'),
                        consumos={IDS['carne']: Decimal('1')}, mermas=[])
        servicios.cerrar_lote(cerrado, IDS['admin'])
        cerrado_id = cerrado.id
        jamon_id = _lote(lote='J-1', producto_id=IDS['jamon'], consumos={}, mermas=[]).id

    # La pantalla ofrece el lote abierto del producto, no el cerrado.
    html = c.get(f'/pedidos/{pedido_id}/pesar').get_data(as_text=True)
    assert 'id="pesar-lote-prod"' in html
    assert f'<option value="{lote_id}"' in html and 'CH-77' in html
    assert f'<option value="{cerrado_id}"' not in html

    def pesar(peso, **extra):
        data = {'detalle_pedido_id': det_id, 'peso': peso, 'lote': 'tecleado-a-mano',
                'fecha_elaboracion': '2026-10-01', 'fecha_vencimiento': '2027-10-01'}
        data.update(extra)
        return c.post(f'/pedidos/{pedido_id}/pesar/caja', data=data, headers={'HX-Request': 'true'})

    assert pesar('12,5', lote_produccion_id=lote_id).status_code == 200
    assert pesar('7.5', lote_produccion_id=lote_id).status_code == 200
    r = pesar('3', lote_produccion_id=jamon_id)
    assert r.status_code == 422 and 'otro producto' in r.get_data(as_text=True)
    r = pesar('3', lote_produccion_id=cerrado_id)
    assert r.status_code == 422 and 'cerrada' in r.get_data(as_text=True)
    assert pesar('3', lote_produccion_id=9999).status_code == 404
    assert pesar('2').status_code == 200                       # sin lote: como siempre
    with app.app_context():
        from app import CajaPesada
        from produccion.models import LoteProduccion
        lote = _db.session.get(LoteProduccion, lote_id)
        assert lote.peso_pesado == Decimal('20.000') and lote.cajas_pesadas_count == 2
        cajas = CajaPesada.query.filter_by(detalle_pedido_id=det_id).order_by(CajaPesada.numero).all()
        assert [c.lote for c in cajas] == ['CH-77', 'CH-77', 'tecleado-a-mano']
        assert [c.numero for c in cajas] == [1, 2, 3]       # los rechazos no consumieron número
        ultima_id = cajas[1].id
    # Al cambiar de chip, el panel sabe con qué lote se venía pesando.
    html = c.get(f'/pedidos/{pedido_id}/pesar').get_data(as_text=True)
    assert f'data-ultimo-lote-prod=""' in html or 'data-ultimo-lote-prod=' in html
    # El detalle del lote lista el pedido.
    html = c.get(f'/produccion/lotes/{lote_id}').get_data(as_text=True)
    assert f'PED-{pedido_id}' in html and '20 kg' in html


def test_deshacer_caja_en_el_pedido_descuenta_del_lote(app):
    c = _login(app, 'admin')
    with app.app_context():
        from produccion import servicios
        lote_id = _lote(peso_adicional=None, consumos={IDS['carne']: Decimal('100')}, mermas=[]).id
        pedido, det = _pedido_con_detalle(IDS['chorizo'])
        pedido_id, det_id = pedido.id, det.id
    c.post(f'/pedidos/{pedido_id}/pesar/caja', headers={'HX-Request': 'true'},
           data={'detalle_pedido_id': det_id, 'peso': '10', 'lote': 'x', 'fecha_elaboracion': '2026-10-01',
                 'fecha_vencimiento': '2027-10-01', 'lote_produccion_id': lote_id})
    with app.app_context():
        from app import CajaPesada
        caja_id = CajaPesada.query.filter_by(detalle_pedido_id=det_id).one().id
    assert c.delete(f'/cajas/{caja_id}', headers={'HX-Request': 'true'}).status_code == 200
    with app.app_context():
        from produccion.models import LoteProduccion, LoteCaja
        assert LoteCaja.query.count() == 0
        assert _db.session.get(LoteProduccion, lote_id).peso_producido == Decimal('0')


def test_la_columna_peso_producido_se_renombra_al_arrancar(app):
    """Base con la versión anterior (peso_producido tecleado): se renombra a
    peso_adicional conservando el valor, y aparece produccion_lote_caja."""
    from sqlalchemy import text
    from produccion import asegurar_tablas
    from produccion.models import LoteProduccion, LoteConsumo, LoteMerma, LoteCaja
    with app.app_context():
        for t in (LoteCaja.__table__, LoteMerma.__table__, LoteConsumo.__table__, LoteProduccion.__table__):
            t.drop(_db.engine)
        with _db.engine.begin() as conn:
            conn.execute(text('CREATE TABLE lote_produccion (id INTEGER PRIMARY KEY, codigo VARCHAR(20), '
                              'producto_id INTEGER, formula_id INTEGER, lote VARCHAR(50), fecha_produccion DATE, '
                              'fecha_vencimiento DATE, peso_producido NUMERIC(10,3) NOT NULL, unidades_producidas INTEGER, '
                              'cajas_producidas INTEGER, estado VARCHAR(20) NOT NULL, notas TEXT, registrado_por INTEGER NOT NULL, '
                              'registrado_en TIMESTAMP NOT NULL, cerrado_por INTEGER, cerrado_en TIMESTAMP, anulado_por INTEGER, '
                              'anulado_en TIMESTAMP, motivo_anulacion TEXT)'))
            conn.execute(text('CREATE TABLE lote_consumo (id INTEGER PRIMARY KEY, lote_id INTEGER, insumo_id INTEGER, '
                              'cantidad_teorica NUMERIC(10,3), cantidad_real NUMERIC(10,3))'))
            conn.execute(text('CREATE TABLE lote_merma (id INTEGER PRIMARY KEY, lote_id INTEGER, tipo VARCHAR(20), '
                              'cantidad NUMERIC(10,3), motivo TEXT)'))
            conn.execute(text("INSERT INTO lote_produccion (id, codigo, producto_id, lote, fecha_produccion, peso_producido, "
                              "estado, registrado_por, registrado_en) VALUES (1, 'PR-2026-0001', :p, 'V1', '2026-10-01', 42.5, "
                              "'abierta', :v, '2026-10-01 10:00:00')"), {'p': IDS['chorizo'], 'v': IDS['admin']})
        asegurar_tablas(app)
        asegurar_tablas(app)
        columnas = {c['name'] for c in _db.inspect(_db.engine).get_columns('lote_produccion')}
        assert 'peso_adicional' in columnas and 'peso_producido' not in columnas
        assert 'produccion_lote_caja' in set(_db.inspect(_db.engine).get_table_names())
        lote = _db.session.get(LoteProduccion, 1)
        assert lote.peso_adicional == Decimal('42.500') and lote.peso_producido == Decimal('42.500')


# ------------------------------------------ número de lote y vencimiento

def test_numero_de_lote_y_vencimiento_automaticos(app):
    with app.app_context():
        from produccion import servicios
        assert servicios.sugerir_lote(date(2026, 10, 2)) == 'L-0210202601'
        assert servicios.vencimiento_por_defecto(date(2026, 10, 2)) == date(2027, 10, 2)
        assert servicios.vencimiento_por_defecto(date(2028, 2, 29)) == date(2029, 2, 28)
        a = _lote(lote='', fecha_produccion=date(2026, 10, 2), fecha_vencimiento=None)
        assert a.lote == 'L-0210202601' and a.fecha_vencimiento == date(2027, 10, 2)
        b = _lote(lote='   ', fecha_produccion=date(2026, 10, 2))
        assert b.lote == 'L-0210202602'
        # Otro producto el mismo día sigue el mismo correlativo del día.
        j = _lote(lote='', producto_id=IDS['jamon'], fecha_produccion=date(2026, 10, 2), mermas=[])
        assert j.lote == 'L-0210202603'
        # Un anulado no libera su número.
        servicios.anular_lote(b, IDS['admin'], 'prueba')
        assert servicios.sugerir_lote(date(2026, 10, 2)) == 'L-0210202604'
        # Otro día empieza en 01, y un lote tecleado a mano se respeta.
        c = _lote(lote='', fecha_produccion=date(2026, 10, 3))
        assert c.lote == 'L-0310202601'
        m = _lote(lote='MANUAL-7', fecha_produccion=date(2026, 10, 3), fecha_vencimiento=date(2026, 12, 1))
        assert m.lote == 'MANUAL-7' and m.fecha_vencimiento == date(2026, 12, 1)
        # Al editar, el lote en blanco también se completa, sin contarse a sí
        # mismo: vuelve a recibir su propio número.
        servicios.editar_lote(c, cabecera=dict(producto_id=IDS['chorizo'], lote='',
                                               fecha_produccion=date(2026, 10, 3), peso_adicional=1),
                              consumos={IDS['carne']: 1})
        assert c.lote == 'L-0310202601'


def test_el_alta_propone_lote_y_vencimiento_y_el_api_responde(app):
    c = _login(app, 'admin')
    html = c.get('/produccion/lotes/nuevo').get_data(as_text=True)
    import re
    assert re.search(r'value="L-\d{8}01"', html)      # el día local de Curazao
    assert 'data-sugerir-url="/produccion/api/sugerir-lote"' in html
    r = c.get('/produccion/api/sugerir-lote?fecha=2026-10-02')
    assert r.status_code == 200
    assert r.get_json() == {'lote': 'L-0210202601', 'fecha_vencimiento': '2027-10-02'}
    assert c.get('/produccion/api/sugerir-lote?fecha=basura').status_code == 400
    # Por formulario, lote y vencimiento vacíos se completan solos.
    r = c.post('/produccion/lotes/nuevo', data={
        'producto_id': str(IDS['chorizo']), 'lote': '', 'fecha_produccion': '2026-10-02',
        'fecha_vencimiento': '', 'consumo_insumo_id': [str(IDS['carne'])], 'consumo_real': ['10'],
    }, follow_redirects=True)
    assert 'L-0210202601' in r.get_data(as_text=True) and '02/10/2027' in r.get_data(as_text=True)
