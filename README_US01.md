# IMPLEMENTACIÓN US01

Esta entrega endurece seguridad sin romper endpoints existentes.

## Cambios clave

- CSRF (Flask-WTF):
  - Habilitado `CSRFProtect(app)` en `app.py`.
  - Templates con `<form method="POST">` incluyen `{{ csrf_token() }}`.
  - `<meta name="csrf-token" content="...">` en `base.html` + `static/js/base.js` añade `X-CSRFToken` a `fetch()`/jQuery automáticamente.

- Formularios protegidos:
  - Insertado `{{ csrf_token() }}` en formularios POST de: `login.html`, `pedido_form.html`, `detalles_pedido.html`, `preparar_pedido.html`, `productos.html`, `editar_producto.html`, `clientes.html`, `cliente_form.html`, `form_generar_etiquetas.html`, `facturacion.html` (dos formularios), `pedidos.html` (acciones inline), `admin/vendedores.html` (crear y actualizar territorio rápido), `admin/territorios.html`, `admin/clientes_vendedores.html`, `formulario_importacion.html`.

- Cookies seguras (solo producción):
  - `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE` y equivalentes de remember-cookie ajustados en `app.py` cuando `FLASK_ENV=production`.

- CSP (solo producción, sin `'unsafe-inline'` en scripts):
  - Configurado con Flask‑Talisman sin `'unsafe-inline'` en `script-src`; se permiten CDNs usados (jsDelivr, code.jquery.com, cdnjs) y nonce automático para scripts si fuese necesario.

- JS inline movido:
  - Script general de `templates/base.html` movido a `static/js/base.js` y referenciado desde el template.

## Migraciones

No se requieren migraciones de base de datos para US01.

## Cómo probar

- Pruebas automáticas (requiere pytest):
```
pip install -r requirements.txt
pytest -q
```
- Cubre:
  - POST sin `csrf_token` → 400
  - POST con `X-CSRFToken` procedente del meta → 200

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


