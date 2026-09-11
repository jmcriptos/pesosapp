"""Cliente de QuickBooks Online: OAuth2 de Intuit y API v3.

Sin Flask ni base de datos. Recibe una `QboConfig` y un `TokenStore` (algo
con `cargar()` y `guardar(tokens)`) y expone `get`, `post` y `query`. Quien
lo construye decide dónde viven los tokens; en la app es la tabla
`qbo_conexion` (ver `app.py`).

Reglas que cumple el wrapper (ver docs/superpowers/plans/2026-09-11-qbo-api-directa.md):

- Antes de cada request, si el access token vence en menos de 60 s, refresca.
- Ante 401 refresca UNA vez y reintenta la misma request; un segundo 401
  levanta `QboError(es_auth=True)`.
- Ante 4xx/5xx con `Fault` levanta `QboError` con el Fault completo.
- Timeout y errores de conexión de `requests` se dejan pasar tal cual, para
  que `facturar_pedido` conserve sus mensajes.
- Nunca loguea tokens ni el client secret.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Callable, NamedTuple, Optional, Protocol
from urllib.parse import urlencode

import requests

AUTHORIZE_URL = 'https://appcenter.intuit.com/connect/oauth2'
TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'
REVOKE_URL = 'https://developer.api.intuit.com/v2/oauth2/tokens/revoke'
SCOPE = 'com.intuit.quickbooks.accounting'

API_HOSTS = {
    'sandbox': 'https://sandbox-quickbooks.api.intuit.com',
    'production': 'https://quickbooks.api.intuit.com',
}

# Margen antes del vencimiento del access token para refrescar de antemano.
MARGEN_REFRESCO_SEG = 60


class QboConfig(NamedTuple):
    client_id: str
    client_secret: str
    redirect_uri: str
    environment: str = 'sandbox'      # 'sandbox' | 'production'
    minor_version: int = 75
    timeout: float = 20.0

    @property
    def api_host(self) -> str:
        try:
            return API_HOSTS[self.environment]
        except KeyError:
            raise ValueError(
                f"QBO_ENVIRONMENT inválido: {self.environment!r} "
                f"(esperado 'sandbox' o 'production')"
            )


class TokenStore(Protocol):
    def cargar(self) -> Optional[dict]: ...
    def guardar(self, tokens: dict) -> None: ...


class MemoriaStore:
    """TokenStore en memoria. Para tests y scripts de una sola corrida."""

    def __init__(self, tokens: Optional[dict] = None):
        self.tokens = tokens

    def cargar(self):
        return self.tokens

    def guardar(self, tokens):
        self.tokens = tokens


class QboError(Exception):
    """Error devuelto por QuickBooks (o por el endpoint de tokens de Intuit).

    `fault` es el objeto `Fault` de QBO cuando lo hay; `status` el código
    HTTP; `es_auth` marca que la conexión ya no sirve y hay que reconectar.
    """

    def __init__(self, mensaje, status=None, fault=None, es_auth=False):
        super().__init__(mensaje)
        self.status = status
        self.fault = fault or {}
        self.es_auth = es_auth

    @property
    def errores(self) -> list:
        return list(self.fault.get('Error') or [])

    @property
    def codigo(self) -> Optional[str]:
        """Código del primer error de QBO (`6240` = DocNumber duplicado)."""
        for e in self.errores:
            if e.get('code'):
                return str(e['code'])
        return None

    @property
    def detalle(self) -> str:
        """Texto para mostrar al usuario: Message y Detail del primer error."""
        for e in self.errores:
            partes = [e.get('Message'), e.get('Detail')]
            texto = ' — '.join(p for p in partes if p)
            if texto:
                return texto
        return str(self)


class QboNoConectado(QboError):
    """No hay tokens guardados, o el refresh token venció: hay que reconectar."""

    def __init__(self, mensaje='QuickBooks no está conectado'):
        super().__init__(mensaje, es_auth=True)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _a_datetime(valor) -> Optional[datetime]:
    if valor is None or isinstance(valor, datetime):
        return valor
    return datetime.fromisoformat(str(valor))


class QboClient:
    def __init__(self, config: QboConfig, store: TokenStore, session=None,
                 ahora: Callable[[], datetime] = _utcnow):
        self.config = config
        self.store = store
        self.session = session or requests.Session()
        self._ahora = ahora
        # Se valida acá para fallar temprano y no en la primera llamada.
        config.api_host

    # ── OAuth2 ────────────────────────────────────────────────────────────

    def url_autorizacion(self, state: str) -> str:
        params = {
            'client_id': self.config.client_id,
            'response_type': 'code',
            'scope': SCOPE,
            'redirect_uri': self.config.redirect_uri,
            'state': state,
        }
        return f'{AUTHORIZE_URL}?{urlencode(params)}'

    def _basic_auth(self) -> str:
        par = f'{self.config.client_id}:{self.config.client_secret}'.encode()
        return 'Basic ' + base64.b64encode(par).decode('ascii')

    def _pedir_tokens(self, datos: dict) -> dict:
        resp = self.session.request(
            'POST', TOKEN_URL, data=datos,
            headers={
                'Authorization': self._basic_auth(),
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            timeout=self.config.timeout,
        )
        if resp.status_code >= 400:
            cuerpo = _json_o_vacio(resp)
            raise QboError(
                f"Intuit rechazó la solicitud de tokens (HTTP {resp.status_code}): "
                f"{cuerpo.get('error_description') or cuerpo.get('error') or 'sin detalle'}",
                status=resp.status_code,
                es_auth=True,
            )
        return resp.json()

    def _guardar_respuesta_tokens(self, cuerpo: dict, realm_id: Optional[str]) -> dict:
        ahora = self._ahora()
        previos = self.store.cargar() or {}
        tokens = {
            'realm_id': realm_id or previos.get('realm_id'),
            'access_token': cuerpo['access_token'],
            'refresh_token': cuerpo.get('refresh_token') or previos.get('refresh_token'),
            'access_expires_at': ahora + timedelta(seconds=int(cuerpo.get('expires_in', 3600))),
            'refresh_expires_at': ahora + timedelta(
                seconds=int(cuerpo.get('x_refresh_token_expires_in', 100 * 86400))
            ),
        }
        self.store.guardar(tokens)
        return tokens

    def canjear_codigo(self, code: str, realm_id: str) -> dict:
        """Canjea el `code` del callback por tokens y los guarda."""
        cuerpo = self._pedir_tokens({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.config.redirect_uri,
        })
        return self._guardar_respuesta_tokens(cuerpo, realm_id)

    def refrescar(self) -> dict:
        tokens = self._tokens_o_error()
        vence = _a_datetime(tokens.get('refresh_expires_at'))
        if vence is not None and vence <= self._ahora():
            raise QboNoConectado(
                'El refresh token de QuickBooks venció; hay que volver a conectar'
            )
        cuerpo = self._pedir_tokens({
            'grant_type': 'refresh_token',
            'refresh_token': tokens['refresh_token'],
        })
        return self._guardar_respuesta_tokens(cuerpo, tokens.get('realm_id'))

    def revocar(self) -> None:
        """Best-effort: pide a Intuit que invalide el refresh token."""
        tokens = self.store.cargar() or {}
        if not tokens.get('refresh_token'):
            return
        self.session.request(
            'POST', REVOKE_URL,
            json={'token': tokens['refresh_token']},
            headers={'Authorization': self._basic_auth(),
                     'Accept': 'application/json',
                     'Content-Type': 'application/json'},
            timeout=self.config.timeout,
        )

    # ── tokens ────────────────────────────────────────────────────────────

    def _tokens_o_error(self) -> dict:
        tokens = self.store.cargar()
        if not tokens or not tokens.get('refresh_token') or not tokens.get('realm_id'):
            raise QboNoConectado()
        return tokens

    def _access_token(self) -> tuple[str, str]:
        """(access_token, realm_id) vigentes, refrescando si hace falta."""
        tokens = self._tokens_o_error()
        vence = _a_datetime(tokens.get('access_expires_at'))
        if (not tokens.get('access_token') or vence is None
                or vence - timedelta(seconds=MARGEN_REFRESCO_SEG) <= self._ahora()):
            tokens = self.refrescar()
        return tokens['access_token'], tokens['realm_id']

    def asegurar_token(self) -> None:
        """Refresca de antemano si hace falta. Se llama ANTES de tomar el
        lock de facturación para que el commit del refresco no lo suelte."""
        self._access_token()

    @property
    def realm_id(self) -> Optional[str]:
        tokens = self.store.cargar() or {}
        return tokens.get('realm_id')

    # ── API v3 ────────────────────────────────────────────────────────────

    def _url(self, realm_id: str, path: str) -> str:
        return f"{self.config.api_host}/v3/company/{realm_id}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, params=None, body=None) -> dict:
        params = dict(params or {})
        params.setdefault('minorversion', self.config.minor_version)
        intentos = 0
        while True:
            access_token, realm_id = self._access_token()
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json',
            }
            kwargs = {'params': params, 'headers': headers,
                      'timeout': self.config.timeout}
            if body is not None:
                headers['Content-Type'] = 'application/json'
                kwargs['json'] = body
            resp = self.session.request(method, self._url(realm_id, path), **kwargs)

            if resp.status_code == 401 and intentos == 0:
                intentos += 1
                self.refrescar()
                continue
            if resp.status_code == 401:
                raise QboError(
                    'QuickBooks rechazó las credenciales; hay que volver a conectar',
                    status=401, fault=_json_o_vacio(resp).get('Fault'), es_auth=True,
                )
            if resp.status_code >= 400:
                cuerpo = _json_o_vacio(resp)
                fault = cuerpo.get('Fault') or {}
                err = QboError(
                    f'QuickBooks respondió HTTP {resp.status_code}',
                    status=resp.status_code, fault=fault,
                    es_auth=resp.status_code == 403,
                )
                raise QboError(err.detalle if fault else str(err),
                               status=err.status, fault=fault, es_auth=err.es_auth)
            return resp.json() if resp.content else {}

    def get(self, path: str, params=None) -> dict:
        return self._request('GET', path, params=params)

    def post(self, path: str, body: dict, params=None) -> dict:
        return self._request('POST', path, params=params, body=body)

    def query(self, sql: str) -> dict:
        """`SELECT ...` de QBO. Devuelve el objeto `QueryResponse` (o `{}`)."""
        return self.get('query', params={'query': sql}).get('QueryResponse') or {}


def _json_o_vacio(resp) -> dict:
    try:
        datos = resp.json()
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}
