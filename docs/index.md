# PesosApp — Índice de Documentación

> Generado por BMAD Document-Project Workflow (Deep Scan)
> Fecha: 2026-02-08

---

## Documentación del Proyecto

### Generada por BMAD

| Documento | Descripción |
|-----------|-------------|
| [architecture.md](architecture.md) | Arquitectura completa: stack, modelos, rutas, autenticación, precios, despliegue |
| [dev-guide.md](dev-guide.md) | Guía de desarrollo: setup local, estructura del código, testing, despliegue Heroku |
| [project-scan-report.json](project-scan-report.json) | Estado y hallazgos del workflow de documentación |

### Documentación Preexistente

| Documento | Ubicación | Descripción |
|-----------|-----------|-------------|
| README_US01.md | `/README_US01.md` | Implementación US01: CSRF, CSP, cookies seguras |
| HEROKU_DEBUG.md | `/HEROKU_DEBUG.md` | Guía de debugging para Heroku |
| OPTIMIZATION_GUIDE.md | `/OPTIMIZATION_GUIDE.md` | Guía de optimización: DB, frontend, cache, monitoreo |
| .env.example | `/.env.example` | Variables de entorno requeridas |

---

## Resumen Rápido del Proyecto

| Atributo | Valor |
|----------|-------|
| **Tipo** | Monolito Flask server-rendered |
| **Lenguaje** | Python 3.12 |
| **Framework** | Flask 3.0.3 + SQLAlchemy 2.0.32 |
| **Base de datos** | PostgreSQL (Heroku) |
| **Hosting** | Heroku (1 dyno Gunicorn) |
| **Modelos** | 17 modelos SQLAlchemy |
| **Rutas** | 53+ endpoints |
| **Templates** | 29 archivos Jinja2 |
| **Integraciones** | QuickBooks (via N8N webhook) |
| **Archivo principal** | `app.py` (5739 líneas) |

---

## Áreas Funcionales

1. **Autenticación** — Login con Flask-Login, RBAC 3 capas (super_admin, supervisor, vendedor)
2. **Productos** — Catálogo con temperatura, qbo_id, tax_rate
3. **Clientes** — Asignados a vendedores y territorios, con qbo_id
4. **Pedidos** — Ciclo: pendiente → listo → facturado (N8N → QuickBooks)
5. **Precios** — Motor de 3 niveles (específico > lista cliente > lista default)
6. **Facturación** — Registro de pesos, lotes y fechas por cliente/producto
7. **Recepciones** — Registro de mercancía entrante
8. **Importaciones** — Costos FOB, CIF, arancel, flete
9. **Etiquetas** — PDF 4"×2" y A4 con ReportLab
10. **Reportes** — Excel (ventas, pesos) + PDF (importaciones)
11. **Admin** — Vendedores, roles, territorios, analytics, exportación, backup, logs
12. **Dashboard** — KPIs (Fill Rate, OTD, Order Accuracy), tendencias, gauges
