"""Lógica de negocio del módulo de maquila.

Funciones puras sobre la sesión de SQLAlchemy: reciben ids, devuelven objetos o
Decimals. Ninguna hace commit — eso es responsabilidad de quien llama, para que
una recepción o un cierre de corrida quepan en una sola transacción.
"""
from decimal import Decimal

from sqlalchemy import func

from app import db
from .models import Ingrediente, MovimientoIngrediente, RecepcionIngrediente, RecepcionLinea

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


class SaldoInsuficiente(Exception):
    """No hay ingrediente suficiente del cliente para cubrir el consumo.

    Se bloquea a propósito: un saldo negativo envenena todos los reportes hacia
    abajo y deja al FIFO sin ninguna recepción honesta de dónde tirar. La salida
    legítima es registrar un ajuste de entrada con su motivo.
    """

    def __init__(self, ingrediente_id, pedido, disponible):
        self.ingrediente_id = ingrediente_id
        self.pedido = pedido
        self.disponible = disponible
        self.faltante = pedido - disponible
        super().__init__(
            f'Faltan {self.faltante} del ingrediente {ingrediente_id}: '
            f'se piden {pedido} y hay {disponible}')


def lineas_con_saldo(cliente_id, ingrediente_id):
    """Líneas de recepción del cliente con saldo > 0, más antigua primero.

    Ordena por fecha de recepción y desempata por id, para que el reparto sea
    determinista aunque dos recepciones lleguen el mismo día.
    """
    lineas = (RecepcionLinea.query
              .join(RecepcionIngrediente,
                    RecepcionIngrediente.id == RecepcionLinea.recepcion_id)
              .filter(RecepcionIngrediente.cliente_id == cliente_id,
                      RecepcionIngrediente.anulada_en.is_(None),
                      RecepcionLinea.ingrediente_id == ingrediente_id)
              .order_by(RecepcionIngrediente.recibido_en.asc(),
                        RecepcionLinea.id.asc())
              .all())
    con_saldo = []
    for linea in lineas:
        saldo = saldo_de_linea(linea.id)
        if saldo > CERO:
            con_saldo.append((linea, saldo))
    return con_saldo


def repartir_fifo(cliente_id, ingrediente_id, cantidad):
    """Reparte `cantidad` contra las recepciones más antiguas del cliente.

    Devuelve pares (recepcion_linea_id, cantidad). No escribe nada: quien llama
    decide si convierte el reparto en movimientos.
    """
    cantidad = _dec(cantidad)
    if cantidad <= CERO:
        raise ValueError('La cantidad a repartir debe ser positiva')

    disponibles = lineas_con_saldo(cliente_id, ingrediente_id)
    total_disponible = sum((saldo for _, saldo in disponibles), CERO)
    if total_disponible < cantidad:
        raise SaldoInsuficiente(ingrediente_id, cantidad, total_disponible)

    reparto = []
    restante = cantidad
    for linea, saldo in disponibles:
        if restante <= CERO:
            break
        toma = saldo if saldo < restante else restante
        reparto.append((linea.id, toma))
        restante -= toma
    return reparto
