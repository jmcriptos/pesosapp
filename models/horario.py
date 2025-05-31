# Archivo: models/horario.py (crear archivo nuevo)
from datetime import datetime, time
from extensions import db


class HorarioCliente(db.Model):
    """
    Horarios de atención y entrega de cada cliente
    """
    __tablename__ = 'horario_cliente'
    
    # ID único del horario
    id = db.Column(db.Integer, primary_key=True)
    
    # Relación con CRM Cliente
    crm_cliente_id = db.Column(db.Integer, db.ForeignKey('crm_cliente.id'), nullable=False)
    
    # === DÍA DE LA SEMANA ===
    dia_semana = db.Column(db.Integer, nullable=False)  # 0=Lunes, 1=Martes, ..., 6=Domingo
    
    # === HORARIOS DE ATENCIÓN A VENDEDORES ===
    acepta_vendedores = db.Column(db.Boolean, default=True)
    hora_inicio_atencion = db.Column(db.Time, nullable=True)  # Ejemplo: 08:00
    hora_fin_atencion = db.Column(db.Time, nullable=True)     # Ejemplo: 17:00
    
    # === HORARIOS DE ENTREGA ===
    acepta_entregas = db.Column(db.Boolean, default=True)
    hora_inicio_entrega = db.Column(db.Time, nullable=True)   # Ejemplo: 09:00
    hora_fin_entrega = db.Column(db.Time, nullable=True)      # Ejemplo: 16:00
    
    # === INFORMACIÓN ADICIONAL ===
    observaciones = db.Column(db.Text, nullable=True)  # "Cerrado de 12-13 para almuerzo"
    prioridad_dia = db.Column(db.Integer, default=5)   # 1-10, qué tan importante es visitar este día
    
    # === FECHAS ===
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        dia_nombre = dias[self.dia_semana] if 0 <= self.dia_semana <= 6 else 'Día inválido'
        return f'<HorarioCliente {dia_nombre} - {self.hora_inicio_atencion}-{self.hora_fin_atencion}>'
    
    def to_dict(self):
        dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        return {
            'id': self.id,
            'dia_semana': self.dia_semana,
            'dia_nombre': dias[self.dia_semana] if 0 <= self.dia_semana <= 6 else 'Inválido',
            'acepta_vendedores': self.acepta_vendedores,
            'hora_inicio_atencion': self.hora_inicio_atencion.strftime('%H:%M') if self.hora_inicio_atencion else None,
            'hora_fin_atencion': self.hora_fin_atencion.strftime('%H:%M') if self.hora_fin_atencion else None,
            'acepta_entregas': self.acepta_entregas,
            'hora_inicio_entrega': self.hora_inicio_entrega.strftime('%H:%M') if self.hora_inicio_entrega else None,
            'hora_fin_entrega': self.hora_fin_entrega.strftime('%H:%M') if self.hora_fin_entrega else None,
            'observaciones': self.observaciones,
            'prioridad_dia': self.prioridad_dia
        }