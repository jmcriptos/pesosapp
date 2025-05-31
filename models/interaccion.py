# Archivo: models/interaccion.py (crear archivo nuevo)
from datetime import datetime
from extensions import db


class InteraccionCliente(db.Model):
    """
    Historial de todas las interacciones con cada cliente
    """
    __tablename__ = 'interaccion_cliente'
    
    # ID único de la interacción
    id = db.Column(db.Integer, primary_key=True)
    
    # Relación con CRM Cliente
    crm_cliente_id = db.Column(db.Integer, db.ForeignKey('crm_cliente.id'), nullable=False)
    
    # === INFORMACIÓN BÁSICA ===
    fecha_interaccion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    tipo_interaccion = db.Column(db.String(50), nullable=False)  # 'visita', 'llamada', 'email', 'venta', 'reclamo', 'cotizacion'
    
    # === DETALLES DE LA INTERACCIÓN ===
    resumen_interaccion = db.Column(db.Text, nullable=False)  # Qué pasó en la interacción
    contacto_interactuado = db.Column(db.String(100), nullable=True)  # Con quién se habló específicamente
    duracion_minutos = db.Column(db.Integer, nullable=True)  # Cuánto duró la interacción
    
    # === INFORMACIÓN COMERCIAL ===
    productos_discutidos = db.Column(db.Text, nullable=True)  # Qué productos se mencionaron
    monto_discutido = db.Column(db.Numeric(10, 2), default=0.0)  # Cuánto dinero se habló
    probabilidad_venta = db.Column(db.Integer, default=50)  # 0-100%, qué probabilidad hay de que compre
    descuento_solicitado = db.Column(db.Numeric(5, 2), default=0.0)  # Qué descuento pidió el cliente
    
    # === SEGUIMIENTO ===
    requiere_seguimiento = db.Column(db.Boolean, default=False)
    fecha_proximo_contacto = db.Column(db.Date, nullable=True)  # Cuándo hay que contactarlo de nuevo
    accion_siguiente = db.Column(db.Text, nullable=True)  # Qué hay que hacer la próxima vez
    prioridad_seguimiento = db.Column(db.Integer, default=5)  # 1-10, qué tan urgente es el seguimiento
    
    # === RESULTADO ===
    resultado_interaccion = db.Column(db.String(50), default='pendiente')  # 'exitoso', 'pendiente', 'rechazado', 'reagendar'
    satisfaccion_cliente = db.Column(db.Integer, nullable=True)  # 1-10, qué tan satisfecho quedó el cliente
    genera_oportunidad = db.Column(db.Boolean, default=False)  # ¿Esta interacción puede generar una venta?
    
    # === ARCHIVOS Y DOCUMENTOS ===
    documentos_adjuntos = db.Column(db.Text, nullable=True)  # URLs o nombres de archivos relacionados
    fotos_tomadas = db.Column(db.Text, nullable=True)  # URLs de fotos que se tomaron
    
    # === CONTROL ===
    usuario_registro = db.Column(db.String(100), nullable=True)  # Quién registró esta interacción
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    editado = db.Column(db.Boolean, default=False)
    fecha_edicion = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<InteraccionCliente {self.tipo_interaccion} - {self.fecha_interaccion.strftime("%Y-%m-%d")}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'fecha_interaccion': self.fecha_interaccion.isoformat(),
            'tipo_interaccion': self.tipo_interaccion,
            'resumen_interaccion': self.resumen_interaccion,
            'contacto_interactuado': self.contacto_interactuado,
            'monto_discutido': float(self.monto_discutido) if self.monto_discutido else 0.0,
            'probabilidad_venta': self.probabilidad_venta,
            'requiere_seguimiento': self.requiere_seguimiento,
            'fecha_proximo_contacto': self.fecha_proximo_contacto.isoformat() if self.fecha_proximo_contacto else None,
            'accion_siguiente': self.accion_siguiente,
            'resultado_interaccion': self.resultado_interaccion,
            'satisfaccion_cliente': self.satisfaccion_cliente,
            'usuario_registro': self.usuario_registro
        }