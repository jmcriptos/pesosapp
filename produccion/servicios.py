"""Lógica de negocio de producción propia.

Funciones sobre la sesión de SQLAlchemy. Las que son una transacción
completa de un caso de uso (`crear_lote`, `editar_lote`, `cerrar_lote`,
`reabrir_lote`, `anular_lote`) hacen commit y su propio rollback ante un
error; las de lectura (`balance`, `receta_para`) no tocan nada.

Regla que da nombre al módulo: NADA acá verifica disponibilidad de
ingredientes. Lo declarado se anota tal cual. El control es a posteriori
—merma y rendimiento por lote— no un bloqueo a la hora de registrar.
"""
from datetime import date as _date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func

from maquila.models import Ingrediente, Receta
from maquila.servicios import consumo_teorico, UNIDAD_PESO

from . import app_module
from .models import LoteConsumo, LoteMerma, LoteProduccion, TIPOS_MERMA_ETIQUETA

# NO reemplazar por `from app import db, Producto`: ver produccion/__init__.py.
db = app_module.db
Producto = app_module.Producto

CERO = Decimal('0')
MILESIMA = Decimal('0.001')
DECIMA = Decimal('0.1')

# Por encima de esto la merma se marca en pantalla y en el Excel. Es el
# mismo umbral que usa el reporte de rendimiento de maquila.
UMBRAL_MERMA_ALTA_PCT = Decimal('10')


class LoteInvalido(ValueError):
    """Faltan datos o no cuadran: el lote no se puede guardar así."""


class LoteNoEditable(Exception):
    """El lote está cerrado o anulado: primero hay que reabrirlo."""


class MotivoRequerido(ValueError):
    """Reabrir o anular sin motivo no es auditable."""


def _dec(valor):
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor if valor not in (None, '') else 0))


def _pct(parte, total):
    """`parte / total` en porcentaje a un decimal, o None si no hay total."""
    if total is None or total <= CERO:
        return None
    return ((_dec(parte) / _dec(total)) * 100).quantize(DECIMA, rounding=ROUND_HALF_UP)


def siguiente_codigo(anio=None):
    """Siguiente correlativo del año: PR-2026-0042.

    Mismo criterio que maquila: se cuenta lo que hay en vez de llevar una
    tabla de secuencias. A decenas de lotes por mes es exacto.
    """
    anio = anio or _date.today().year
    patron = f'PR-{anio}-%'
    ultimo = (db.session.query(func.max(LoteProduccion.codigo))
              .filter(LoteProduccion.codigo.like(patron))
              .scalar())
    siguiente = 1 if not ultimo else int(ultimo.rsplit('-', 1)[1]) + 1
    return f'PR-{anio}-{siguiente:04d}'


def receta_para(producto_id):
    """La receta genérica activa del producto (sin cliente), o None.

    Las recetas con cliente son de maquila: fórmulas que un cliente pidió
    para SU producto. Para producción propia aplica la de la casa.
    """
    return (Receta.query
            .filter(Receta.producto_id == producto_id,
                    Receta.cliente_id.is_(None),
                    Receta.activa.is_(True))
            .order_by(Receta.id.desc())
            .first())


def lote_repetido(producto_id, lote, excluir_id=None):
    """Otro lote VIVO (no anulado) del mismo producto con ese número."""
    query = LoteProduccion.query.filter(
        LoteProduccion.producto_id == producto_id,
        LoteProduccion.lote == lote,
        LoteProduccion.estado != 'anulada')
    if excluir_id is not None:
        query = query.filter(LoteProduccion.id != excluir_id)
    return query.first()


def _validar_cabecera(producto_id, lote, fecha_produccion, peso_producido,
                      unidades, cajas, excluir_id=None):
    lote = (lote or '').strip()
    if not lote:
        raise LoteInvalido('El lote necesita un número, como va en la etiqueta')
    if fecha_produccion is None:
        raise LoteInvalido('El lote necesita una fecha de producción válida')
    if producto_id is None or db.session.get(Producto, producto_id) is None:
        raise LoteInvalido('Elegí un producto válido')
    repetido = lote_repetido(producto_id, lote, excluir_id=excluir_id)
    if repetido:
        raise LoteInvalido(
            f'Ya existe {repetido.codigo} con el lote {lote} para ese producto')
    peso = _dec(peso_producido)
    if peso < CERO:
        raise LoteInvalido('El peso producido no puede ser negativo')
    for nombre, valor in (('unidades', unidades), ('cajas', cajas)):
        if valor is not None and valor < 0:
            raise LoteInvalido(f'La cantidad de {nombre} no puede ser negativa')
    return lote, peso


def _validar_consumos(consumos):
    """{ingrediente_id: Decimal} con solo lo positivo. Un ingrediente
    inexistente es error; cero o vacío es «no se usó» y se omite."""
    limpios = {}
    for ingrediente_id, cantidad in (consumos or {}).items():
        cantidad = _dec(cantidad)
        if cantidad < CERO:
            raise LoteInvalido('El consumo de un ingrediente no puede ser negativo')
        if cantidad == CERO:
            continue
        if db.session.get(Ingrediente, ingrediente_id) is None:
            raise LoteInvalido(f'El ingrediente {ingrediente_id} no existe')
        limpios[ingrediente_id] = cantidad
    return limpios


def _validar_mermas(mermas):
    """Lista de {'tipo','cantidad','motivo'} con solo las filas con cantidad."""
    limpias = []
    for fila in (mermas or []):
        cantidad = _dec(fila.get('cantidad'))
        tipo = (fila.get('tipo') or '').strip()
        motivo = (fila.get('motivo') or '').strip() or None
        if cantidad == CERO and not motivo:
            continue
        if cantidad <= CERO:
            raise LoteInvalido('Cada merma necesita una cantidad positiva en kg')
        if tipo not in TIPOS_MERMA_ETIQUETA:
            raise LoteInvalido('Elegí el tipo de cada merma')
        if tipo == 'otro' and not motivo:
            raise LoteInvalido('Una merma de tipo «Otra» necesita decir qué fue')
        limpias.append({'tipo': tipo, 'cantidad': cantidad, 'motivo': motivo})
    return limpias


def _escribir_lineas(lote, consumos, mermas):
    """Reemplaza consumos y mermas del lote por lo validado y recalcula el
    teórico contra la receta y el peso producido actuales."""
    teoricos = {}
    if lote.receta and _dec(lote.peso_producido) > CERO:
        teoricos = consumo_teorico(lote.receta, lote.peso_producido)

    lote.consumos.clear()
    lote.mermas.clear()
    db.session.flush()
    for ingrediente_id, cantidad in consumos.items():
        lote.consumos.append(LoteConsumo(
            ingrediente_id=ingrediente_id,
            cantidad_teorica=teoricos.get(ingrediente_id, CERO),
            cantidad_real=cantidad))
    for fila in mermas:
        lote.mermas.append(LoteMerma(**fila))


def crear_lote(*, producto_id, lote, fecha_produccion, vendedor_id,
               fecha_vencimiento=None, peso_producido=None,
               unidades_producidas=None, cajas_producidas=None,
               consumos=None, mermas=None, notas=None):
    """Registra un lote con todo lo que se sabe de él. Comitea.

    No pide consumo ni peso para guardar: en planta se abre el lote al
    empezar y se completa cuando sale de la balanza. Lo que sí exige
    `cerrar_lote`.
    """
    lote, peso = _validar_cabecera(producto_id, lote, fecha_produccion,
                                   peso_producido, unidades_producidas,
                                   cajas_producidas)
    consumos = _validar_consumos(consumos)
    mermas = _validar_mermas(mermas)
    receta = receta_para(producto_id)
    try:
        nuevo = LoteProduccion(
            codigo=siguiente_codigo(fecha_produccion.year),
            producto_id=producto_id,
            receta_id=receta.id if receta else None,
            lote=lote,
            fecha_produccion=fecha_produccion,
            fecha_vencimiento=fecha_vencimiento,
            peso_producido=peso,
            unidades_producidas=unidades_producidas,
            cajas_producidas=cajas_producidas,
            estado='abierta',
            notas=(notas or '').strip() or None,
            registrado_por=vendedor_id,
        )
        db.session.add(nuevo)
        db.session.flush()
        _escribir_lineas(nuevo, consumos, mermas)
        db.session.commit()
        return nuevo
    except Exception:
        db.session.rollback()
        raise


def editar_lote(lote, *, cabecera, consumos=None, mermas=None):
    """Reescribe cabecera, consumos y mermas de un lote ABIERTO. Comitea.

    `cabecera` trae producto_id, lote, fecha_produccion, fecha_vencimiento,
    peso_producido, unidades_producidas, cajas_producidas y notas. Si cambia
    el producto, la receta se vuelve a resolver: la del nuevo producto.
    """
    if lote.estado != 'abierta':
        raise LoteNoEditable(
            f'{lote.codigo} está {lote.estado}: reabrilo para corregirlo')
    numero, peso = _validar_cabecera(
        cabecera.get('producto_id'), cabecera.get('lote'),
        cabecera.get('fecha_produccion'), cabecera.get('peso_producido'),
        cabecera.get('unidades_producidas'), cabecera.get('cajas_producidas'),
        excluir_id=lote.id)
    consumos = _validar_consumos(consumos)
    mermas = _validar_mermas(mermas)
    try:
        if cabecera.get('producto_id') != lote.producto_id:
            lote.producto_id = cabecera['producto_id']
            receta = receta_para(lote.producto_id)
            lote.receta_id = receta.id if receta else None
        elif lote.receta_id is None:
            # Un producto que recibió receta después de abrir el lote: se
            # engancha ahora, para que el teórico exista al cerrar.
            receta = receta_para(lote.producto_id)
            lote.receta_id = receta.id if receta else None
        lote.lote = numero
        lote.fecha_produccion = cabecera['fecha_produccion']
        lote.fecha_vencimiento = cabecera.get('fecha_vencimiento')
        lote.peso_producido = peso
        lote.unidades_producidas = cabecera.get('unidades_producidas')
        lote.cajas_producidas = cabecera.get('cajas_producidas')
        lote.notas = (cabecera.get('notas') or '').strip() or None
        db.session.flush()
        # `lote.receta` puede estar cacheada con el id viejo: se expira
        # para que el teórico salga de la receta que acaba de quedar.
        db.session.expire(lote, ['receta'])
        _escribir_lineas(lote, consumos, mermas)
        db.session.commit()
        return lote
    except Exception:
        db.session.rollback()
        raise


def cerrar_lote(lote, vendedor_id):
    """Cierra el lote: desde acá cuenta en los reportes. Comitea.

    Exige lo mínimo para que el balance signifique algo: peso producido y
    al menos un consumo en peso. No exige que la merma esté explicada: lo
    que no se explica queda como «sin identificar», que es un dato en sí.
    """
    if lote.estado != 'abierta':
        raise LoteInvalido(f'{lote.codigo} no está abierto')
    if _dec(lote.peso_producido) <= CERO:
        raise LoteInvalido('Para cerrar hace falta el peso producido')
    if consumo_en_peso(lote) <= CERO:
        raise LoteInvalido('Para cerrar hace falta declarar el consumo de al '
                           'menos un ingrediente en kg')
    try:
        lote.estado = 'cerrada'
        lote.cerrado_por = vendedor_id
        lote.cerrado_en = datetime.utcnow()
        db.session.commit()
        return lote
    except Exception:
        db.session.rollback()
        raise


def _sellar_nota(lote, texto):
    """Deja constancia en las notas, con fecha. No hay tabla de eventos:
    el lote es el documento, y el motivo queda donde se lee el lote."""
    sello = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    lote.notas = ((lote.notas or '') + f'\n[{sello}] {texto}').strip()


def reabrir_lote(lote, vendedor_id, motivo):
    """Vuelve un lote cerrado a abierto para corregirlo. Comitea."""
    if not (motivo or '').strip():
        raise MotivoRequerido('Reabrir un lote exige un motivo')
    if lote.estado != 'cerrada':
        raise LoteInvalido(f'{lote.codigo} no está cerrado')
    try:
        lote.estado = 'abierta'
        lote.cerrado_por = None
        lote.cerrado_en = None
        _sellar_nota(lote, f'Reabierto: {motivo.strip()}')
        db.session.commit()
        return lote
    except Exception:
        db.session.rollback()
        raise


def anular_lote(lote, vendedor_id, motivo):
    """Saca el lote de todos los reportes sin borrarlo. Comitea."""
    if not (motivo or '').strip():
        raise MotivoRequerido('Anular un lote exige un motivo')
    if lote.estado == 'anulada':
        raise LoteInvalido(f'{lote.codigo} ya estaba anulado')
    try:
        lote.estado = 'anulada'
        lote.anulado_por = vendedor_id
        lote.anulado_en = datetime.utcnow()
        lote.motivo_anulacion = motivo.strip()
        _sellar_nota(lote, f'Anulado: {motivo.strip()}')
        db.session.commit()
        return lote
    except Exception:
        db.session.rollback()
        raise


def consumo_en_peso(lote):
    """Suma SOLO los consumos en kg. Tripa (ud) no entra en un balance de
    kilos: sumarla daría un número que no es nada (ver maquila)."""
    return sum((_dec(c.cantidad_real) for c in lote.consumos
                if c.ingrediente and c.ingrediente.unidad == UNIDAD_PESO), CERO)


def balance(lote):
    """Todo lo que se deriva de un lote, en un dict listo para pantalla,
    reporte y Excel. Nada de esto se guarda.

    - merma_total: consumido en kg − producido. Negativa si el producto
      pesa más que lo que entró (inyección de salmuera que no se declaró
      como ingrediente, por ejemplo): se muestra tal cual, no se esconde.
    - merma_identificada: la suma de las mermas declaradas.
    - merma_sin_identificar: total − identificada. Es la cifra que vale
      la pena mirar: lo que nadie supo explicar.
    - rendimiento_pct: producido / consumido × 100.
    """
    consumido = consumo_en_peso(lote)
    producido = _dec(lote.peso_producido)
    otras_unidades = sorted({c.ingrediente.unidad for c in lote.consumos
                             if c.ingrediente and c.ingrediente.unidad != UNIDAD_PESO})
    identificada = sum((_dec(m.cantidad) for m in lote.mermas), CERO)

    merma_total = (consumido - producido) if consumido > CERO else None
    sin_identificar = (merma_total - identificada) if merma_total is not None else None
    merma_pct = _pct(merma_total, consumido) if merma_total is not None else None
    rendimiento_pct = _pct(producido, consumido)

    varianzas = []
    for consumo in lote.consumos:
        teorica = _dec(consumo.cantidad_teorica)
        real = _dec(consumo.cantidad_real)
        varianzas.append({
            'ingrediente_id': consumo.ingrediente_id,
            'ingrediente': consumo.ingrediente.nombre if consumo.ingrediente else '—',
            'unidad': consumo.ingrediente.unidad if consumo.ingrediente else 'kg',
            'teorica': teorica,
            'real': real,
            'diferencia': real - teorica,
            'pct': _pct(real - teorica, teorica) if teorica > CERO else None,
        })

    por_tipo = {}
    for merma in lote.mermas:
        por_tipo[merma.tipo] = por_tipo.get(merma.tipo, CERO) + _dec(merma.cantidad)
    mermas_por_tipo = [{
        'tipo': tipo, 'etiqueta': TIPOS_MERMA_ETIQUETA.get(tipo, tipo),
        'cantidad': cantidad,
        'pct': _pct(cantidad, consumido),
    } for tipo, cantidad in sorted(por_tipo.items(), key=lambda kv: -kv[1])]

    return {
        'consumido': consumido,
        'producido': producido,
        'otras_unidades': otras_unidades,
        'merma_total': merma_total,
        'merma_identificada': identificada,
        'merma_sin_identificar': sin_identificar,
        'merma_pct': merma_pct,
        'merma_alta': merma_pct is not None and abs(merma_pct) > UMBRAL_MERMA_ALTA_PCT,
        'rendimiento_pct': rendimiento_pct,
        'varianzas': varianzas,
        'mermas_por_tipo': mermas_por_tipo,
    }
