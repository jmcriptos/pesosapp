"""Módulo de maquila: ingredientes del cliente, producción y trazabilidad."""
import sys

# app.py define `db` y el resto de los símbolos que usan los submódulos de
# este paquete (Cliente, Producto, Pedido, requiere_rol, DASHBOARD_TIMEZONE,
# ...). Resolverlos con `from app import X`, símbolo por símbolo en cada
# archivo, funciona cuando app.py se importa COMO MÓDULO — gunicorn
# `app:app`, o `from app import app` en los tests — porque ahí
# `sys.modules['app']` ya existe antes de que ningún submódulo de maquila
# lo necesite. Pero cuando se levanta con `python app.py` (así arranca el
# preview local, vía launch.json), Python registra el script como
# `__main__`, NO como `app`: un `from app import X` desde un submódulo de
# maquila no encuentra 'app' en sys.modules y REIMPORTA app.py entero desde
# cero. Esa segunda ejecución de app.py vuelve a llegar a
# `registrar_maquila()` mientras la primera ejecución sigue a medio
# inicializar, y revienta más abajo con "cannot import name 'X' from
# partially initialized module 'maquila.models' (most likely due to a
# circular import)".
#
# Se resuelve UNA sola vez acá, mirando sys.modules en vez de importar por
# nombre, y cada submódulo reusa este objeto (`from . import app_module`)
# en vez de repetir su propio `from app import X`. Así ningún submódulo
# dispara la reimportación — funciona igual en los dos caminos (módulo o
# `__main__`), y nadie tiene que acordarse de este truco archivo por
# archivo. NO "simplificar" esto de vuelta a imports directos de `app`: eso
# es exactamente lo que rompe `python app.py`.
app_module = sys.modules.get('app') or sys.modules['__main__']


def registrar_maquila(app):
    """Importa los modelos y registra el blueprint.

    Los modelos DEBEN quedar importados aunque nadie los use aquí: si no,
    `db.create_all()` no ve las tablas y todo el módulo falla en silencio.
    """
    from . import models  # noqa: F401
    from .routes import bp

    app.register_blueprint(bp)
    return bp
