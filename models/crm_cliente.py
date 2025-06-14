# Archivo: models/crm_cliente.py (crear archivo nuevo)
from datetime import datetime
from extensions import db
from models.cliente import Cliente


# models/crm_cliente.py  (o donde lo tengas)
class CRMCliente(db.Model):
    __tablename__ = 'crm_cliente'

    id = db.Column(db.Integer, primary_key=True)

    # FK correcta ⚠️
    cliente_original_id = db.Column(
        db.Integer,
        db.ForeignKey('cliente.id', ondelete='CASCADE'),
        nullable=False,
        unique=True
    )

    # Relación
    cliente_original = db.relationship(
        'Cliente',
        backref=db.backref('registro_crm', uselist=False, cascade='all, delete-orphan')
    )
    
    # === INFORMACIÓN DE CONTACTO ===
    direccion_completa = db.Column(db.Text, nullable=True)
    telefono_principal = db.Column(db.String(20), nullable=True)
    telefono_secundario = db.Column(db.String(20), nullable=True)
    email_principal = db.Column(db.String(100), nullable=True)
    email_facturacion = db.Column(db.String(100), nullable=True)
    
    # === CLASIFICACIÓN COMERCIAL ===
    categoria_cliente = db.Column(db.String(1), default='B', nullable=False)  # A, B, C
    potencial_mensual = db.Column(db.Numeric(10, 2), default=0.0)  # Dinero que puede comprar por mes
    frecuencia_compra_dias = db.Column(db.Integer, default=30)  # Cada cuántos días compra
    
    # === PREFERENCIAS COMERCIALES ===
    descuento_habitual = db.Column(db.Numeric(5, 2), default=0.0)  # Porcentaje de descuento usual
    metodo_pago_preferido = db.Column(db.String(50), default='Efectivo')
    dia_preferido_entrega = db.Column(db.Integer, nullable=True)  # 0=Lunes, 6=Domingo
    requiere_factura_fiscal = db.Column(db.Boolean, default=False)
    
    # === UBICACIÓN PARA RUTAS ===
    latitud = db.Column(db.Numeric(10, 8), nullable=True)  # Coordenadas GPS
    longitud = db.Column(db.Numeric(11, 8), nullable=True)
    zona_geografica = db.Column(db.String(50), nullable=True)  # Norte, Sur, Este, Oeste, Centro
    
    # === FECHAS DE CONTROL ===
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ultimo_contacto = db.Column(db.Date, nullable=True)
    fecha_ultima_compra = db.Column(db.Date, nullable=True)
    
    # === OBSERVACIONES ===
    notas_generales = db.Column(db.Text, nullable=True)
    es_cliente_activo = db.Column(db.Boolean, default=True)
    
    # === RELACIONES ===
    # Relación con el cliente original
    cliente_original = db.relationship('Cliente', backref=db.backref('crm_data', uselist=False))
    
    # Relaciones con otras tablas CRM (las crearemos después)
    contactos = db.relationship('ContactoCliente', backref='crm_cliente', cascade='all, delete-orphan', lazy=True)
    horarios = db.relationship('HorarioCliente', backref='crm_cliente', cascade='all, delete-orphan', lazy=True)
    interacciones = db.relationship('InteraccionCliente', backref='crm_cliente', cascade='all, delete-orphan', lazy=True)
    
    def __repr__(self):
        cliente_nombre = self.cliente_original.nombre if self.cliente_original else "Sin nombre"
        return f'<CRMCliente {cliente_nombre} - Categoría {self.categoria_cliente}>'
    
    def to_dict(self):
        """Convierte el objeto a diccionario para JSON"""
        return {
            'id': self.id,
            'cliente_original_id': self.cliente_original_id,
            'cliente_nombre': self.cliente_original.nombre if self.cliente_original else None,
            'direccion_completa': self.direccion_completa,
            'telefono_principal': self.telefono_principal,
            'email_principal': self.email_principal,
            'categoria_cliente': self.categoria_cliente,
            'potencial_mensual': float(self.potencial_mensual) if self.potencial_mensual else 0.0,
            'zona_geografica': self.zona_geografica,
            'es_cliente_activo': self.es_cliente_activo,
            'ultimo_contacto': self.ultimo_contacto.isoformat() if self.ultimo_contacto else None
        }