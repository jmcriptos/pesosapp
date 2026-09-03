"""Lógica de negocio del módulo de maquila.

Funciones puras sobre la sesión de SQLAlchemy: reciben ids, devuelven objetos o
Decimals. Ninguna hace commit — eso es responsabilidad de quien llama, para que
una recepción o un cierre de corrida quepan en una sola transacción.
"""
from decimal import Decimal

from sqlalchemy import func

from app import db
from .models import Ingrediente, MovimientoIngrediente

TIPOS_NEGATIVOS = {'salida'}
TIPOS_CON_MOTIVO = {'ajuste', 'devolucion'}
CERO = Decimal('0')


class MotivoRequerido(ValueError):
    """Un ajuste o una devolución sin motivo no es auditable."""


def _dec(valor):
    return valor if isinstance(valor, Decimal) else Decimal(str(valor or 0))


def registrar_movimiento(*, cliente_id, ingrediente_id, tipo, cantidad,
                         origen_tipo, vendedor_id, origen_id=None,
                         recepcion_linea_id=None, motivo=None):
    """Añade un movimiento al ledger. No hace commit.

    El signo lo pone el tipo, no quien llama: una `salida` siempre se guarda
    negativa aunque llegue en positivo.
    """
    if tipo in TIPOS_CON_MOTIVO and not (motivo or '').strip():
        raise MotivoRequerido(f'Un movimiento de tipo "{tipo}" exige un motivo')

    cantidad = _dec(cantidad)
    if tipo in TIPOS_NEGATIVOS:
        cantidad = -abs(cantidad)

    mov = MovimientoIngrediente(
        cliente_id=cliente_id,
        ingrediente_id=ingrediente_id,
        recepcion_linea_id=recepcion_linea_id,
        tipo=tipo,
        cantidad=cantidad,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        motivo=(motivo or None),
        registrado_por=vendedor_id,
    )
    db.session.add(mov)
    return mov


def saldo_de_linea(recepcion_linea_id):
    """Cuánto queda de una línea de recepción concreta. Es lo que usa el FIFO."""
    total = (db.session.query(func.sum(MovimientoIngrediente.cantidad))
             .filter(MovimientoIngrediente.recepcion_linea_id == recepcion_linea_id)
             .scalar())
    return _dec(total)


def saldo_cliente_ingrediente(cliente_id, ingrediente_id):
    total = (db.session.query(func.sum(MovimientoIngrediente.cantidad))
             .filter(MovimientoIngrediente.cliente_id == cliente_id,
                     MovimientoIngrediente.ingrediente_id == ingrediente_id)
             .scalar())
    return _dec(total)


def saldos_de_cliente(cliente_id):
    """Una fila por ingrediente con movimiento, desglosando entradas y salidas."""
    filas = (db.session.query(
                MovimientoIngrediente.ingrediente_id,
                Ingrediente.nombre,
                Ingrediente.unidad,
                func.sum(MovimientoIngrediente.cantidad).label('saldo'))
             .join(Ingrediente, Ingrediente.id == MovimientoIngrediente.ingrediente_id)
             .filter(MovimientoIngrediente.cliente_id == cliente_id)
             .group_by(MovimientoIngrediente.ingrediente_id,
                       Ingrediente.nombre, Ingrediente.unidad)
             .order_by(Ingrediente.nombre)
             .all())

    desglose = dict(
        db.session.query(
            MovimientoIngrediente.ingrediente_id,
            func.sum(MovimientoIngrediente.cantidad))
        .filter(MovimientoIngrediente.cliente_id == cliente_id,
                MovimientoIngrediente.cantidad > 0,
                MovimientoIngrediente.tipo == 'entrada')
        .group_by(MovimientoIngrediente.ingrediente_id).all())

    salidas = dict(
        db.session.query(
            MovimientoIngrediente.ingrediente_id,
            func.sum(MovimientoIngrediente.cantidad))
        .filter(MovimientoIngrediente.cliente_id == cliente_id,
                MovimientoIngrediente.tipo == 'salida')
        .group_by(MovimientoIngrediente.ingrediente_id).all())

    ajustes = dict(
        db.session.query(
            MovimientoIngrediente.ingrediente_id,
            func.sum(MovimientoIngrediente.cantidad))
        .filter(MovimientoIngrediente.cliente_id == cliente_id,
                MovimientoIngrediente.tipo.in_(('ajuste', 'devolucion')))
        .group_by(MovimientoIngrediente.ingrediente_id).all())

    resultado = []
    for ingrediente_id, nombre, unidad, saldo in filas:
        resultado.append({
            'ingrediente_id': ingrediente_id,
            'ingrediente': nombre,
            'unidad': unidad,
            'recibido': _dec(desglose.get(ingrediente_id)),
            'consumido': abs(_dec(salidas.get(ingrediente_id))),
            'ajustes': _dec(ajustes.get(ingrediente_id)),
            'saldo': _dec(saldo),
        })
    return resultado
