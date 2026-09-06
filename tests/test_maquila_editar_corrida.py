"""Corregir una corrida sin que el ledger, el saldo y las cajas se desdigan."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}
FIRMA = b'\x89PNG firma'


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
        otro = Cliente(nombre='Otro cliente')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        prod2 = Producto(nombre='Salchicha', se_pesa=True, tax_rate=10)
        carne = Ingrediente(nombre='Carne de res', unidad='kg')
        grasa = Ingrediente(nombre='Grasa', unidad='kg')
        _db.session.add_all([v, cli, otro, prod, prod2, carne, grasa])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, otro_cliente=otro.id,
                   producto=prod.id, producto2=prod2.id,
                   carne=carne.id, grasa=grasa.id)
        yield flask_app
        _db.drop_all()


def _recepcion(kg=100, ingrediente=None, dia=1):
    from maquila import servicios
    return servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, dia),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': ingrediente or IDS['carne'],
                 'peso_total': Decimal(str(kg))}])


def _corrida(cerrar=False, consumos=None, cajas=(10,), lote='L-1'):
    from maquila import servicios
    corrida = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote=lote,
        fecha_produccion=date(2026, 9, 5), fecha_vencimiento=date(2026, 10, 5),
        vendedor_id=IDS['vendedor'])
    for peso in cajas:
        servicios.agregar_caja_producida(corrida, Decimal(str(peso)))
    _db.session.commit()
    if cerrar:
        servicios.cerrar_corrida(
            corrida, consumos or {IDS['carne']: Decimal('8')},
            IDS['vendedor'], firma=FIRMA, firma_mimetype='image/png')
    return corrida


def _cabecera(corrida, **cambios):
    base = {'cliente_id': corrida.cliente_id, 'producto_id': corrida.producto_id,
            'receta_id': corrida.receta_id, 'lote': corrida.lote,
            'fecha_produccion': corrida.fecha_produccion,
            'fecha_vencimiento': corrida.fecha_vencimiento,
            'notas': corrida.notas}
    base.update(cambios)
    return base


def _cajas(corrida, **por_numero):
    """Las cajas tal cual están, con overrides por número: `c1={'peso': 9}`."""
    out = []
    for caja in corrida.cajas:
        datos = {'id': caja.id, 'peso': Decimal(str(caja.peso)), 'quitar': False}
        datos.update(por_numero.get(f'c{caja.numero}', {}))
        out.append(datos)
    return out


def _editar(corrida, **kw):
    from maquila import servicios
    kw.setdefault('vendedor_id', IDS['vendedor'])
    kw.setdefault('cabecera', _cabecera(corrida))
    kw.setdefault('cajas', _cajas(corrida))
    return servicios.editar_corrida(corrida, **kw)


def _movs():
    from maquila.models import MovimientoIngrediente
    return MovimientoIngrediente.query.order_by(MovimientoIngrediente.id).all()


def _saldo(linea_id):
    from maquila import servicios
    return servicios.saldo_de_linea(linea_id)


# ---------------------------------------------------------------- cabecera

def test_abierta_cambia_lote_fechas_y_notas(app):
    with app.app_context():
        corrida = _corrida()
        _editar(corrida, cabecera=_cabecera(
            corrida, lote='L-2', fecha_produccion=date(2026, 9, 6),
            fecha_vencimiento=None, notas='corregida'))
        assert corrida.lote == 'L-2'
        assert corrida.fecha_produccion == date(2026, 9, 6)
        assert corrida.fecha_vencimiento is None
        assert corrida.notas == 'corregida'
        assert _movs() == []


def test_abierta_cambia_cliente_y_producto(app):
    with app.app_context():
        corrida = _corrida()
        _editar(corrida, cabecera=_cabecera(
            corrida, cliente_id=IDS['otro_cliente'], producto_id=IDS['producto2']))
        assert corrida.cliente_id == IDS['otro_cliente']
        assert corrida.producto_id == IDS['producto2']


def test_cerrada_no_cambia_cliente(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True)
        with pytest.raises(servicios.CorreccionImposible):
            _editar(corrida, cabecera=_cabecera(corrida, cliente_id=IDS['otro_cliente']))
        assert corrida.cliente_id == IDS['cliente']


def test_cerrada_no_cambia_producto(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True)
        with pytest.raises(servicios.CorreccionImposible):
            _editar(corrida, cabecera=_cabecera(corrida, producto_id=IDS['producto2']))


def test_cerrada_si_cambia_lote_y_notas(app):
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True)
        antes = len(_movs())
        _editar(corrida, cabecera=_cabecera(corrida, lote='L-9', notas='ok'))
        assert corrida.lote == 'L-9'
        assert corrida.notas == 'ok'
        assert len(_movs()) == antes


def test_anulada_no_es_editable(app):
    from maquila import servicios
    with app.app_context():
        corrida = _corrida()
        servicios.anular_corrida(corrida, IDS['vendedor'], 'se abrió por error')
        _db.session.commit()
        with pytest.raises(servicios.CorridaNoEditable):
            _editar(corrida, cabecera=_cabecera(corrida, lote='L-2'))


def test_lote_repetido_del_mismo_cliente_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        _corrida(lote='L-1')
        otra = _corrida(lote='L-2')
        with pytest.raises(servicios.CorridaInvalida):
            _editar(otra, cabecera=_cabecera(otra, lote='L-1'))


# ------------------------------------------------------------------- cajas

def test_corrige_el_peso_de_una_caja(app):
    with app.app_context():
        corrida = _corrida(cajas=(10, 12))
        _editar(corrida, cajas=_cajas(corrida, c2={'peso': Decimal('11.5')}))
        pesos = {c.numero: Decimal(str(c.peso)) for c in corrida.cajas}
        assert pesos == {1: Decimal('10'), 2: Decimal('11.5')}
        assert corrida.peso_producido == Decimal('21.5')


def test_peso_de_caja_no_positivo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        corrida = _corrida()
        with pytest.raises(servicios.CorridaInvalida):
            _editar(corrida, cajas=_cajas(corrida, c1={'peso': Decimal('0')}))


def test_quitar_una_caja_la_anula_con_motivo_y_conserva_la_numeracion(app):
    with app.app_context():
        corrida = _corrida(cajas=(10, 12, 14))
        _editar(corrida, cajas=_cajas(corrida, c2={'quitar': True}),
                motivo='se pesó dos veces')
        por_numero = {c.numero: c for c in corrida.cajas}
        assert set(por_numero) == {1, 2, 3}
        assert por_numero[2].anulada_en is not None
        assert por_numero[2].motivo_anulacion == 'se pesó dos veces'
        assert por_numero[2].disponible is False
        assert corrida.peso_producido == Decimal('24')


def test_quitar_una_caja_exige_motivo(app):
    from maquila import servicios
    with app.app_context():
        corrida = _corrida(cajas=(10, 12))
        with pytest.raises(servicios.MotivoRequerido):
            _editar(corrida, cajas=_cajas(corrida, c2={'quitar': True}))
        assert all(c.anulada_en is None for c in corrida.cajas)


def test_una_caja_ajena_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        corrida = _corrida()
        otra = _corrida(lote='L-2')
        ajena = _cajas(otra)
        with pytest.raises(servicios.CorreccionImposible):
            _editar(corrida, cajas=ajena)


def test_una_caja_ya_anulada_no_se_toca(app):
    from maquila import servicios
    with app.app_context():
        corrida = _corrida(cajas=(10, 12))
        _editar(corrida, cajas=_cajas(corrida, c2={'quitar': True}), motivo='dup')
        with pytest.raises(servicios.CorreccionImposible):
            _editar(corrida, cajas=_cajas(corrida, c2={'peso': Decimal('9')}))


# ---------------------------------------------------- consumo por diferencia

def test_subir_el_consumo_escribe_una_salida_por_la_diferencia(app):
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        corrida = _corrida(cerrar=True)          # 8 kg de carne
        antes = len(_movs())

        _editar(corrida, consumos={IDS['carne']: Decimal('10')},
                motivo='faltaban 2 kg', firma=FIRMA, firma_mimetype='image/png')

        movs = _movs()
        assert len(movs) == antes + 1
        assert movs[-1].tipo == 'salida'
        assert movs[-1].cantidad == Decimal('-2.000')
        assert movs[-1].recepcion_linea_id == linea.id
        assert movs[-1].origen_tipo == 'corrida' and movs[-1].origen_id == corrida.id
        assert _saldo(linea.id) == Decimal('90')
        consumo = corrida.consumos[0]
        assert consumo.cantidad_real == Decimal('10.000')
        assert [(o.recepcion_linea_id, o.cantidad) for o in consumo.origenes] == \
            [(linea.id, Decimal('10.000'))]


def test_bajar_el_consumo_escribe_un_ajuste_por_la_diferencia(app):
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        corrida = _corrida(cerrar=True)          # 8 kg
        antes = len(_movs())

        _editar(corrida, consumos={IDS['carne']: Decimal('5')},
                motivo='sobraron 3 kg', firma=FIRMA, firma_mimetype='image/png')

        movs = _movs()
        assert len(movs) == antes + 1
        assert movs[-1].tipo == 'ajuste'
        assert movs[-1].cantidad == Decimal('3.000')
        assert movs[-1].recepcion_linea_id == linea.id
        assert 'sobraron 3 kg' in movs[-1].motivo
        assert _saldo(linea.id) == Decimal('95')
        consumo = corrida.consumos[0]
        assert consumo.cantidad_real == Decimal('5.000')
        assert [o.cantidad for o in consumo.origenes] == [Decimal('5.000')]


def test_bajar_devuelve_primero_a_la_linea_mas_nueva(app):
    """El FIFO tomó de la vieja primero; deshacer devuelve a la nueva primero,
    para que el rastro de la vieja quede tal como se consumió."""
    with app.app_context():
        vieja = _recepcion(5, dia=1).lineas[0]
        nueva = _recepcion(10, dia=2).lineas[0]
        corrida = _corrida(cerrar=True, consumos={IDS['carne']: Decimal('12')})
        assert _saldo(vieja.id) == Decimal('0') and _saldo(nueva.id) == Decimal('3')

        _editar(corrida, consumos={IDS['carne']: Decimal('3')},
                motivo='se pesó mal', firma=FIRMA, firma_mimetype='image/png')

        assert _saldo(nueva.id) == Decimal('10')
        assert _saldo(vieja.id) == Decimal('2')
        consumo = corrida.consumos[0]
        assert [(o.recepcion_linea_id, o.cantidad) for o in consumo.origenes] == \
            [(vieja.id, Decimal('3.000'))]


def test_quitar_un_ingrediente_devuelve_todo_y_borra_el_consumo(app):
    with app.app_context():
        _recepcion(100)
        _recepcion(20, ingrediente=IDS['grasa'])
        corrida = _corrida(cerrar=True, consumos={IDS['carne']: Decimal('8'),
                                                  IDS['grasa']: Decimal('2')})
        linea_grasa = [c for c in corrida.consumos
                       if c.ingrediente_id == IDS['grasa']][0].origenes[0].recepcion_linea_id

        _editar(corrida, consumos={IDS['carne']: Decimal('8')},
                motivo='no llevó grasa', firma=FIRMA, firma_mimetype='image/png')

        assert [c.ingrediente_id for c in corrida.consumos] == [IDS['carne']]
        assert _saldo(linea_grasa) == Decimal('20')
        assert _movs()[-1].tipo == 'ajuste' and _movs()[-1].cantidad == Decimal('2.000')


def test_agregar_un_ingrediente_crea_el_consumo_y_su_salida(app):
    with app.app_context():
        _recepcion(100)
        linea_grasa = _recepcion(20, ingrediente=IDS['grasa']).lineas[0]
        corrida = _corrida(cerrar=True)

        _editar(corrida, consumos={IDS['carne']: Decimal('8'), IDS['grasa']: Decimal('2')},
                motivo='faltó la grasa', firma=FIRMA, firma_mimetype='image/png')

        por_ing = {c.ingrediente_id: c for c in corrida.consumos}
        assert por_ing[IDS['grasa']].cantidad_real == Decimal('2.000')
        assert [(o.recepcion_linea_id, o.cantidad, o.automatico)
                for o in por_ing[IDS['grasa']].origenes] == [(linea_grasa.id, Decimal('2.000'), True)]
        assert _saldo(linea_grasa.id) == Decimal('18')


def test_subir_sin_saldo_no_escribe_nada(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(10)
        corrida = _corrida(cerrar=True)          # 8 de 10
        antes = len(_movs())
        with pytest.raises(servicios.SaldoInsuficiente):
            _editar(corrida, consumos={IDS['carne']: Decimal('15')},
                    motivo='x', firma=FIRMA, firma_mimetype='image/png')
        _db.session.rollback()
        assert len(_movs()) == antes
        assert corrida.consumos[0].cantidad_real == Decimal('8.000')
        assert _saldo(rec.lineas[0].id) == Decimal('2')


def test_cambiar_el_consumo_exige_motivo(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True)
        with pytest.raises(servicios.MotivoRequerido):
            _editar(corrida, consumos={IDS['carne']: Decimal('10')},
                    firma=FIRMA, firma_mimetype='image/png')


def test_cambiar_el_consumo_exige_firma(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True)
        with pytest.raises(servicios.FirmaRequerida):
            _editar(corrida, consumos={IDS['carne']: Decimal('10')}, motivo='x')


def test_consumo_igual_no_escribe_ni_pide_motivo(app):
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True)
        antes = len(_movs())
        _editar(corrida, consumos={IDS['carne']: Decimal('8')})
        assert len(_movs()) == antes


def test_la_firma_de_correccion_reemplaza_la_del_cierre_y_el_motivo_queda_en_notas(app):
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True)
        _editar(corrida, consumos={IDS['carne']: Decimal('9')},
                motivo='se pesó mal', firma=b'otra firma', firma_mimetype='image/png')
        assert corrida.firma_cierre == b'otra firma'
        assert 'Corregida: se pesó mal' in corrida.notas


def test_consumo_en_una_abierta_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida()
        with pytest.raises(servicios.CorridaInvalida):
            _editar(corrida, consumos={IDS['carne']: Decimal('8')},
                    motivo='x', firma=FIRMA, firma_mimetype='image/png')


def test_consumo_negativo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True)
        with pytest.raises(servicios.CorridaInvalida):
            _editar(corrida, consumos={IDS['carne']: Decimal('-1')},
                    motivo='x', firma=FIRMA, firma_mimetype='image/png')


# ------------------------------------------------- cajas que ya salieron

def _detalle(estado='pendiente'):
    """Un pedido del cliente de maquila con una línea del producto."""
    from app import Pedido, DetallePedido
    p = Pedido(cliente_id=IDS['cliente'], estado=estado)
    _db.session.add(p)
    _db.session.flush()
    d = DetallePedido(pedido_id=p.id, producto_id=IDS['producto'], cajas=2,
                      cajas_pedidas=2, peso=0, precio_unitario=0,
                      subtotal=0, es_linea_pedido=True)
    _db.session.add(d)
    _db.session.commit()
    return d


def test_cerrada_cambia_lote_y_fechas_y_los_propaga_a_las_cajas_pesadas(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True, cajas=(10, 12))
        detalle = _detalle()
        caja1 = [c for c in corrida.cajas if c.numero == 1][0]
        servicios.asignar_cajas(detalle, [caja1], IDS['vendedor'])

        _editar(corrida, cabecera=_cabecera(
            corrida, lote='L-9', fecha_produccion=date(2026, 9, 7),
            fecha_vencimiento=date(2026, 11, 1)))

        pesada = caja1.caja_pesada
        assert pesada.lote == 'L-9'
        assert pesada.fecha_elaboracion == date(2026, 9, 7)
        assert pesada.fecha_vencimiento == date(2026, 11, 1)


def test_cerrada_con_caja_en_pedido_facturado_no_cambia_lote_ni_fechas(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True, cajas=(10, 12))
        detalle = _detalle(estado='facturado')
        caja1 = [c for c in corrida.cajas if c.numero == 1][0]
        servicios.asignar_cajas(detalle, [caja1], IDS['vendedor'])

        with pytest.raises(servicios.CorridaFacturada):
            _editar(corrida, cabecera=_cabecera(corrida, lote='L-9'))
        with pytest.raises(servicios.CorridaFacturada):
            _editar(corrida, cabecera=_cabecera(corrida, fecha_vencimiento=date(2026, 11, 1)))
        assert corrida.lote == 'L-1' and caja1.caja_pesada.lote == 'L-1'

        # Lo que la factura no lleva sí se puede corregir.
        _editar(corrida, cabecera=_cabecera(corrida, notas='nota tardía'))
        assert corrida.notas == 'nota tardía'


def test_una_caja_que_salio_en_un_pedido_no_se_toca(app):
    from maquila import servicios
    with app.app_context():
        _recepcion(100)
        corrida = _corrida(cerrar=True, cajas=(10, 12))
        caja1 = [c for c in corrida.cajas if c.numero == 1][0]
        servicios.asignar_cajas(_detalle(), [caja1], IDS['vendedor'])

        with pytest.raises(servicios.CorreccionImposible):
            _editar(corrida, cajas=_cajas(corrida, c1={'peso': Decimal('9')}))
        with pytest.raises(servicios.CorreccionImposible):
            _editar(corrida, cajas=_cajas(corrida, c1={'quitar': True}), motivo='x')
        assert Decimal(str(caja1.peso)) == Decimal('10') and caja1.anulada_en is None


# ------------------------------------------------------------ teórico

def test_corregir_el_consumo_recalcula_el_teorico_con_el_peso_actual(app):
    from maquila import servicios
    from maquila.models import Receta, RecetaIngrediente
    with app.app_context():
        _recepcion(100)
        receta = Receta(producto_id=IDS['producto'], cliente_id=IDS['cliente'],
                        nombre='R', base_kg=Decimal('100'), activa=True)
        _db.session.add(receta)
        _db.session.flush()
        _db.session.add(RecetaIngrediente(receta_id=receta.id,
                                          ingrediente_id=IDS['carne'],
                                          cantidad=Decimal('120')))
        _db.session.commit()
        corrida = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-R',
            fecha_produccion=date(2026, 9, 5), vendedor_id=IDS['vendedor'],
            receta_id=receta.id)
        servicios.agregar_caja_producida(corrida, Decimal('50'))
        _db.session.commit()
        servicios.cerrar_corrida(corrida, {IDS['carne']: Decimal('55')},
                                 IDS['vendedor'], firma=FIRMA)
        assert corrida.consumos[0].cantidad_teorica == Decimal('60.000')

        _editar(corrida, cajas=_cajas(corrida, c1={'peso': Decimal('40')}),
                consumos={IDS['carne']: Decimal('50')},
                motivo='se pesó mal', firma=FIRMA, firma_mimetype='image/png')

        assert corrida.consumos[0].cantidad_teorica == Decimal('48.000')
        assert corrida.consumos[0].cantidad_real == Decimal('50.000')
