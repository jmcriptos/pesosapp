# models/cliente.py
from extensions import db

class Cliente(db.Model):
    __tablename__ = 'cliente'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    
    def __repr__(self):
        return f'<Cliente {self.nombre}>'
