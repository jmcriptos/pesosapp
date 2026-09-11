# Workflow de facturación de n8n — export del 2026-09-11

Resumen del export que JM entregó el 2026-09-11. Se omiten el path del
webhook (es la URL secreta de entrada) y el realm id de QuickBooks (va en
`QboConexion`, no en el repo). El nodo de código está completo en
`n8n-facturacion-nodo-codigo.js`.

## Nodos y flujo

```
Webhook (POST, responde con el último nodo)
  ├─▶ Get Invoice Number      GET /query?query=SELECT DocNumber FROM Invoice ORDER BY MetaData.CreateTime DESC MAXRESULTS 50
  └─▶ Get Credit Memo Number  GET /query?query=SELECT DocNumber FROM CreditMemo ORDER BY MetaData.CreateTime DESC MAXRESULTS 50
        └─▶ Merge (las dos respuestas)
              └─▶ Generar Numero Factura (Code, ver .js)
                    └─▶ HTTP Facturar QBO
                          POST /invoice?minorversion=75&include=enhancedAllCustomFields
```

Todos los nodos HTTP usan la credencial OAuth2 «QuickBooks Online
Production» de n8n y los headers `Content-Type: application/json`,
`Accept: application/json`. Los dos GET y el Code tienen
`onError: continueErrorOutput`.

## Body del nodo «HTTP Facturar QBO»

Es un template que reenvía lo que arma el nodo de código, más un
`CustomerMemo` fijo:

```
Line, CustomerRef, SalesTermRef, TxnDate, DueDate, DocNumber, CustomField,
GlobalTaxCalculation,
TxnTaxDetail  (solo si existe),
CurrencyRef   (solo si existe),
ExchangeRate  (solo si existe)
```

`CustomerMemo.value`:

```
Jomar Foods, BV
Crib nr.: 102505329
K.V.K.: 148768
RBC Account# 8000009000132576
```

Historial: el primer export que entregó JM el 2026-09-11 tenía un template
anterior que **no** reenviaba `GlobalTaxCalculation`, `TxnTaxDetail` ni
`ExchangeRate`. El segundo export, del mismo día, es el desplegado y sí los
reenvía; la facturación funciona correctamente con él.
