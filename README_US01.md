# IMPLEMENTACIÓN US01

Esta entrega endurece seguridad sin romper endpoints existentes.

## Cambios clave

- CSRF global:
  - Utilidades añadidas en `app.py`: generación de token por sesión, helper `csrf_token()` para `<input hidden>` y `csrf_token_value()` para meta.
  - Verificación en `before_request` para métodos no seguros (POST/PUT/DELETE), aceptando token vía campo `csrf_token` o cabeceras `X-CSRFToken`/`X-CSRF-Token`.
  - Inyección `<meta name="csrf-token">` en `templates/base.html` y `static/js/base.js` intercepta `fetch()` para enviar el header automáticamente.

- Formularios protegidos:
  - Insertado `{{ csrf_token() }}` en formularios POST de: `login.html`, `pedido_form.html`, `detalles_pedido.html`, `preparar_pedido.html`, `productos.html`, `editar_producto.html`, `clientes.html`, `cliente_form.html`, `form_generar_etiquetas.html`, `facturacion.html` (dos formularios), `pedidos.html` (acciones inline), `admin/vendedores.html` (crear y actualizar territorio rápido), `admin/territorios.html`, `admin/clientes_vendedores.html`, `formulario_importacion.html`.

- Cookies seguras (solo producción):
  - `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE` y equivalentes de remember-cookie ajustados en `app.py` cuando `FLASK_ENV=production`.

- CSP (solo producción):
  - Política Talisman compatible con los CDNs usados (jsDelivr, code.jquery.com, cdnjs) y `unsafe-inline` temporal para no romper scripts actuales.

- JS inline movido:
  - Script general de `templates/base.html` movido a `static/js/base.js` y referenciado desde el template.

## Migraciones

No se requieren migraciones de base de datos para US01.

## Comandos útiles

Entorno local (ejemplo):

```
export FLASK_ENV=development
export SECRET_KEY="<clave-secreta>"
flask run
```

Producción (habilita cookies seguras y CSP):

```
export FLASK_ENV=production
export SECRET_KEY="<clave-secreta-fuerte>"
gunicorn 'app:app'
```

## Notas

- Si alguna vista POST personalizada retorna 400 por CSRF en pruebas con JS, asegúrese de:
  - Incluir `{{ csrf_token() }}` en el `<form>`; o
  - Enviar header `X-CSRFToken` al usar `fetch()`/AJAX (el `base.js` ya lo hace globalmente cuando se carga `base.html`).


