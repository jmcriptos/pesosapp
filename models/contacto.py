# Archivo: models/contacto.py (crear archivo nuevo)
from datetime import datetime
from extensions import db


class ContactoCliente(db.Model):
    """
    Personas clave dentro de cada cliente
    """
    __tablename__ = 'contacto_cliente'
    
    # ID único del contacto
    id = db.Column(db.Integer, primary_key=True)
    
    # Relación con CRM Cliente
    crm_cliente_id = db.Column(db.Integer, db.ForeignKey('crm_cliente.id'), nullable=False)
    
    # === INFORMACIÓN PERSONAL ===
    nombre_completo = db.Column(db.String(100), nullable=False)
    cargo_posicion = db.Column(db.String(100), nullable=True)
    departamento = db.Column(db.String(50), nullable=True)
    
    # === INFORMACIÓN DE CONTACTO ===
    telefono_directo = db.Column(db.String(20), nullable=True)
    telefono_movil = db.Column(db.String(20), nullable=True)
    email_personal = db.Column(db.String(100), nullable=True)
    extension_interna = db.Column(db.String(10), nullable=True)
    
    # === ROL EN LA EMPRESA CLIENTE ===
    es_decision_compras = db.Column(db.Boolean, default=False)  # ¿Decide las compras?
    es_contacto_principal = db.Column(db.Boolean, default=False)  # ¿Es el contacto principal?
    nivel_influencia = db.Column(db.Integer, default=5)  # 1-10, qué tanto influye en las decisiones
    autoriza_credito = db.Column(db.Boolean, default=False)  # ¿Puede autorizar créditos?
    
    # === PREFERENCIAS PERSONALES ===
    productos_interes = db.Column(db.Text, nullable=True)  # Lista de productos que más le interesan
    mejor_horario_contacto = db.Column(db.String(50), nullable=True)  # "Mañanas", "Tardes", etc.
    dia_preferido_contacto = db.Column(db.String(20), nullable=True)  # "Lunes a Viernes", etc.
    notas_personales = db.Column(db.Text, nullable=True)  # Información personal útil
    
    # === FECHAS ===
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_contacto = db.Column(db.Date, nullable=True)
    
    # === CONTROL ===
    activo = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<ContactoCliente {self.nombre_completo} - {self.cargo_posicion}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'nombre_completo': self.nombre_completo,
            'cargo_posicion': self.cargo_posicion,
            'telefono_directo': self.telefono_directo,
            'email_personal': self.email_personal,
            'es_decision_compras': self.es_decision_compras,
            'es_contacto_principal': self.es_contacto_principal,
            'nivel_influencia': self.nivel_influencia,
            'mejor_horario_contacto': self.mejor_horario_contacto,
            'activo': self.activo
        }