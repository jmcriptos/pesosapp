# Arquitectura del Proyecto — PesosApp

> Documento generado por BMAD Document-Project Workflow (Deep Scan)
> Fecha: 2026-02-08 | Versión: 1.0

---

## 1. Visión General

**PesosApp** es un sistema de gestión comercial para distribución de alimentos, desplegado como aplicación web monolítica server-rendered en Heroku. Gestiona el ciclo completo desde recepción de mercancía, inventario de productos, pedidos con precios por cliente, preparación, facturación automática vía QuickBooks, hasta generación de etiquetas y reportes.

### Clasificación del Proyecto

| Atributo | Valor |
|----------|-------|
| Tipo | Monolito server-rendered |
| Repositorio | Single repo (monorepo: NO) |
| Partes | 1 (web) |
| Lenguaje | Python 3.12 |
| Framework | Flask 3.0.3 |
| Base de datos | PostgreSQL (Heroku) / SQLite (dev) |
| Hosting | Heroku (1 dyno web) |

---

## 2. Stack Tecnológico

### 2.1 Backend

| Componente | Tecnología | Versión | Notas |
|-----------|-----------|---------|-------|
| Framework web | Flask | 3.0.3 | Todo en `app.py` (5739 líneas) |
| ORM | SQLAlchemy | 2.0.32 | + Flask-SQLAlchemy 3.1.1 |
| Migraciones | Alembic | 1.13.2 | Flask-Migrate 4.0.7 — 14 versiones |
| Autenticación | Flask-Login | 0.6.3 | + Werkzeug password hashing |
| CSRF | Flask-WTF | 1.2.1 | CSRFProtect global |
| CSP/HSTS | Flask-Talisman | 1.1.0 | Solo producción |
| WSGI | Gunicorn | 23.0.0 | `Procfile: web: gunicorn app:app` |
| DB driver | psycopg2-binary | 2.9.10 | PostgreSQL |

### 2.2 Frontend (Server-rendered)

| Componente | Tecnología | Fuente |
|-----------|-----------|--------|
| Templates | Jinja2 3.1.6 | 29 archivos HTML |
| CSS framework | Custom CSS + Bootstrap 5 | CDN jsdelivr |
| JS library | jQuery | CDN |
| Iconos | Font Awesome 6 | CDN cdnjs |
| Charts | Chart.js | CDN (dashboard) |
| Minificación | Manual | `.min.css` / `.min.js` en static/ |

### 2.3 Reportes y Exportación

| Componente | Uso |
|-----------|-----|
| ReportLab 4.2.2 | PDFs: etiquetas 4"×2", A4, reportes de importación |
| XlsxWriter 3.2.0 | Exportación Excel (ventas, reportes) |
| openpyxl 3.1.5 | Lectura de archivos Excel |
| pandas 2.2.2+ | Procesamiento de datos, DataFrames |
| Pillow 11.0.0+ | Logos en etiquetas PDF |

### 2.4 Integraciones Externas

| Integración | Protocolo | Propósito |
|-------------|-----------|-----------|
| QuickBooks | N8N Webhook (HTTP POST) | Facturación automática de pedidos |
| QuickBooks IDs | `qbo_id` en Cliente y Producto | Sincronización de entidades |
| Webhook precios | `POST /webhook/actualizacion-precios` | Actualización masiva desde sistemas externos |

---

## 3. Modelo de Datos

### 3.1 Diagrama de Entidades (17 modelos)

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│    Rol       │────<│  Vendedor    │>────│  Territorio  │
│             │     │  (UserMixin) │     │             │
└─────────────┘     └──────┬───────┘     └──────┬──────┘
      │                    │                     │
      │              ┌─────┴──────┐              │
┌─────┴─────┐        │ClienteVend.│        ┌─────┴─────┐
│ Permiso   │        └─────┬──────┘        │  Cliente   │
│           │              │               │  (qbo_id)  │
└───────────┘              │               └──┬──┬──┬───┘
      │              ┌─────┴──────┐           │  │  │
┌─────┴─────┐        │   Pedido   │───────────┘  │  │
│RolPermiso │        │  (estado)  │              │  │
└───────────┘        └─────┬──────┘              │  │
                           │                     │  │
                     ┌─────┴──────┐              │  │
                     │DetallePed. │              │  │
                     │(precio_u.) │              │  │
                     └─────┬──────┘              │  │
                           │                     │  │
                     ┌─────┴──────┐              │  │
                     │  Producto  │──────────────┘  │
                     │  (qbo_id)  │                 │
                     └──┬──┬──┬───┘                 │
                        │  │  │                     │
              ┌─────────┘  │  └──────────┐          │
              │            │             │          │
        ┌─────┴────┐ ┌────┴─────┐ ┌─────┴─────┐    │
        │Recepcion │ │Importac. │ │Facturac.  │────┘
        └──────────┘ └──────────┘ └───────────┘

        SISTEMA DE PRECIOS:
        ┌─────────────┐     ┌───────────────┐
        │ ListaPrecio │────<│PrecioProducto │>────Producto
        └──────┬──────┘     └───────────────┘
               │
        ┌──────┴──────────┐
        │ClienteListaPrec.│>────Cliente
        └─────────────────┘

        ┌───────────────────────┐
        │PrecioClienteProducto  │>────Cliente + Producto
        │(precio específico)    │
        └───────────────────────┘
```

### 3.2 Modelos Principales

| Modelo | Tabla | Columnas clave | FK / Relaciones |
|--------|-------|---------------|-----------------|
| **Vendedor** | vendedor | username, email, password_hash, nombre_completo, activo | → Rol, → Territorio, → self (supervisor), ← ClienteVendedor |
| **Producto** | producto | nombre, descripcion, temperatura, qbo_id, tax_rate | ← Facturacion, ← Recepcion, ← Importacion |
| **Cliente** | cliente | nombre, qbo_id | → Territorio, ← Pedido, ← Facturacion |
| **Pedido** | pedido | fecha_pedido, fecha_facturacion, estado, notas | → Cliente, ← DetallePedido |
| **DetallePedido** | detalle_pedido | cajas, peso, lote, precio_unitario, subtotal | → Pedido, → Producto |
| **Facturacion** | facturacion | peso, lote, fecha_fabricacion, fecha_expiracion | → Producto, → Cliente |
| **Recepcion** | recepcion | peso, proveedor, numero_factura, recibido_en | → Producto |
| **Importacion** | importacion | numero_factura, cantidades, precios FOB/CIF/arancel | → Producto |
| **Rol** | rol | nombre, nivel_jerarquia | ← Vendedor, ← RolPermiso |
| **Permiso** | permiso | nombre, categoria, recurso | — |
| **RolPermiso** | rol_permiso | puede_leer/crear/editar/eliminar | → Rol, → Permiso (UK: rol+permiso) |
| **Territorio** | territorio | nombre, tipo, coordenadas (JSON) | ← Vendedor, ← Cliente |
| **ClienteVendedor** | cliente_vendedor | tipo_asignacion, porcentaje_comision, activo | → Cliente, → Vendedor |
| **ListaPrecio** | lista_precio | nombre, es_default, activa | ← PrecioProducto, ← ClienteListaPrecio |
| **PrecioProducto** | precio_producto | precio_base, margenes jomar/retail | → ListaPrecio, → Producto (UK: lista+producto) |
| **ClienteListaPrecio** | cliente_lista_precio | activa | → Cliente, → ListaPrecio (UK: cliente+lista) |
| **PrecioClienteProducto** | precio_cliente_producto | precio_base, margenes | → Cliente, → Producto (UK: cliente+producto) |

### 3.3 Índices de Rendimiento (8 indexes)

Definidos en migración `z99_add_performance_indexes.py`:
- Pedido: `fecha_pedido`, `estado`, `cliente_id`
- DetallePedido: `pedido_id`, `producto_id`
- Facturacion: `cliente_id`, `producto_id`
- Recepcion: `producto_id`

---

## 4. Arquitectura de Rutas (53+ endpoints)

### 4.1 Distribución por Área Funcional

| Área | Rutas | Autenticación | Descripción |
|------|-------|---------------|-------------|
| Auth & Security | 3 | Pública (login, csrf_ping) | Login/Logout, CSRF ping |
| Dashboard | 4 | @login_required | Dashboards admin y vendedor, API métricas |
| Admin | 17 | @requiere_rol('super_admin') | Vendedores, roles, territorios, reportes, analytics, export, backup, logs |
| Pedidos | 11 | @login_required + permisos | CRUD, detalles, preparar, facturar, etiquetas |
| Precios | 24 | @login_required + permisos | Listas, productos en lista, clientes, precio específico, carga masiva CSV |
| Productos | 4 | @login_required | CRUD + API JSON |
| Recepciones | 4 | @login_required | CRUD |
| Facturación | 4 | @login_required | CRUD |
| Importaciones | 3 | @login_required | Formulario, registro, reporte PDF |
| Clientes | 4 | @login_required + permisos | CRUD filtrado por vendedor |

### 4.2 Patrones de API

- **Server-rendered:** Mayoría de rutas retornan `render_template()` con Jinja2
- **JSON API:** Endpoints `/api/*` retornan `jsonify()` (productos, recepciones, precios, admin stats)
- **Webhooks:** `POST /webhook/actualizacion-precios` (sin auth, TODO en código)
- **File downloads:** PDFs (etiquetas, reportes importación) y Excel (reportes ventas/pesos)

---

## 5. Sistema de Autenticación y Autorización

### 5.1 Autenticación (Flask-Login)

- **Vendedor** (db.Model + UserMixin): Login con username/password, hash con Werkzeug
- **DefaultUser** (UserMixin): Fallback legacy — solo si `DEFAULT_USERNAME` + `DEFAULT_PASSWORD` en env vars
- **user_loader:** Intenta cargar como DefaultUser primero, luego como Vendedor por ID numérico

### 5.2 Autorización — 3 Capas

```
Capa 1: @login_required                     → Cualquier usuario autenticado
Capa 2: @requiere_rol(['super_admin'])       → Solo roles específicos
Capa 3: @requiere_permiso_recurso('X','Y')   → Recurso + tipo de acceso
```

### 5.3 Roles y Permisos (Hardcoded en `Vendedor.tiene_permiso()`)

| Rol | Productos | Clientes | Pedidos | Vendedores | Precios | Reportes | Importaciones | Facturación |
|-----|-----------|----------|---------|------------|---------|----------|---------------|-------------|
| **super_admin** | LCEE | LCEE | LCEE | LCEE | LCEE | LCEE | LCEE | LCEE |
| **supervisor** | L | LE | LCE | L | L | L | — | L |
| **vendedor** | L | LE | LCE | — | L | — | — | — |

*L=Leer, C=Crear, E=Editar, E=Eliminar*

### 5.4 Context Processor

`inject_permissions()` inyecta `puede_crear()`, `puede_editar()`, `puede_eliminar()` en todos los templates para control de UI.

---

## 6. Motor de Precios

### 6.1 Resolución de Precios (Prioridad descendente)

```
1. PrecioClienteProducto (precio específico cliente+producto)
   ↓ si no existe
2. ClienteListaPrecio → PrecioProducto (lista asignada al cliente)
   ↓ si no existe
3. ListaPrecio(es_default=True) → PrecioProducto (lista por defecto)
   ↓ si no existe
4. None (sin precio)
```

### 6.2 Estructura de Precios

Cada nivel tiene 3 precios calculados:
- `precio_base` — Precio de referencia ingresado manualmente
- `precio_jomar` = `precio_base × margen_jomar` (default 1.0)
- `precio_retail` = `precio_base × margen_retail` (default 1.2)

### 6.3 Carga Masiva (CSV)

3 tipos de plantilla descargables:
1. **Precios por lista** — `codigo_producto`, `precio_base`, márgenes
2. **Asignación clientes** — `codigo_cliente`, `nombre_lista_precio`
3. **Precios específicos** — `codigo_cliente`, `codigo_producto`, `precio_base`, márgenes

---

## 7. Ciclo de Vida del Pedido

```
                    ┌──────────────────────────────────────────────┐
                    │                                              │
  [Crear Pedido] → pendiente → [Preparar] → listo → [Facturar] → facturado
       │                           │                      │
       │ + DetallePedido           │ + lote, peso real    │ + N8N webhook
       │ + precio_unitario         │ + fecha_fab/exp      │ + QuickBooks invoice
       │ + subtotal                │                      │ + fecha_facturacion
       └───────────────────────────┴──────────────────────┘
```

### Facturación vía N8N

Al facturar, `pedido_a_json()` serializa:
- `customer_qbo_id`, `order_date`, `notes`
- Líneas: `product_qbo_id`, `qty`, `unit_price`, `amount`, `tax_rate`
- Se envía como HTTP POST a `N8N_WEBHOOK_URL` → QuickBooks crea invoice

---

## 8. Generación de Etiquetas (PDF)

### Formatos

| Formato | Dimensiones | Labels/página | Uso |
|---------|-------------|---------------|-----|
| Estándar | 4" × 2" | 1 | Impresión directa a etiquetadora |
| A4 | 100.16mm × 50.8mm | 2 | Impresión en hojas A4 |

### Contenido de Etiqueta de Pedido

- Logo de empresa
- Nombre del cliente
- Nombre del producto
- Lote, fecha fabricación, fecha expiración
- Temperatura de almacenamiento
- Peso

---

## 9. Estructura de Archivos

```
pesosapp/
├── app.py                          # 5739 líneas — Monolito principal
├── config.py                       # Configuraciones Dev/Prod/Test
├── extensions.py                   # db = SQLAlchemy() (no usado por app.py)
├── init_multivendor_data.py        # Seed: roles, permisos, vendedores
├── test_dashboard.py               # Tests de dashboard
├── Procfile                        # web: gunicorn app:app
├── requirements.txt                # 46 dependencias Python
├── .python-version                 # 3.12
├── .env.example                    # Variables de entorno
│
├── templates/ (29 archivos)
│   ├── base.html                   # Layout: header, mobile nav, CSRF meta
│   ├── [16 templates principales]  # Páginas de la aplicación
│   ├── admin/ (4)                  # Vendedores, reportes, territorios, asignaciones
│   └── precios/ (8)               # Sistema de precios completo
│
├── static/
│   ├── js/ (base.js, scripts.js + minified)
│   ├── css/ (main.css, dashboard_pro.css + minified)
│   ├── styles.css + styles.min.css
│   └── logo_etiquetas.png, favicon.ico
│
├── utils/
│   ├── label_utils.py              # PDF: draw_order_label, create_a4_page_pdf
│   ├── cache.py                    # SimpleCache + @cached decorators
│   ├── filters.py                  # Jinja2: kpi_tag()
│   └── performance.py              # PerformanceMonitor, @timer, batch_loader
│
├── tests/
│   ├── conftest.py                 # Fixtures: app, client, csrf_token
│   └── test_csrf.py                # 4 tests de protección CSRF
│
├── scripts/
│   └── us01_runtime_check.py       # Validación de seguridad en runtime
│
├── migrations/versions/ (14)       # Alembic: desde tablas iniciales hasta multivendor
│
└── docs/
    ├── architecture.md             # Este documento
    └── project-scan-report.json    # Estado del workflow BMAD
```

---

## 10. Configuración y Entorno

### 10.1 Variables de Entorno Requeridas

| Variable | Requerida | Propósito |
|----------|-----------|-----------|
| `DATABASE_URL` | Si (prod) | PostgreSQL connection string |
| `SECRET_KEY` | Si (prod) | Clave para sesiones y CSRF |
| `FLASK_ENV` | Si | `development` / `production` |
| `DEFAULT_USERNAME` | No | Legacy user (desactivar en producción) |
| `DEFAULT_PASSWORD` | No | Legacy user password |
| `N8N_WEBHOOK_URL` | Si (facturación) | URL del webhook N8N para QuickBooks |
| `PORT` | Auto (Heroku) | Puerto del servidor |
| `REDIS_URL` | No | Cache Redis en producción |
| `LOG_LEVEL` | No | Nivel de logging (default: INFO) |

### 10.2 Configuraciones por Entorno

| Setting | Development | Production | Testing |
|---------|-------------|------------|---------|
| DEBUG | True | False | — |
| DB | SQLite (local.db) | PostgreSQL | SQLite (memory) |
| CSRF | Enabled | Enabled | Disabled |
| Cookies seguras | No | Si | No |
| Talisman CSP | No | Si | No |
| Pool size | Default | 20 | Default |
| Pool recycle | 3600s | 1800s | — |

---

## 11. Seguridad

### Implementado (US01)

- CSRF protection global con Flask-WTF + meta tag + `X-CSRFToken` header auto-inject
- Flask-Talisman en producción: CSP, HSTS (1 año), X-Frame-Options DENY
- Secure cookies: HttpOnly, SameSite=Lax, Secure (prod)
- Password hashing con Werkzeug
- Open redirect prevention (`_is_safe_next()`)
- `MAX_CONTENT_LENGTH = 16MB` limit
- Audit logging de acciones de vendedores

### TODOs Identificados en Código

- `'unsafe-inline'` en script-src y style-src del CSP (migrar a nonces)
- Webhook de precios sin autenticación (`/webhook/actualizacion-precios`)
- Legacy user (`DefaultUser`) debería deshabilitarse en producción

---

## 12. Observaciones Arquitectónicas

### Fortalezas

- Sistema de precios robusto con 3 niveles de prioridad
- RBAC funcional con 3 capas de autorización
- Integración QuickBooks vía N8N (desacoplada)
- Generación de etiquetas PDF profesional
- Security hardening completo (CSRF, CSP, HSTS, secure cookies)
- Migraciones bien organizadas con branch merge

### Áreas de Mejora Potencial

- **Monolito masivo:** `app.py` con 5739 líneas contiene modelos, rutas y lógica — candidato a refactorización con Blueprints
- **`extensions.py` no utilizado:** `app.py` crea su propio `db = SQLAlchemy(app)` en lugar de usar `extensions.py`
- **Permisos hardcoded:** `Vendedor.tiene_permiso()` tiene permisos por rol en un dict hardcoded, no usa la tabla `RolPermiso` de la BD
- **Cobertura de tests mínima:** Solo 4 tests (CSRF), sin tests de rutas, modelos o lógica de negocio
- **Sin bundler frontend:** CSS/JS minificados manualmente, sin pipeline de build
- **Config dual:** `config.py` existe pero `app.py` configura todo inline
