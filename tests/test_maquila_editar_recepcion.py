"""Editar una recepción sin que el saldo y la pantalla dejen de coincidir."""
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
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, rv, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        vend = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                        rol_id=rv.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        otro = Cliente(nombre='Otro cliente')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        carne = Ingrediente(nombre='Carne de res', unidad='kg')
        grasa = Ingrediente(nombre='Grasa', unidad='kg')
        _db.session.add_all([v, vend, cli, otro, prod, carne, grasa])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, otro_cliente=otro.id,
                   producto=prod.id, carne=carne.id, grasa=grasa.id)
        yield flask_app
        _db.drop_all()


def _recepcion(kg=100, ingrediente=None, dia=1):
    """Una recepción de una línea, a granel."""
    from maquila import servicios
    return servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, dia),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': ingrediente or IDS['carne'],
                 'peso_total': Decimal(str(kg))}])


def test_una_linea_nueva_no_nace_anulada(app):
    with app.app_context():
        rec = _recepcion()
        linea = rec.lineas[0]
        assert linea.anulada_en is None
        assert linea.anulada is False


def _consumir(linea_id, ingrediente_id, kg):
    """Simula que una corrida tomó material de esa línea."""
    from maquila import servicios
    servicios.registrar_movimiento(
        cliente_id=IDS['cliente'], ingrediente_id=ingrediente_id,
        tipo='salida', cantidad=Decimal(str(kg)), origen_tipo='corrida',
        origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=linea_id)
    _db.session.commit()


def _cabecera(rec, **cambios):
    base = {'cliente_id': rec.cliente_id, 'recibido_en': rec.recibido_en,
            'documento_cliente': rec.documento_cliente,
            'temperatura': rec.temperatura, 'transportista': rec.transportista,
            'notas': rec.notas}
    base.update(cambios)
    return base


def _linea_dict(linea, **cambios):
    base = {'id': linea.id, 'ingrediente_id': linea.ingrediente_id,
            'lote_cliente': linea.lote_cliente,
            'fecha_vencimiento': linea.fecha_vencimiento,
            'cantidad_bultos': 0, 'peso_total': Decimal(str(linea.peso_total)),
            'quitar': False}
    base.update(cambios)
    return base


def test_corregir_escribe_exactamente_un_movimiento_por_la_diferencia(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')

        movs = MovimientoIngrediente.query.order_by(
            MovimientoIngrediente.id).all()
        assert len(movs) == antes + 1
        assert movs[-1].tipo == 'ajuste'
        assert movs[-1].cantidad == Decimal('-10.000')
        assert movs[-1].recepcion_linea_id == linea.id
        assert 'tecleó mal' in movs[-1].motivo
        assert linea.peso_total == Decimal('90.000')


def test_tras_corregir_se_mantiene_la_identidad_del_fifo(app):
    """peso_total − consumido == saldo_de_linea. De ahí cuelga el reparto."""
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')

        consumido = servicios.consumido_de_linea(linea)
        assert consumido == Decimal('40.000')
        assert (Decimal(str(linea.peso_total)) - consumido
                == servicios.saldo_de_linea(linea.id))


def test_editar_solo_la_cabecera_no_toca_el_ledger(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(rec, transportista='Rudsel Martina',
                               documento_cliente='GD-999'),
            lineas=[_linea_dict(linea)])

        assert MovimientoIngrediente.query.count() == antes
        assert rec.transportista == 'Rudsel Martina'
        assert rec.documento_cliente == 'GD-999'


def test_guardar_sin_cambiar_nada_no_escribe_nada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea)])
        assert MovimientoIngrediente.query.count() == antes


def test_corregir_por_debajo_de_lo_consumido_se_rechaza(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 64)
        antes = MovimientoIngrediente.query.count()

        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('59'))],
                motivo='Imposible')

        _db.session.rollback()
        assert MovimientoIngrediente.query.count() == antes
        assert Decimal(str(rec.lineas[0].peso_total)) == Decimal('100.000')


def test_corregir_a_cero_o_negativo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        for valor in (Decimal('0'), Decimal('-5')):
            with pytest.raises(servicios.RecepcionInvalida):
                servicios.editar_recepcion(
                    rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                    lineas=[_linea_dict(linea, peso_total=valor)],
                    motivo='x')
            _db.session.rollback()


def test_corregir_sin_motivo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        with pytest.raises(servicios.MotivoRequerido):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('90'))])


def test_quitar_una_linea_intacta_escribe_su_inverso_y_la_marca(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, quitar=True)],
            motivo='No vino')
        assert linea.anulada is True
        assert servicios.saldo_de_linea(linea.id) == Decimal('0')


def test_quitar_una_linea_consumida_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)
        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, quitar=True)],
                motivo='No vino')
        _db.session.rollback()
        assert rec.lineas[0].anulada is False


def test_agregar_una_linea_escribe_su_entrada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea),
                    {'id': None, 'ingrediente_id': IDS['grasa'],
                     'lote_cliente': None, 'fecha_vencimiento': None,
                     'cantidad_bultos': 2, 'peso_total': Decimal('20'), 'quitar': False}])
        entradas = MovimientoIngrediente.query.filter_by(
            ingrediente_id=IDS['grasa'], tipo='entrada').all()
        assert len(entradas) == 1
        assert entradas[0].cantidad == Decimal('20.000')


def test_cambiar_el_cliente_con_material_consumido_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)
        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'],
                cabecera=_cabecera(rec, cliente_id=IDS['otro_cliente']),
                lineas=[_linea_dict(linea)])
        _db.session.rollback()


def test_cambiar_el_cliente_con_todo_intacto_se_acepta(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(rec, cliente_id=IDS['otro_cliente']),
            lineas=[_linea_dict(linea)])
        assert rec.cliente_id == IDS['otro_cliente']


def test_cambiar_el_cliente_compensa_el_ledger(app):
    """Hoy `recepcion.cliente_id` pasa a B pero los `entrada` que escribió
    `crear_recepcion` siguen con `cliente_id`=A: A queda con stock fantasma
    para siempre y B llega a saldo negativo en cuanto produce. El arreglo
    compensa en el ledger: -peso contra el cliente viejo, +peso contra el
    nuevo, ambos sobre la misma `recepcion_linea_id`."""
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(rec, cliente_id=IDS['otro_cliente']),
            lineas=[_linea_dict(linea)])

        saldos_viejo = {f['ingrediente_id']: f['saldo']
                        for f in servicios.saldos_de_cliente(IDS['cliente'])}
        saldos_nuevo = {f['ingrediente_id']: f['saldo']
                        for f in servicios.saldos_de_cliente(IDS['otro_cliente'])}
        assert saldos_viejo.get(IDS['carne'], Decimal('0')) == Decimal('0')
        assert saldos_nuevo[IDS['carne']] == Decimal('100.000')
        # El saldo de LÍNEA no se mueve: sigue siendo el mismo peso de antes.
        assert servicios.saldo_de_linea(linea.id) == Decimal('100.000')

        # El cliente nuevo puede consumir sin quedar en negativo.
        reparto = servicios.repartir_fifo(IDS['otro_cliente'], IDS['carne'],
                                          Decimal('100'))
        assert reparto == [(linea.id, Decimal('100'))]


def test_linea_duplicada_en_el_post_se_rechaza(app):
    """Reproducido con un POST real: el mismo id dos veces con
    `linea_quitar_<id>` marcado escribía DOS movimientos inversos y dejaba
    `saldo_de_linea` en -100. `routes.py` no deduplica; el rechazo vive en
    `editar_recepcion`."""
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()

        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, quitar=True),
                        _linea_dict(linea, quitar=True)],
                motivo='Duplicado')

        _db.session.rollback()
        assert MovimientoIngrediente.query.count() == antes
        assert servicios.saldo_de_linea(linea.id) == Decimal('100.000')


def test_cambiar_el_ingrediente_de_una_linea_intacta_mueve_el_saldo(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100, ingrediente=IDS['carne'])
        linea = rec.lineas[0]

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, ingrediente_id=IDS['grasa'])],
            motivo='Era grasa, no carne')

        assert linea.ingrediente_id == IDS['grasa']
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['carne']) == Decimal('0')
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['grasa']) == Decimal('100.000')
        assert servicios.saldo_de_linea(linea.id) == Decimal('100.000')


def test_cambiar_el_ingrediente_de_una_linea_consumida_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100, ingrediente=IDS['carne'])
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)

        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, ingrediente_id=IDS['grasa'])],
                motivo='x')

        _db.session.rollback()
        assert rec.lineas[0].ingrediente_id == IDS['carne']


def test_totales_por_unidad_no_cuenta_linea_quitada(app):
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['carne'], 'peso_total': Decimal('15')},
                    {'ingrediente_id': IDS['grasa'], 'peso_total': Decimal('20')}])
        linea_quitar = rec.lineas[0]
        otra = rec.lineas[1]

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea_quitar, quitar=True), _linea_dict(otra)],
            motivo='No vino')

        totales = dict(rec.totales_por_unidad)
        assert totales == {'kg': Decimal('20')}


def test_cabecera_con_cliente_id_o_fecha_none_no_los_borra(app):
    """La ruta siempre manda las seis claves de cabecera; un `None` en
    `cliente_id`/`recibido_en` (columnas NOT NULL) tiene que leerse como "no
    tocar", igual que ya lo trata la guarda de arriba — si no, el `setattr`
    deja un NULL que revienta en el commit con un IntegrityError genérico."""
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        cliente_original = rec.cliente_id
        recibido_original = rec.recibido_en

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(rec, cliente_id=None, recibido_en=None,
                               transportista='Nuevo transportista'),
            lineas=[_linea_dict(linea)])

        assert rec.cliente_id == cliente_original
        assert rec.recibido_en == recibido_original
        assert rec.transportista == 'Nuevo transportista'


def test_editar_una_recepcion_anulada_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.anular_recepcion(rec, IDS['vendedor'], 'Llegó mal')
        _db.session.commit()
        with pytest.raises(servicios.RecepcionNoEditable):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
                motivo='x')


def test_corregir_la_fecha_reordena_el_fifo_siguiente(app):
    """El FIFO ordena por recibido_en: corregir la fecha cambia contra qué
    línea consumirán las corridas FUTURAS, y no toca ningún reparto ya hecho."""
    from maquila import servicios
    from maquila.models import CorridaConsumoOrigen
    with app.app_context():
        vieja = _recepcion(50, dia=1)
        nueva = _recepcion(50, dia=20)
        origenes_antes = CorridaConsumoOrigen.query.count()

        # Antes de corregir, el FIFO toma de la del día 1.
        assert servicios.repartir_fifo(
            IDS['cliente'], IDS['carne'], Decimal('10')
        )[0][0] == vieja.lineas[0].id

        # Se corrige la fecha de la vieja: ahora es la MÁS reciente.
        servicios.editar_recepcion(
            vieja, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(vieja, recibido_en=date(2026, 9, 25)),
            lineas=[_linea_dict(vieja.lineas[0])])

        assert servicios.repartir_fifo(
            IDS['cliente'], IDS['carne'], Decimal('10')
        )[0][0] == nueva.lineas[0].id
        # Nada del pasado se reescribió.
        assert CorridaConsumoOrigen.query.count() == origenes_antes


def test_el_fifo_reparte_bien_contra_una_linea_corregida(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['carne'],
                                          Decimal('90'))
        assert reparto == [(linea.id, Decimal('90'))]
        with pytest.raises(servicios.SaldoInsuficiente):
            servicios.repartir_fifo(IDS['cliente'], IDS['carne'],
                                    Decimal('91'))


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'},
           follow_redirects=True)
    return c


def test_la_pantalla_de_edicion_carga(app):
    with app.app_context():
        rec = _recepcion(100)
        rec_id = rec.id
    c = _login(app, 'admin')
    r = c.get(f'/maquila/recepciones/{rec_id}/editar')
    assert r.status_code == 200
    assert b'Carne de res' in r.data


def test_un_vendedor_no_entra_a_editar(app):
    with app.app_context():
        rec = _recepcion(100)
        rec_id = rec.id
    c = _login(app, 'vend')
    r = c.get(f'/maquila/recepciones/{rec_id}/editar', follow_redirects=False)
    assert r.status_code == 302


def test_corregir_por_la_ruta(app):
    from maquila.models import RecepcionLinea
    with app.app_context():
        rec = _recepcion(100)
        rec_id, linea_id = rec.id, rec.lineas[0].id
        ing = rec.lineas[0].ingrediente_id
    c = _login(app, 'admin')
    r = c.post(f'/maquila/recepciones/{rec_id}/editar', data={
        'cliente_id': str(IDS['cliente']),
        'recibido_en': '2026-09-01',
        'motivo': 'Se tecleó mal',
        'linea_id': [str(linea_id)],
        'linea_ingrediente_id': [str(ing)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_bultos': [''],
        'linea_peso_total': ['90'],
        'linea_quitar': [''],
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert _db.session.get(RecepcionLinea, linea_id).peso_total == Decimal('90.000')


def test_una_correccion_imposible_da_mensaje_no_500(app):
    with app.app_context():
        rec = _recepcion(100)
        rec_id, linea_id = rec.id, rec.lineas[0].id
        ing = rec.lineas[0].ingrediente_id
        _consumir(linea_id, ing, 64)
    c = _login(app, 'admin')
    r = c.post(f'/maquila/recepciones/{rec_id}/editar', data={
        'cliente_id': str(IDS['cliente']),
        'recibido_en': '2026-09-01',
        'motivo': 'Imposible',
        'linea_id': [str(linea_id)],
        'linea_ingrediente_id': [str(ing)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_bultos': [''],
        'linea_peso_total': ['59'],
        'linea_quitar': [''],
    }, follow_redirects=True)
    assert r.status_code == 200
    assert 'ya cedió'.encode() in r.data


def test_ingrediente_desactivado_no_cambia_solo_al_guardar(app):
    """Ronda 2: el test de Ronda 1 comparaba `value="{ing_id}"` como
    substring, que matchea CUALQUIER value=N del formulario (el hidden
    linea_id, el <option> de cliente, el checkbox de quitar...) y encima
    reusaba el primer Ingrediente del fixture (id 1, un valor que aparece en
    medio formulario). Acá se crea un ingrediente propio del test (para no
    colisionar con ningún id 1) y se exige el <option> COMPLETO con el
    atributo `selected` — que es justo lo que el bug rompía: sin `selected`
    en ninguna opción, el navegador cae en la primera del <select> y manda
    OTRO ingrediente al guardar."""
    from maquila import servicios
    from maquila.models import Ingrediente, RecepcionLinea
    with app.app_context():
        tripa = Ingrediente(nombre='Tripa natural', unidad='ud')
        _db.session.add(tripa)
        _db.session.commit()
        tripa_id = tripa.id
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': tripa_id, 'peso_total': Decimal('100')}])
        rec_id, linea_id = rec.id, rec.lineas[0].id
        tripa.activo = False
        _db.session.commit()

    c = _login(app, 'admin')
    r = c.get(f'/maquila/recepciones/{rec_id}/editar')
    assert r.status_code == 200
    assert f'<option value="{tripa_id}" selected'.encode() in r.data

    r = c.post(f'/maquila/recepciones/{rec_id}/editar', data={
        'cliente_id': str(IDS['cliente']),
        'recibido_en': '2026-09-01',
        'temperatura': '2',
        'linea_id': [str(linea_id)],
        'linea_ingrediente_id': [str(tripa_id)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_bultos': [''],
        'linea_peso_total': ['100'],
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert _db.session.get(RecepcionLinea, linea_id).ingrediente_id == tripa_id


def test_quitar_una_linea_sin_js_por_nombre_propio(app):
    """Ronda 1: `linea_quitar_<id>` viaja solo, sin hidden ni JS de
    sincronización — el fallo silencioso de antes (JS no corre, checkbox
    marcado no se envía, la línea sigue ahí) ya no puede pasar."""
    from maquila.models import RecepcionLinea
    with app.app_context():
        rec = _recepcion(100)
        rec_id, linea_id = rec.id, rec.lineas[0].id
        ing = rec.lineas[0].ingrediente_id

    c = _login(app, 'admin')
    r = c.post(f'/maquila/recepciones/{rec_id}/editar', data={
        'cliente_id': str(IDS['cliente']),
        'recibido_en': '2026-09-01',
        'motivo': 'No vino',
        'linea_id': [str(linea_id)],
        'linea_ingrediente_id': [str(ing)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_bultos': [''],
        'linea_peso_total': ['100'],
        f'linea_quitar_{linea_id}': '1',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert _db.session.get(RecepcionLinea, linea_id).anulada is True


def test_la_correccion_se_lee_en_el_kardex(app):
    from maquila import servicios, reportes
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal en planta')

        filas = reportes.kardex(IDS['cliente'])
        ajustes = [f for f in filas if f['tipo'] == 'ajuste']
        assert len(ajustes) == 1
        assert ajustes[0]['cantidad'] == Decimal('-10.000')
        assert 'Se tecleó mal en planta' in ajustes[0]['motivo']
        assert ajustes[0]['responsable'] == 'Admin'
        assert ajustes[0]['unidad'] == 'kg'


def test_los_bultos_son_una_cantidad_no_una_lista_de_pesos(app):
    """«Bultos» es cuántos vinieron. El peso total se escribe aparte.

    Antes era la lista de lo que pesaba cada bulto, separada por comas: JM
    escribió «2» queriendo decir dos bultos y el sistema guardó un bulto de
    2 kg en una línea de 16. La columna del resumen contaba filas y decía 1.
    """
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['carne'],
                     'cantidad_bultos': 9,
                     'peso_total': Decimal('121.32')}])
        linea = rec.lineas[0]
        assert linea.cantidad_bultos == 9
        assert Decimal(str(linea.peso_total)) == Decimal('121.320')


def test_corregir_la_cantidad_de_bultos_no_toca_el_peso(app):
    """Los dos números son independientes: uno no calcula al otro."""
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['carne'], 'cantidad_bultos': 1,
                     'peso_total': Decimal('16')}])
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[{'id': linea.id, 'ingrediente_id': IDS['carne'],
                     'lote_cliente': None, 'fecha_vencimiento': None,
                     'cantidad_bultos': 2, 'peso_total': Decimal('16'),
                     'quitar': False}])

        assert linea.cantidad_bultos == 2
        assert Decimal(str(linea.peso_total)) == Decimal('16.000')
        # Cambiar la cantidad de bultos no mueve el saldo: no es una cantidad
        # de ingrediente, es cuántos paquetes vinieron.
        assert MovimientoIngrediente.query.count() == antes
