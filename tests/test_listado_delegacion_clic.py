# tests/test_listado_delegacion_clic.py
"""Los botones del listado tienen que recibir sus clics.

Reportado desde iPhone: el PDF de factura funciona desde el detalle del pedido
pero no desde el listado. Mismo botón, mismo handler, distinto contenedor.

Causa: `data-factura-share` se delega en `document` (evento click), y en el
listado el botón vive dentro de `<div class="pc-actions" data-stop-propagation>`,
que hace `ev.stopPropagation()`. El clic muere en ese div y nunca llega a
`document`, así que el handler no corre. Comprobado en el navegador: el clic
llega al contenedor y NO llega a document.

`data-stop-propagation` ahí es además innecesario: el handler de navegación de
la tarjeta ya ignora los clics sobre `a, button, form, input, label`.

El borrado seguía funcionando porque `data-confirm` se delega sobre `submit`,
no sobre `click`.
"""
import os
import re
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
        from app import Rol, Territorio, Vendedor, Cliente, Pedido

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        terr = Territorio(nombre='t', descripcion='t')
        _db.session.add(terr)
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=rol.id, territorio_id=terr.id, activo=True)
        v.set_password('testpass')
        _db.session.add(v)
        cli = Cliente(nombre='Cliente Uno', territorio_id=terr.id)
        _db.session.add(cli)
        _db.session.flush()
        # Un pedido facturado CON invoice: es la única forma de que el botón
        # de factura PDF se renderice en el listado.
        _db.session.add(Pedido(cliente_id=cli.id, estado='facturado',
                               invoice_id_qbo='12345', doc_number_qbo='INV-777'))
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'testpass'},
           follow_redirects=True)
    return c


def test_el_boton_de_factura_no_queda_dentro_de_stop_propagation(app, logged_client):
    """Si un ancestro corta la propagación, el handler delegado nunca corre.

    Se comprueba sobre el HTML renderizado y de la forma más directa posible:
    el contenedor de acciones es el único ancestro del botón que llevaba
    data-stop-propagation, así que basta con que ese atributo ya no esté ahí.
    """
    html = logged_client.get('/pedidos').get_data(as_text=True)

    assert 'data-factura-share' in html, 'el listado debe renderizar el botón'

    contenedores_que_cortan = re.findall(
        r'<div class="pc-actions"[^>]*data-stop-propagation', html)
    assert not contenedores_que_cortan, (
        'El botón de factura PDF vive dentro de <div class="pc-actions" '
        'data-stop-propagation>: el clic muere ahí y nunca llega a document, '
        'que es donde base.js delega data-factura-share.'
    )


def test_los_forms_de_accion_tampoco_cortan_la_propagacion(app, logged_client):
    """Mismo motivo: cualquier ancestro que corte deja sordo al handler."""
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'class="pc-action-form"' not in html or \
        not re.findall(r'class="pc-action-form"[^>]*data-stop-propagation', html), (
        'un form de acción sigue cortando la propagación del clic'
    )


def test_la_tarjeta_ignora_los_clics_sobre_controles(app):
    """Es lo que hace innecesario el stopPropagation: el handler de navegación
    de la tarjeta ya se desentiende de los clics sobre controles."""
    with open(os.path.join(os.path.dirname(__file__), '..',
                           'templates', 'pedidos.html'), encoding='utf-8') as fh:
        js = fh.read()

    assert "closest('a, button, form, input, label')" in js, (
        'sin esta guarda, quitar data-stop-propagation haría que tocar un '
        'botón de la tarjeta además navegue al detalle'
    )
