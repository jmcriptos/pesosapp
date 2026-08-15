# Factura PDF bajo demanda — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el usuario genere el PDF de una factura desde la pantalla del pedido, con los datos vigentes en QuickBooks, y que ese PDF se archive solo en Google Drive.

**Architecture:** Un módulo nuevo `utils/factura_pdf.py` con dos funciones puras — una que normaliza el objeto `Invoice` de QBO a un dict plano, y otra que lo dibuja en PDF con reportlab. `app.py` gana una columna, dos helpers de webhook y una ruta. n8n gana dos webhooks de dos nodos cada uno. La app nunca habla con QuickBooks ni con Drive directamente: siempre a través de n8n, que ya tiene ambas credenciales.

**Tech Stack:** Flask, SQLAlchemy, reportlab 4.2.2 (ya instalado), pytest, n8n Cloud.

## Global Constraints

- Python 3.13, correr tests con `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/ -q` **sin** forzar `DATABASE_URL` (conftest usa sqlite en memoria).
- **No agregar dependencias.** reportlab ya está en `requirements.txt`. No usar pypdf ni ninguna librería de extracción de texto.
- **No usar Alembic.** La cadena de migraciones tiene 5 heads y `flask db upgrade` falla. Los cambios de esquema van por `ALTER TABLE` directo, local y en Heroku, como indica CLAUDE.md.
- Todo texto visible al usuario va en español.
- Los helpers de webhook salientes usan `_webhook_headers()` (ya existe en `app.py`).
- Cualquier `innerHTML` con datos de API usa el helper global `escapeHtml` de `base.js`.
- Al editar `static/js/base.js` hay que regenerar `base.min.js` con `cp static/js/base.js static/js/base.min.js` — es lo que carga `base.html`.
- Manejadores inline en templates están prohibidos: usar convenciones `data-*` como el resto de `base.js`.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `utils/factura_pdf.py` (crear) | Normalizar el `Invoice` de QBO y dibujarlo en PDF. Sin Flask, sin DB, sin red. |
| `tests/test_factura_pdf.py` (crear) | Tests del módulo anterior. |
| `tests/fixtures/facturas/*.json` (crear) | Objetos `Invoice` de QBO para los tests. |
| `app.py` (modificar) | Columna `doc_number_qbo`, helpers `_obtener_factura_qbo` y `_archivar_factura_drive`, ruta `factura_pdf`. |
| `templates/detalles_pedido.html` (modificar) | Botón de factura. |
| `static/js/base.js` (modificar) | Lógica de Web Share con `data-factura-share`. |

---

### Task 1: Persistir el número de factura de QBO

**Files:**
- Modify: `app.py` (modelo `Pedido` ~línea 2231; `facturar_pedido`)
- Test: `tests/test_facturacion_validacion.py`

**Interfaces:**
- Consumes: `_extraer_invoice_id(resp_data) -> (invoice_id, doc_number)` (ya existe)
- Produces: `Pedido.doc_number_qbo` — `String(20)`, nullable

- [ ] **Step 1: Write the failing test**

En `tests/test_facturacion_validacion.py`, junto a `test_lee_invoice_id_del_objeto_invoice_de_qbo`:

```python
@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_persiste_doc_number_al_facturar(mock_post, logged_client, app):
    """El número visible de la factura (DocNumber) se guarda para poder
    nombrar el PDF y mostrarlo sin volver a consultar QuickBooks."""
    from unittest.mock import MagicMock

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        'Invoice': {'Id': '47349', 'DocNumber': '5816'},
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado()

        logged_client.post(f'/pedidos/{pedido_id}/facturar', follow_redirects=True)

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.doc_number_qbo == '5816'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_facturacion_validacion.py::test_persiste_doc_number_al_facturar -q`
Expected: FAIL con `AttributeError: 'Pedido' object has no attribute 'doc_number_qbo'`

- [ ] **Step 3: Add the column to the model**

En `app.py`, en `class Pedido`, justo después de `invoice_id_qbo`:

```python
    invoice_id_qbo = db.Column(db.String(100), nullable=True)
    doc_number_qbo = db.Column(db.String(20), nullable=True)
```

- [ ] **Step 4: Persist it when invoicing**

En `facturar_pedido`, donde se asigna el estado:

```python
    pedido.estado = 'facturado'
    pedido.invoice_id_qbo = invoice_id
    pedido.doc_number_qbo = doc_number
    pedido.fecha_facturacion = datetime.now(timezone.utc)
```

- [ ] **Step 5: Run the full suite**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/ -q`
Expected: todo verde (363 passed esperados)

- [ ] **Step 6: Apply the column in production**

```bash
heroku pg:psql --app pesosapp -c "ALTER TABLE pedido ADD COLUMN IF NOT EXISTS doc_number_qbo VARCHAR(20);"
```

Verificar:

```bash
heroku pg:psql --app pesosapp -c "\d pedido" | grep doc_number
```

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_facturacion_validacion.py
git commit -m "feat(facturacion): persiste doc_number_qbo al facturar"
```

---

### Task 2: Normalizar el Invoice de QBO

**Files:**
- Create: `utils/factura_pdf.py`
- Create: `tests/test_factura_pdf.py`
- Create: `tests/fixtures/facturas/xcg_con_ob.json`, `tests/fixtures/facturas/xcg_sin_ob.json`, `tests/fixtures/facturas/usd.json`

**Interfaces:**
- Produces: `extraer_datos_factura(invoice_json: dict) -> dict` con las claves
  `numero`, `fecha`, `vence`, `terminos`, `cliente`, `direccion` (lista de str),
  `crib`, `moneda` (`'XCG'`/`'USD'`), `moneda_label`, `lineas` (lista de dicts con
  `producto`, `pesos` lista de str, `detalle_texto`, `qty`, `rate`, `amount`),
  `subtotal`, `ob_pct`, `ob`, `total`, `balance`

- [ ] **Step 1: Create the fixtures**

`tests/fixtures/facturas/xcg_con_ob.json` — datos reales de la factura 5811 (Esperamos, importados, OB 6%), recortada a tres líneas:

```json
{
  "Invoice": {
    "Id": "47344",
    "DocNumber": "5811",
    "TxnDate": "2026-08-14",
    "DueDate": "2026-08-21",
    "SalesTermRef": { "value": "46", "name": "Net 7" },
    "CustomerRef": { "value": "1497", "name": "Esperamos Supermarket" },
    "BillAddr": {
      "Line1": "Esperamos Supermarket",
      "City": "Willemstad",
      "CountrySubDivisionCode": "CRIB: 104123456"
    },
    "Line": [
      {
        "Id": "1",
        "Description": "2.00",
        "Amount": 293.34,
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "ItemRef": { "value": "1388", "name": "Untables Underwood:Deviled Ham 32/120 gr" },
          "Qty": 2, "UnitPrice": 146.67
        }
      },
      {
        "Id": "2",
        "Description": "3.00",
        "Amount": 393.24,
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "ItemRef": { "value": "1297", "name": "Atún Van Camps:VCamps Atun en Agua 48x160g" },
          "Qty": 3, "UnitPrice": 131.08
        }
      },
      {
        "Id": "3",
        "Amount": 185.71,
        "DetailType": "SubTotalLineDetail",
        "SubTotalLineDetail": {}
      }
    ],
    "SubTotal": 686.58,
    "TxnTaxDetail": {
      "TotalTax": 41.19,
      "TaxLine": [
        {
          "Amount": 41.19,
          "DetailType": "TaxLineDetail",
          "TaxLineDetail": { "TaxPercent": 6, "NetAmountTaxable": 686.58, "PercentBased": true }
        }
      ]
    },
    "TotalAmt": 727.77,
    "Balance": 727.77
  }
}
```

`tests/fixtures/facturas/xcg_sin_ob.json` — factura 5814 (Centrum, producción local, OB 0%), con el grid de pesos:

```json
{
  "Invoice": {
    "Id": "47347",
    "DocNumber": "5814",
    "TxnDate": "2026-08-14",
    "DueDate": "2026-08-21",
    "SalesTermRef": { "value": "46", "name": "Net 7" },
    "CustomerRef": { "value": "1570", "name": "New Centrum Supermarket, BV" },
    "BillAddr": { "Line1": "Mahaai", "City": "Willemstad" },
    "Line": [
      {
        "Id": "1",
        "Description": "13.50\t12.05",
        "Amount": 868.70,
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "ItemRef": { "value": "1407", "name": "Smoked and Cooked:Smoked Turkey Breast" },
          "Qty": 25.55, "UnitPrice": 34
        }
      },
      {
        "Id": "2",
        "Description": "19.65\t19.60",
        "Amount": 732.01,
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "ItemRef": { "value": "1352", "name": "Smoked and Cooked:Smoked Turkey Ham" },
          "Qty": 39.25, "UnitPrice": 18.65
        }
      }
    ],
    "SubTotal": 1600.71,
    "TxnTaxDetail": { "TotalTax": 0 },
    "TotalAmt": 1600.71,
    "Balance": 1600.71
  }
}
```

`tests/fixtures/facturas/usd.json` — factura 5807 (Caribe Nobo, USD), 6 cajas:

```json
{
  "Invoice": {
    "Id": "47340",
    "DocNumber": "5807",
    "TxnDate": "2026-08-12",
    "DueDate": "2026-08-19",
    "SalesTermRef": { "value": "46", "name": "Net 7" },
    "CustomerRef": { "value": "1473", "name": "Caribe Nobo Supermarkett" },
    "CurrencyRef": { "value": "USD", "name": "United States Dollar" },
    "BillAddr": { "Line1": "Caribe Nobo", "City": "Willemstad" },
    "Line": [
      {
        "Id": "1",
        "Description": "16.80\t18.10\t17.55\t17.80\t17.80\t14.85",
        "Amount": 823.20,
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "ItemRef": { "value": "1351", "name": "Smoked and Cooked:Smoked Pork Chop" },
          "Qty": 102.9, "UnitPrice": 8
        }
      }
    ],
    "SubTotal": 823.20,
    "TxnTaxDetail": { "TotalTax": 0 },
    "TotalAmt": 823.20,
    "Balance": 823.20
  }
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_factura_pdf.py`:

```python
"""Tests del renderizador de facturas PDF.

Los fixtures son objetos Invoice de QuickBooks con datos reales de facturas
emitidas el 2026-08-12 y 2026-08-14.
"""
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures' / 'facturas'


def cargar(nombre):
    return json.loads((FIXTURES / f'{nombre}.json').read_text())


def test_extrae_cabecera_y_cliente():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_con_ob'))

    assert datos['numero'] == '5811'
    assert datos['cliente'] == 'Esperamos Supermarket'
    assert datos['crib'] == '104123456'
    assert datos['moneda'] == 'XCG'
    assert datos['terminos'] == 'Net 7'


def test_extrae_pesos_por_caja_de_la_descripcion():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_sin_ob'))
    linea = datos['lineas'][0]

    assert linea['producto'] == 'Smoked Turkey Breast'
    assert linea['pesos'] == ['13.50', '12.05']
    assert linea['qty'] == 25.55
    assert linea['rate'] == 34


def test_ignora_lineas_que_no_son_de_producto():
    """QBO mete líneas SubTotalLineDetail que no deben aparecer en la tabla."""
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_con_ob'))

    assert len(datos['lineas']) == 2


def test_detecta_usd():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('usd'))

    assert datos['moneda'] == 'USD'
    assert datos['moneda_label'] == 'USD - US Dollar'


def test_ob_cero_cuando_no_hay_impuesto():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_sin_ob'))

    assert datos['ob'] == 0
    assert datos['ob_pct'] == 0
    assert datos['total'] == 1600.71


def test_tolera_factura_sin_direccion():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura({'Invoice': {'Id': '1', 'DocNumber': '9999'}})

    assert datos['numero'] == '9999'
    assert datos['direccion'] == []
    assert datos['crib'] == ''
    assert datos['lineas'] == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_pdf.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'utils.factura_pdf'`

- [ ] **Step 4: Write the implementation**

`utils/factura_pdf.py`:

```python
"""Render de facturas de QuickBooks a PDF.

Dos responsabilidades separadas a propósito: `extraer_datos_factura` normaliza
el objeto Invoice de QBO a un dict plano (testeable con aserciones ricas), y
`render_factura_pdf` lo dibuja (se verifica estructuralmente).

El módulo es puro: sin Flask, sin base de datos, sin red.
"""
import re


def _pick_invoice(src):
    """QBO puede venir envuelto de varias formas según el nodo de n8n."""
    if not src:
        return {}
    if isinstance(src, list):
        src = src[0] if src else {}
    if not isinstance(src, dict):
        return {}
    if isinstance(src.get('Invoice'), dict):
        return src['Invoice']
    query = src.get('QueryResponse') or {}
    if isinstance(query.get('Invoice'), list) and query['Invoice']:
        return query['Invoice'][0]
    return src


def _es_usd(inv):
    ref = inv.get('CurrencyRef') or {}
    texto = f"{ref.get('value') or ''} {ref.get('name') or ''}".upper()
    return 'USD' in texto or 'DOLLAR' in texto


def _pesos_de_descripcion(desc):
    """La descripción de QBO trae los pesos de cada caja separados por
    tabulaciones o espacios. Si tiene letras es una nota, no pesos."""
    if not desc or re.search(r'[A-Za-zÁÉÍÓÚÑáéíóúñ]', desc):
        return []
    pesos = []
    for token in re.split(r'\s+', desc.strip()):
        try:
            valor = float(token)
        except ValueError:
            continue
        if valor > 0:
            pesos.append(f'{valor:.2f}')
    return pesos


def extraer_datos_factura(invoice_json):
    inv = _pick_invoice(invoice_json)
    bill = inv.get('BillAddr') or {}

    lineas = []
    for l in inv.get('Line') or []:
        if l.get('DetailType') != 'SalesItemLineDetail':
            continue
        det = l.get('SalesItemLineDetail') or {}
        nombre = (det.get('ItemRef') or {}).get('name') or ''
        producto = nombre.split(':')[1].strip() if ':' in nombre else nombre
        desc = l.get('Description') or ''
        pesos = _pesos_de_descripcion(desc)
        lineas.append({
            'producto': producto,
            'pesos': pesos,
            'detalle_texto': '' if pesos else desc,
            'qty': float(det.get('Qty') or 0),
            'rate': float(det.get('UnitPrice') or 0),
            'amount': float(l.get('Amount') or 0),
        })

    subtotal = float(inv.get('SubTotal') or 0)
    if not subtotal:
        subtotal = sum(l['amount'] for l in lineas)

    tax = inv.get('TxnTaxDetail') or {}
    ob = float(tax.get('TotalTax') or 0)
    tax_lines = tax.get('TaxLine') or []
    if tax_lines and (tax_lines[0].get('TaxLineDetail') or {}).get('TaxPercent') is not None:
        ob_pct = float(tax_lines[0]['TaxLineDetail']['TaxPercent'])
    elif ob and subtotal:
        ob_pct = (ob / subtotal) * 100
    else:
        ob_pct = 0.0

    total = float(inv.get('TotalAmt') if inv.get('TotalAmt') is not None else subtotal + ob)
    usd = _es_usd(inv)

    direccion = [v for v in (bill.get('Line1'), bill.get('Line2'), bill.get('City')) if v]
    crib = re.sub(r'^CRIB:\s*', '', bill.get('CountrySubDivisionCode') or '', flags=re.I).strip()

    return {
        'numero': str(inv.get('DocNumber') or inv.get('Id') or ''),
        'fecha': inv.get('TxnDate') or '',
        'vence': inv.get('DueDate') or '',
        'terminos': (inv.get('SalesTermRef') or {}).get('name') or '',
        'cliente': (inv.get('CustomerRef') or {}).get('name') or '',
        'direccion': direccion,
        'crib': crib,
        'moneda': 'USD' if usd else 'XCG',
        'moneda_label': 'USD - US Dollar' if usd else 'XCG - Caribbean Guilder',
        'lineas': lineas,
        'subtotal': round(subtotal, 2),
        'ob_pct': ob_pct,
        'ob': round(ob, 2),
        'total': round(total, 2),
        'balance': round(float(inv.get('Balance') if inv.get('Balance') is not None else total), 2),
    }
```

Nota: la dirección excluye `Line1` cuando repite el nombre del cliente — eso se resuelve en el dibujado, no aquí, para que el dict siga siendo un reflejo fiel de QBO.

- [ ] **Step 5: Run test to verify it passes**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_pdf.py -q`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add utils/factura_pdf.py tests/test_factura_pdf.py tests/fixtures/facturas/
git commit -m "feat(factura-pdf): normaliza el objeto Invoice de QuickBooks"
```

---

### Task 3: Dibujar el PDF

**Files:**
- Modify: `utils/factura_pdf.py`
- Test: `tests/test_factura_pdf.py`

**Interfaces:**
- Consumes: `extraer_datos_factura(invoice_json) -> dict` (Task 2)
- Produces: `render_factura_pdf(invoice_json: dict) -> bytes`

- [ ] **Step 1: Write the failing test**

Al final de `tests/test_factura_pdf.py`:

```python
@pytest.mark.parametrize('fixture', ['xcg_con_ob', 'xcg_sin_ob', 'usd'])
def test_render_produce_pdf_valido(fixture):
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf(cargar(fixture))

    assert pdf[:5] == b'%PDF-'
    assert pdf.rstrip()[-5:] == b'%%EOF'
    assert len(pdf) > 2000


def test_render_tolera_factura_minima():
    """Una factura sin líneas ni dirección no debe reventar el render."""
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf({'Invoice': {'Id': '1', 'DocNumber': '9999'}})

    assert pdf[:5] == b'%PDF-'


def test_render_con_muchas_cajas_pagina_extra():
    """20 cajas pesadas (caso real de la factura 5806) genera más de una página."""
    from utils.factura_pdf import render_factura_pdf

    pesos = '\t'.join(f'{12 + i * 0.15:.2f}' for i in range(20))
    factura = {'Invoice': {
        'Id': '47339', 'DocNumber': '5806', 'TxnDate': '2026-08-11',
        'CustomerRef': {'name': 'Mangusa Supermarket na Rio Canario, BV'},
        'Line': [{
            'DetailType': 'SalesItemLineDetail',
            'Description': pesos,
            'Amount': 3339.70,
            'SalesItemLineDetail': {
                'ItemRef': {'name': 'Smoked and Cooked:Smoked Pork Chop'},
                'Qty': 256.9, 'UnitPrice': 13,
            },
        }] * 6,
        'SubTotal': 20038.2, 'TotalAmt': 20038.2,
    }}

    pdf = render_factura_pdf(factura)

    assert pdf.count(b'/Type /Page\n') >= 2 or pdf.count(b'/Type /Page') >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_pdf.py -q -k render`
Expected: FAIL con `ImportError: cannot import name 'render_factura_pdf'`

- [ ] **Step 3: Write the implementation**

Agregar a `utils/factura_pdf.py`:

```python
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

EMPRESA = [
    'JOMAR FOODS, BV',
    'Industriepark Brievengat, Unit H.I.1.',
    'Willemstad, Curacao',
    'WhatsApp: +5999 6905484',
    'sales@jomarfoods.com',
    'www.jomarfoods.com',
]

BANCO = [
    'Jomar Foods, BV',
    'Crib nr.: 102505329',
    'K.V.K.: 148768',
    'RBC Account#: 8000009000132576',
]


def _xe(s):
    """Escapa para Paragraph de reportlab, que interpreta markup tipo XML."""
    return (str(s or '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _money(n):
    return f'{float(n or 0):,.2f}'


def _pct(p):
    return str(round(p)) if abs(p - round(p)) < 0.05 else f'{p:.1f}'


def _grid_pesos(pesos, estilo):
    """Los pesos de cada caja en 5 columnas, como el HTML."""
    filas = [pesos[i:i + 5] for i in range(0, len(pesos), 5)]
    filas = [f + [''] * (5 - len(f)) for f in filas]
    tabla = Table(
        [[Paragraph(_xe(c), estilo) for c in fila] for fila in filas],
        colWidths=[12 * mm] * 5,
    )
    tabla.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    return tabla


def render_factura_pdf(invoice_json):
    d = extraer_datos_factura(invoice_json)

    base = getSampleStyleSheet()
    st_normal = ParagraphStyle('n', parent=base['Normal'], fontName='Helvetica',
                               fontSize=8, leading=10)
    st_bold = ParagraphStyle('b', parent=st_normal, fontName='Helvetica-Bold')
    st_small = ParagraphStyle('s', parent=st_normal, fontSize=7, leading=9)
    st_titulo = ParagraphStyle('t', parent=st_normal, fontName='Helvetica-Bold',
                               fontSize=22, alignment=TA_RIGHT)
    st_empresa = ParagraphStyle('e', parent=st_normal, fontName='Helvetica-Bold',
                                fontSize=11)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f'Invoice {d["numero"]}',
    )

    flow = []

    # Encabezado: empresa a la izquierda, título a la derecha
    empresa = [Paragraph(_xe(EMPRESA[0]), st_empresa)]
    empresa += [Paragraph(_xe(l), st_normal) for l in EMPRESA[1:]]
    flow.append(Table(
        [[empresa, Paragraph('INVOICE', st_titulo)]],
        colWidths=[110 * mm, 76 * mm],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    ))
    flow.append(Spacer(1, 8 * mm))

    # Bill To + detalles de la factura
    bill = [Paragraph('BILL TO', st_small), Paragraph(_xe(d['cliente']), st_bold)]
    for linea in d['direccion']:
        if linea != d['cliente']:
            bill.append(Paragraph(_xe(linea), st_normal))
    if d['crib']:
        bill.append(Paragraph(f'CRIB: {_xe(d["crib"])}', st_small))

    detalles = [
        ('Invoice #:', d['numero']),
        ('Date:', d['fecha']),
        ('Terms:', d['terminos']),
        ('Due Date:', d['vence']),
        ('Currency:', d['moneda_label']),
    ]
    tabla_detalles = Table(
        [[Paragraph(_xe(k), st_small), Paragraph(_xe(v), st_bold)] for k, v in detalles],
        colWidths=[22 * mm, 44 * mm],
        style=TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]),
    )
    flow.append(Table(
        [[bill, tabla_detalles]],
        colWidths=[120 * mm, 66 * mm],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    ))
    flow.append(Spacer(1, 6 * mm))

    # Tabla de líneas
    cab = ['PRODUCT', 'DETAILS', 'QUANTITY', 'RATE', 'AMOUNT']
    filas = [[Paragraph(f'<b>{_xe(c)}</b>', st_small) for c in cab]]
    for l in d['lineas']:
        detalle = (_grid_pesos(l['pesos'], st_small) if l['pesos']
                   else Paragraph(_xe(l['detalle_texto']), st_small))
        filas.append([
            Paragraph(_xe(l['producto']), st_normal),
            detalle,
            Paragraph(f'{l["qty"]:,.2f}', st_small),
            Paragraph(_money(l['rate']), st_small),
            Paragraph(f'<b>{_money(l["amount"])}</b>', st_small),
        ])

    tabla = Table(filas, colWidths=[52 * mm, 66 * mm, 20 * mm, 20 * mm, 28 * mm],
                  repeatRows=1)
    tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, colors.black),
        ('LINEBELOW', (0, 1), (-1, -2), 0.25, colors.HexColor('#dddddd')),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    flow.append(tabla)
    flow.append(Spacer(1, 6 * mm))

    # Datos bancarios + totales
    banco = [Paragraph(_xe(BANCO[0]), st_bold)]
    banco += [Paragraph(_xe(l), st_small) for l in BANCO[1:]]

    totales_datos = [
        ('SUBTOTAL', _money(d['subtotal'])),
        (f'OB ({_pct(d["ob_pct"])}%)', _money(d['ob'])),
        ('TOTAL', _money(d['total'])),
        ('BALANCE DUE', _money(d['balance'])),
    ]
    totales = Table(
        [[Paragraph(_xe(k), st_normal), Paragraph(f'<b>{v}</b>', st_normal)]
         for k, v in totales_datos],
        colWidths=[40 * mm, 34 * mm],
        style=TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LINEABOVE', (0, -1), (-1, -1), 1.2, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]),
    )
    flow.append(KeepTogether(Table(
        [[banco, totales]],
        colWidths=[112 * mm, 74 * mm],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    )))

    doc.build(flow)
    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_pdf.py -q`
Expected: 11 passed

- [ ] **Step 5: Look at the result**

Generar un PDF de verdad y abrirlo, porque los tests verifican estructura, no apariencia:

```bash
/Users/josedasilva/Projects/pesosapp/.venv/bin/python -c "
import json, pathlib
from utils.factura_pdf import render_factura_pdf
d = json.loads(pathlib.Path('tests/fixtures/facturas/xcg_sin_ob.json').read_text())
pathlib.Path('/tmp/factura.pdf').write_bytes(render_factura_pdf(d))
print('/tmp/factura.pdf')
"
open /tmp/factura.pdf
```

Revisar: que el grid de pesos se vea en 5 columnas, que nada se desborde del A4 y que los totales queden alineados a la derecha.

- [ ] **Step 6: Commit**

```bash
git add utils/factura_pdf.py tests/test_factura_pdf.py
git commit -m "feat(factura-pdf): dibuja la factura en A4 con reportlab"
```

---

### Task 4: Traer la factura vigente desde QuickBooks

**Files:**
- Modify: `app.py` (junto a `N8N_WEBHOOK_URL`, ~línea 6760)
- Test: `tests/test_factura_ruta.py` (crear)

**Interfaces:**
- Produces: `_obtener_factura_qbo(invoice_id: str) -> dict | None`

- [ ] **Step 1: Write the failing test**

`tests/test_factura_ruta.py`:

```python
"""Tests de la obtención de facturas desde QBO vía n8n y de la ruta del PDF."""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_obtener_factura_devuelve_el_invoice(mock_post, app):
    from app import _obtener_factura_qbo

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {'Invoice': {'Id': '47349', 'DocNumber': '5816'}}
    mock_post.return_value = mock_resp

    with app.app_context():
        factura = _obtener_factura_qbo('47349')

    assert factura['Invoice']['DocNumber'] == '5816'
    assert mock_post.call_args.kwargs['json'] == {'invoice_id': '47349'}


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', '')
def test_obtener_factura_sin_webhook_configurado(app):
    from app import _obtener_factura_qbo

    with app.app_context():
        assert _obtener_factura_qbo('47349') is None


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_obtener_factura_traga_errores_de_red(mock_post, app):
    import requests as req_lib
    from app import _obtener_factura_qbo

    mock_post.side_effect = req_lib.ConnectionError('n8n caído')

    with app.app_context():
        assert _obtener_factura_qbo('47349') is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_ruta.py -q`
Expected: FAIL con `ImportError: cannot import name '_obtener_factura_qbo'`

- [ ] **Step 3: Write the implementation**

En `app.py`, justo debajo de la definición de `N8N_WEBHOOK_TIMEOUT`:

```python
N8N_INVOICE_FETCH_WEBHOOK_URL = os.environ.get('N8N_INVOICE_FETCH_WEBHOOK_URL', '').strip()
try:
    N8N_INVOICE_FETCH_TIMEOUT = int(os.environ.get('N8N_INVOICE_FETCH_TIMEOUT', 20))
except (ValueError, TypeError):
    N8N_INVOICE_FETCH_TIMEOUT = 20


def _obtener_factura_qbo(invoice_id):
    """Pide a n8n la factura vigente en QuickBooks.

    Se consulta en vivo en lugar de guardar un snapshot al facturar porque las
    facturas se corrigen a mano en QBO cuando la lista de precios de la app
    está desactualizada. Devuelve None ante cualquier fallo; quien llama decide
    qué mostrar.
    """
    if not N8N_INVOICE_FETCH_WEBHOOK_URL:
        app.logger.warning('N8N_INVOICE_FETCH_WEBHOOK_URL no configurada')
        return None
    try:
        resp = requests.post(
            N8N_INVOICE_FETCH_WEBHOOK_URL,
            json={'invoice_id': str(invoice_id)},
            timeout=N8N_INVOICE_FETCH_TIMEOUT,
            headers=_webhook_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        app.logger.error(f'No se pudo obtener la factura {invoice_id} de QBO: {e}')
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_ruta.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_factura_ruta.py
git commit -m "feat(factura-pdf): helper para traer la factura vigente de QBO via n8n"
```

---

### Task 5: Archivar el PDF en Google Drive

**Files:**
- Modify: `app.py`
- Test: `tests/test_factura_ruta.py`

**Interfaces:**
- Produces: `_archivar_factura_drive(pdf_bytes: bytes, filename: str) -> bool`

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_factura_ruta.py`:

```python
@patch('app.N8N_DRIVE_WEBHOOK_URL', 'http://n8n.local/drive')
@patch('app.requests.post')
def test_archivar_manda_el_pdf_en_base64(mock_post, app):
    import base64
    from app import _archivar_factura_drive

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    with app.app_context():
        ok = _archivar_factura_drive(b'%PDF-fake', 'Factura_5816.pdf')

    assert ok is True
    enviado = mock_post.call_args.kwargs['json']
    assert enviado['filename'] == 'Factura_5816.pdf'
    assert base64.b64decode(enviado['pdf_base64']) == b'%PDF-fake'


@patch('app.N8N_DRIVE_WEBHOOK_URL', 'http://n8n.local/drive')
@patch('app.requests.post')
def test_archivar_no_propaga_fallos(mock_post, app):
    import requests as req_lib
    from app import _archivar_factura_drive

    mock_post.side_effect = req_lib.Timeout('drive lento')

    with app.app_context():
        assert _archivar_factura_drive(b'%PDF-fake', 'x.pdf') is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_ruta.py -q -k archivar`
Expected: FAIL con `ImportError: cannot import name '_archivar_factura_drive'`

- [ ] **Step 3: Write the implementation**

En `app.py`, debajo de `_obtener_factura_qbo`:

```python
N8N_DRIVE_WEBHOOK_URL = os.environ.get('N8N_DRIVE_WEBHOOK_URL', '').strip()
try:
    N8N_DRIVE_TIMEOUT = int(os.environ.get('N8N_DRIVE_TIMEOUT', 15))
except (ValueError, TypeError):
    N8N_DRIVE_TIMEOUT = 15


def _archivar_factura_drive(pdf_bytes, filename):
    """Sube el PDF a Google Drive vía n8n. Best-effort: nunca lanza.

    Si falla, el usuario igual recibe su PDF; solo queda sin archivar.
    """
    if not N8N_DRIVE_WEBHOOK_URL:
        app.logger.info('N8N_DRIVE_WEBHOOK_URL no configurada; se omite el archivado')
        return False
    try:
        resp = requests.post(
            N8N_DRIVE_WEBHOOK_URL,
            json={
                'filename': filename,
                'pdf_base64': base64.b64encode(pdf_bytes).decode('ascii'),
            },
            timeout=N8N_DRIVE_TIMEOUT,
            headers=_webhook_headers(),
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        app.logger.warning(f'No se pudo archivar {filename} en Drive: {e}')
        return False
```

`base64` ya está importado en `app.py` (línea 5).

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_ruta.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_factura_ruta.py
git commit -m "feat(factura-pdf): archivado best-effort en Drive via n8n"
```

---

### Task 6: La ruta del PDF

**Files:**
- Modify: `app.py` (después de `facturar_pedido`)
- Test: `tests/test_factura_ruta.py`

**Interfaces:**
- Consumes: `_obtener_factura_qbo`, `_archivar_factura_drive`, `render_factura_pdf`, `_user_can_manage_pedido`
- Produces: ruta `factura_pdf` en `GET /pedidos/<int:pedido_id>/factura.pdf`

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_factura_ruta.py` (arriba, junto a los imports, el helper de sesión):

```python
def _crear_pedido_facturado(invoice_id='47349', doc_number='5816'):
    from app import Rol, Territorio, Vendedor, Cliente, Pedido

    rol = Rol(nombre='super_admin', descripcion='Admin')
    _db.session.add(rol)
    territorio = Territorio(nombre='t', descripcion='T')
    _db.session.add(territorio)
    _db.session.flush()

    vendedor = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                        rol_id=rol.id, territorio_id=territorio.id, activo=True)
    vendedor.set_password('testpass')
    _db.session.add(vendedor)

    cliente = Cliente(nombre='Centrum', territorio_id=territorio.id, qbo_id='1570')
    _db.session.add(cliente)
    _db.session.flush()

    pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                    invoice_id_qbo=invoice_id, doc_number_qbo=doc_number)
    _db.session.add(pedido)
    _db.session.commit()
    return pedido.id


def _login(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.N8N_DRIVE_WEBHOOK_URL', '')
@patch('app.requests.post')
def test_ruta_devuelve_pdf(mock_post, app):
    import json, pathlib

    factura = json.loads(
        pathlib.Path('tests/fixtures/facturas/xcg_sin_ob.json').read_text())
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = factura
    mock_post.return_value = mock_resp

    with app.app_context():
        pedido_id = _crear_pedido_facturado()
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data[:5] == b'%PDF-'
    assert 'Factura_5814.pdf' in resp.headers['Content-Disposition']


def test_ruta_404_sin_invoice_id(app):
    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id=None, doc_number=None)
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 404


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_ruta_502_si_n8n_falla(mock_post, app):
    import requests as req_lib
    mock_post.side_effect = req_lib.ConnectionError('n8n caído')

    with app.app_context():
        pedido_id = _crear_pedido_facturado()
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 502
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_ruta.py -q -k ruta`
Expected: FAIL con 404 en todas (la ruta no existe)

- [ ] **Step 3: Write the implementation**

En `app.py`, justo después de `facturar_pedido`:

```python
@app.route('/pedidos/<int:pedido_id>/factura.pdf')
@login_required
@requiere_permiso_recurso('pedidos', 'leer')
def factura_pdf(pedido_id):
    """PDF de la factura, con los datos vigentes en QuickBooks.

    Se consulta QBO en cada llamada en vez de guardar un snapshot: las facturas
    se corrigen a mano cuando la lista de precios está desactualizada, y el PDF
    tiene que reflejar lo que realmente se le cobró al cliente.
    """
    pedido = Pedido.query.get_or_404(pedido_id)

    if not _user_can_manage_pedido(pedido):
        abort(403)

    if not pedido.invoice_id_qbo:
        abort(404, description='Este pedido no tiene factura en QuickBooks.')

    factura = _obtener_factura_qbo(pedido.invoice_id_qbo)
    if not factura:
        abort(502, description='No se pudo obtener la factura desde QuickBooks.')

    from utils.factura_pdf import render_factura_pdf, extraer_datos_factura

    try:
        pdf = render_factura_pdf(factura)
    except Exception as e:
        app.logger.error(f'Error al renderizar la factura del pedido {pedido_id}: {e}')
        abort(500, description='No se pudo generar el PDF de la factura.')

    numero = extraer_datos_factura(factura)['numero'] or pedido.doc_number_qbo or pedido.id
    filename = f'Factura_{numero}.pdf'

    _archivar_factura_drive(pdf, filename)

    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename,
    )
```

`send_file`, `abort` (línea 9), `base64` (línea 5) y `BytesIO` (línea 20) ya están importados en `app.py`; no hace falta tocar imports.

Nota de orden: el guard de autorización va **antes** del chequeo de `invoice_id_qbo`, para que un vendedor ajeno reciba 403 y no un 404 que le revele si el pedido está facturado.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_ruta.py -q`
Expected: 8 passed

- [ ] **Step 5: Add the IDOR test**

En `tests/test_authz_idor.py`, siguiendo el patrón del archivo (usa el seed con `vend_a`/`vend_b` y `IDS`), junto a los otros tests de vendedor ajeno:

```python
@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://test/fetch')
@patch('app.requests.post')
def test_vendedor_ajeno_no_descarga_factura_pdf(mock_post, app):
    c = _login(app, 'vend_b')
    resp = c.get(f'/pedidos/{IDS["pedido_a"]}/factura.pdf', follow_redirects=False)
    assert resp.status_code in (302, 403)
    mock_post.assert_not_called()  # no debe consultarse QBO
```

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_authz_idor.py -q`
Expected: todo verde, incluido el test nuevo

- [ ] **Step 6: Run the full suite**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/ -q`
Expected: todo verde

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_factura_ruta.py tests/test_authz_idor.py
git commit -m "feat(factura-pdf): ruta GET /pedidos/<id>/factura.pdf"
```

---

### Task 7: Botón de factura con Web Share

**Files:**
- Modify: `templates/detalles_pedido.html`
- Modify: `static/js/base.js` (y regenerar `static/js/base.min.js`)
- Test: `tests/test_factura_ruta.py`

**Interfaces:**
- Consumes: ruta `factura_pdf` (Task 6)

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_factura_ruta.py`:

```python
def test_detalles_muestra_boton_factura_si_hay_invoice_id(app):
    with app.app_context():
        pedido_id = _crear_pedido_facturado()
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/detalles')

    assert b'data-factura-share' in resp.data


def test_detalles_oculta_boton_sin_invoice_id(app):
    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id=None, doc_number=None)
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/detalles')

    assert b'data-factura-share' not in resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/test_factura_ruta.py -q -k boton`
Expected: FAIL — `data-factura-share` no está en el HTML

- [ ] **Step 3: Add the button to the template**

En `templates/detalles_pedido.html`, justo después del bloque de "Reintentar facturación":

```html
    <!-- Factura PDF (solo si ya está en QuickBooks) -->
    {% if pedido.invoice_id_qbo %}
    <div style="margin: 0 16px 14px;">
      <button type="button" class="btn-secondary"
              style="width:100%; display:flex; align-items:center; justify-content:center; gap:8px;"
              data-factura-share
              data-factura-url="{{ url_for('factura_pdf', pedido_id=pedido.id) }}"
              data-factura-nombre="Factura_{{ pedido.doc_number_qbo or pedido.id }}.pdf">
        <i class="fas fa-file-invoice"></i> Factura PDF
      </button>
    </div>
    {% endif %}
```

- [ ] **Step 4: Add the share handler**

En `static/js/base.js`, junto a los otros manejadores `data-*`:

```javascript
    // Factura PDF: Web Share API en el PWA de iOS (una descarga normal no
    // funciona en standalone), con enlace de descarga como fallback.
    document.addEventListener('click', async function (e) {
        const btn = e.target.closest('[data-factura-share]');
        if (!btn) return;

        const url = btn.dataset.facturaUrl;
        const nombre = btn.dataset.facturaNombre || 'Factura.pdf';
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.textContent = 'Generando...';

        try {
            const resp = await fetch(url, { credentials: 'same-origin' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const blob = await resp.blob();
            const file = new File([blob], nombre, { type: 'application/pdf' });

            if (navigator.canShare && navigator.canShare({ files: [file] })) {
                await navigator.share({ files: [file], title: nombre });
            } else {
                const objectUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = objectUrl;
                a.download = nombre;
                document.body.appendChild(a);
                a.click();
                a.remove();
                setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
            }
        } catch (err) {
            if (err && err.name === 'AbortError') return;  // el usuario canceló
            alert('No se pudo generar la factura. Intente de nuevo.');
        } finally {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    });
```

- [ ] **Step 5: Regenerate base.min.js**

`base.html` carga `base.min.js`, no `base.js`. No hay minificador real en el repo:

```bash
cp static/js/base.js static/js/base.min.js
```

- [ ] **Step 6: Run the full suite**

Run: `/Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest tests/ -q`
Expected: todo verde

- [ ] **Step 7: Commit**

```bash
git add templates/detalles_pedido.html static/js/base.js static/js/base.min.js tests/test_factura_ruta.py
git commit -m "feat(factura-pdf): boton de factura con Web Share para el PWA de iOS"
```

---

### Task 8: Crear los webhooks en n8n y configurar producción

**Files:** ninguno del repo — configuración en n8n Cloud y Heroku.

- [ ] **Step 1: Create the "Obtener Factura" workflow in n8n**

Nuevo workflow con dos nodos:

1. **Webhook** — método POST, y en Response Mode elegir **Last Node**
2. **QuickBooks** — Resource: `Invoice`, Operation: `Get`, Invoice ID: `={{ $json.body.invoice_id }}`, credencial *QuickBooks Online Production*

Conectar Webhook → QuickBooks. Guardar y **activar**.

Copiar la Production URL.

- [ ] **Step 2: Create the "Archivar en Drive" workflow in n8n**

Nuevo workflow con tres nodos:

1. **Webhook** — POST, Response Mode **Last Node**
2. **Convert to File** — Operation: `Convert to Binary`, Source Property: `body.pdf_base64`, File Name: `={{ $json.body.filename }}`, MIME: `application/pdf`
3. **Google Drive** — Operation: `Upload`, File Name: `={{ $('Webhook').item.json.body.filename }}`, carpeta *Facturacion Jomar Foods 2025* (`1edf16j6GCS8jpjluDBdcwOvGFU-qIWxN`), credencial *Google Drive account*

Conectar Webhook → Convert to File → Google Drive. Guardar y **activar**.

Copiar la Production URL.

- [ ] **Step 3: Set the config vars in Heroku**

```bash
heroku config:set --app pesosapp \
  N8N_INVOICE_FETCH_WEBHOOK_URL="<url del paso 1>" \
  N8N_DRIVE_WEBHOOK_URL="<url del paso 2>"
```

- [ ] **Step 4: Verify the fetch webhook end to end**

Con una factura real que exista (por ejemplo el Id interno `47348`, que es la 5815):

```bash
curl -s -X POST "$(heroku config:get N8N_INVOICE_FETCH_WEBHOOK_URL --app pesosapp)" \
  -H 'Content-Type: application/json' -d '{"invoice_id":"47348"}' | head -c 400
```

Expected: JSON con `"Invoice"` y `"DocNumber":"5815"`.

- [ ] **Step 5: Verify in production**

Facturar un pedido real, abrir sus detalles y pulsar **Factura PDF**. Confirmar que el PDF se ve bien, que se puede compartir por WhatsApp desde el iPhone, y que aparece en la carpeta de Drive.

---

## Notas de despliegue

El orden importa: la columna `doc_number_qbo` (Task 1, Step 6) hay que aplicarla en Heroku **antes** de desplegar el código, o producción rompe al arrancar.

El botón solo aparece en pedidos con `invoice_id_qbo`, o sea los facturados desde el release v838 en adelante. Los 909 anteriores no lo tendrán.
