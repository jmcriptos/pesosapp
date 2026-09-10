"""Tras el backfill, ~960 pedidos pasan de `facturado` a `entregado` en
producción. En esta empresa se factura ANTES de entregar, así que un pedido
entregado se facturó igual — entregarlo no lo desfactura. Si el dashboard
siguiera contando solo `estado == 'facturado'`, todas las métricas que miden
"lo facturado" caerían de 964 a 4 sin que nadie hubiera dejado de facturar:
una regresión silenciosa en cifras que JM mira todos los días.

Este archivo prueba el único punto que cubre nueve de los llamadores de una
sola vez: `_pedido_facturado_en_periodo_local`. Las seis consultas SQL y los
dos contadores que no pasan por el helper se arreglaron uno por uno en
app.py y se verificaron a mano en el reporte de la Task 6.
"""
import os

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


def test_un_pedido_entregado_sigue_contando_como_facturado(app):
    """Tras el backfill, 960 pedidos pasan a `entregado`. Si el dashboard
    sigue contando solo `facturado`, las cifras caen de 964 a 4 sin que nadie
    haya dejado de facturar: una regresión silenciosa en números que JM mira
    todos los días."""
    from app import _pedido_facturado_en_periodo_local, Pedido
    from datetime import date, datetime
    p = Pedido(estado='entregado', fecha_facturacion=datetime(2026, 9, 1, 12, 0))
    assert _pedido_facturado_en_periodo_local(p, date(2026, 9, 1)) is True


def test_un_pendiente_no_cuenta_como_facturado(app):
    from app import _pedido_facturado_en_periodo_local, Pedido
    from datetime import date, datetime
    p = Pedido(estado='pendiente', fecha_facturacion=datetime(2026, 9, 1, 12, 0))
    assert _pedido_facturado_en_periodo_local(p, date(2026, 9, 1)) is False
