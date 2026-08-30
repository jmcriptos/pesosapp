"""El grupo de facturación es el impuesto, no el par (se_pesa, tax_rate).

`se_pesa` estaba en la clave sin una razón de facturación: el docstring de
`_grupo_facturable` justificaba el `tax_rate` («QuickBooks no factura junto lo
que paga impuestos distintos») y arrastraba el `se_pesa` sin justificarlo.

La evidencia de producción dice que no corresponde: de 941 pedidos, 0 mezclan
impuestos, pero 7 mezclan pesable con importado bajo un mismo impuesto — y los
7 se facturaron en QuickBooks sin problema (agosto 2026, ids 1272..1297).
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
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


def _producto(nombre, se_pesa, tax):
    from app import Producto
    producto = Producto(nombre=nombre, temperatura='4°C', se_pesa=se_pesa,
                        tax_rate=tax, qbo_id=f'QBO-{nombre[:6]}-{tax:g}')
    _db.session.add(producto)
    _db.session.commit()
    return producto


# === La clave del grupo ===

def test_pesable_e_importado_del_mismo_impuesto_son_el_mismo_grupo(app):
    """Es el cambio de fondo: `se_pesa` sale de la clave."""
    with app.app_context():
        from app import _grupo_facturable

        pesable = _producto('Ham di Pasku', True, 14.0)
        importado = _producto('Cooked Chicken Ham', False, 14.0)

        assert _grupo_facturable(pesable) == _grupo_facturable(importado)


def test_impuestos_distintos_siguen_siendo_grupos_distintos(app):
    """La restricción real de QuickBooks se conserva intacta."""
    with app.app_context():
        from app import _grupo_facturable

        assert _grupo_facturable(_producto('Aceite', False, 10.0)) != \
               _grupo_facturable(_producto('Ham', False, 14.0))


def test_un_producto_inexistente_no_tiene_grupo(app):
    with app.app_context():
        from app import _grupo_facturable
        assert _grupo_facturable(None) is None


def test_el_impuesto_cero_tiene_clave_propia(app):
    """Regresión: 0.0 es falsy y no debe colapsar a «sin grupo».

    `tax_rate` es 0.0 por defecto, así que un producto recién creado sin
    impuesto elegido caería en ese agujero.
    """
    with app.app_context():
        from app import _grupo_facturable, _clave_grupo, _etiqueta_grupo

        grupo = _grupo_facturable(_producto('Sin impuesto', False, 0.0))

        assert grupo is not None
        assert _clave_grupo(grupo) != ''
        assert _etiqueta_grupo(grupo) != '—'


# === Qué pedidos se aceptan ===

def test_un_pedido_puede_mezclar_pesable_e_importado_del_mismo_impuesto(app):
    """Los 7 pedidos de producción que QuickBooks facturó sin quejarse."""
    with app.app_context():
        from app import _validar_grupo_unico

        pesable = _producto('Ham di Pasku', True, 14.0)
        importado = _producto('Cooked Chicken Ham', False, 14.0)

        # No debe levantar _PedidoFormError
        _validar_grupo_unico([
            {'producto_id': pesable.id},
            {'producto_id': importado.id},
        ])


def test_un_pedido_sigue_sin_poder_mezclar_impuestos(app):
    with app.app_context():
        from app import _validar_grupo_unico, _PedidoFormError

        diez = _producto('Aceite', False, 10.0)
        catorce = _producto('Ham', True, 14.0)

        with pytest.raises(_PedidoFormError) as exc:
            _validar_grupo_unico([
                {'producto_id': diez.id},
                {'producto_id': catorce.id},
            ])
        assert 'impuestos distintos' in str(exc.value)


# === La pantalla de grupos ===

def test_el_catalogo_ofrece_un_grupo_por_impuesto(app):
    """Cuatro combinaciones de (se_pesa, tax) colapsan en dos grupos."""
    with app.app_context():
        from app import _grupos_del_catalogo

        _producto('Aceite', False, 10.0)
        _producto('Chuleta', True, 10.0)
        _producto('Cooked Ham', False, 14.0)
        _producto('Ham di Pasku', True, 14.0)

        grupos = _grupos_del_catalogo()

        assert len(grupos) == 2, [g['etiqueta'] for g in grupos]
        assert [g['clave'] for g in grupos] == ['imp:10', 'imp:14']


def test_los_ejemplos_del_grupo_mezclan_pesables_e_importados(app):
    """Los dos productos de muestra ya no salen de un solo tipo."""
    with app.app_context():
        from app import _grupos_del_catalogo

        _producto('AAA Importado', False, 14.0)
        _producto('BBB Pesable', True, 14.0)

        ejemplos = _grupos_del_catalogo()[0]['ejemplos']

        assert ejemplos == ['AAA Importado', 'BBB Pesable']


def test_la_etiqueta_nombra_el_impuesto(app):
    """Desde Task 1 (2026-08-30) esto es el OB traducido, no el código crudo:
    `_etiqueta_grupo` delega en `_ob_de_codigo` (ver test_pedido_impuesto.py
    para la traducción en sí). Lo que este test protege es que no vuelva a
    salir «Pesable»/«Importado», que es lo que originó el bug de fondo."""
    with app.app_context():
        from app import _grupo_facturable, _etiqueta_grupo

        etiqueta = _etiqueta_grupo(_grupo_facturable(_producto('Ham', True, 14.0)))

        assert etiqueta == 'OB 0%'
        assert 'Pesable' not in etiqueta and 'Importado' not in etiqueta


# === Compatibilidad de las claves viejas ===

@pytest.mark.parametrize('clave_vieja', ['pesable:14', 'importado:14'])
def test_una_clave_vieja_sigue_resolviendo_al_grupo_de_su_impuesto(app, clave_vieja):
    """Un enlace guardado o una sesión a medio camino no debe romperse.

    Antes se verificaba con '14' en la etiqueta; desde que `_etiqueta_grupo`
    traduce a OB (Task 1, 2026-08-30) ese dígito ya no aparece ahí, así que
    se compara contra la etiqueta de la clave actual del mismo impuesto —
    prueba lo mismo (misma resolución) sin depender del código crudo.
    """
    with app.app_context():
        from app import _etiqueta_de_clave_grupo

        assert _etiqueta_de_clave_grupo(clave_vieja) == _etiqueta_de_clave_grupo('imp:14')
        assert _etiqueta_de_clave_grupo(clave_vieja) == 'OB 0%'


def test_una_clave_basura_no_resuelve(app):
    with app.app_context():
        from app import _etiqueta_de_clave_grupo
        assert _etiqueta_de_clave_grupo('basura') == ''
        assert _etiqueta_de_clave_grupo('') == ''


def test_un_enlace_viejo_aterriza_en_el_grupo_correcto(app):
    """Una URL con la clave vieja no debe mandar al vendedor a reelegir.

    Es el caso del marcador guardado y de la pestaña que quedó abierta desde
    antes del cambio: `pesable:10` sigue siendo el grupo del impuesto 10.
    """
    with app.app_context():
        from app import Rol, Territorio, Vendedor, Cliente

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='t', descripcion='T')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(username='admin', email='a@test.com',
                            nombre_completo='Admin', rol_id=rol.id,
                            territorio_id=territorio.id, activo=True)
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        cliente = Cliente(nombre='Cliente', territorio_id=territorio.id)
        _db.session.add(cliente)
        _producto('Chuleta', True, 10.0)
        _db.session.commit()

        client = flask_app.test_client()
        client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                    follow_redirects=True)

        html = client.get(
            f'/pedidos/nuevo?cliente={cliente.id}&grupo=pesable:10'
        ).get_data(as_text=True)

        # Llegó al paso del pedido (no volvió a la pantalla de grupos)
        assert 'id="form-nuevo-pedido"' in html
        assert 'name="grupo" value="imp:10"' in html
