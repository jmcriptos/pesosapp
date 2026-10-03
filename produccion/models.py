"""Modelos del módulo de producción propia.

Tres tablas nuevas. Los ingredientes y las recetas se REUSAN del módulo de
maquila (`ingrediente`, `receta`): son el mismo catálogo físico (carne,
tripa, sal) y la misma fórmula, con o sin cliente dueño. Para producción
propia aplica la receta genérica del producto (la que no tiene cliente).

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


class LoteProduccion(db.Model):
    __tablename__ = 'lote_produccion'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False, index=True)
    # La receta genérica del producto al momento de registrar. Puede ser
    # NULL (producto sin receta): entonces no hay teórico, solo el real.
    receta_id = db.Column(db.Integer, db.ForeignKey('receta.id'), nullable=True)
    lote = db.Column(db.String(50), nullable=False, index=True)
    fecha_produccion = db.Column(db.Date, nullable=False, index=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    # Lo que salió. Se guarda porque es un DATO (lo que marcó la balanza),
    # no un total derivado. Unidades y cajas son informativas: el balance
    # se hace en kilos.
    peso_producido = db.Column(db.Numeric(10, 3), nullable=False, default=0)
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
    receta = db.relationship('Receta')
    consumos = db.relationship('LoteConsumo', back_populates='lote',
                               cascade='all, delete-orphan',
                               order_by='LoteConsumo.id')
    mermas = db.relationship('LoteMerma', back_populates='lote',
                             cascade='all, delete-orphan',
                             order_by='LoteMerma.id')

    # Sin UNIQUE en base: un lote anulado por error de tecleo tiene que
    # poder volver a registrarse con el mismo número. La unicidad entre los
    # lotes vivos la valida `servicios.crear_lote` / `editar_lote`.
    __table_args__ = (
        db.Index('ix_lote_produccion_producto_lote', 'producto_id', 'lote'),
    )

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
    """Un ingrediente usado en el lote: lo que decía la receta y lo que se
    pesó de verdad. El teórico es un snapshot al guardar, para que cambiar
    la receta mañana no reescriba el rendimiento de ayer."""
    __tablename__ = 'lote_consumo'
    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey('lote_produccion.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False, index=True)
    cantidad_teorica = db.Column(db.Numeric(10, 3), nullable=False, default=0)
    cantidad_real = db.Column(db.Numeric(10, 3), nullable=False)

    lote = db.relationship('LoteProduccion', back_populates='consumos')
    ingrediente = db.relationship('Ingrediente')

    __table_args__ = (
        db.UniqueConstraint('lote_id', 'ingrediente_id', name='uq_lote_consumo'),
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
