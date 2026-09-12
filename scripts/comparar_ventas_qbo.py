"""Compara las ventas del dashboard por n8n y por API directa (Fase 2, Task 11).

Trae el mismo rango por los dos caminos y lista las diferencias: totales,
por cliente, por producto y línea por línea. El corte a `QB_SALES_BACKEND=qbo`
se hace cuando este script no encuentra diferencias (o todas están
explicadas). Consume UNA ejecución de n8n por corrida.

Uso, con las variables de producción en el entorno (por ejemplo dentro de
`heroku run --app pesosapp -- python scripts/comparar_ventas_qbo.py`):

    python scripts/comparar_ventas_qbo.py [--desde 2026-01-01] [--hasta 2026-09-12]
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _agrupar(filas, clave):
    tot = defaultdict(Decimal)
    for f in filas:
        tot[f.get(clave) or '?'] += Decimal(str(f.get('amount') or 0))
    return tot


def _clave_linea(f):
    return (str(f.get('invoice_number')), str(f.get('product')), str(f.get('amount')))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--desde', default=date(date.today().year, 1, 1).isoformat())
    parser.add_argument('--hasta', default=date.today().isoformat())
    args = parser.parse_args()

    import app as m
    from utils.qbo_ventas import consultar_ventas
    import requests

    with m.app.app_context():
        url = m.N8N_QB_SALES_WEBHOOK_URL
        if not url:
            sys.exit('Falta N8N_QB_SALES_WEBHOOK_URL: no hay con qué comparar')
        client = m._qbo_client()
        if client is None:
            sys.exit('Faltan QBO_CLIENT_ID/QBO_CLIENT_SECRET')

        payload = {'from_date': args.desde, 'to_date': args.hasta,
                   'timezone': str(m.DASHBOARD_TIMEZONE),
                   'group_by': ['day', 'week', 'customer', 'product'], 'include_summary': True}
        resp = requests.post(url, json=payload, timeout=float(m.N8N_QB_SALES_TIMEOUT),
                             headers=m._webhook_headers())
        resp.raise_for_status()
        n8n = resp.json()
        api = consultar_ventas(client, date.fromisoformat(args.desde),
                               date.fromisoformat(args.hasta), m._qbo_tasa_usd())

    fn, fa = n8n.get('transactions') or [], api.get('transactions') or []
    print(f'Rango {args.desde} → {args.hasta}')
    print(f'n8n: {len(fn)} líneas, total {sum(_agrupar(fn, "customer").values()):.2f}')
    print(f'API: {len(fa)} líneas, total {sum(_agrupar(fa, "customer").values()):.2f}')

    diferencias = 0
    for nombre, clave in (('cliente', 'customer'), ('producto', 'product'), ('fecha', 'date')):
        tn, ta = _agrupar(fn, clave), _agrupar(fa, clave)
        for k in sorted(set(tn) | set(ta)):
            if tn[k] != ta[k]:
                diferencias += 1
                print(f'  [{nombre}] {k}: n8n {tn[k]:.2f} vs API {ta[k]:.2f}')

    sn, sa = {_clave_linea(f) for f in fn}, {_clave_linea(f) for f in fa}
    for k in sorted(sn - sa):
        diferencias += 1
        print(f'  solo en n8n: factura {k[0]} · {k[1]} · {k[2]}')
    for k in sorted(sa - sn):
        diferencias += 1
        print(f'  solo en API: factura {k[0]} · {k[1]} · {k[2]}')

    if diferencias == 0:
        print('Sin diferencias: se puede cortar a QB_SALES_BACKEND=qbo.')
    else:
        print(f'{diferencias} diferencias. Revisar antes de cortar.')
        sys.exit(1)


if __name__ == '__main__':
    main()
