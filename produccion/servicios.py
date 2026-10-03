"""Lógica de negocio de producción propia.

Funciones sobre la sesión de SQLAlchemy. Las que son una transacción
completa de un caso de uso (`crear_lote`, `editar_lote`, `cerrar_lote`,
`reabrir_lote`, `anular_lote`) hacen commit y su propio rollback ante un
error; las de lectura (`balance`, `receta_para`) no tocan nada.

Regla que da nombre al módulo: NADA acá verifica disponibilidad de
ingredientes. Lo declarado se anota tal cual. El control es a posteriori
—merma y rendimiento por lote— no un bloqueo a la hora de registrar.
"""
import re
from datetime import date as _date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func

from . import app_module
from .models import (Formula, FormulaInsumo, Insumo, LoteConsumo, LoteMerma,
                     LoteProduccion, TIPOS_MERMA_ETIQUETA, UNIDAD_PESO, UNIDADES)

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


class InsumoInvalido(ValueError):
    """El insumo no se puede guardar así (sin nombre, repetido, unidad rara)."""


class FormulaInvalida(ValueError):
    """La fórmula no se puede guardar así."""


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

    Se cuenta lo que hay en vez de llevar una tabla de secuencias: a
    decenas de lotes por mes es exacto.
    """
    anio = anio or _date.today().year
    patron = f'PR-{anio}-%'
    ultimo = (db.session.query(func.max(LoteProduccion.codigo))
              .filter(LoteProduccion.codigo.like(patron))
              .scalar())
    siguiente = 1 if not ultimo else int(ultimo.rsplit('-', 1)[1]) + 1
    return f'PR-{anio}-{siguiente:04d}'


# ------------------------------------------------------------ catálogo

UNIDADES_VALIDAS = {clave for clave, _ in UNIDADES}


def crear_insumo(*, nombre, unidad='kg', notas=None):
    """Da de alta un insumo. Comitea."""
    nombre = (nombre or '').strip()
    if not nombre:
        raise InsumoInvalido('El insumo necesita un nombre')
    if unidad not in UNIDADES_VALIDAS:
        raise InsumoInvalido('La unidad tiene que ser kg, m, ud o l')
    if Insumo.query.filter(func.lower(Insumo.nombre) == nombre.lower()).first():
        raise InsumoInvalido(f'Ya existe un insumo llamado {nombre}')
    try:
        insumo = Insumo(nombre=nombre, unidad=unidad, notas=(notas or '').strip() or None)
        db.session.add(insumo)
        db.session.commit()
        return insumo
    except Exception:
        db.session.rollback()
        raise


def cargar_insumos(texto):
    """Carga masiva desde texto pegado: una línea por insumo, con la unidad
    opcional al final separada por coma, punto y coma, tabulador o barra
    («Sal fina, kg» · «Tripa natural; ud» · «Palatinata»). Sin unidad, kg.

    Devuelve (creados, omitidos): los nombres que ya existían se omiten y se
    informan, no se duplican ni se pisan. Una unidad inválida rechaza la
    carga ENTERA con el número de línea, para corregir el texto y volver a
    pegarlo: cargar la mitad y fallar en la otra deja al operario sin saber
    qué entró. Comitea.
    """
    filas = []
    for numero, cruda in enumerate((texto or '').splitlines(), start=1):
        linea = cruda.strip().strip('-•*').strip()
        if not linea:
            continue
        partes = [p.strip() for p in re.split(r'[,;|\t]', linea) if p.strip()]
        if not partes:
            continue
        nombre, unidad = partes[0], 'kg'
        if len(partes) > 1:
            unidad = partes[-1].lower()
            if unidad not in UNIDADES_VALIDAS:
                raise InsumoInvalido(
                    f'Línea {numero}: la unidad «{partes[-1]}» no es kg, m, ud ni l')
        filas.append((nombre, unidad))

    existentes = {i.nombre.lower() for i in Insumo.query.all()}
    creados, omitidos, vistos = [], [], set()
    try:
        for nombre, unidad in filas:
            clave = nombre.lower()
            if clave in existentes or clave in vistos:
                omitidos.append(nombre)
                continue
            vistos.add(clave)
            insumo = Insumo(nombre=nombre, unidad=unidad)
            db.session.add(insumo)
            creados.append(insumo)
        db.session.commit()
        return creados, omitidos
    except Exception:
        db.session.rollback()
        raise


def formula_para(producto_id):
    """La fórmula activa del producto, o None. Si hubiera más de una (no
    debería: `guardar_formula` lo impide), gana la más nueva."""
    return (Formula.query
            .filter(Formula.producto_id == producto_id, Formula.activa.is_(True))
            .order_by(Formula.id.desc())
            .first())


def guardar_formula(formula, *, producto_id, nombre, base_kg, activa, items,
                    vendedor_id=None):
    """Crea o reescribe una fórmula con sus insumos. Comitea.

    `items` es {insumo_id: cantidad}. Una sola fórmula activa por producto:
    se rechaza al guardar, no al usarla, que es descubrirlo tarde.
    """
    nombre = (nombre or '').strip()
    if not nombre:
        raise FormulaInvalida('La fórmula necesita un nombre')
    if producto_id is None or db.session.get(Producto, producto_id) is None:
        raise FormulaInvalida('Elegí un producto válido')
    base = _dec(base_kg)
    if base <= CERO:
        raise FormulaInvalida('La base en kg tiene que ser positiva')
    limpios = {}
    for insumo_id, cantidad in (items or {}).items():
        cantidad = _dec(cantidad)
        if cantidad <= CERO:
            continue
        if db.session.get(Insumo, insumo_id) is None:
            raise FormulaInvalida(f'El insumo {insumo_id} no existe')
        limpios[insumo_id] = cantidad
    if not limpios:
        raise FormulaInvalida('La fórmula necesita al menos un insumo con cantidad')
    if activa:
        otra = (Formula.query
                .filter(Formula.producto_id == producto_id, Formula.activa.is_(True)))
        if formula is not None:
            otra = otra.filter(Formula.id != formula.id)
        if otra.first():
            raise FormulaInvalida('Ese producto ya tiene una fórmula activa: '
                                  'desactivá la otra o editala')
    try:
        if formula is None:
            formula = Formula(creada_por=vendedor_id)
            db.session.add(formula)
        formula.producto_id = producto_id
        formula.nombre = nombre
        formula.base_kg = base
        formula.activa = bool(activa)
        db.session.flush()
        formula.insumos.clear()
        db.session.flush()
        for insumo_id, cantidad in limpios.items():
            formula.insumos.append(FormulaInsumo(insumo_id=insumo_id, cantidad=cantidad))
        db.session.commit()
        return formula
    except Exception:
        db.session.rollback()
        raise


def consumo_teorico(formula, kg_producidos):
    """Cuánto debería consumirse de cada insumo para producir esos kilos."""
    kg_producidos = _dec(kg_producidos)
    base = _dec(formula.base_kg)
    if base <= CERO:
        raise ValueError('La base de la fórmula debe ser positiva')
    factor = kg_producidos / base
    return {item.insumo_id: (_dec(item.cantidad) * factor).quantize(MILESIMA)
            for item in formula.insumos}


# --------------------------------------------------------------- lotes


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
    """{insumo_id: Decimal} con solo lo positivo. Un insumo inexistente es
    error; cero o vacío es «no se usó» y se omite."""
    limpios = {}
    for insumo_id, cantidad in (consumos or {}).items():
        cantidad = _dec(cantidad)
        if cantidad < CERO:
            raise LoteInvalido('El consumo de un insumo no puede ser negativo')
        if cantidad == CERO:
            continue
        if db.session.get(Insumo, insumo_id) is None:
            raise LoteInvalido(f'El insumo {insumo_id} no existe')
        limpios[insumo_id] = cantidad
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
    teórico contra la fórmula y el peso producido actuales."""
    teoricos = {}
    if lote.formula and _dec(lote.peso_producido) > CERO:
        teoricos = consumo_teorico(lote.formula, lote.peso_producido)

    lote.consumos.clear()
    lote.mermas.clear()
    db.session.flush()
    for insumo_id, cantidad in consumos.items():
        lote.consumos.append(LoteConsumo(
            insumo_id=insumo_id,
            cantidad_teorica=teoricos.get(insumo_id, CERO),
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
    formula = formula_para(producto_id)
    try:
        nuevo = LoteProduccion(
            codigo=siguiente_codigo(fecha_produccion.year),
            producto_id=producto_id,
            formula_id=formula.id if formula else None,
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
    el producto, la fórmula se vuelve a resolver: la del nuevo producto.
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
            formula = formula_para(lote.producto_id)
            lote.formula_id = formula.id if formula else None
        elif lote.formula_id is None:
            # Un producto que recibió fórmula después de abrir el lote: se
            # engancha ahora, para que el teórico exista al cerrar.
            formula = formula_para(lote.producto_id)
            lote.formula_id = formula.id if formula else None
        lote.lote = numero
        lote.fecha_produccion = cabecera['fecha_produccion']
        lote.fecha_vencimiento = cabecera.get('fecha_vencimiento')
        lote.peso_producido = peso
        lote.unidades_producidas = cabecera.get('unidades_producidas')
        lote.cajas_producidas = cabecera.get('cajas_producidas')
        lote.notas = (cabecera.get('notas') or '').strip() or None
        db.session.flush()
        # `lote.formula` puede estar cacheada con el id viejo: se expira
        # para que el teórico salga de la fórmula que acaba de quedar.
        db.session.expire(lote, ['formula'])
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
                           'menos un insumo en kg')
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
    kilos: sumarla daría un número que no es nada."""
    return sum((_dec(c.cantidad_real) for c in lote.consumos
                if c.insumo and c.insumo.unidad == UNIDAD_PESO), CERO)


def balance(lote):
    """Todo lo que se deriva de un lote, en un dict listo para pantalla,
    reporte y Excel. Nada de esto se guarda.

    - merma_total: consumido en kg − producido. Negativa si el producto
      pesa más que lo que entró (inyección de salmuera que no se declaró
      como insumo, por ejemplo): se muestra tal cual, no se esconde.
    - merma_identificada: la suma de las mermas declaradas.
    - merma_sin_identificar: total − identificada. Es la cifra que vale
      la pena mirar: lo que nadie supo explicar.
    - rendimiento_pct: producido / consumido × 100.
    - varianzas: por insumo, teórico de la fórmula contra lo real.
    """
    consumido = consumo_en_peso(lote)
    producido = _dec(lote.peso_producido)
    otras_unidades = sorted({c.insumo.unidad for c in lote.consumos
                             if c.insumo and c.insumo.unidad != UNIDAD_PESO})
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
            'insumo_id': consumo.insumo_id,
            'insumo': consumo.insumo.nombre if consumo.insumo else '—',
            'unidad': consumo.insumo.unidad if consumo.insumo else 'kg',
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
