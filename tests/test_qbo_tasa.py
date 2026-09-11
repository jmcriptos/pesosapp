# tests/test_qbo_tasa.py
"""Tasa USD→ANG fija (utils/qbo_tasa.py). Cliente mockeado, sin red."""
from datetime import date
from unittest.mock import MagicMock

from utils.qbo_tasa import asegurar_tasa_usd, leer_tasa_usd

FECHA = date(2026, 9, 11)


def _cliente(rate=None, sync_token=None, as_of=None):
    cliente = MagicMock()
    if rate is None:
        cliente.get.return_value = {}
    else:
        er = {'SourceCurrencyCode': 'USD', 'TargetCurrencyCode': 'ANG',
              'Rate': rate, 'AsOfDate': as_of or FECHA.isoformat()}
        if sync_token is not None:
            er['SyncToken'] = sync_token
        cliente.get.return_value = {'ExchangeRate': er}
    return cliente


def test_leer_tasa_consulta_por_moneda_y_fecha():
    cliente = _cliente(rate=1.79)
    assert leer_tasa_usd(cliente, FECHA)['Rate'] == 1.79
    cliente.get.assert_called_once_with('exchangerate', params={
        'sourcecurrencycode': 'USD', 'asofdate': '2026-09-11'})


def test_tasa_ya_correcta_no_escribe():
    cliente = _cliente(rate=1.78, sync_token='3')
    assert asegurar_tasa_usd(cliente, FECHA, 1.78) is False
    cliente.post.assert_not_called()


def test_tasa_como_string_o_decimal_se_compara_bien():
    cliente = _cliente(rate=1.78)
    assert asegurar_tasa_usd(cliente, FECHA, '1.78') is False
    assert asegurar_tasa_usd(cliente, FECHA, 1.780) is False
    cliente.post.assert_not_called()


def test_tasa_distinta_se_fija_con_sync_token():
    cliente = _cliente(rate=1.7925, sync_token='4', as_of='2026-09-11')
    assert asegurar_tasa_usd(cliente, FECHA, 1.78) is True
    cliente.post.assert_called_once_with('exchangerate', {
        'SourceCurrencyCode': 'USD', 'TargetCurrencyCode': 'ANG',
        'Rate': 1.78, 'AsOfDate': '2026-09-11', 'SyncToken': '4',
    })


def test_sin_tasa_previa_se_crea_sin_sync_token_con_la_fecha_pedida():
    cliente = _cliente()
    assert asegurar_tasa_usd(cliente, date(2026, 9, 12), 1.78) is True
    body = cliente.post.call_args.args[1]
    assert body['AsOfDate'] == '2026-09-12'
    assert 'SyncToken' not in body
    assert body['Rate'] == 1.78


def test_respeta_el_as_of_date_que_devuelve_qbo():
    cliente = _cliente(rate=1.79, sync_token='0', as_of='2026-09-10')
    asegurar_tasa_usd(cliente, FECHA, 1.78)
    assert cliente.post.call_args.args[1]['AsOfDate'] == '2026-09-10'
