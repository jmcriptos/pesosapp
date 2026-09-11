# Workflow «Fijar USD en 1.78» de n8n — export del 2026-09-11

Corre todos los días a las 05:00 (hora del servidor de n8n). Realm id y
credencial omitidos.

```
Schedule 05:00
  └─▶ Code «Fechas UTC a fijar»: devuelve [hoy, mañana] en UTC
        └─▶ GET /exchangerate?sourcecurrencycode=USD&asofdate={fecha}&minorversion=75
              └─▶ POST /exchangerate?minorversion=75
                    body: { SourceCurrencyCode: 'USD', TargetCurrencyCode: 'ANG',
                            Rate: 1.78, AsOfDate: <AsOfDate leído>,
                            SyncToken: <si el GET lo trae> }
```

Por qué hoy **y** mañana: el `TxnDate` de la factura en n8n sale de
`new Date().toISOString()`, o sea la fecha UTC. Facturando de tarde en
Curaçao (UTC-4) ya es el día siguiente en UTC (la 5865, emitida a las 21:45
del 8 de septiembre, salió con `TxnDate` 2026-09-09). Fijando solo hoy, esas
facturas tomarían la tasa de QuickBooks.

Consumo: una ejecución por día (~30 al mes).
