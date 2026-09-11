"""Tasa USD→ANG fija en QuickBooks.

Reemplaza al workflow «Fijar USD en 1.78» de n8n (ver
docs/superpowers/specs/n8n-tasa-usd-export.md): las facturas en USD y las
transacciones hechas a mano en QBO se contabilizan a la tasa de la empresa,
no a la del día de Intuit.

Sin Flask ni DB: recibe un `QboClient`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

MONEDA_ORIGEN = 'USD'
MONEDA_DESTINO = 'ANG'


def leer_tasa_usd(client, fecha: date) -> dict:
    """El objeto `ExchangeRate` de QBO para esa fecha, o `{}` si no hay."""
    datos = client.get('exchangerate', params={
        'sourcecurrencycode': MONEDA_ORIGEN,
        'asofdate': fecha.isoformat(),
    })
    return datos.get('ExchangeRate') or {}


def asegurar_tasa_usd(client, fecha: date, tasa) -> bool:
    """Deja la tasa USD→ANG de `fecha` en `tasa`. Idempotente.

    Devuelve False si ya estaba en ese valor (no escribe nada) y True si la
    fijó. Manda el `SyncToken` leído, como hacía n8n, para que QBO acepte la
    actualización de una tasa existente.
    """
    tasa = Decimal(str(tasa))
    actual = leer_tasa_usd(client, fecha)
    vigente = actual.get('Rate')
    if vigente is not None and Decimal(str(vigente)) == tasa:
        return False

    body = {
        'SourceCurrencyCode': MONEDA_ORIGEN,
        'TargetCurrencyCode': MONEDA_DESTINO,
        'Rate': float(tasa),
        'AsOfDate': actual.get('AsOfDate') or fecha.isoformat(),
    }
    if actual.get('SyncToken') is not None:
        body['SyncToken'] = actual['SyncToken']
    client.post('exchangerate', body)
    return True
