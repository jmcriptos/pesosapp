"""Lógica de negocio del módulo de maquila.

Funciones puras sobre la sesión de SQLAlchemy: reciben ids, devuelven objetos o
Decimals. Ninguna hace commit — eso es responsabilidad de quien llama, para que
una recepción o un cierre de corrida quepan en una sola transacción.
"""
from datetime import date as _date, datetime
from decimal import Decimal

from sqlalchemy import func

from app import db
from .models import (Ingrediente, MovimientoIngrediente, RecepcionIngrediente,
                     RecepcionLinea, RecepcionBulto, RecepcionFoto, Receta,
                     CorridaProduccion, CorridaCaja, CorridaConsumo,
                     CorridaConsumoOrigen)

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


class RecepcionInvalida(ValueError):
    """Faltan datos mínimos para dar de alta la recepción."""


class RecepcionConsumida(Exception):
    """La recepción ya alimentó una corrida: anularla rompería la cadena.

    La corrección legítima a esta altura es un ajuste con motivo, no una
    anulación.
    """


def siguiente_codigo(prefijo, anio=None):
    """Siguiente correlativo del año, con el formato R-2026-0042.

    Cuenta los códigos existentes del año en vez de llevar una tabla de
    secuencias: a la escala de esta app (decenas de recepciones al mes) es
    exacto y no añade una pieza más que mantener.
    """
    modelos = {'R': RecepcionIngrediente, 'P': CorridaProduccion}
    modelo = modelos.get(prefijo)
    if modelo is None:
        raise ValueError(f'Prefijo de código desconocido: {prefijo}')

    anio = anio or _date.today().year
    patron = f'{prefijo}-{anio}-%'
    ultimo = (db.session.query(func.max(modelo.codigo))
              .filter(modelo.codigo.like(patron))
              .scalar())
    siguiente = 1 if not ultimo else int(ultimo.rsplit('-', 1)[1]) + 1
    return f'{prefijo}-{anio}-{siguiente:04d}'


def crear_recepcion(*, cliente_id, recibido_en, vendedor_id, lineas,
                    documento_cliente=None, temperatura=None, transportista=None,
                    notas=None, firma=None, firma_mimetype=None, fotos=None):
    """Da de alta una recepción completa en una sola transacción.

    Cabecera, líneas, bultos, fotos y un movimiento de entrada por línea. Si
    algo falla, no queda media recepción.
    """
    if not lineas:
        raise RecepcionInvalida('Una recepción necesita al menos una línea')

    try:
        recepcion = RecepcionIngrediente(
            codigo=siguiente_codigo('R', recibido_en.year),
            cliente_id=cliente_id,
            recibido_en=recibido_en,
            documento_cliente=(documento_cliente or None),
            temperatura=(_dec(temperatura) if temperatura not in (None, '') else None),
            transportista=(transportista or None),
            notas=(notas or None),
            firma=firma,
            firma_mimetype=firma_mimetype,
            registrado_por=vendedor_id,
        )
        db.session.add(recepcion)
        db.session.flush()

        for datos in lineas:
            bultos = [_dec(p) for p in (datos.get('bultos') or [])]
            for i, peso in enumerate(bultos, start=1):
                if peso <= CERO:
                    raise RecepcionInvalida(
                        f'Bulto {i} de la línea tiene peso no positivo: {peso}')
            if bultos:
                peso_total = sum(bultos, CERO)
            else:
                peso_total = _dec(datos.get('peso_total'))
            if peso_total <= CERO:
                raise RecepcionInvalida(
                    'Cada línea necesita bultos pesados o un peso total positivo')

            linea = RecepcionLinea(
                recepcion_id=recepcion.id,
                ingrediente_id=datos['ingrediente_id'],
                lote_cliente=(datos.get('lote_cliente') or None),
                fecha_vencimiento=datos.get('fecha_vencimiento'),
                peso_total=peso_total,
            )
            db.session.add(linea)
            db.session.flush()

            for numero, peso in enumerate(bultos, start=1):
                db.session.add(RecepcionBulto(
                    recepcion_linea_id=linea.id, numero=numero, peso=peso))

            registrar_movimiento(
                cliente_id=cliente_id,
                ingrediente_id=linea.ingrediente_id,
                tipo='entrada',
                cantidad=peso_total,
                origen_tipo='recepcion',
                origen_id=recepcion.id,
                vendedor_id=vendedor_id,
                recepcion_linea_id=linea.id,
            )

        for imagen, mimetype in (fotos or []):
            db.session.add(RecepcionFoto(
                recepcion_id=recepcion.id, imagen=imagen, mimetype=mimetype))

        db.session.commit()
        return recepcion
    except Exception:
        db.session.rollback()
        raise


def anular_recepcion(recepcion, vendedor_id, motivo):
    """Anula una recepción escribiendo los movimientos inversos.

    Solo se permite si ninguna línea se consumió: el saldo de cada una tiene que
    seguir igual a su peso. No borra ninguna fila — el ledger es append-only.
    """
    if not (motivo or '').strip():
        raise MotivoRequerido('Anular una recepción exige un motivo')
    if recepcion.anulada:
        raise RecepcionInvalida('La recepción ya estaba anulada')

    for linea in recepcion.lineas:
        if saldo_de_linea(linea.id) != _dec(linea.peso_total):
            raise RecepcionConsumida(
                f'La línea {linea.id} de {recepcion.codigo} ya se consumió; '
                f'la corrección a esta altura es un ajuste, no una anulación')

    for linea in recepcion.lineas:
        registrar_movimiento(
            cliente_id=recepcion.cliente_id,
            ingrediente_id=linea.ingrediente_id,
            tipo='ajuste',
            cantidad=-_dec(linea.peso_total),
            origen_tipo='recepcion',
            origen_id=recepcion.id,
            vendedor_id=vendedor_id,
            recepcion_linea_id=linea.id,
            motivo=f'Anulación de {recepcion.codigo}: {motivo.strip()}',
        )

    recepcion.anulada_en = datetime.utcnow()
    recepcion.anulada_por = vendedor_id
    recepcion.motivo_anulacion = motivo.strip()
    return recepcion


class RecetaDuplicada(ValueError):
    """Ya existe otra receta activa para ese producto y ese cliente.

    Se rechaza al guardar la receta, no al usarla: descubrir el empate cuando ya
    estás cerrando una corrida es descubrirlo tarde.
    """


def receta_activa(producto_id, cliente_id):
    """La receta que aplica: la del cliente gana; si no hay, la genérica."""
    propia = (Receta.query
              .filter_by(producto_id=producto_id, cliente_id=cliente_id, activa=True)
              .first())
    if propia:
        return propia
    return (Receta.query
            .filter(Receta.producto_id == producto_id,
                    Receta.cliente_id.is_(None),
                    Receta.activa.is_(True))
            .first())


def validar_receta_unica(producto_id, cliente_id, receta_id=None):
    query = Receta.query.filter(Receta.producto_id == producto_id,
                                Receta.activa.is_(True))
    if cliente_id is None:
        query = query.filter(Receta.cliente_id.is_(None))
    else:
        query = query.filter(Receta.cliente_id == cliente_id)
    if receta_id is not None:
        query = query.filter(Receta.id != receta_id)
    if query.first():
        raise RecetaDuplicada(
            'Ya hay una receta activa para ese producto y ese cliente')


def consumo_teorico(receta, kg_producidos):
    """Cuánto debería consumirse de cada ingrediente para producir esos kilos."""
    kg_producidos = _dec(kg_producidos)
    base = _dec(receta.base_kg)
    if base <= CERO:
        raise ValueError('La base de la receta debe ser positiva')
    factor = kg_producidos / base
    return {item.ingrediente_id: (_dec(item.cantidad) * factor).quantize(Decimal('0.001'))
            for item in receta.ingredientes}


class CorridaInvalida(ValueError):
    """La corrida no está en condiciones de hacer lo que se le pide."""


class CorridaFacturada(Exception):
    """Alguna caja de la corrida ya salió en un pedido facturado.

    A esa altura la cifra ya está en QuickBooks: deshacerla en la app dejaría
    los dos sistemas contando cosas distintas.
    """


def abrir_corrida(*, cliente_id, producto_id, lote, fecha_produccion, vendedor_id,
                  fecha_vencimiento=None, receta_id=None, notas=None):
    lote = (lote or '').strip()
    if not lote:
        raise CorridaInvalida('La corrida necesita un lote')

    repetido = CorridaProduccion.query.filter_by(
        cliente_id=cliente_id, lote=lote).first()
    if repetido:
        raise CorridaInvalida(
            f'El cliente ya tiene la corrida {repetido.codigo} con el lote {lote}')

    if receta_id is None:
        sugerida = receta_activa(producto_id, cliente_id)
        receta_id = sugerida.id if sugerida else None

    corrida = CorridaProduccion(
        codigo=siguiente_codigo('P', fecha_produccion.year),
        cliente_id=cliente_id,
        producto_id=producto_id,
        receta_id=receta_id,
        lote=lote,
        fecha_produccion=fecha_produccion,
        fecha_vencimiento=fecha_vencimiento,
        estado='abierta',
        notas=(notas or None),
        registrado_por=vendedor_id,
    )
    db.session.add(corrida)
    db.session.commit()
    return corrida


def agregar_caja_producida(corrida, peso):
    """Añade una caja pesada a la corrida. No hace commit."""
    if corrida.estado != 'abierta':
        raise CorridaInvalida('Solo se pueden añadir cajas a una corrida abierta')
    peso = _dec(peso)
    if peso <= CERO:
        raise CorridaInvalida('El peso de la caja debe ser positivo')

    # Consulta directa (no `corrida.cajas`): esa relación queda cacheada en
    # memoria desde el primer acceso y, sin un commit entre cada caja, no ve
    # las que se acaban de añadir en esta misma transacción.
    ultimo = (db.session.query(func.max(CorridaCaja.numero))
              .filter(CorridaCaja.corrida_id == corrida.id)
              .scalar())
    caja = CorridaCaja(corrida_id=corrida.id,
                       numero=(ultimo + 1 if ultimo else 1),
                       peso=peso)
    db.session.add(caja)
    return caja


def cerrar_corrida(corrida, consumos_reales, vendedor_id, reparto_manual=None):
    """Cierra la corrida: snapshot del teórico, reparto FIFO y salidas del ledger.

    Todo en una transacción. Si un ingrediente no tiene saldo, no se escribe
    nada: `SaldoInsuficiente` sube y quien llama hace rollback.
    """
    if corrida.estado != 'abierta':
        raise CorridaInvalida(f'La corrida {corrida.codigo} no está abierta')
    if not corrida.cajas:
        raise CorridaInvalida('No se puede cerrar una corrida sin cajas producidas')
    if not consumos_reales:
        raise CorridaInvalida('Hay que declarar el consumo de al menos un ingrediente')

    producido = corrida.peso_producido
    teoricos = {}
    if corrida.receta:
        teoricos = consumo_teorico(corrida.receta, producido)

    reparto_manual = reparto_manual or {}

    for ingrediente_id, cantidad in consumos_reales.items():
        cantidad = _dec(cantidad)
        if cantidad <= CERO:
            continue

        if ingrediente_id in reparto_manual:
            tramos = [(linea_id, _dec(c)) for linea_id, c in reparto_manual[ingrediente_id]]
            suma = sum((c for _, c in tramos), CERO)
            if suma != cantidad:
                raise CorridaInvalida(
                    f'El reparto manual del ingrediente {ingrediente_id} suma {suma} '
                    f'y el consumo declarado es {cantidad}')
            automatico = False
        else:
            tramos = repartir_fifo(corrida.cliente_id, ingrediente_id, cantidad)
            automatico = True

        consumo = CorridaConsumo(
            corrida_id=corrida.id,
            ingrediente_id=ingrediente_id,
            cantidad_teorica=teoricos.get(ingrediente_id, CERO),
            cantidad_real=cantidad,
        )
        db.session.add(consumo)
        db.session.flush()

        for linea_id, tramo in tramos:
            db.session.add(CorridaConsumoOrigen(
                corrida_consumo_id=consumo.id,
                recepcion_linea_id=linea_id,
                cantidad=tramo,
                automatico=automatico,
            ))
            registrar_movimiento(
                cliente_id=corrida.cliente_id,
                ingrediente_id=ingrediente_id,
                tipo='salida',
                cantidad=tramo,
                origen_tipo='corrida',
                origen_id=corrida.id,
                vendedor_id=vendedor_id,
                recepcion_linea_id=linea_id,
            )

    corrida.estado = 'cerrada'
    corrida.cerrada_por = vendedor_id
    corrida.cerrada_en = datetime.utcnow()
    db.session.commit()
    return corrida


def merma_de_corrida(corrida):
    """Kilos consumidos menos kilos producidos. Se deriva, no se guarda."""
    consumido = sum((_dec(c.cantidad_real) for c in corrida.consumos), CERO)
    return consumido - corrida.peso_producido


def anular_corrida(corrida, vendedor_id, motivo):
    """Devuelve los ingredientes al saldo y libera las cajas no entregadas."""
    if not (motivo or '').strip():
        raise MotivoRequerido('Anular una corrida exige un motivo')
    if corrida.estado == 'anulada':
        raise CorridaInvalida('La corrida ya estaba anulada')

    for caja in corrida.cajas:
        if caja.caja_pesada_id is None:
            continue
        pedido = getattr(getattr(caja.caja_pesada, 'detalle_pedido', None), 'pedido', None)
        if pedido is not None and pedido.estado == 'facturado':
            raise CorridaFacturada(
                f'La caja {caja.numero} de {corrida.codigo} salió en el pedido '
                f'{pedido.id}, que ya está facturado')

    for consumo in corrida.consumos:
        for origen in consumo.origenes:
            registrar_movimiento(
                cliente_id=corrida.cliente_id,
                ingrediente_id=consumo.ingrediente_id,
                tipo='ajuste',
                cantidad=_dec(origen.cantidad),
                origen_tipo='corrida',
                origen_id=corrida.id,
                vendedor_id=vendedor_id,
                recepcion_linea_id=origen.recepcion_linea_id,
                motivo=f'Anulación de {corrida.codigo}: {motivo.strip()}',
            )

    for caja in corrida.cajas:
        if caja.anulada_en is None:
            caja.anulada_en = datetime.utcnow()
            caja.motivo_anulacion = motivo.strip()

    corrida.estado = 'anulada'
    corrida.notas = ((corrida.notas or '') +
                     f'\nAnulada: {motivo.strip()}').strip()
    return corrida
