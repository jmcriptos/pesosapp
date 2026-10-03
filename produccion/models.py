"""Modelos del módulo de producción propia.

Seis tablas, todas propias: nada se comparte con maquila. Allá el catálogo
es el de los clientes de maquila (ingredientes que ellos entregan, recetas
que ellos piden); acá son los insumos y las fórmulas de la casa. Son
mundos distintos y mezclarlos confundía a quien registra.

No hay ledger: un lote anota lo que se usó y lo que salió, y el balance
(merma, rendimiento) se deriva en cada lectura. Ningún total calculado se
guarda; lo único guardado es lo que alguien tecleó.
"""
from datetime import datetime
from decimal import Decimal

from . import app_module

# NO reemplazar por `from app import db`: revienta `python app.py` con un
# ImportError circular. Ver el comentario en produccion/__init__.py.
db = app_module.db

# Dónde se fue el kilo que no salió como producto. Se guarda la clave; la
# etiqueta vive acá para que una pantalla y un Excel la escriban igual.
TIPOS_MERMA = (
    ('coccion', 'Cocción y ahumado'),
    ('recorte', 'Recorte y limpieza'),
    ('descarte', 'Descarte (no conforme)'),
    ('proceso', 'Pérdida en proceso'),
    ('muestras', 'Muestras y control de calidad'),
    ('otro', 'Otra'),
)
TIPOS_MERMA_ETIQUETA = dict(TIPOS_MERMA)

ESTADOS = ('abierta', 'cerrada', 'anulada')

# Las unidades que admite un insumo. Solo lo que va en kg entra en el
# balance de kilos; lo demás (tripa por metro o por pieza, líquidos por
# litro) se registra y se compara contra su teórico, pero no suma kilos.
UNIDADES = (('kg', 'kg — se pesa'), ('m', 'm — se mide (tripa)'),
            ('ud', 'ud — se cuenta'), ('l', 'l — líquidos'))
UNIDAD_PESO = 'kg'


class Insumo(db.Model):
    """Un ingrediente de la casa: carne, grasa, sal, tripa, hielo."""
    __tablename__ = 'produccion_insumo'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)
    unidad = db.Column(db.String(10), nullable=False, default='kg')
    activo = db.Column(db.Boolean, nullable=False, default=True)
    notas = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Insumo {self.id} {self.nombre}>'


class Formula(db.Model):
    """La fórmula de un producto: cuánto de cada insumo por `base_kg` de
    producto terminado. Una sola activa por producto."""
    __tablename__ = 'produccion_formula'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    base_kg = db.Column(db.Numeric(10, 3), nullable=False, default=100)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creada_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    creada_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)

    producto = db.relationship('Producto')
    insumos = db.relationship('FormulaInsumo', back_populates='formula',
                              cascade='all, delete-orphan', order_by='FormulaInsumo.id')


class FormulaInsumo(db.Model):
    __tablename__ = 'produccion_formula_insumo'
    id = db.Column(db.Integer, primary_key=True)
    formula_id = db.Column(db.Integer, db.ForeignKey('produccion_formula.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('produccion_insumo.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)

    formula = db.relationship('Formula', back_populates='insumos')
    insumo = db.relationship('Insumo')

    __table_args__ = (
        db.UniqueConstraint('formula_id', 'insumo_id', name='uq_produccion_formula_insumo'),
    )


class LoteProduccion(db.Model):
    __tablename__ = 'lote_produccion'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False, index=True)
    # La fórmula activa del producto al momento de registrar. Puede ser
    # NULL (producto sin fórmula): entonces no hay teórico, solo el real.
    formula_id = db.Column(db.Integer, db.ForeignKey('produccion_formula.id'), nullable=True)
    lote = db.Column(db.String(50), nullable=False, index=True)
    fecha_produccion = db.Column(db.Date, nullable=False, index=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    # Lo que salió se toma de las cajas pesadas en los pedidos (ver
    # `LoteCaja` y `peso_pesado`). `peso_adicional` es lo que NO pasó por
    # la balanza de pedidos (muestras, stock que se congela, un remanente)
    # y se declara a mano; es un dato, no un total derivado. Unidades y
    # cajas declaradas son informativas: el balance se hace en kilos.
    peso_adicional = db.Column(db.Numeric(10, 3), nullable=False, default=0)
    unidades_producidas = db.Column(db.Integer, nullable=True)
    cajas_producidas = db.Column(db.Integer, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='abierta', index=True)
    notas = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=False)
    registrado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cerrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    cerrado_en = db.Column(db.DateTime, nullable=True)
    anulado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    anulado_en = db.Column(db.DateTime, nullable=True)
    motivo_anulacion = db.Column(db.Text, nullable=True)

    producto = db.relationship('Producto')
    formula = db.relationship('Formula')
    consumos = db.relationship('LoteConsumo', back_populates='lote',
                               cascade='all, delete-orphan',
                               order_by='LoteConsumo.id')
    mermas = db.relationship('LoteMerma', back_populates='lote',
                             cascade='all, delete-orphan',
                             order_by='LoteMerma.id')
    cajas = db.relationship('LoteCaja', back_populates='lote',
                            cascade='all, delete-orphan',
                            order_by='LoteCaja.id')

    # Sin UNIQUE en base: un lote anulado por error de tecleo tiene que
    # poder volver a registrarse con el mismo número. La unicidad entre los
    # lotes vivos la valida `servicios.crear_lote` / `editar_lote`.
    __table_args__ = (
        db.Index('ix_lote_produccion_producto_lote', 'producto_id', 'lote'),
    )

    @property
    def peso_pesado(self):
        """Suma de las cajas pesadas en pedidos y vinculadas a este lote.
        NO se guarda: un número guardado puede mentir cuando una caja se
        borra o se corrige en el pedido."""
        total = Decimal('0')
        for vinculo in self.cajas:
            if vinculo.caja_pesada is not None:
                total += Decimal(str(vinculo.caja_pesada.peso))
        return total

    @property
    def peso_producido(self):
        """Lo pesado en pedidos más lo declarado a mano."""
        return self.peso_pesado + Decimal(str(self.peso_adicional or 0))

    @property
    def cajas_pesadas_count(self):
        return sum(1 for v in self.cajas if v.caja_pesada is not None)

    @property
    def abierto(self):
        return self.estado == 'abierta'

    @property
    def cerrado(self):
        return self.estado == 'cerrada'

    @property
    def anulado(self):
        return self.estado == 'anulada'

    def __repr__(self):
        return f'<LoteProduccion {self.id} {self.codigo}>'


class LoteConsumo(db.Model):
    """Un insumo usado en el lote: lo que decía la fórmula y lo que se pesó
    de verdad. El teórico es un snapshot al guardar, para que cambiar la
    fórmula mañana no reescriba el rendimiento de ayer."""
    __tablename__ = 'lote_consumo'
    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey('lote_produccion.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('produccion_insumo.id'), nullable=False, index=True)
    cantidad_teorica = db.Column(db.Numeric(10, 3), nullable=False, default=0)
    cantidad_real = db.Column(db.Numeric(10, 3), nullable=False)

    lote = db.relationship('LoteProduccion', back_populates='consumos')
    insumo = db.relationship('Insumo')

    __table_args__ = (
        db.UniqueConstraint('lote_id', 'insumo_id', name='uq_lote_consumo'),
    )


class LoteMerma(db.Model):
    """Una merma identificada del lote, en kilos, con su causa. La merma
    total no se guarda: es consumido en peso menos producido, y lo que esta
    tabla no explica queda como «sin identificar»."""
    __tablename__ = 'lote_merma'
    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey('lote_produccion.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)
    motivo = db.Column(db.Text, nullable=True)

    lote = db.relationship('LoteProduccion', back_populates='mermas')

    @property
    def etiqueta(self):
        return TIPOS_MERMA_ETIQUETA.get(self.tipo, self.tipo)


class LoteCaja(db.Model):
    """Una caja pesada en un pedido, atribuida a este lote. El peso del
    producto terminado sale de acá: al pesar para un pedido se elige el
    lote y la caja queda vinculada. `ON DELETE CASCADE` en los dos lados:
    si la caja se borra del pedido («Deshacer»), el vínculo cae solo y el
    lote deja de contarla sin que ningún código lo recuerde."""
    __tablename__ = 'produccion_lote_caja'
    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey('lote_produccion.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    caja_pesada_id = db.Column(db.Integer, db.ForeignKey('caja_pesada.id', ondelete='CASCADE'),
                               nullable=False, unique=True, index=True)
    registrado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    lote = db.relationship('LoteProduccion', back_populates='cajas')
    caja_pesada = db.relationship('CajaPesada')
