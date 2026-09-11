# tests/test_qbo_client.py
"""Cliente OAuth2 + API v3 de QuickBooks (utils/qbo_client.py).

Sin red: `requests.Session` se reemplaza por un MagicMock cuyo `.request`
devuelve respuestas armadas a mano. Sin Flask ni DB.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

from utils.qbo_client import (
    QboClient, QboConfig, QboError, QboNoConectado, MemoriaStore,
    AUTHORIZE_URL, TOKEN_URL, REVOKE_URL, SCOPE,
)

AHORA = datetime(2026, 9, 11, 15, 0, 0)

CONFIG = QboConfig(
    client_id='cid', client_secret='csecret',
    redirect_uri='http://localhost:5000/admin/quickbooks/callback',
    environment='sandbox', minor_version=75, timeout=5.0,
)


def _resp(status=200, json=None, content=b'{}'):
    r = MagicMock()
    r.status_code = status
    r.content = content
    if json is None:
        r.json.side_effect = ValueError('sin json')
    else:
        r.json.return_value = json
    return r


def _tokens(**cambios):
    base = {
        'realm_id': '123',
        'access_token': 'acc-1',
        'refresh_token': 'ref-1',
        'access_expires_at': AHORA + timedelta(hours=1),
        'refresh_expires_at': AHORA + timedelta(days=100),
    }
    base.update(cambios)
    return base


def _cliente(tokens=None, respuestas=()):
    session = MagicMock()
    session.request.side_effect = list(respuestas)
    store = MemoriaStore(tokens)
    return QboClient(CONFIG, store, session=session, ahora=lambda: AHORA), session, store


# ── configuración ───────────────────────────────────────────────────────

def test_environment_invalido_falla_al_construir():
    with pytest.raises(ValueError):
        QboClient(CONFIG._replace(environment='prod'), MemoriaStore())


def test_host_por_environment():
    assert 'sandbox-quickbooks' in CONFIG.api_host
    assert CONFIG._replace(environment='production').api_host == 'https://quickbooks.api.intuit.com'


# ── OAuth2 ──────────────────────────────────────────────────────────────

def test_url_autorizacion_lleva_todos_los_parametros():
    cliente, _, _ = _cliente()
    url = cliente.url_autorizacion('estado-xyz')
    parsed = urlparse(url)
    assert url.startswith(AUTHORIZE_URL + '?')
    q = parse_qs(parsed.query)
    assert q['client_id'] == ['cid']
    assert q['response_type'] == ['code']
    assert q['scope'] == [SCOPE]
    assert q['redirect_uri'] == [CONFIG.redirect_uri]
    assert q['state'] == ['estado-xyz']


def test_canjear_codigo_guarda_tokens_y_vencimientos():
    cliente, session, store = _cliente(respuestas=[_resp(200, {
        'access_token': 'acc-nuevo', 'refresh_token': 'ref-nuevo',
        'expires_in': 3600, 'x_refresh_token_expires_in': 8726400,
    })])
    tokens = cliente.canjear_codigo('code-abc', realm_id='999')

    assert store.tokens is tokens
    assert tokens['realm_id'] == '999'
    assert tokens['access_token'] == 'acc-nuevo'
    assert tokens['refresh_token'] == 'ref-nuevo'
    assert tokens['access_expires_at'] == AHORA + timedelta(seconds=3600)
    assert tokens['refresh_expires_at'] == AHORA + timedelta(seconds=8726400)

    metodo, url = session.request.call_args.args
    kwargs = session.request.call_args.kwargs
    assert (metodo, url) == ('POST', TOKEN_URL)
    assert kwargs['data'] == {
        'grant_type': 'authorization_code', 'code': 'code-abc',
        'redirect_uri': CONFIG.redirect_uri,
    }
    # Basic base64("cid:csecret")
    assert kwargs['headers']['Authorization'] == 'Basic Y2lkOmNzZWNyZXQ='


def test_canjear_codigo_rechazado_es_error_de_auth():
    cliente, _, store = _cliente(respuestas=[_resp(400, {
        'error': 'invalid_grant', 'error_description': 'Incorrect or invalid code',
    })])
    with pytest.raises(QboError) as exc:
        cliente.canjear_codigo('code-malo', realm_id='999')
    assert exc.value.es_auth
    assert 'invalid code' in str(exc.value)
    assert store.tokens is None


def test_refrescar_manda_el_refresh_token_y_conserva_realm():
    cliente, session, store = _cliente(tokens=_tokens(), respuestas=[_resp(200, {
        'access_token': 'acc-2', 'refresh_token': 'ref-2', 'expires_in': 3600,
    })])
    tokens = cliente.refrescar()
    assert tokens['realm_id'] == '123'
    assert tokens['access_token'] == 'acc-2'
    assert tokens['refresh_token'] == 'ref-2'
    assert session.request.call_args.kwargs['data'] == {
        'grant_type': 'refresh_token', 'refresh_token': 'ref-1',
    }


def test_refrescar_sin_tokens_es_no_conectado():
    cliente, session, _ = _cliente()
    with pytest.raises(QboNoConectado):
        cliente.refrescar()
    session.request.assert_not_called()


def test_refresh_token_vencido_es_no_conectado_sin_llamar_a_intuit():
    """Pasan 100 días sin uso: el access token venció hace rato y el refresh
    también. No se llama a Intuit; hay que reconectar desde la app."""
    cliente, session, _ = _cliente(
        tokens=_tokens(access_expires_at=AHORA - timedelta(days=99),
                       refresh_expires_at=AHORA - timedelta(days=1)))
    with pytest.raises(QboNoConectado):
        cliente.get('companyinfo/123')
    session.request.assert_not_called()


def test_revocar_manda_el_refresh_token_con_basic_auth():
    cliente, session, _ = _cliente(tokens=_tokens(), respuestas=[_resp(200, {})])
    cliente.revocar()
    metodo, url = session.request.call_args.args
    assert (metodo, url) == ('POST', REVOKE_URL)
    assert session.request.call_args.kwargs['json'] == {'token': 'ref-1'}


def test_revocar_sin_tokens_no_hace_nada():
    cliente, session, _ = _cliente()
    cliente.revocar()
    session.request.assert_not_called()


# ── API v3 ──────────────────────────────────────────────────────────────

def test_get_arma_url_headers_y_minorversion():
    cliente, session, _ = _cliente(tokens=_tokens(), respuestas=[
        _resp(200, {'CompanyInfo': {'CompanyName': 'Jomar Foods BV'}}),
    ])
    datos = cliente.get('companyinfo/123')
    assert datos['CompanyInfo']['CompanyName'] == 'Jomar Foods BV'
    metodo, url = session.request.call_args.args
    kwargs = session.request.call_args.kwargs
    assert metodo == 'GET'
    assert url == 'https://sandbox-quickbooks.api.intuit.com/v3/company/123/companyinfo/123'
    assert kwargs['params'] == {'minorversion': 75}
    assert kwargs['headers']['Authorization'] == 'Bearer acc-1'
    assert kwargs['headers']['Accept'] == 'application/json'
    assert kwargs['timeout'] == 5.0
    assert 'json' not in kwargs


def test_post_manda_json_y_params_extra():
    cliente, session, _ = _cliente(tokens=_tokens(), respuestas=[
        _resp(200, {'Invoice': {'Id': '47997', 'DocNumber': '5879'}}),
    ])
    datos = cliente.post('invoice', {'DocNumber': '5879'},
                         params={'include': 'enhancedAllCustomFields'})
    assert datos['Invoice']['Id'] == '47997'
    kwargs = session.request.call_args.kwargs
    assert session.request.call_args.args[0] == 'POST'
    assert kwargs['json'] == {'DocNumber': '5879'}
    assert kwargs['params'] == {'include': 'enhancedAllCustomFields', 'minorversion': 75}
    assert kwargs['headers']['Content-Type'] == 'application/json'


def test_query_manda_el_sql_como_parametro_y_devuelve_queryresponse():
    cliente, session, _ = _cliente(tokens=_tokens(), respuestas=[
        _resp(200, {'QueryResponse': {'Invoice': [{'DocNumber': '5879'}]}}),
    ])
    qr = cliente.query('SELECT DocNumber FROM Invoice MAXRESULTS 50')
    assert qr == {'Invoice': [{'DocNumber': '5879'}]}
    kwargs = session.request.call_args.kwargs
    assert kwargs['params']['query'] == 'SELECT DocNumber FROM Invoice MAXRESULTS 50'
    assert session.request.call_args.args[1].endswith('/v3/company/123/query')


def test_query_sin_resultados_devuelve_dict_vacio():
    cliente, _, _ = _cliente(tokens=_tokens(), respuestas=[
        _resp(200, {'QueryResponse': {}}),
    ])
    assert cliente.query('SELECT DocNumber FROM CreditMemo') == {}


def test_refresca_antes_de_llamar_si_el_access_token_esta_por_vencer():
    cliente, session, store = _cliente(
        tokens=_tokens(access_expires_at=AHORA + timedelta(seconds=30)),
        respuestas=[
            _resp(200, {'access_token': 'acc-fresco', 'refresh_token': 'ref-2',
                        'expires_in': 3600}),
            _resp(200, {'CompanyInfo': {}}),
        ])
    cliente.get('companyinfo/123')
    assert session.request.call_count == 2
    primera, segunda = session.request.call_args_list
    assert primera.args[1] == TOKEN_URL
    assert segunda.kwargs['headers']['Authorization'] == 'Bearer acc-fresco'
    assert store.tokens['access_token'] == 'acc-fresco'


def test_ante_401_refresca_una_vez_y_reintenta():
    cliente, session, _ = _cliente(tokens=_tokens(), respuestas=[
        _resp(401, {'Fault': {'Error': [{'Message': 'Token expired', 'code': '3200'}]}}),
        _resp(200, {'access_token': 'acc-2', 'refresh_token': 'ref-2', 'expires_in': 3600}),
        _resp(200, {'CompanyInfo': {'CompanyName': 'ok'}}),
    ])
    datos = cliente.get('companyinfo/123')
    assert datos['CompanyInfo']['CompanyName'] == 'ok'
    llamadas = session.request.call_args_list
    assert [c.args[1] for c in llamadas][1] == TOKEN_URL
    assert llamadas[2].kwargs['headers']['Authorization'] == 'Bearer acc-2'


def test_segundo_401_es_error_de_auth():
    cliente, session, _ = _cliente(tokens=_tokens(), respuestas=[
        _resp(401, {}),
        _resp(200, {'access_token': 'acc-2', 'refresh_token': 'ref-2', 'expires_in': 3600}),
        _resp(401, {}),
    ])
    with pytest.raises(QboError) as exc:
        cliente.get('companyinfo/123')
    assert exc.value.es_auth
    assert exc.value.status == 401
    assert session.request.call_count == 3


def test_fault_de_validacion_expone_codigo_y_detalle():
    fault = {'Error': [{
        'Message': 'Duplicate Document Number Error',
        'Detail': 'You must specify a different number. This number has already been used.',
        'code': '6240', 'element': '',
    }], 'type': 'ValidationFault'}
    cliente, _, _ = _cliente(tokens=_tokens(), respuestas=[_resp(400, {'Fault': fault})])
    with pytest.raises(QboError) as exc:
        cliente.post('invoice', {'DocNumber': '5879'})
    e = exc.value
    assert e.status == 400
    assert e.codigo == '6240'
    assert not e.es_auth
    assert 'Duplicate Document Number Error' in e.detalle
    assert 'already been used' in e.detalle
    assert 'Duplicate Document Number Error' in str(e)


def test_error_sin_fault_es_qboerror_generico():
    cliente, _, _ = _cliente(tokens=_tokens(), respuestas=[_resp(502, None)])
    with pytest.raises(QboError) as exc:
        cliente.get('companyinfo/123')
    assert exc.value.status == 502
    assert exc.value.codigo is None


def test_get_sin_tokens_es_no_conectado():
    cliente, session, _ = _cliente()
    with pytest.raises(QboNoConectado):
        cliente.get('companyinfo/1')
    session.request.assert_not_called()


def test_timeout_de_requests_se_deja_pasar():
    import requests as req_lib
    cliente, session, _ = _cliente(tokens=_tokens())
    session.request.side_effect = req_lib.Timeout('lento')
    with pytest.raises(req_lib.Timeout):
        cliente.get('companyinfo/123')


def test_fechas_guardadas_como_texto_iso_se_entienden():
    """El store de la app puede devolver datetimes o su isoformat; ambos valen."""
    cliente, session, _ = _cliente(
        tokens=_tokens(access_expires_at=(AHORA + timedelta(hours=1)).isoformat(),
                       refresh_expires_at=(AHORA + timedelta(days=50)).isoformat()),
        respuestas=[_resp(200, {'CompanyInfo': {}})])
    cliente.get('companyinfo/123')
    assert session.request.call_count == 1
