# Guía de Desarrollo — PesosApp

> Documento generado por BMAD Document-Project Workflow (Deep Scan)
> Fecha: 2026-02-08 | Versión: 1.0

---

## 1. Setup Local

### Prerrequisitos

- Python 3.12
- pip
- PostgreSQL (opcional, SQLite funciona para dev)

### Instalación

```bash
# Clonar repositorio
git clone https://github.com/jmcriptos/pesosapp.git
cd pesosapp

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores (SECRET_KEY, DATABASE_URL, etc.)
```

### Variables de Entorno Mínimas (.env)

```bash
FLASK_ENV=development
SECRET_KEY=tu-clave-secreta-dev
DATABASE_URL=sqlite:///local.db
# O para PostgreSQL local:
# DATABASE_URL=postgresql://user:pass@localhost:5432/pesosapp
```

### Ejecutar Migraciones

```bash
flask db upgrade
```

### Inicializar Datos Multi-vendedor

```bash
python init_multivendor_data.py
```

### Ejecutar Servidor de Desarrollo

```bash
flask run
# O directamente:
python app.py
# Disponible en http://0.0.0.0:5002
```

---

## 2. Estructura del Código

### Archivo Principal: `app.py` (5739 líneas)

El archivo está organizado en secciones:

| Líneas | Sección |
|--------|---------|
| 1-55 | Imports y configuración de Flask |
| 56-167 | Setup: DB, CSRF, Talisman, Login Manager |
| 168-300 | Modelo `Vendedor` con métodos de permisos |
| 302-412 | Auth: user_loader, login/logout, require_login |
| 413-770 | Dashboards (admin y vendedor) + API métricas |
| 772-1020 | Modelos: Producto, Cliente, Facturacion, Recepcion, Importacion, Pedido, DetallePedido, Rol, Permiso, RolPermiso, Territorio, ClienteVendedor |
| 1022-1074 | Decoradores de seguridad: requiere_permiso_recurso, requiere_rol |
| 1076-1196 | Modelos pricing: ListaPrecio, PrecioProducto, ClienteListaPrecio, PrecioClienteProducto |
| 1197-1345 | Helpers: obtener_precio_producto_cliente, pedido_a_json, obtener_ip_servidor |
| 1347-2236 | Rutas Admin: vendedores, territorios, asignaciones, reportes, analytics, export |
| 2238-2720 | Dashboard principal (KPIs, ventas, tendencias) |
| 2723-3434 | Rutas Pedidos: CRUD, detalles, preparar, facturar, etiquetas |
| 3438-3930 | Rutas Precios: listas, productos, clientes, API |
| 3982-4095 | Rutas Productos: CRUD + API |
| 4099-4165 | Rutas Recepciones: CRUD |
| 4168-4270 | Rutas Facturación: CRUD |
| 4271-4590 | Rutas Importaciones + Reportes |
| 4590-4700 | Rutas Clientes: CRUD |
| 4702-4930 | Reportes Excel y etiquetas vencimiento |
| 4930-5140 | Etiquetas de pedidos (4"×2" y A4) |
| 5141-5728 | Carga masiva de precios (CSV) |
| 5730-5739 | if __name__ == '__main__' |

### Utilidades (utils/)

| Archivo | Uso Principal |
|---------|--------------|
| `label_utils.py` | Generar PDFs de etiquetas con ReportLab |
| `cache.py` | Cache en memoria con decoradores (@cached) |
| `filters.py` | Filtro Jinja2 kpi_tag() para badges de KPI |
| `performance.py` | Monitor de performance, query counter, @timer |

---

## 3. Base de Datos

### Migraciones

```bash
# Ver estado de migraciones
flask db current

# Crear nueva migración
flask db migrate -m "descripción del cambio"

# Aplicar migraciones pendientes
flask db upgrade

# Revertir última migración
flask db downgrade
```

### Historial de Migraciones (14 versiones)

1. `55278b70cebe` — Tablas iniciales (Cliente, Producto, Facturacion, Recepcion, Importacion)
2. `833a686387a1` — Pedido + DetallePedido
3. `d8bda71c9188` — Campo `cajas` en DetallePedido
4. `9b5b69d7a839` — NULLs permitidos en lote/fechas
5. `a3dfe2d3a498` — Sistema de precios (ListaPrecio, PrecioProducto, etc.)
6. `ed70f8d30408` — precio_unitario y subtotal en DetallePedido
7. `fde620f42cae` — qbo_id en Cliente y Producto
8. `08181e47fe1e` — tax_rate en Producto
9. `43bbe6237561` — Confirmación qbo_id
10. `z99` — 8 índices de rendimiento
11. `660d129cdef9` — Sistema multi-vendedor (branch separado)
12. `4cf82d9de5ac` — Merge branches main + multivendor
13. `9d79cf425a74` — territorio_id en Cliente
14. `f7a8b9c0d1e2` — fecha_facturacion en Pedido

---

## 4. Testing

### Ejecutar Tests

```bash
pip install pytest
pytest -q
```

### Tests Existentes

- `tests/test_csrf.py` — 4 tests de protección CSRF
  - POST sin token → 400
  - POST con X-CSRFToken → 200
  - Login requiere CSRF
  - Login acepta CSRF en hidden input

### Fixtures (conftest.py)

- `app` — App Flask con TestingConfig (SQLite in-memory, CSRF deshabilitado parcial)
- `client` — Test client Flask
- `csrf_token` — Token CSRF para requests

---

## 5. Despliegue en Heroku

### Configuración Requerida

```bash
# Variables de entorno en Heroku
heroku config:set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
heroku config:set FLASK_ENV=production
heroku config:set N8N_WEBHOOK_URL=https://tu-n8n-instance.com/webhook/...

# La DATABASE_URL se configura automáticamente con el addon PostgreSQL
```

### Procfile

```
web: gunicorn app:app
```

### Migraciones en Heroku

```bash
heroku run flask db upgrade
```

### Pool de Conexiones (Producción)

- `pool_size`: 20
- `pool_recycle`: 1800s (30 min)
- `pool_timeout`: 30s
- `max_overflow`: 20
- `pool_pre_ping`: True

---

## 6. Convenciones del Código

### Naming

- **Modelos:** PascalCase español (Vendedor, DetallePedido, ListaPrecio)
- **Tablas:** snake_case español (detalle_pedido, lista_precio)
- **Rutas:** snake_case para funciones, kebab-case para URLs
- **Templates:** snake_case.html, agrupados por módulo (admin/, precios/)

### Patrones Recurrentes

- `to_dict()` en modelos para serialización JSON
- `calcular_precios()` en modelos de pricing para computar márgenes
- Decoradores custom para permisos por recurso
- Flash messages para feedback al usuario en rutas server-rendered
- JSON responses para endpoints API consumidos por JS frontend

### CSRF en AJAX

El `base.js` auto-inyecta `X-CSRFToken` header en todas las llamadas `fetch()` y jQuery AJAX. El token viene del meta tag `<meta name="csrf-token">` en `base.html`.
