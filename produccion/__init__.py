"""Módulo de producción propia: lotes, consumo de ingredientes, mermas y
rendimiento, SIN inventario de ingredientes.

Es el hermano simple de `maquila`. Allá el material es ajeno y cada kilo
que entra o sale queda en un ledger que no deja cerrar una corrida sin
saldo. Acá el material es de Jomar: lo que se declara consumido se anota
tal cual, nadie verifica disponibilidad, y lo que importa es el balance
del lote (cuánto entró, cuánto salió, dónde se fue la diferencia).
"""
import sys

# Mismo truco que maquila/__init__.py, y por el mismo motivo: con
# `python app.py` el script vive en sys.modules como `__main__`, no como
# `app`, y un `from app import X` desde acá reimportaría app.py entero a
# mitad de su propia carga. Se resuelve UNA vez acá y cada submódulo reusa
# este objeto. NO "simplificar" a imports directos de `app`.
app_module = sys.modules.get('app') or sys.modules['__main__']


def asegurar_tablas(app):
    """Crea las tres tablas del módulo si faltan. Idempotente y seguro de
    correr en cada arranque, en SQLite y en Postgres.

    Mismo criterio que `_ensure_haccp_columns` en app.py: el script
    `scripts/produccion_migracion.sql` sigue siendo la vía documentada, pero
    si el código llega a Heroku antes que el script, `/produccion` no puede
    responder un 500 por una tabla que no existe. Un fallo acá se registra y
    no tumba el arranque: el resto de la app no depende de estas tablas.
    """
    from .models import LoteConsumo, LoteMerma, LoteProduccion

    db = app_module.db
    try:
        with app.app_context():
            for modelo in (LoteProduccion, LoteConsumo, LoteMerma):
                modelo.__table__.create(bind=db.engine, checkfirst=True)
    except Exception as exc:  # pragma: no cover - depende del motor real
        app.logger.warning(f'[produccion] no se pudieron asegurar las tablas: {exc}')


def registrar_produccion(app):
    """Importa los modelos, asegura sus tablas y registra el blueprint.

    Los modelos DEBEN quedar importados aunque nadie los use aquí: si no,
    `db.create_all()` no ve las tablas y el módulo falla en silencio.
    """
    from . import models  # noqa: F401
    from .routes import bp

    asegurar_tablas(app)
    app.register_blueprint(bp)
    return bp
