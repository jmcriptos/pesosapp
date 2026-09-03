"""Módulo de maquila: ingredientes del cliente, producción y trazabilidad."""


def registrar_maquila(app):
    """Importa los modelos y registra el blueprint.

    Los modelos DEBEN quedar importados aunque nadie los use aquí: si no,
    `db.create_all()` no ve las tablas y todo el módulo falla en silencio.
    """
    from . import models  # noqa: F401
    from .routes import bp

    app.register_blueprint(bp)
    return bp
