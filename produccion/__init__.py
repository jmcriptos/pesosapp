"""Módulo de producción propia: lotes, consumo de insumos, mermas y
rendimiento, SIN inventario de insumos.

Es el hermano simple de `maquila`, pero NO comparte nada con él: allá el
material es ajeno y cada kilo queda en un ledger que no deja cerrar una
corrida sin saldo. Acá el material es de Jomar, con sus propios insumos y
fórmulas: lo que se declara consumido se anota tal cual, nadie verifica
disponibilidad, y lo que importa es el balance del lote (cuánto entró,
cuánto salió, dónde se fue la diferencia).
"""
import sys

# Mismo truco que maquila/__init__.py, y por el mismo motivo: con
# `python app.py` el script vive en sys.modules como `__main__`, no como
# `app`, y un `from app import X` desde acá reimportaría app.py entero a
# mitad de su propia carga. Se resuelve UNA vez acá y cada submódulo reusa
# este objeto. NO "simplificar" a imports directos de `app`.
app_module = sys.modules.get('app') or sys.modules['__main__']


def asegurar_tablas(app):
    """Crea las tablas del módulo si faltan. Idempotente y seguro de correr
    en cada arranque, en SQLite y en Postgres.

    Mismo criterio que `_ensure_haccp_columns` en app.py: el script
    `scripts/produccion_migracion.sql` sigue siendo la vía explícita, pero si
    el código llega a Heroku antes que el script, `/produccion` no puede
    responder un 500 por una tabla que no existe. Un fallo acá se registra y
    no tumba el arranque: el resto de la app no depende de estas tablas.

    Caso especial, de una sola vez: la primera versión del módulo (2026-10-02)
    ató los lotes a `ingrediente`/`receta` de maquila. Se reconoce porque
    `lote_consumo` existe sin la columna `insumo_id`. Esas tres tablas se
    tiran y se recrean con el catálogo propio; lo registrado con esa versión
    (lotes de prueba del primer día) se pierde, y queda dicho en el log.
    """
    from sqlalchemy import inspect as _inspect

    from sqlalchemy import text as _text

    from .models import (Formula, FormulaInsumo, Insumo, LoteCaja, LoteConsumo,
                         LoteMerma, LoteProduccion)

    db = app_module.db
    try:
        with app.app_context():
            insp = _inspect(db.engine)
            existentes = set(insp.get_table_names())
            if 'lote_consumo' in existentes:
                columnas = {c['name'] for c in insp.get_columns('lote_consumo')}
                if 'insumo_id' not in columnas:
                    app.logger.warning('[produccion] lote_consumo es de la primera '
                                       'versión (sin insumo_id): se recrean las '
                                       'tablas de lotes con el catálogo propio')
                    for modelo in (LoteMerma, LoteConsumo, LoteProduccion):
                        modelo.__table__.drop(bind=db.engine, checkfirst=True)
                    # El inspector cachea lo que ya miró: se vuelve a leer
                    # para que el paso siguiente no vea tablas recién tiradas.
                    insp = _inspect(db.engine)
                    existentes = set(insp.get_table_names())
            # 2026-10-03: el peso producido pasó a salir de las cajas pesadas
            # en pedidos, y la columna tecleada a mano cambió de sentido y de
            # nombre (peso_producido → peso_adicional). Se renombra, no se
            # recrea: lo ya declarado sigue contando como peso adicional.
            if 'lote_produccion' in existentes:
                columnas = {c['name'] for c in insp.get_columns('lote_produccion')}
                if 'peso_adicional' not in columnas and 'peso_producido' in columnas:
                    with db.engine.begin() as conn:
                        conn.execute(_text('ALTER TABLE lote_produccion '
                                           'RENAME COLUMN peso_producido TO peso_adicional'))
                    app.logger.info('[produccion] lote_produccion.peso_producido '
                                    'renombrada a peso_adicional')
            # En orden de dependencia: las FK apuntan a tablas ya creadas.
            for modelo in (Insumo, Formula, FormulaInsumo, LoteProduccion,
                           LoteConsumo, LoteMerma, LoteCaja):
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
