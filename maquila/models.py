"""Modelos del módulo de maquila.

`db` sale de `app` (no de `extensions`, que es código muerto). El ciclo de
importación se resuelve porque `app.py` importa este paquete AL FINAL,
cuando `db` y los modelos base ya existen.
"""
from datetime import datetime

from sqlalchemy import event
from sqlalchemy.engine import Engine

from . import app_module

# NO reemplazar por `from app import db`: revienta `python app.py` (el
# preview local) con un ImportError circular. Ver el comentario largo en
# maquila/__init__.py para el porqué.
db = app_module.db


@event.listens_for(Engine, 'checkout')
def _activar_foreign_keys_sqlite(dbapi_connection, connection_record, connection_proxy):
    """SQLite ignora las FK salvo que se le pida. En Postgres es un no-op.

    Se engancha a `checkout` (no a `connect`): en SQLite `:memory:` el engine
    usa `StaticPool`, una sola conexión física para toda la vida del proceso.
    `_ensure_haccp_columns()` (app.py, antes de importar este paquete) ya la
    abre al arrancar, así que un listener de `connect` llegaría tarde y jamás
    dispararía. `checkout` sí se dispara en cada préstamo de conexión del
    pool, incluida esa primera conexión ya viva — cuesta una pragma de más
    por checkout en SQLite, y en Postgres es un chequeo de string sin tocar
    la conexión.
    """
    if dbapi_connection.__class__.__module__.startswith('sqlite3'):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()


class Ingrediente(db.Model):
    __tablename__ = 'ingrediente'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)
    unidad = db.Column(db.String(10), nullable=False, default='kg')
    activo = db.Column(db.Boolean, nullable=False, default=True)
    notas = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Ingrediente {self.id} {self.nombre}>'


class RecepcionIngrediente(db.Model):
    __tablename__ = 'recepcion_ingrediente'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    recibido_en = db.Column(db.Date, nullable=False)
    documento_cliente = db.Column(db.String(100), nullable=True)
    temperatura = db.Column(db.Numeric(5, 2), nullable=True)
    transportista = db.Column(db.String(120), nullable=True)
    firma = db.Column(db.LargeBinary, nullable=True)
    firma_mimetype = db.Column(db.String(50), nullable=True)
    notas = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=False)
    registrado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    anulada_en = db.Column(db.DateTime, nullable=True)
    anulada_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    motivo_anulacion = db.Column(db.Text, nullable=True)

    cliente = db.relationship('Cliente')
    lineas = db.relationship('RecepcionLinea', back_populates='recepcion',
                             cascade='all, delete-orphan')
    fotos = db.relationship('RecepcionFoto', back_populates='recepcion',
                            cascade='all, delete-orphan')

    @property
    def anulada(self):
        return self.anulada_en is not None


class RecepcionLinea(db.Model):
    __tablename__ = 'recepcion_linea'
    id = db.Column(db.Integer, primary_key=True)
    recepcion_id = db.Column(db.Integer, db.ForeignKey('recepcion_ingrediente.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False, index=True)
    lote_cliente = db.Column(db.String(50), nullable=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    peso_total = db.Column(db.Numeric(10, 3), nullable=False, default=0)

    recepcion = db.relationship('RecepcionIngrediente', back_populates='lineas')
    ingrediente = db.relationship('Ingrediente')
    bultos = db.relationship('RecepcionBulto', back_populates='linea',
                             cascade='all, delete-orphan', order_by='RecepcionBulto.numero')


class RecepcionBulto(db.Model):
    __tablename__ = 'recepcion_bulto'
    id = db.Column(db.Integer, primary_key=True)
    recepcion_linea_id = db.Column(db.Integer, db.ForeignKey('recepcion_linea.id', ondelete='CASCADE'),
                                   nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)
    peso = db.Column(db.Numeric(8, 3), nullable=False)

    linea = db.relationship('RecepcionLinea', back_populates='bultos')

    __table_args__ = (
        db.UniqueConstraint('recepcion_linea_id', 'numero', name='uq_bulto_linea_numero'),
    )


class RecepcionFoto(db.Model):
    __tablename__ = 'recepcion_foto'
    id = db.Column(db.Integer, primary_key=True)
    recepcion_id = db.Column(db.Integer, db.ForeignKey('recepcion_ingrediente.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    imagen = db.Column(db.LargeBinary, nullable=False)
    mimetype = db.Column(db.String(50), nullable=False)
    subida_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    recepcion = db.relationship('RecepcionIngrediente', back_populates='fotos')


class Receta(db.Model):
    __tablename__ = 'receta'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    base_kg = db.Column(db.Numeric(10, 3), nullable=False, default=100)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creada_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    creada_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)

    producto = db.relationship('Producto')
    cliente = db.relationship('Cliente')
    ingredientes = db.relationship('RecetaIngrediente', back_populates='receta',
                                   cascade='all, delete-orphan')


class RecetaIngrediente(db.Model):
    __tablename__ = 'receta_ingrediente'
    id = db.Column(db.Integer, primary_key=True)
    receta_id = db.Column(db.Integer, db.ForeignKey('receta.id', ondelete='CASCADE'),
                          nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)

    receta = db.relationship('Receta', back_populates='ingredientes')
    ingrediente = db.relationship('Ingrediente')

    __table_args__ = (
        db.UniqueConstraint('receta_id', 'ingrediente_id', name='uq_receta_ingrediente'),
    )


class CorridaProduccion(db.Model):
    __tablename__ = 'corrida_produccion'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False, index=True)
    receta_id = db.Column(db.Integer, db.ForeignKey('receta.id'), nullable=True)
    lote = db.Column(db.String(50), nullable=False, index=True)
    fecha_produccion = db.Column(db.Date, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='abierta')
    notas = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=False)
    registrado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cerrada_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    cerrada_en = db.Column(db.DateTime, nullable=True)

    cliente = db.relationship('Cliente')
    producto = db.relationship('Producto')
    receta = db.relationship('Receta')
    cajas = db.relationship('CorridaCaja', back_populates='corrida',
                            cascade='all, delete-orphan', order_by='CorridaCaja.numero')
    consumos = db.relationship('CorridaConsumo', back_populates='corrida',
                               cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'lote', name='uq_corrida_cliente_lote'),
    )

    @property
    def peso_producido(self):
        """Suma de las cajas vivas. NO se guarda: un número guardado puede mentir."""
        from decimal import Decimal
        total = Decimal('0')
        for caja in self.cajas:
            if caja.anulada_en is None:
                total += Decimal(str(caja.peso))
        return total


class CorridaCaja(db.Model):
    __tablename__ = 'corrida_caja'
    id = db.Column(db.Integer, primary_key=True)
    corrida_id = db.Column(db.Integer, db.ForeignKey('corrida_produccion.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)
    peso = db.Column(db.Numeric(8, 3), nullable=False)
    # ON DELETE SET NULL: si se borra la línea del pedido, la CajaPesada cae por
    # cascada y esta caja vuelve al stock sola, sin que ningún código lo recuerde.
    caja_pesada_id = db.Column(db.Integer,
                               db.ForeignKey('caja_pesada.id', ondelete='SET NULL'),
                               nullable=True, unique=True, index=True)
    anulada_en = db.Column(db.DateTime, nullable=True)
    motivo_anulacion = db.Column(db.Text, nullable=True)

    corrida = db.relationship('CorridaProduccion', back_populates='cajas')
    caja_pesada = db.relationship('CajaPesada')

    __table_args__ = (
        db.UniqueConstraint('corrida_id', 'numero', name='uq_corrida_caja_numero'),
    )

    @property
    def disponible(self):
        return self.caja_pesada_id is None and self.anulada_en is None


class CorridaConsumo(db.Model):
    __tablename__ = 'corrida_consumo'
    id = db.Column(db.Integer, primary_key=True)
    corrida_id = db.Column(db.Integer, db.ForeignKey('corrida_produccion.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False)
    cantidad_teorica = db.Column(db.Numeric(10, 3), nullable=False, default=0)
    cantidad_real = db.Column(db.Numeric(10, 3), nullable=False)

    corrida = db.relationship('CorridaProduccion', back_populates='consumos')
    ingrediente = db.relationship('Ingrediente')
    origenes = db.relationship('CorridaConsumoOrigen', back_populates='consumo',
                               cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('corrida_id', 'ingrediente_id', name='uq_corrida_consumo'),
    )


class CorridaConsumoOrigen(db.Model):
    __tablename__ = 'corrida_consumo_origen'
    id = db.Column(db.Integer, primary_key=True)
    corrida_consumo_id = db.Column(db.Integer, db.ForeignKey('corrida_consumo.id', ondelete='CASCADE'),
                                   nullable=False, index=True)
    recepcion_linea_id = db.Column(db.Integer, db.ForeignKey('recepcion_linea.id'),
                                   nullable=False, index=True)
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)
    automatico = db.Column(db.Boolean, nullable=False, default=True)

    consumo = db.relationship('CorridaConsumo', back_populates='origenes')
    recepcion_linea = db.relationship('RecepcionLinea')


class MovimientoIngrediente(db.Model):
    """Ledger append-only. Nunca se hace UPDATE ni DELETE sobre esta tabla."""
    __tablename__ = 'movimiento_ingrediente'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False, index=True)
    recepcion_linea_id = db.Column(db.Integer, db.ForeignKey('recepcion_linea.id'),
                                   nullable=True, index=True)
    tipo = db.Column(db.String(20), nullable=False)          # entrada|salida|ajuste|devolucion
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)  # CON SIGNO
    origen_tipo = db.Column(db.String(20), nullable=False)   # recepcion|corrida|manual
    origen_id = db.Column(db.Integer, nullable=True)
    motivo = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=False)
    registrado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    cliente = db.relationship('Cliente')
    ingrediente = db.relationship('Ingrediente')
    recepcion_linea = db.relationship('RecepcionLinea')
    vendedor = db.relationship('Vendedor')

    __table_args__ = (
        db.Index('ix_mov_cliente_ingr_fecha', 'cliente_id', 'ingrediente_id', 'registrado_en'),
    )
