"""Traduce el payload de `pedido_a_json` al `Invoice` de la API v3 de QBO.

Reemplaza al nodo de código «Generar Numero Factura» de n8n. La copia de ese
nodo está en docs/superpowers/specs/n8n-facturacion-nodo-codigo.js y es la
referencia de cada regla de acá; los números de factura entre paréntesis
(5848, 5863, 5865, 5867…) son los casos medidos en producción que fijaron
cada decisión. Antes de «arreglar» algo, leer ese archivo.

Funciones puras: sin Flask, sin DB, sin red. `siguiente_doc_number` es la
excepción: recibe un cliente y consulta QBO.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# ── constantes medidas contra la empresa real ──────────────────────────────

# Término de pago de QuickBooks (fijo en n8n, no depende del cliente).
QBO_SALES_TERM_ID = '46'
# Vendedor que va en el campo personalizado «Sales Rep».
QBO_SALES_REP = 'OF'
DIAS_VENCIMIENTO = 7

# Texto fijo que el nodo HTTP de n8n pone en el memo del cliente (se imprime
# en la factura). Las `notes` del pedido NO viajan a QBO; así estaba en n8n.
QBO_CUSTOMER_MEMO = (
    'Jomar Foods, BV\n'
    'Crib nr.: 102505329\n'
    'K.V.K.: 148768\n'
    'RBC Account# 8000009000132576'
)

CURRENCY_DISPLAY = {
    'XCG': 'XCG - Caribbean Guilder',
    'ANG': 'XCG - Caribbean Guilder',
    'USD': 'USD - US Dollar',
}

# `Currency2` (DefinitionId 1000000003) es el campo de moneda que SE VE en la
# pantalla de QBO. Es una lista: guarda el id de la opción, no el texto.
# Medido el 2026-09-08: 1 = XCG, 2 = USD, 3 = ANG. Nunca se manda el 3.
# OJO: el POST necesita `include=enhancedAllCustomFields` o QBO lo ignora.
CURRENCY2_OPCION = {'XCG': '1', 'ANG': '1', 'USD': '2'}

# Porcentaje por TaxCode. `tax_rate` es el Id del TaxCode de QBO, no un
# porcentaje. QBO NO calcula el impuesto solo con TxnTaxCodeRef (la 5848
# salió al 0 %): hay que mandar TotalTax y TaxLine. Y el bloque va también
# al 0 %: sin él la factura queda SIN código (5865) y no entra en el reporte
# de OB.
PCT_POR_CODIGO = {
    '10': 6,   # OB 6%
    '11': 9,   # OB 9%
    '13': 0,   # Non Tax (exportación)
    '14': 0,   # OB Non Tax Local Prod
}

# TaxRate: va SIEMPRE '25', para cualquier código.
#
# NO es la que corresponde. Las reales son 17 = OB 6%, 18 = OB 9%,
# 19 = Non Tax, 25 = OB Non Tax Local Prod. Y esa es justamente la gracia:
# QuickBooks no acepta la que le mandamos, recalcula la tasa desde el
# TxnTaxCodeRef y guarda la correcta (la 5863 se mandó con 25 y quedó
# guardada con 17, al 6 %).
#
# Mandarle la 17 «correcta» le rompe el cálculo: la factura sale al 0 % y hay
# que ajustarla a mano. Pasó con la 5867 el 2026-09-08, y fue un cambio hecho
# sobre la teoría de que daba igual. No da igual. No lo vuelvas a «arreglar».
TAX_RATE_REF = '25'

# La empresa está en modo US: el TaxCodeRef DE LÍNEA solo acepta 'TAX' o
# 'NON' (error 6100 con otro valor). Y va TAX siempre: con NON la venta se
# caía del reporte de ventas gravadas y había que marcar cada línea a mano
# (5864). El 0 % lo define el código de la TRANSACCIÓN.
LINEA_GRAVABLE = 'TAX'

# Red de seguridad para líneas sin `class_ref`: la misma tabla de n8n, en el
# mismo orden (la primera coincidencia gana). Sin coincidencia, la línea va
# sin clase y la app ya avisa («se facturaron sin clase de QuickBooks»).
CLASS_KEYWORDS = {
    '600000000005541105': [   # Cocidos y Ahumados
        'smoked', 'ahumad', 'cooked', 'cocid',
        'pork', 'cerdo', 'chop', 'chuleta',
        'bacon', 'tocino', 'ham', 'jamon', 'jamón',
        'chorizo', 'salami', 'sausage', 'salchicha',
        'shoulder', 'picnic', 'ribs', 'costilla',
    ],
    '600000000005391641': [   # Atún Van Camps
        'atun', 'atún', 'tuna',
        'van camps', 'vancamps', 'van camp',
    ],
    '529395': [               # Mantova
        'mantova', 'oil', 'aceite', 'olive', 'oliva',
        'vinegar', 'vinagre', 'balsamic', 'balsamico',
        'extra virgin', 'virgen extra',
    ],
    '600000000005012031': [   # Tomate
        'tomat', 'tomato', 'ketchup', 'catsup',
        'salsa', 'sauce', 'pasta', 'puree', 'pure',
        'puré', 'marinara', 'pomodoro',
    ],
    '600000000005391660': [   # Untables Underwood
        'underwood', 'spread', 'untable', 'pate',
        'paté', 'pâté', 'deviled', 'meat spread',
    ],
}

# ── dinero en Decimal ──────────────────────────────────────────────────────
# QuickBooks revalida Amount == UnitPrice × Qty con redondeo media-arriba y
# rechaza con 6070 si difiere en medio centavo: 128,350 kg × 14,50 son
# 1.861,075 exactos, pero el double da 1.861,0749… y salía 1.861,07 (pedido
# 1334, 2026-09-08). Por eso todo va en Decimal desde el string original y
# nunca pasa por float en el medio.
MILESIMA = Decimal('0.001')   # el peso trae 3 decimales
CENTAVO = Decimal('0.01')     # el precio trae 2


def _dec(valor, cuanto: Decimal) -> Decimal:
    """Decimal a partir del valor tal cual viene (str, int, float), redondeado
    media-arriba a `cuanto`. Se pasa por `str()` para no heredar el ruido
    binario del float."""
    return Decimal(str(valor)).quantize(cuanto, rounding=ROUND_HALF_UP)


def _num(d: Decimal):
    """Número JSON: entero si no tiene decimales, float si los tiene."""
    if d == d.to_integral_value():
        return int(d)
    return float(d)


def _dos_decimales(valor) -> str:
    """`Number(x).toFixed(2)` de n8n: es lo que va en `Description`."""
    return f"{_dec(valor, CENTAVO):.2f}"


# ── clase ─────────────────────────────────────────────────────────────────

def detectar_clase(nombre: Optional[str]) -> Optional[str]:
    """Id de clase de QBO por palabra clave en el nombre, o None."""
    if not nombre:
        return None
    nombre_min = nombre.lower()
    for clase, palabras in CLASS_KEYWORDS.items():
        for palabra in palabras:
            if palabra in nombre_min:
                return clase
    return None


# ── impuesto ──────────────────────────────────────────────────────────────

def _codigo_impuesto(valor) -> str:
    """`String(Number(v))` de n8n: '10', '14'… o '' si no viene."""
    if valor is None or valor == '':
        return ''
    return str(int(Decimal(str(valor))))


def codigo_impuesto_del_payload(payload: dict) -> str:
    """El TaxCode de la factura. Todas las líneas tienen que traer el mismo:
    el grupo de facturación lo garantiza, pero el traductor no confía."""
    lineas = payload.get('lines') or []
    if not lineas:
        raise ValueError('El pedido no tiene líneas para facturar')
    codigos = {_codigo_impuesto(l.get('tax_rate')) for l in lineas}
    if len(codigos) > 1:
        raise ValueError(
            'El pedido mezcla códigos de impuesto: '
            + ', '.join(sorted(c or '(vacío)' for c in codigos))
        )
    codigo = codigos.pop()
    if not codigo:
        raise ValueError('Las líneas no traen código de impuesto de QuickBooks')
    if codigo not in PCT_POR_CODIGO:
        raise ValueError(
            f'Código de impuesto {codigo} desconocido; los válidos son '
            + ', '.join(PCT_POR_CODIGO)
        )
    return codigo


# ── factura ───────────────────────────────────────────────────────────────

def construir_invoice(payload: dict, doc_number: str, hoy: date) -> dict:
    """Body del `POST /invoice` a partir del payload de `pedido_a_json`.

    `hoy` es la fecha local de Curaçao (n8n usaba la UTC del servidor, que
    de tarde ya es mañana; ver n8n-tasa-usd-export.md).
    """
    codigo = codigo_impuesto_del_payload(payload)

    moneda = str(payload.get('currency') or 'XCG').upper()
    currency_display = (
        payload.get('currency_display')
        or CURRENCY_DISPLAY.get(moneda)
        or CURRENCY_DISPLAY['XCG']
    )
    currency2 = CURRENCY2_OPCION.get(moneda, '1')

    factura = {
        'CustomerRef': {'value': str(payload['customer_qbo_id'])},
        'DocNumber': str(doc_number),
        'TxnDate': hoy.isoformat(),
        'DueDate': (hoy + timedelta(days=DIAS_VENCIMIENTO)).isoformat(),
        'SalesTermRef': {'value': QBO_SALES_TERM_ID},
        'GlobalTaxCalculation': 'TaxExcluded',
        'CustomField': [
            {'DefinitionId': '1', 'Name': 'Currency', 'Type': 'StringType',
             'StringValue': currency_display},
            {'DefinitionId': '2', 'Name': 'Sales Rep', 'Type': 'StringType',
             'StringValue': payload.get('sales_rep') or QBO_SALES_REP},
            {'DefinitionId': '3', 'Name': 'Tax ID No.', 'Type': 'StringType',
             'StringValue': payload.get('tax_id') or ''},
            {'DefinitionId': '1000000003', 'Name': 'Currency2',
             'Type': 'StringType', 'StringValue': currency2},
        ],
        'Line': [],
    }

    if payload.get('currency_qbo'):
        factura['CurrencyRef'] = {'value': str(payload['currency_qbo'])}
        tipo_cambio = payload.get('exchange_rate')
        if tipo_cambio:
            factura['ExchangeRate'] = float(tipo_cambio)

    # ── agrupar líneas por (producto, precio), en orden de aparición ──
    grupos: dict = {}
    for linea in payload.get('lines') or []:
        precio = _dec(linea.get('unit_price') or 0, CENTAVO)
        clave = (str(linea.get('product_qbo_id')), precio)
        grupo = grupos.get(clave)
        if grupo is None:
            grupo = {'linea': linea, 'precio': precio,
                     'qty': Decimal('0'), 'descripciones': []}
            grupos[clave] = grupo
        qty = _dec(linea.get('qty') or 0, MILESIMA)
        grupo['qty'] += qty
        grupo['descripciones'].append(_dos_decimales(linea.get('qty') or 0))

    subtotal = Decimal('0')
    for grupo in grupos.values():
        linea = grupo['linea']
        # `descripcion` es como la manda la app; el resto son alias.
        nombre = (linea.get('descripcion') or linea.get('product_name')
                  or linea.get('name') or linea.get('description') or '')
        monto = (grupo['qty'] * grupo['precio']).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        subtotal += monto

        detalle = {
            'ItemRef': {'value': str(linea.get('product_qbo_id')), 'name': nombre},
            'Qty': _num(grupo['qty']),
            'UnitPrice': _num(grupo['precio']),
            'TaxCodeRef': {'value': LINEA_GRAVABLE},
        }
        clase = linea.get('class_ref') or detectar_clase(nombre)
        if clase:
            detalle['ClassRef'] = {'value': str(clase)}

        factura['Line'].append({
            'DetailType': 'SalesItemLineDetail',
            'Description': '\t'.join(grupo['descripciones']),
            'Amount': _num(monto),
            'SalesItemLineDetail': detalle,
        })

    # ── impuesto de la transacción: siempre, también al 0 % ──
    pct = PCT_POR_CODIGO[codigo]
    impuesto = (subtotal * pct / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    factura['TxnTaxDetail'] = {
        'TotalTax': _num(impuesto),
        'TxnTaxCodeRef': {'value': codigo},
        'TaxLine': [{
            'Amount': _num(impuesto),
            'DetailType': 'TaxLineDetail',
            'TaxLineDetail': {
                'TaxPercent': pct,
                'NetAmountTaxable': _num(subtotal),
                'PercentBased': True,
                'TaxRateRef': {'value': TAX_RATE_REF},
            },
        }],
    }

    factura['CustomerMemo'] = {'value': QBO_CUSTOMER_MEMO}
    # No se imprime. Es la única forma de rastrear un duplicado desde QBO.
    factura['PrivateNote'] = f"PesosApp pedido {payload.get('order_id')}"
    return factura
