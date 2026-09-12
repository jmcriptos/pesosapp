# tests/test_qbo_ventas.py
"""Ventas del dashboard directo de QuickBooks (Fase 2). Reproduce el nodo
«Process Transactions1» de n8n (docs/superpowers/specs/n8n-ventas-export.md)
y agrega paginación."""
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from utils.qbo_ventas import aplanar_facturas, consultar_ventas, facturas_del_rango, PAGINA


def _linea(nombre, qty, precio, monto):
    return {'DetailType': 'SalesItemLineDetail', 'Amount': monto,
            'SalesItemLineDetail': {'ItemRef': {'value': '1', 'name': nombre},
                                    'Qty': qty, 'UnitPrice': precio}}


FACTURA_ANG = {
    'Id': '47997', 'DocNumber': '5879', 'TxnDate': '2026-09-11',
    'CustomerRef': {'value': '1497', 'name': 'Esperamos Supermarket'},
    'CurrencyRef': {'value': 'ANG'}, 'TotalAmt': 7037.15,
    'Line': [
        _linea('Smoked and Cooked:Cooked Chicken Ham', 46.55, 13.2, 614.46),
        _linea('Smoked and Cooked:Cooked Shoulder', 116.75, 14.25, 1663.69),
        {'DetailType': 'SubTotalLineDetail', 'Amount': 2278.15},
    ],
}
FACTURA_USD = {
    'Id': '47987', 'DocNumber': '5869', 'TxnDate': '2026-09-09',
    'CustomerRef': {'value': '1737', 'name': 'Famoso Supermarket'},
    'CurrencyRef': {'value': 'USD'}, 'ExchangeRate': 1.79, 'TotalAmt': 771.2,
    'Line': [_linea('Smoked and Cooked:Smoked Pork Chop', 96.4, 8, 771.2)],
}
FACTURA_SIN_DETALLE = {
    'Id': '1', 'DocNumber': '5800', 'TxnDate': '2026-09-01',
    'CustomerRef': {'name': 'Deli Nova'}, 'TotalAmt': 106, 'TxnTaxDetail': {'TotalTax': 6},
    'Line': [{'DetailType': 'SubTotalLineDetail', 'Amount': 100}],
}


def test_una_fila_por_linea_de_producto_en_florines():
    out = aplanar_facturas([FACTURA_ANG])
    assert out['transactions'] == [
        {'date': '2026-09-11', 'invoice_number': '5879', 'customer': 'Esperamos Supermarket',
         'product': 'Smoked and Cooked:Cooked Chicken Ham', 'quantity': 46.55, 'unit_price': 13.2,
         'amount': 614.46, 'currency_origin': 'ANG', 'fx_applied': 1, 'transaction_type': 'Invoice'},
        {'date': '2026-09-11', 'invoice_number': '5879', 'customer': 'Esperamos Supermarket',
         'product': 'Smoked and Cooked:Cooked Shoulder', 'quantity': 116.75, 'unit_price': 14.25,
         'amount': 1663.69, 'currency_origin': 'ANG', 'fx_applied': 1, 'transaction_type': 'Invoice'},
    ]
    assert out['summary'] == {'total_amount': 2278.15, 'total_invoices': 1, 'total_lines': 2}


def test_usd_se_convierte_con_la_tasa_fija_no_con_la_de_la_factura():
    """n8n multiplica por 1,78 fijo aunque la factura traiga otro ExchangeRate."""
    fila = aplanar_facturas([FACTURA_USD])['transactions'][0]
    assert fila['currency_origin'] == 'USD' and fila['fx_applied'] == 1.78
    assert fila['amount'] == 1372.74          # 771.20 × 1.78 = 1372.736
    assert fila['unit_price'] == 14.24        # 8 × 1.78
    assert aplanar_facturas([FACTURA_USD], tasa_usd=Decimal('1.80'))['transactions'][0]['amount'] == 1388.16


def test_factura_sin_detalle_usa_el_neto():
    fila = aplanar_facturas([FACTURA_SIN_DETALLE])['transactions'][0]
    assert fila['product'] == '(sin detalle)' and fila['quantity'] == 0 and fila['unit_price'] == 0
    assert fila['amount'] == 100              # 106 − 6


def test_lineas_con_monto_cero_o_negativo_se_omiten():
    inv = dict(FACTURA_ANG, Line=[_linea('Gratis', 1, 0, 0), _linea('Ajuste', 1, -5, -5),
                                   _linea('Real', 2, 10, 20)])
    out = aplanar_facturas([inv])
    assert [f['product'] for f in out['transactions']] == ['Real']


def test_sin_cliente_ni_numero_usa_los_fallbacks_de_n8n():
    inv = {'Id': '99', 'TxnDate': '2026-09-02', 'Line': [_linea(None, 1, 5, 5)]}
    inv['Line'][0]['SalesItemLineDetail']['ItemRef'] = {}
    fila = aplanar_facturas([inv])['transactions'][0]
    assert fila == {'date': '2026-09-02', 'invoice_number': '99', 'customer': 'Sin cliente',
                    'product': 'Sin producto', 'quantity': 1, 'unit_price': 5, 'amount': 5,
                    'currency_origin': 'ANG', 'fx_applied': 1, 'transaction_type': 'Invoice'}


def test_summary_cuenta_facturas_distintas_y_lineas():
    out = aplanar_facturas([FACTURA_ANG, FACTURA_USD, FACTURA_SIN_DETALLE])
    assert out['summary'] == {'total_amount': 3750.89, 'total_invoices': 3, 'total_lines': 4}


def test_lista_vacia():
    assert aplanar_facturas([]) == {'transactions': [], 'summary': {
        'total_amount': 0, 'total_invoices': 0, 'total_lines': 0}}


# ── paginación ────────────────────────────────────────────────────────────

def _cliente_paginado(total):
    facturas = [dict(FACTURA_ANG, Id=str(i), DocNumber=str(6000 + i)) for i in range(total)]
    cliente = MagicMock()

    def query(sql):
        import re
        inicio = int(re.search(r'STARTPOSITION (\d+)', sql).group(1))
        pagina = facturas[inicio - 1:inicio - 1 + PAGINA]
        return {'Invoice': pagina} if pagina else {}

    cliente.query.side_effect = query
    return cliente


def test_pagina_de_a_mil_hasta_agotar():
    cliente = _cliente_paginado(1003)
    facturas = facturas_del_rango(cliente, date(2026, 1, 1), date(2026, 9, 12))
    assert len(facturas) == 1003
    consultas = [c.args[0] for c in cliente.query.call_args_list]
    assert len(consultas) == 2
    assert "TxnDate >= '2026-01-01' AND TxnDate <= '2026-09-12'" in consultas[0]
    assert 'STARTPOSITION 1 MAXRESULTS 1000' in consultas[0]
    assert 'STARTPOSITION 1001 MAXRESULTS 1000' in consultas[1]


def test_exactamente_mil_pide_una_pagina_mas_y_termina():
    cliente = _cliente_paginado(1000)
    assert len(facturas_del_rango(cliente, date(2026, 1, 1), date(2026, 9, 12))) == 1000
    assert cliente.query.call_count == 2


def test_consultar_ventas_junta_todo():
    cliente = _cliente_paginado(3)
    out = consultar_ventas(cliente, date(2026, 9, 1), date(2026, 9, 12))
    assert out['summary']['total_invoices'] == 3 and out['summary']['total_lines'] == 6


# ── enganche en la app ────────────────────────────────────────────────────

import app as app_module
from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def backend_qbo(monkeypatch):
    monkeypatch.setenv('QB_SALES_BACKEND', 'qbo')
    monkeypatch.setenv('QBO_CLIENT_ID', 'cid')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'sec')
    monkeypatch.setenv('QBO_TASA_USD', '1.78')


def test_con_backend_qbo_las_ventas_estan_habilitadas_sin_webhook(app, backend_qbo):
    with patch.object(app_module, 'N8N_QB_SALES_WEBHOOK_URL', ''):
        assert app_module._quickbooks_sales_enabled() is True


def test_sin_backend_ni_webhook_no_hay_ventas(app, monkeypatch):
    monkeypatch.setenv('QB_SALES_BACKEND', 'n8n')
    with patch.object(app_module, 'N8N_QB_SALES_WEBHOOK_URL', ''):
        assert app_module._quickbooks_sales_enabled() is False


def test_refresco_con_backend_qbo_guarda_el_crudo_sin_tocar_n8n(app, backend_qbo):
    from app import VentasQbCache
    cliente = _cliente_paginado(2)
    with patch.object(app_module, '_qbo_client', return_value=cliente), \
            patch.object(app_module.requests, 'post') as post:
        data = app_module._qb_refrescar_desde_red({'from_date': '2026-09-01', 'to_date': '2026-09-12'})
    post.assert_not_called()
    assert data['summary']['total_invoices'] == 2
    fila = _db.session.get(VentasQbCache, 1)
    assert fila.from_date == date(2026, 9, 1) and fila.to_date == date(2026, 9, 12)
    assert fila.last_error is None and '"transactions"' in fila.raw_json
    assert "TxnDate >= '2026-09-01' AND TxnDate <= '2026-09-12'" in cliente.query.call_args_list[0].args[0]


def test_refresco_con_backend_qbo_usa_la_tasa_del_entorno(app, backend_qbo, monkeypatch):
    monkeypatch.setenv('QBO_TASA_USD', '1.80')
    cliente = MagicMock()
    cliente.query.return_value = {'Invoice': [FACTURA_USD]}
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        data = app_module._qb_refrescar_desde_red({'from_date': '2026-09-01', 'to_date': '2026-09-12'})
    assert data['transactions'][0]['amount'] == 1388.16


def test_error_de_qbo_deja_last_error_y_conserva_el_crudo_anterior(app, backend_qbo):
    from app import VentasQbCache
    from utils.qbo_client import QboError
    _db.session.add(VentasQbCache(id=1, raw_json='{"transactions": []}', fetched_at=datetime(2026, 9, 11)))
    _db.session.commit()
    cliente = MagicMock()
    cliente.query.side_effect = QboError('caído', status=502)
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        assert app_module._qb_refrescar_desde_red({'from_date': '2026-09-01', 'to_date': '2026-09-12'}) is None
    fila = _db.session.get(VentasQbCache, 1)
    assert 'caído' in fila.last_error and fila.raw_json == '{"transactions": []}'


def test_backend_qbo_sin_credenciales_cae_a_n8n_en_el_refresco(app, monkeypatch):
    monkeypatch.setenv('QB_SALES_BACKEND', 'qbo')
    monkeypatch.delenv('QBO_CLIENT_ID', raising=False)
    with patch.object(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'http://n8n.local/ventas'), \
            patch.object(app_module.requests, 'post') as post:
        post.return_value.json.return_value = {'transactions': [], 'summary': {}}
        app_module._qb_refrescar_desde_red({'from_date': '2026-09-01', 'to_date': '2026-09-12'})
    post.assert_called_once()
