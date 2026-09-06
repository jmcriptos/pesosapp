"""Lógica de negocio del módulo de maquila.

Funciones puras sobre la sesión de SQLAlchemy: reciben ids, devuelven objetos o
Decimals. La mayoría NO hace commit — queda a cargo de quien llama, para que
una operación compuesta quepa en una sola transacción. Las cuatro excepciones,
que sí comitean (y hacen su propio rollback ante un error), porque cada una ES
la transacción completa de su caso de uso: `crear_recepcion`, `abrir_corrida`,
`cerrar_corrida` y `asignar_cajas`.
"""
from datetime import date as _date, datetime
from decimal import Decimal

from sqlalchemy import and_, case, func

from . import app_module
from .models import (Ingrediente, MovimientoIngrediente, RecepcionIngrediente,
                     RecepcionLinea, RecepcionFoto, Receta,
                     CorridaProduccion, CorridaCaja, CorridaConsumo,
                     CorridaConsumoOrigen)

# NO reemplazar por `from app import db, CajaPesada`: revienta `python app.py`
# (el preview local) con un ImportError circular. Ver el comentario largo en
# maquila/__init__.py para el porqué.
db = app_module.db
CajaPesada = app_module.CajaPesada

TIPOS_NEGATIVOS = {'salida'}
TIPOS_CON_MOTIVO = {'ajuste', 'devolucion'}
CERO = Decimal('0')


class MotivoRequerido(ValueError):
    """Un ajuste o una devolución sin motivo no es auditable."""


def _dec(valor):
    return valor if isinstance(valor, Decimal) else Decimal(str(valor or 0))


def _entero_no_negativo(valor):
    """Cantidad de bultos: entero, nunca negativo. Vacío o basura → 0."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


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


def saldos_por_linea(linea_ids):
    """Saldo de varias líneas en UNA consulta: {linea_id: Decimal}.

    Una línea sin movimientos sale en 0, igual que en `saldo_de_linea`. Es
    la versión en lote para las pantallas y guardas que antes preguntaban
    línea por línea (FIFO, saldos, detalle y edición de recepción).
    """
    ids = {i for i in linea_ids if i is not None}
    saldos = {i: CERO for i in ids}
    if not ids:
        return saldos
    filas = (db.session.query(MovimientoIngrediente.recepcion_linea_id,
                              func.sum(MovimientoIngrediente.cantidad))
             .filter(MovimientoIngrediente.recepcion_linea_id.in_(ids))
             .group_by(MovimientoIngrediente.recepcion_linea_id)
             .all())
    for linea_id, total in filas:
        saldos[linea_id] = _dec(total)
    return saldos


def saldo_cliente_ingrediente(cliente_id, ingrediente_id):
    total = (db.session.query(func.sum(MovimientoIngrediente.cantidad))
             .filter(MovimientoIngrediente.cliente_id == cliente_id,
                     MovimientoIngrediente.ingrediente_id == ingrediente_id)
             .scalar())
    return _dec(total)


def ajustes_manuales_de_cliente(cliente_id):
    """Los ajustes manuales (`origen_tipo='manual'`) ya registrados de ese
    cliente, más reciente primero. Es lo que la pantalla de ajustes muestra
    para que el operario vea lo que ya se hizo, no solo el formulario para
    hacer uno nuevo."""
    return (MovimientoIngrediente.query
            .filter_by(cliente_id=cliente_id, tipo='ajuste', origen_tipo='manual')
            .order_by(MovimientoIngrediente.registrado_en.desc(),
                      MovimientoIngrediente.id.desc())
            .all())


def saldos_de_cliente(cliente_id):
    """Una fila por ingrediente con movimiento, desglosando entradas y salidas.

    Una sola consulta con sumas condicionales, no cuatro: el índice de
    maquila la corre una vez por cliente y cada tarjeta pagaba cuatro viajes.
    `recibido` cuenta solo las `entrada` positivas, `consumido` es el valor
    absoluto de las `salida`, y `ajustes` suma ajustes y devoluciones.
    """
    mov = MovimientoIngrediente
    filas = (db.session.query(
                mov.ingrediente_id,
                Ingrediente.nombre,
                Ingrediente.unidad,
                func.sum(case((and_(mov.tipo == 'entrada', mov.cantidad > 0),
                               mov.cantidad), else_=0)).label('recibido'),
                func.sum(case((mov.tipo == 'salida', mov.cantidad),
                              else_=0)).label('salidas'),
                func.sum(case((mov.tipo.in_(('ajuste', 'devolucion')),
                               mov.cantidad), else_=0)).label('ajustes'),
                # Una corrección de recepción también es `tipo='ajuste'`,
                # pero para quien lee el saldo es otra cosa: la cantidad
                # recibida cambió, no hubo un ajuste de inventario. Se
                # separa por `origen_tipo`.
                func.sum(case((and_(mov.tipo == 'ajuste',
                                    mov.origen_tipo == 'recepcion'),
                               mov.cantidad), else_=0)).label('correcciones'),
                func.sum(mov.cantidad).label('saldo'))
             .join(Ingrediente, Ingrediente.id == mov.ingrediente_id)
             .filter(mov.cliente_id == cliente_id)
             .group_by(mov.ingrediente_id, Ingrediente.nombre, Ingrediente.unidad)
             .order_by(Ingrediente.nombre)
             .all())

    return [{
        'ingrediente_id': ingrediente_id,
        'ingrediente': nombre,
        'unidad': unidad,
        'recibido': _dec(recibido),
        'consumido': abs(_dec(salidas)),
        'correcciones': _dec(correcciones),
        'ajustes': _dec(ajustes) - _dec(correcciones),
        'saldo': _dec(saldo),
    } for ingrediente_id, nombre, unidad, recibido, salidas, ajustes, correcciones, saldo in filas]


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
                      RecepcionLinea.anulada_en.is_(None),
                      RecepcionLinea.ingrediente_id == ingrediente_id)
              .order_by(RecepcionIngrediente.recibido_en.asc(),
                        RecepcionLinea.id.asc())
              .all())
    saldos = saldos_por_linea(l.id for l in lineas)
    return [(linea, saldos[linea.id]) for linea in lineas
            if saldos[linea.id] > CERO]


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
    if cliente_id is None:
        raise RecepcionInvalida('La recepción necesita un cliente válido')
    if recibido_en is None:
        raise RecepcionInvalida('La recepción necesita una fecha de recepción válida')
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
            # `cantidad_bultos` es cuántos paquetes llegaron; el peso total se
            # escribe aparte. Dos números independientes: uno no calcula al
            # otro. Antes el campo era la lista de pesos de cada bulto y en
            # planta escribían la cantidad, dejando un bulto de 9 kg en una
            # línea de 121,32.
            if not datos.get('ingrediente_id'):
                raise RecepcionInvalida('Cada línea necesita un ingrediente')
            cantidad_bultos = _entero_no_negativo(datos.get('cantidad_bultos'))
            peso_total = _dec(datos.get('peso_total'))
            if peso_total <= CERO:
                raise RecepcionInvalida(
                    'Cada línea necesita un peso total positivo')

            linea = RecepcionLinea(
                recepcion_id=recepcion.id,
                ingrediente_id=datos['ingrediente_id'],
                lote_cliente=(datos.get('lote_cliente') or None),
                fecha_vencimiento=datos.get('fecha_vencimiento'),
                cantidad_bultos=cantidad_bultos,
                peso_total=peso_total,
            )
            db.session.add(linea)
            db.session.flush()

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

    # Filtrar las líneas anuladas (quitadas desde `editar_recepcion`) en LOS
    # DOS bucles: quitar una línea ya escribió su inverso y la dejó en saldo
    # 0 sin tocar `peso_total`, así que comparar contra `peso_total` para una
    # línea anulada compara 0 contra su peso original y siempre da falso —
    # `RecepcionConsumida` disparando por algo que nunca se consumió, y la
    # recepción queda imposible de anular. Y si esta guarda se relajara, el
    # segundo bucle escribiría un segundo inverso sobre la línea ya anulada,
    # dejando el saldo en negativo.
    vivas = [l for l in recepcion.lineas if not l.anulada]
    saldos = saldos_por_linea(l.id for l in vivas)

    for linea in vivas:
        if saldos[linea.id] != _dec(linea.peso_total):
            raise RecepcionConsumida(
                f'La línea {linea.id} de {recepcion.codigo} ya se consumió; '
                f'la corrección a esta altura es un ajuste, no una anulación')

    for linea in vivas:
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


class RecepcionNoEditable(Exception):
    """La recepción está anulada: no hay nada que corregir."""


class CorreccionImposible(ValueError):
    """La corrección pedida dejaría el rastro en un estado imposible.

    Corregir por debajo de lo ya consumido, quitar una línea que ya alimentó
    una corrida, o mover a otro cliente una recepción de la que ya se consumió.
    """


def consumido_de_linea(linea):
    """Cuánto salió ya de esta línea hacia corridas de producción."""
    return _dec(linea.peso_total) - saldo_de_linea(linea.id)


def consumidos_por_linea(lineas):
    """`consumido_de_linea` para varias líneas en una consulta: {id: Decimal}."""
    lineas = list(lineas)
    saldos = saldos_por_linea(l.id for l in lineas)
    return {l.id: _dec(l.peso_total) - saldos[l.id] for l in lineas}


def editar_recepcion(recepcion, *, vendedor_id, cabecera, lineas, motivo=None,
                     fotos_a_borrar=None, fotos_nuevas=None,
                     firma=None, firma_mimetype=None):
    """Corrige una recepción en una sola transacción.

    `peso_total` pasa al valor real Y se escribe un ajuste por la diferencia,
    de modo que `peso_total − consumido == saldo_de_linea` se mantiene: es la
    identidad de la que cuelga el FIFO. El ledger sigue append-only.

    Solo se escribe movimiento para las líneas cuya cantidad cambió. Sin eso,
    cada guardado dejaría un ajuste de cero por línea y el kardex —el único
    reporte que hoy le sirve a un auditor— se volvería ilegible.
    """
    if recepcion.anulada:
        raise RecepcionNoEditable(
            f'{recepcion.codigo} está anulada: no se puede editar')

    # `registrar_movimiento` recibe `cliente_id` explícito, así que la
    # compensación de más abajo no puede depender de `recepcion.cliente_id`
    # mientras el bucle de cabecera lo está reasignando: hay que leer el
    # viejo ACÁ, antes de que nada lo pise.
    cliente_viejo = recepcion.cliente_id

    vivas = [l for l in recepcion.lineas if not l.anulada]
    consumidas = consumidos_por_linea(vivas)
    hay_consumo = any(c > CERO for c in consumidas.values())

    # --- Guardas: todas antes de escribir nada ---
    nuevo_cliente = cabecera.get('cliente_id')
    # `None` en `cliente_id`/`recibido_en` significa "no tocar" (columnas NOT
    # NULL, y la ruta siempre manda las seis claves de cabecera aunque el
    # campo no haya cambiado o el parseo haya fallado): la escritura de abajo
    # tiene que leer esto mismo, o un `None` que acá no cuenta como cambio
    # terminaría poniendo NULL en una columna que no lo admite.
    cambia_cliente = nuevo_cliente is not None and nuevo_cliente != cliente_viejo
    if cambia_cliente and hay_consumo:
        raise CorreccionImposible(
            f'{recepcion.codigo} ya alimentó una corrida: cambiarle el cliente '
            f'movería carne de un cliente a otro')

    por_id = {l.id: l for l in vivas}
    planes = []
    vistos = set()
    for datos in lineas:
        linea_id = datos.get('id')
        if linea_id is None:
            planes.append(('nueva', None, datos))
            continue
        # Un `id` repetido en el POST (dos entradas para la misma línea, la
        # segunda con `linea_quitar_<id>` marcado) escribiría su inverso dos
        # veces y dejaría `saldo_de_linea` en negativo: se rechaza acá,
        # ANTES de la primera escritura, no se deduplica en silencio.
        if linea_id in vistos:
            raise CorreccionImposible(
                f'La línea {linea_id} aparece más de una vez en la corrección: '
                f'un id duplicado escribiría su inverso dos veces')
        vistos.add(linea_id)
        linea = por_id.get(linea_id)
        if linea is None:
            raise CorreccionImposible(
                f'La línea {linea_id} no pertenece a {recepcion.codigo}')

        if datos.get('quitar'):
            if consumidas[linea.id] > CERO:
                raise CorreccionImposible(
                    f'La línea {linea.id} ya cedió {consumidas[linea.id]} a una '
                    f'corrida: se corrige su cantidad, no se quita')
            planes.append(('quitar', linea, datos))
            continue

        # Cambiar el ingrediente de una línea ya consumida es tan corrupto
        # como cambiarle el cliente: el kilo ya salió hacia una corrida bajo
        # el ingrediente viejo, y no hay forma honesta de reescribir eso.
        # Con la línea intacta, se acepta y se compensa igual que el cliente.
        nuevo_ingrediente_id = datos.get('ingrediente_id')
        cambia_ingrediente = (nuevo_ingrediente_id is not None
                              and nuevo_ingrediente_id != linea.ingrediente_id)
        if cambia_ingrediente and consumidas[linea.id] > CERO:
            raise CorreccionImposible(
                f'La línea {linea.id} ya cedió {consumidas[linea.id]} a una '
                f'corrida: no se puede cambiar de ingrediente')

        # `cantidad_bultos` y `peso_total` son independientes: la cantidad no
        # calcula el peso ni al revés. Toda la maquinaria que decidía «quién
        # manda» entre los dos —tres intentos, uno imposible de cumplir y otro
        # que dependía del JS— desapareció con el cambio de significado.
        cantidad_bultos = _entero_no_negativo(datos.get('cantidad_bultos'))
        nuevo_peso = _dec(datos.get('peso_total'))
        if nuevo_peso <= CERO:
            raise RecepcionInvalida(
                f'La línea {linea.id} necesita una cantidad positiva; '
                f'para dejarla en cero, quitala')
        if nuevo_peso < consumidas[linea.id]:
            raise CorreccionImposible(
                f'La línea {linea.id} ya cedió {consumidas[linea.id]} a una '
                f'corrida: no se puede corregir a {nuevo_peso}')
        planes.append(('editar', linea, {**datos, '_peso': nuevo_peso,
                                         '_bultos_cant': cantidad_bultos,
                                         '_cambia_ingrediente': cambia_ingrediente}))

    cambia_cantidad = any(
        (accion == 'quitar') or
        (accion == 'editar' and (datos['_peso'] != _dec(linea.peso_total)
                                 or datos['_cambia_ingrediente']))
        for accion, linea, datos in planes)
    if cambia_cantidad and not (motivo or '').strip():
        raise MotivoRequerido(
            'Corregir una cantidad o el ingrediente exige un motivo')

    # --- Escritura ---
    try:
        for campo in ('cliente_id', 'recibido_en', 'documento_cliente',
                      'temperatura', 'transportista', 'notas'):
            if campo not in cabecera:
                continue
            valor = cabecera[campo]
            if campo in ('cliente_id', 'recibido_en'):
                if valor is None:
                    continue
                setattr(recepcion, campo, valor)
                continue
            if campo == 'temperatura' and valor not in (None, ''):
                valor = _dec(valor)
            setattr(recepcion, campo, valor or None
                    if campo in ('documento_cliente', 'transportista', 'notas')
                    else valor)

        if cambia_cliente:
            # Compensación en el ledger, no prohibición del cambio: por cada
            # línea viva se escribe un `ajuste` de -peso_total contra el
            # cliente VIEJO y una `entrada` de +peso_total contra el NUEVO,
            # ambos anclados a la misma `recepcion_linea_id`. El saldo de
            # línea no se mueve (-peso +peso sobre la misma línea); lo que
            # cambia es a qué cliente pertenece. Usa `linea.peso_total` tal
            # cual está AHORA, antes de que el bucle de abajo lo corrija —
            # si la cantidad también cambia en este mismo pedido, esa
            # corrección se escribe aparte, ya contra el cliente nuevo.
            motivo_migracion = (f'Recepción {recepcion.codigo} movida del '
                               f'cliente {cliente_viejo} al {nuevo_cliente}'
                               + (f': {motivo.strip()}'
                                  if (motivo or '').strip() else ''))
            for linea_viva in vivas:
                registrar_movimiento(
                    cliente_id=cliente_viejo,
                    ingrediente_id=linea_viva.ingrediente_id,
                    tipo='ajuste', cantidad=-_dec(linea_viva.peso_total),
                    origen_tipo='recepcion', origen_id=recepcion.id,
                    vendedor_id=vendedor_id, recepcion_linea_id=linea_viva.id,
                    motivo=motivo_migracion)
                registrar_movimiento(
                    cliente_id=nuevo_cliente,
                    ingrediente_id=linea_viva.ingrediente_id,
                    tipo='entrada', cantidad=_dec(linea_viva.peso_total),
                    origen_tipo='recepcion', origen_id=recepcion.id,
                    vendedor_id=vendedor_id, recepcion_linea_id=linea_viva.id)

        for accion, linea, datos in planes:
            if accion == 'quitar':
                registrar_movimiento(
                    cliente_id=recepcion.cliente_id,
                    ingrediente_id=linea.ingrediente_id,
                    tipo='ajuste', cantidad=-_dec(linea.peso_total),
                    origen_tipo='recepcion', origen_id=recepcion.id,
                    vendedor_id=vendedor_id, recepcion_linea_id=linea.id,
                    motivo=f'Línea quitada de {recepcion.codigo}: {motivo.strip()}')
                linea.anulada_en = datetime.utcnow()

            elif accion == 'editar':
                linea.lote_cliente = datos.get('lote_cliente') or None
                linea.fecha_vencimiento = datos.get('fecha_vencimiento')
                anterior = _dec(linea.peso_total)
                nuevo = datos['_peso']

                if datos['_cambia_ingrediente']:
                    # Mismo patrón que el cambio de cliente: ajuste -peso
                    # contra el ingrediente viejo, entrada +peso contra el
                    # nuevo, ambos con la misma `recepcion_linea_id`. Usa
                    # `anterior` (el peso ANTES de este mismo guardado): si
                    # la cantidad también cambia acá, esa diferencia se
                    # escribe después, ya contra el ingrediente nuevo.
                    ingrediente_viejo = linea.ingrediente_id
                    ingrediente_nuevo = datos['ingrediente_id']
                    registrar_movimiento(
                        cliente_id=recepcion.cliente_id,
                        ingrediente_id=ingrediente_viejo,
                        tipo='ajuste', cantidad=-anterior,
                        origen_tipo='recepcion', origen_id=recepcion.id,
                        vendedor_id=vendedor_id, recepcion_linea_id=linea.id,
                        motivo=(f'Línea de {recepcion.codigo} reasignada del '
                               f'ingrediente {ingrediente_viejo} al '
                               f'{ingrediente_nuevo}: {motivo.strip()}'))
                    registrar_movimiento(
                        cliente_id=recepcion.cliente_id,
                        ingrediente_id=ingrediente_nuevo,
                        tipo='entrada', cantidad=anterior,
                        origen_tipo='recepcion', origen_id=recepcion.id,
                        vendedor_id=vendedor_id, recepcion_linea_id=linea.id)
                    linea.ingrediente_id = ingrediente_nuevo

                linea.cantidad_bultos = datos['_bultos_cant']
                if nuevo != anterior:
                    linea.peso_total = nuevo
                    registrar_movimiento(
                        cliente_id=recepcion.cliente_id,
                        ingrediente_id=linea.ingrediente_id,
                        tipo='ajuste', cantidad=(nuevo - anterior),
                        origen_tipo='recepcion', origen_id=recepcion.id,
                        vendedor_id=vendedor_id, recepcion_linea_id=linea.id,
                        motivo=(f'Corrección de {recepcion.codigo}: '
                                f'{anterior} → {nuevo}. {motivo.strip()}'))

            else:  # nueva
                peso_total = _dec(datos.get('peso_total'))
                if peso_total <= CERO:
                    raise RecepcionInvalida(
                        'Una línea nueva necesita un peso total positivo')
                nueva = RecepcionLinea(
                    recepcion_id=recepcion.id,
                    ingrediente_id=datos['ingrediente_id'],
                    lote_cliente=datos.get('lote_cliente') or None,
                    fecha_vencimiento=datos.get('fecha_vencimiento'),
                    cantidad_bultos=_entero_no_negativo(datos.get('cantidad_bultos')),
                    peso_total=peso_total)
                db.session.add(nueva)
                db.session.flush()
                registrar_movimiento(
                    cliente_id=recepcion.cliente_id,
                    ingrediente_id=nueva.ingrediente_id,
                    tipo='entrada', cantidad=peso_total,
                    origen_tipo='recepcion', origen_id=recepcion.id,
                    vendedor_id=vendedor_id, recepcion_linea_id=nueva.id)

        for foto_id in (fotos_a_borrar or []):
            foto = db.session.get(RecepcionFoto, foto_id)
            if foto is not None and foto.recepcion_id == recepcion.id:
                db.session.delete(foto)

        for imagen, mimetype in (fotos_nuevas or []):
            db.session.add(RecepcionFoto(
                recepcion_id=recepcion.id, imagen=imagen, mimetype=mimetype))

        if firma is not None:
            recepcion.firma = firma
            recepcion.firma_mimetype = firma_mimetype

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
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
    if fecha_produccion is None:
        raise CorridaInvalida('La corrida necesita una fecha de producción válida')

    repetido = CorridaProduccion.query.filter_by(
        cliente_id=cliente_id, lote=lote).first()
    if repetido:
        raise CorridaInvalida(
            f'El cliente ya tiene la corrida {repetido.codigo} con el lote {lote}')

    if receta_id is None:
        sugerida = receta_activa(producto_id, cliente_id)
        receta_id = sugerida.id if sugerida else None

    try:
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
    except Exception:
        db.session.rollback()
        raise


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


def cerrar_corrida(corrida, consumos_reales, vendedor_id, reparto_manual=None,
                   firma=None, firma_mimetype=None):
    """Cierra la corrida: snapshot del teórico, reparto FIFO y salidas del ledger.

    Todo en una transacción: si algo falla a mitad de camino (saldo
    insuficiente, un reparto manual inválido), se hace rollback acá mismo y
    no queda ni un `CorridaConsumo` ni un movimiento colgando. Mismo contrato
    que `crear_recepcion`.

    NOTA: `reparto_manual` todavía no lo usa ninguna ruta — `corrida_cerrar`
    en routes.py siempre llama con el reparto en None, y el reparto FIFO
    automático es el único camino real hoy. La UI para que un operario edite
    el reparto a mano está pendiente de decisión; hasta que exista, esta
    rama solo corre desde los tests.
    """
    if corrida.estado != 'abierta':
        raise CorridaInvalida(f'La corrida {corrida.codigo} no está abierta')
    if not corrida.cajas:
        raise CorridaInvalida('No se puede cerrar una corrida sin cajas producidas')
    if not consumos_reales:
        raise CorridaInvalida('Hay que declarar el consumo de al menos un ingrediente')
    if all(_dec(c) <= CERO for c in consumos_reales.values()):
        raise CorridaInvalida(
            'El consumo declarado tiene que tener al menos una cantidad positiva')

    try:
        producido = corrida.peso_producido
        teoricos = {}
        if corrida.receta:
            teoricos = consumo_teorico(corrida.receta, producido)

        reparto_manual = reparto_manual or {}

        # Validar el reparto_manual completo ANTES de tocar la sesión, y
        # acumulando por línea a lo largo de TODOS los ingredientes del
        # cierre: en este punto todavía no se escribió ningún movimiento, así
        # que `saldo_de_linea` siempre devuelve el saldo inicial. Si se
        # comparara tramo por tramo, dos tramos contra la misma línea (del
        # mismo ingrediente o de dos distintos) podrían pasar cada uno por
        # separado y entre los dos sobregirarla.
        if reparto_manual:
            lineas_por_id = {}
            solicitado_por_linea = {}
            for ingrediente_id, tramos_manual in reparto_manual.items():
                for linea_id, tramo in tramos_manual:
                    tramo = _dec(tramo)
                    if tramo <= CERO:
                        raise CorridaInvalida(
                            f'El tramo del reparto manual contra la línea {linea_id} '
                            f'del ingrediente {ingrediente_id} tiene que ser positivo '
                            f'(llegó {tramo}): un tramo negativo o cero deja la suma '
                            'del reparto cuadrando con el consumo pero anota salidas '
                            'de más en el ledger')
                    linea = lineas_por_id.get(linea_id)
                    if linea is None:
                        linea = db.session.get(RecepcionLinea, linea_id)
                        if linea is None:
                            raise CorridaInvalida(
                                f'La línea {linea_id} del reparto manual no existe')
                        lineas_por_id[linea_id] = linea
                    if linea.recepcion.cliente_id != corrida.cliente_id:
                        raise CorridaInvalida(
                            f'La línea {linea_id} del reparto manual no es del cliente '
                            f'de la corrida ({corrida.cliente_id})')
                    if linea.ingrediente_id != ingrediente_id:
                        raise CorridaInvalida(
                            f'La línea {linea_id} del reparto manual es del ingrediente '
                            f'{linea.ingrediente_id}, no del {ingrediente_id} declarado')
                    solicitado_por_linea[linea_id] = (
                        solicitado_por_linea.get(linea_id, CERO) + tramo)

            for linea_id, total_pedido in solicitado_por_linea.items():
                saldo = saldo_de_linea(linea_id)
                if total_pedido > saldo:
                    raise SaldoInsuficiente(
                        lineas_por_id[linea_id].ingrediente_id, total_pedido, saldo)

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
        if firma:
            corrida.firma_cierre = firma
            corrida.firma_cierre_mimetype = firma_mimetype or 'image/png'
        db.session.commit()
        return corrida
    except Exception:
        db.session.rollback()
        raise


UNIDAD_PESO = 'kg'


def consumo_en_peso(corrida):
    """Suma SOLO los consumos denominados en peso.

    Una receta de chorizo lleva tripa, que se cuenta en unidades. Sumar 78 kg
    de carne con 120 tripas da un número que no es nada, y ese número
    alimentaba la merma y el reporte de rendimiento. Los ingredientes que no
    se miden en peso se siguen descontando del saldo (el ledger es correcto);
    lo que no hacen es participar de un balance de kilos.
    """
    return sum((_dec(c.cantidad_real) for c in corrida.consumos
                if c.ingrediente and c.ingrediente.unidad == UNIDAD_PESO), CERO)


def merma_de_corrida(corrida):
    """Kilos consumidos menos kilos producidos. Se deriva, no se guarda."""
    return consumo_en_peso(corrida) - corrida.peso_producido


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


# Las corridas sin vencimiento van al final del orden FEFO. Se usa un coalesce en
# vez de NULLS LAST porque ese modificador no es portable entre SQLite y Postgres
# y cambió de nombre entre versiones de SQLAlchemy.
_SIN_VENCIMIENTO = _date(9999, 12, 31)


class CajaNoDisponible(Exception):
    """La caja producida ya salió en otro pedido o está anulada."""


def cajas_disponibles(cliente_id, producto_id):
    """Cajas producidas del cliente para ese producto, en orden FEFO.

    Vencimiento más próximo primero; a igualdad, la corrida más antigua. Las
    corridas anuladas no cuentan.
    """
    return (CorridaCaja.query
            .join(CorridaProduccion, CorridaProduccion.id == CorridaCaja.corrida_id)
            .filter(CorridaProduccion.cliente_id == cliente_id,
                    CorridaProduccion.producto_id == producto_id,
                    CorridaProduccion.estado != 'anulada',
                    CorridaCaja.caja_pesada_id.is_(None),
                    CorridaCaja.anulada_en.is_(None))
            .order_by(func.coalesce(CorridaProduccion.fecha_vencimiento,
                                    _SIN_VENCIMIENTO).asc(),
                      CorridaProduccion.fecha_produccion.asc(),
                      CorridaCaja.numero.asc())
            .all())


def proponer_fefo(detalle):
    """Las cajas que la app sugiere para esta línea de pedido.

    Solo las que faltan: si ya se pesaron tres a mano y el objetivo son cinco,
    propone dos.
    """
    faltan = detalle.cajas_objetivo - detalle.cajas_pesadas_count
    if faltan <= 0:
        return []
    disponibles = cajas_disponibles(detalle.pedido.cliente_id, detalle.producto_id)
    return disponibles[:faltan]


def asignar_cajas(detalle, corrida_cajas, vendedor_id):
    """Convierte cajas producidas en CajaPesada del pedido.

    Copia peso, lote y fechas desde la corrida: el pesador no re-teclea nada y
    el lote deja de depender de que alguien lo escriba bien. Todo o nada,
    mismo contrato que `crear_recepcion` y `cerrar_corrida`: si una caja del
    medio ya no está disponible, no quedan las anteriores a mitad de camino.
    """
    if not corrida_cajas:
        return []

    try:
        # Consulta directa (no `detalle.cajas_pesadas`): esa relación queda
        # cacheada en memoria desde el primer acceso y las `CajaPesada` de
        # esta función se crean seteando `detalle_pedido_id` a mano, no con
        # `.append()`, así que no la invalida sola. Mismo patrón que
        # `agregar_caja_producida`.
        ultimo = (db.session.query(func.max(CajaPesada.numero))
                  .filter(CajaPesada.detalle_pedido_id == detalle.id)
                  .scalar())
        siguiente = (ultimo + 1) if ultimo else 1

        creadas = []
        for caja in corrida_cajas:
            if not caja.disponible:
                raise CajaNoDisponible(
                    f'La caja {caja.numero} de {caja.corrida.codigo} ya no está disponible')

            pesada = CajaPesada(
                detalle_pedido_id=detalle.id,
                numero=siguiente,
                peso=caja.peso,
                lote=caja.corrida.lote,
                fecha_elaboracion=caja.corrida.fecha_produccion,
                fecha_vencimiento=(caja.corrida.fecha_vencimiento
                                   or caja.corrida.fecha_produccion),
                pesado_por=vendedor_id,
            )
            db.session.add(pesada)
            db.session.flush()

            caja.caja_pesada_id = pesada.id
            creadas.append(pesada)

            # Mismo rastro que `registrar_caja_pesada` en app.py (~línea 8212):
            # sin este evento, una caja que entra al pedido desde producción
            # no deja ni una línea en el historial, a diferencia de las tres
            # rutas equivalentes que sí lo hacen. Va en la misma transacción
            # que la CajaPesada, no como paso aparte.
            app_module._log_pedido_evento(
                detalle.pedido,
                'caja_asignada',
                f'Caja #{siguiente:02d} de {detalle.producto.nombre}: {caja.peso} kg '
                f'(lote {caja.corrida.lote}) asignada desde {caja.corrida.codigo}',
                meta={'detalle_id': detalle.id, 'numero': siguiente,
                      'peso': float(caja.peso), 'lote': caja.corrida.lote,
                      'corrida_id': caja.corrida_id, 'corrida_caja_id': caja.id},
            )
            siguiente += 1

        db.session.commit()
        return creadas
    except Exception:
        db.session.rollback()
        raise
