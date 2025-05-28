import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, send_file, jsonify, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import io
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import openpyxl
from openpyxl.styles import Font, Alignment
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from flask_migrate import Migrate
import xlsxwriter
import socket
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import locale
import traceback
from decimal import Decimal
import requests

from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin

try:
    from flask_talisman import Talisman
except ImportError:
    Talisman = None

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

basedir = os.path.abspath(os.path.dirname(__file__))

uri = os.environ.get("DATABASE_URL", "sqlite:///local.db")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Solo activa Talisman en producción (cuando uses HTTPS real)
if Talisman and os.environ.get("FLASK_ENV") == "production":
    Talisman(app, content_security_policy={
        'default-src': ['\'self\''],
        'img-src': ['\'self\'', 'data:']
    })


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DEFAULT_USERNAME = os.environ["DEFAULT_USERNAME"]
DEFAULT_PASSWORD = os.environ["DEFAULT_PASSWORD"]

class DefaultUser(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    if user_id == DEFAULT_USERNAME:
        return DefaultUser(DEFAULT_USERNAME)
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
            user = DefaultUser(username)
            login_user(user)
            flash("Inicio de sesión exitoso", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash("Credenciales inválidas", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada", "success")
    return redirect(url_for('login'))

@app.before_request
def require_login():
    allowed_endpoints = ['login', 'logout', 'static']
    if request.endpoint and not any(request.endpoint.startswith(ep) for ep in allowed_endpoints):
        if not current_user.is_authenticated:
            return redirect(url_for('login', next=request.url))

############################################
# MODELOS Y BASE DE DATOS
############################################

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(200))
    temperatura = db.Column(db.String(50))
    facturaciones = db.relationship('Facturacion', back_populates='producto', cascade="all, delete-orphan")
    recepciones = db.relationship('Recepcion', back_populates='producto', lazy=True, cascade="all, delete-orphan")
    importaciones = db.relationship('Importacion', back_populates='producto', lazy=True, cascade="all, delete-orphan")
    qbo_id = db.Column(db.String(20), unique=True)
    tax_rate = db.Column(db.Float, nullable=False, default=0.0)  # Nueva columna para tasa de impuesto
    
    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'temperatura': self.temperatura,
            'qbo_id': self.qbo_id,
            'tax_rate': self.tax_rate  # Incluir en el diccionario
        }

class Cliente(db.Model):
    __tablename__ = 'cliente'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    facturaciones = db.relationship('Facturacion', back_populates='cliente', cascade="all, delete-orphan")
    pedidos = db.relationship('Pedido', back_populates='cliente', cascade="all, delete-orphan")
    qbo_id = db.Column(db.String(20), unique=True)

    def to_dict(self):
        return {'id': self.id, 'nombre': self.nombre, 'qbo_id': self.qbo_id} 

class Facturacion(db.Model):
    __tablename__ = 'facturacion'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    peso = db.Column(db.Float, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    lote = db.Column(db.String(50), nullable=False)
    fecha_fabricacion = db.Column(db.String(10), nullable=False)
    fecha_expiracion = db.Column(db.String(10), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    producto = db.relationship('Producto', back_populates='facturaciones')
    cliente = db.relationship('Cliente', back_populates='facturaciones')

    def to_dict(self):
        return {
            'id': self.id,
            'producto_id': self.producto_id,
            'producto': self.producto.nombre if self.producto else None,
            'peso': self.peso,
            'cliente_id': self.cliente_id,
            'cliente': self.cliente.nombre if self.cliente else None,
            'lote': self.lote,
            'fecha_fabricacion': self.fecha_fabricacion,
            'fecha_expiracion': self.fecha_expiracion,
            'fecha_registro': self.fecha_registro.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_registro else None
        }

class Recepcion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    peso = db.Column(db.Float, nullable=False)
    proveedor = db.Column(db.String(100), nullable=False)
    numero_factura = db.Column(db.String(100), nullable=False)
    recibido_en = db.Column(db.Date, nullable=False)
    producto = db.relationship('Producto', back_populates='recepciones')
    
    def to_dict(self):
        return {
            'id': self.id,
            'producto_id': self.producto_id,
            'producto': self.producto.nombre if self.producto else 'undefined',
            'peso': self.peso,
            'recibido_en': self.recibido_en.strftime('%Y-%m-%d') if self.recibido_en else 'No disponible',
            'proveedor': self.proveedor,
            'numero_factura': self.numero_factura
        }

class Importacion(db.Model):
    __tablename__ = 'importacion'
    id = db.Column(db.Integer, primary_key=True)
    numero_factura = db.Column(db.String(100), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad_cajas = db.Column(db.Integer, nullable=False)
    cantidad_total = db.Column(db.Float, nullable=False)
    precio_fob_unidad = db.Column(db.Float, nullable=False)
    flete = db.Column(db.Float, nullable=False)
    arancel = db.Column(db.Float, nullable=False)
    costo_aduana = db.Column(db.Float, nullable=False)
    precio_jomar = db.Column(db.Float, nullable=False)
    precio_retail = db.Column(db.Float, nullable=False)
    cif_ang = db.Column(db.Float, nullable=True)
    ob_ang = db.Column(db.Float, nullable=True)
    fecha_importacion = db.Column(db.DateTime, default=datetime.utcnow)
    flete_local = db.Column(db.Float, nullable=True)
    costo_total_almacen = db.Column(db.Float, nullable=True)
    producto = db.relationship('Producto', back_populates='importaciones')

# MODELOS NUEVOS PARA PEDIDOS

class Pedido(db.Model):
    __tablename__ = 'pedido'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    fecha_pedido = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    estado = db.Column(db.String(30), default="pendiente", nullable=False)
    notas = db.Column(db.Text, nullable=True)
    cliente = db.relationship('Cliente', back_populates='pedidos')
    detalles = db.relationship('DetallePedido', back_populates='pedido', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Pedido {self.id} - Cliente {self.cliente.nombre} - Estado {self.estado}>'

class DetallePedido(db.Model):
    __tablename__ = 'detalle_pedido'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cajas = db.Column(db.Integer, nullable=False, default=0)  # NUEVO
    peso = db.Column(db.Float, nullable=False, default=0)
    lote = db.Column(db.String(50), nullable=True)
    fecha_fabricacion = db.Column(db.String(10), nullable=True)
    fecha_expiracion = db.Column(db.String(10), nullable=True)
    pedido = db.relationship('Pedido', back_populates='detalles')
    producto = db.relationship('Producto')
    precio_unitario = db.Column(db.Numeric(10,2), nullable=False, default=0)
    subtotal        = db.Column(db.Numeric(10,2), nullable=False)


    def __repr__(self):
        return f'<DetallePedido {self.id} - Producto {self.producto.nombre} - Peso {self.peso}>'

# Agregar estos modelos al archivo app.py, después de los modelos existentes

class ListaPrecio(db.Model):
    __tablename__ = 'lista_precio'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(200))
    es_default = db.Column(db.Boolean, default=False, nullable=False)
    activa = db.Column(db.Boolean, default=True, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    precios_productos = db.relationship('PrecioProducto', back_populates='lista_precio', cascade="all, delete-orphan")
    clientes = db.relationship('ClienteListaPrecio', back_populates='lista_precio', cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'es_default': self.es_default,
            'activa': self.activa,
            'fecha_creacion': self.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_creacion else None
        }


class PrecioProducto(db.Model):
    __tablename__ = 'precio_producto'
    id = db.Column(db.Integer, primary_key=True)
    lista_precio_id = db.Column(db.Integer, db.ForeignKey('lista_precio.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    precio_base = db.Column(db.Float, nullable=False)
    precio_jomar = db.Column(db.Float)
    precio_retail = db.Column(db.Float)
    margen_jomar = db.Column(db.Float, default=1.0)
    margen_retail = db.Column(db.Float, default=1.2)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    lista_precio = db.relationship('ListaPrecio', back_populates='precios_productos')
    producto = db.relationship('Producto')
    
    __table_args__ = (db.UniqueConstraint('lista_precio_id', 'producto_id', name='uk_lista_producto'),)
    
    def calcular_precios(self):
        """Calcula precios Jomar y Retail basados en precio base y márgenes"""
        self.precio_jomar = self.precio_base * (self.margen_jomar or 1.0)
        self.precio_retail = self.precio_base * (self.margen_retail or 1.2)
    
    def to_dict(self):
        return {
            'id': self.id,
            'lista_precio_id': self.lista_precio_id,
            'producto_id': self.producto_id,
            'producto_nombre': self.producto.nombre if self.producto else None,
            'precio_base': self.precio_base,
            'precio_jomar': self.precio_jomar,
            'precio_retail': self.precio_retail,
            'margen_jomar': self.margen_jomar,
            'margen_retail': self.margen_retail,
            'activo': self.activo,
            'fecha_actualizacion': self.fecha_actualizacion.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_actualizacion else None
        }


class ClienteListaPrecio(db.Model):
    __tablename__ = 'cliente_lista_precio'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    lista_precio_id = db.Column(db.Integer, db.ForeignKey('lista_precio.id'), nullable=False)
    fecha_asignacion = db.Column(db.DateTime, default=datetime.utcnow)
    activa = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relaciones
    cliente = db.relationship('Cliente')
    lista_precio = db.relationship('ListaPrecio', back_populates='clientes')
    
    __table_args__ = (db.UniqueConstraint('cliente_id', 'lista_precio_id', name='uk_cliente_lista'),)


class PrecioClienteProducto(db.Model):
    __tablename__ = 'precio_cliente_producto'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    precio_base = db.Column(db.Float, nullable=False)
    precio_jomar = db.Column(db.Float)
    precio_retail = db.Column(db.Float)
    margen_jomar = db.Column(db.Float, default=1.0)
    margen_retail = db.Column(db.Float, default=1.2)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    cliente = db.relationship('Cliente')
    producto = db.relationship('Producto')
    
    __table_args__ = (db.UniqueConstraint('cliente_id', 'producto_id', name='uk_cliente_producto_precio'),)
    
    def calcular_precios(self):
        """Calcula precios Jomar y Retail basados en precio base y márgenes"""
        self.precio_jomar = self.precio_base * (self.margen_jomar or 1.0)
        self.precio_retail = self.precio_base * (self.margen_retail or 1.2)
    
    def to_dict(self):
        return {
            'id': self.id,
            'cliente_id': self.cliente_id,
            'cliente_nombre': self.cliente.nombre if self.cliente else None,
            'producto_id': self.producto_id,
            'producto_nombre': self.producto.nombre if self.producto else None,
            'precio_base': self.precio_base,
            'precio_jomar': self.precio_jomar,
            'precio_retail': self.precio_retail,
            'margen_jomar': self.margen_jomar,
            'margen_retail': self.margen_retail,
            'activo': self.activo,
            'fecha_creacion': self.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_creacion else None,
            'fecha_actualizacion': self.fecha_actualizacion.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_actualizacion else None
        }


# Función auxiliar para obtener el precio de un producto para un cliente específico
def obtener_precio_producto_cliente(cliente_id, producto_id, tipo_precio='jomar'):
    """
    Obtiene el precio de un producto para un cliente específico.
    Prioridad: Precio específico cliente-producto > Lista de precios del cliente > Lista default
    
    Args:
        cliente_id: ID del cliente
        producto_id: ID del producto
        tipo_precio: 'base', 'jomar' o 'retail'
    
    Returns:
        Float: Precio encontrado o None si no existe
    """
    print(f"DEBUG: Buscando precio para cliente_id={cliente_id}, producto_id={producto_id}, tipo={tipo_precio}")
    
    # 1. Verificar precio específico cliente-producto
    precio_especifico = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id,
        producto_id=producto_id,
        activo=True
    ).first()
    
    if precio_especifico:
        print(f"DEBUG: Encontrado precio específico cliente-producto")
        if tipo_precio == 'base':
            precio = precio_especifico.precio_base
        elif tipo_precio == 'jomar':
            precio = precio_especifico.precio_jomar
        elif tipo_precio == 'retail':
            precio = precio_especifico.precio_retail
        print(f"DEBUG: Precio específico: {precio}")
        return precio
    else:
        print(f"DEBUG: No hay precio específico cliente-producto")
    
    # 2. Verificar lista de precios del cliente
    cliente_lista = ClienteListaPrecio.query.filter_by(
        cliente_id=cliente_id,
        activa=True
    ).first()
    
    if cliente_lista:
        print(f"DEBUG: Cliente tiene lista asignada: {cliente_lista.lista_precio_id}")
        precio_lista = PrecioProducto.query.filter_by(
            lista_precio_id=cliente_lista.lista_precio_id,
            producto_id=producto_id,
            activo=True
        ).first()
        
        if precio_lista:
            print(f"DEBUG: Encontrado precio en lista del cliente")
            if tipo_precio == 'base':
                precio = precio_lista.precio_base
            elif tipo_precio == 'jomar':
                precio = precio_lista.precio_jomar
            elif tipo_precio == 'retail':
                precio = precio_lista.precio_retail
            print(f"DEBUG: Precio de lista cliente: {precio}")
            return precio
        else:
            print(f"DEBUG: Producto no encontrado en lista del cliente")
    else:
        print(f"DEBUG: Cliente no tiene lista asignada")
    
    # 3. Usar lista de precios por defecto
    lista_default = ListaPrecio.query.filter_by(es_default=True, activa=True).first()
    if lista_default:
        print(f"DEBUG: Usando lista por defecto: {lista_default.id}")
        precio_default = PrecioProducto.query.filter_by(
            lista_precio_id=lista_default.id,
            producto_id=producto_id,
            activo=True
        ).first()
        
        if precio_default:
            print(f"DEBUG: Encontrado precio en lista por defecto")
            if tipo_precio == 'base':
                precio = precio_default.precio_base
            elif tipo_precio == 'jomar':
                precio = precio_default.precio_jomar
            elif tipo_precio == 'retail':
                precio = precio_default.precio_retail
            print(f"DEBUG: Precio por defecto: {precio}")
            return precio
        else:
            print(f"DEBUG: Producto no encontrado en lista por defecto")
    else:
        print(f"DEBUG: No hay lista por defecto configurada")
    
    print(f"DEBUG: No se encontró precio, devolviendo None")
    return None

def obtener_precio_default_producto(producto_id, tipo_precio='jomar'):
    """
    Devuelve el precio de un producto tomado de la lista marcada como es_default.
    Si no existe, devuelve None.
    """
    lista_default = ListaPrecio.query.filter_by(es_default=True, activa=True).first()
    if not lista_default:
        return None

    precio = PrecioProducto.query.filter_by(
        lista_precio_id=lista_default.id,
        producto_id=producto_id,
        activo=True
    ).first()

    if not precio:
        return None

    if   tipo_precio == 'base':
        return precio.precio_base
    elif tipo_precio == 'jomar':
        return precio.precio_jomar
    elif tipo_precio == 'retail':
        return precio.precio_retail
    return None

############################################
# FUNCIONES Y RUTAS DE PEDIDOS
############################################

# --------------------------------------------------
# Helper: convierte un pedido y sus detalles en JSON
# --------------------------------------------------
# Actualizar la función pedido_a_json en app.py

def pedido_a_json(pedido: Pedido) -> dict:
    lineas = []
    total  = 0

    for d in pedido.detalles:
        descripcion = d.producto.nombre
        if d.lote:
            descripcion += f" (Lote {d.lote})"

        subtotal = float(d.precio_unitario) * (d.cajas or d.peso or 0)
        total   += subtotal

        lineas.append({
            "product_qbo_id": d.producto.qbo_id,
            "descripcion"   : descripcion,
            "qty"           : float(d.cajas or d.peso or 0),
            "unit_price"    : float(d.precio_unitario),
            "amount"        : round(subtotal, 2),
            "tax_rate"      : d.producto.tax_rate  # 🆕 Incluir la tasa de impuesto
        })

    return {
        "order_id"        : pedido.id,
        "order_date"      : pedido.fecha_pedido.isoformat(),
        "customer_qbo_id" : pedido.cliente.qbo_id,
        "notes"           : pedido.notas,
        "lines"           : lineas,
        "total"           : round(total, 2)
    }


def obtener_ip_servidor():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip_servidor = s.getsockname()[0]
    except Exception:
        ip_servidor = '127.0.0.1'
    finally:
        s.close()
    return ip_servidor

@app.route('/')
@login_required
def index():
    ip_servidor = obtener_ip_servidor()
    port = 5002
    return render_template('index.html', server_ip=f"{ip_servidor}:{port}")


# Reemplazar la función dashboard en app.py con esta versión corregida

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard con métricas de ventas y KPIs"""
    try:
        # Fechas para análisis
        hoy = datetime.now().date()
        inicio_mes = hoy.replace(day=1)
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        hace_30_dias = hoy - timedelta(days=30)
        
        # === MÉTRICAS PRINCIPALES ===
        
        # Total de pedidos y ventas del mes actual
        pedidos_mes = db.session.query(
            func.count(Pedido.id).label('cantidad'),
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('total')
        ).select_from(Pedido).outerjoin(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).filter(
            Pedido.fecha_pedido >= inicio_mes
        ).first()
        
        # Pedidos pendientes (urgentes)
        pedidos_pendientes = Pedido.query.filter_by(estado='pendiente').count()
        
        # Pedidos de esta semana
        pedidos_semana = db.session.query(
            func.count(Pedido.id).label('cantidad'),
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('total')
        ).select_from(Pedido).outerjoin(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).filter(
            Pedido.fecha_pedido >= inicio_semana
        ).first()
        
        # Comparación con período anterior
        pedidos_mes_anterior = db.session.query(
            func.coalesce(func.sum(DetallePedido.subtotal), 0)
        ).select_from(Pedido).outerjoin(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).filter(
            Pedido.fecha_pedido >= (inicio_mes - timedelta(days=30)),
            Pedido.fecha_pedido < inicio_mes
        ).scalar()
        
        # === TOP CLIENTES ===
        top_clientes = db.session.query(
            Cliente.nombre,
            func.count(Pedido.id).label('pedidos'),
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('total')
        ).select_from(Cliente).join(
            Pedido, Cliente.id == Pedido.cliente_id
        ).outerjoin(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).filter(
            Pedido.fecha_pedido >= hace_30_dias
        ).group_by(Cliente.id, Cliente.nombre).order_by(
            func.coalesce(func.sum(DetallePedido.subtotal), 0).desc()
        ).limit(5).all()
        
        # === PRODUCTOS MÁS VENDIDOS ===
        top_productos = db.session.query(
            Producto.nombre,
            func.sum(DetallePedido.cajas).label('cajas_vendidas'),
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('ingresos')
        ).select_from(Producto).join(
            DetallePedido, Producto.id == DetallePedido.producto_id
        ).join(
            Pedido, DetallePedido.pedido_id == Pedido.id
        ).filter(
            Pedido.fecha_pedido >= hace_30_dias
        ).group_by(Producto.id, Producto.nombre).order_by(
            func.sum(DetallePedido.cajas).desc()
        ).limit(5).all()
        
        # === ESTADOS DE PEDIDOS ===
        estados_pedidos = db.session.query(
            Pedido.estado,
            func.count(Pedido.id).label('cantidad')
        ).filter(
            Pedido.fecha_pedido >= hace_30_dias
        ).group_by(Pedido.estado).all()
        
        # === TENDENCIA SEMANAL (últimas 8 semanas) ===
        tendencia_semanal = []
        for i in range(8):
            inicio_semana_i = hoy - timedelta(days=hoy.weekday() + (7 * i))
            fin_semana_i = inicio_semana_i + timedelta(days=6)
            
            ventas_semana = db.session.query(
                func.coalesce(func.sum(DetallePedido.subtotal), 0)
            ).select_from(DetallePedido).join(
                Pedido, DetallePedido.pedido_id == Pedido.id
            ).filter(
                Pedido.fecha_pedido >= inicio_semana_i,
                Pedido.fecha_pedido <= fin_semana_i
            ).scalar()
            
            tendencia_semanal.append({
                'semana': inicio_semana_i.strftime('%d/%m'),
                'ventas': float(ventas_semana or 0)
            })
        
        tendencia_semanal.reverse()  # Mostrar de más antigua a más reciente
        
        # === PEDIDOS RECIENTES ===
        pedidos_recientes = db.session.query(
            Pedido,
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('total')
        ).select_from(Pedido).outerjoin(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).group_by(Pedido.id).order_by(
            Pedido.fecha_pedido.desc()
        ).limit(8).all()
        
        # === CALCULAR PORCENTAJES DE CRECIMIENTO ===
        crecimiento_mes = 0
        if pedidos_mes_anterior and pedidos_mes_anterior > 0:
            crecimiento_mes = ((float(pedidos_mes.total) - float(pedidos_mes_anterior)) / float(pedidos_mes_anterior)) * 100
        
        return render_template('dashboard.html',
            # Métricas principales
            ventas_mes=float(pedidos_mes.total or 0),
            pedidos_mes=pedidos_mes.cantidad or 0,
            ventas_semana=float(pedidos_semana.total or 0),
            pedidos_semana=pedidos_semana.cantidad or 0,
            pedidos_pendientes=pedidos_pendientes,
            crecimiento_mes=round(crecimiento_mes, 1),
            
            # Rankings
            top_clientes=top_clientes,
            top_productos=top_productos,
            
            # Distribución
            estados_pedidos=estados_pedidos,
            
            # Tendencias
            tendencia_semanal=tendencia_semanal,
            
            # Actividad reciente
            pedidos_recientes=pedidos_recientes,
            
            # Fechas para referencia
            fecha_actual=hoy
        )
        
    except Exception as e:
        print(f"Error en dashboard: {e}")
        import traceback
        traceback.print_exc()
        flash('Error al cargar el dashboard', 'danger')
        return redirect(url_for('index'))
    
@app.route('/pedidos')
@login_required
def lista_pedidos():
    # Consulta con subconsulta para calcular totales usando los subtotales existentes
    pedidos_query = db.session.query(
        Pedido,
        func.coalesce(
            func.sum(DetallePedido.subtotal), 
            0
        ).label('total_calculado')
    ).outerjoin(DetallePedido).filter(
        Pedido.estado != 'entregado'
    ).group_by(Pedido.id).order_by(
        # Ordenar por estado: pendientes primero, luego listos, luego facturados
        db.case(
            (Pedido.estado == 'pendiente', 0),
            (Pedido.estado == 'listo', 1),
            (Pedido.estado == 'facturado', 2),
            else_=3
        ),
        # Luego por fecha: más antiguos primero
        Pedido.fecha_pedido.asc()
    ).all()
    
    # Agregar el total calculado como atributo a cada pedido
    pedidos = []
    for pedido, total in pedidos_query:
        pedido.total_calculado = float(total)
        pedidos.append(pedido)
    
    return render_template('pedidos.html', pedidos=pedidos)


@app.route('/pedidos/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_pedido():
    # ---------- Datos para el formulario ----------
    clientes  = Cliente.query.all()
    productos = Producto.query.all()

    # Enviamos al front-end cada producto con su precio (lista default)
    # Para nuevo pedido, usamos precios por defecto ya que no hay cliente seleccionado aún
    productos_dicts = [{
        'id'    : p.id,
        'nombre': p.nombre,
        # Para nuevo pedido, usar precio por defecto
        'precio': float(
            obtener_precio_default_producto(p.id, 'jomar') or 0
        )
    } for p in productos]

    # ---------- Alta de un nuevo pedido ----------
    if request.method == 'POST':
        # 1) Cabecera
        cliente_id = int(request.form['cliente_id'])
        notas      = request.form.get('notas')
        pedido = Pedido(cliente_id=cliente_id, notas=notas)
        db.session.add(pedido)
        db.session.commit()      # obtenemos pedido.id

        # 2) Detalle
        idx = 0
        while f'productos[{idx}][id]' in request.form:
            prod_id = int(request.form.get(f'productos[{idx}][id]'))
            cajas   = int(request.form.get(f'productos[{idx}][cajas]', 0))

            # 2.1 Precio unitario - ahora sí podemos usar el cliente del pedido
            precio_raw = request.form.get(f'productos[{idx}][precio]')
            if precio_raw:
                precio_unitario = Decimal(precio_raw)
            else:
                # Obtener precio específico para este cliente
                precio_cliente = obtener_precio_producto_cliente(cliente_id, prod_id, 'jomar')
                if precio_cliente is not None:
                    precio_unitario = Decimal(precio_cliente)
                else:
                    precio_def = obtener_precio_default_producto(prod_id, 'jomar')
                    precio_unitario = Decimal(precio_def) if precio_def is not None else Decimal('0')

            # 2.2 Sub-total  (app lo calcula)
            subtotal = precio_unitario * cajas

            # 2.3 Crear detalle
            detalle = DetallePedido(
                pedido_id      = pedido.id,
                producto_id    = prod_id,
                cajas          = cajas,
                precio_unitario= precio_unitario,
                subtotal       = subtotal
            )
            db.session.add(detalle)
            idx += 1

        db.session.commit()

        # 3) Total del pedido (si la columna existe en Pedido)
        total = db.session.query(
            func.coalesce(func.sum(DetallePedido.subtotal), 0)
        ).filter_by(pedido_id=pedido.id).scalar()
        
        # Solo actualizar total si la columna existe en el modelo Pedido
        if hasattr(pedido, 'total'):
            pedido.total = total
            db.session.commit()

        flash('Pedido creado con precios registrados.', 'success')
        return redirect(url_for('lista_pedidos'))

    # ---------- GET: renderizar formulario ----------
    return render_template(
        'pedido_form.html',
        clientes        = clientes,
        productos       = productos_dicts,
        pedido          = None,
        productos_pedido= []
    )

@app.route('/pedidos/<int:pedido_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_pedido(pedido_id):
    pedido    = Pedido.query.get_or_404(pedido_id)
    clientes  = Cliente.query.all()
    productos = Producto.query.all()

    # Para editar, sí tenemos el cliente del pedido, así que podemos usar precios específicos
    productos_dicts = [{
        'id'    : p.id,
        'nombre': p.nombre,
        # precio mostrado = el que vería ESTE cliente específico
        'precio': float(
            obtener_precio_producto_cliente(
                pedido.cliente_id,  # Ahora sí existe pedido
                p.id, 'jomar'
            ) or obtener_precio_default_producto(p.id, 'jomar') or 0
        )
    } for p in productos]

    if request.method == 'POST':
        # Actualizar cabecera
        pedido.cliente_id = int(request.form['cliente_id'])
        pedido.notas = request.form.get('notas')
        
        # Eliminar detalles existentes
        DetallePedido.query.filter_by(pedido_id=pedido.id).delete()
        
        # Agregar nuevos detalles
        idx = 0
        while f'productos[{idx}][id]' in request.form:
            prod_id = int(request.form.get(f'productos[{idx}][id]'))
            cajas   = int(request.form.get(f'productos[{idx}][cajas]', 0))

            # Precio unitario
            precio_raw = request.form.get(f'productos[{idx}][precio]')
            if precio_raw:
                precio_unitario = Decimal(precio_raw)
            else:
                # Usar cliente actualizado para obtener precio
                precio_cliente = obtener_precio_producto_cliente(pedido.cliente_id, prod_id, 'jomar')
                if precio_cliente is not None:
                    precio_unitario = Decimal(precio_cliente)
                else:
                    precio_def = obtener_precio_default_producto(prod_id, 'jomar')
                    precio_unitario = Decimal(precio_def) if precio_def is not None else Decimal('0')

            # Sub-total
            subtotal = precio_unitario * cajas

            # Crear detalle
            detalle = DetallePedido(
                pedido_id      = pedido.id,
                producto_id    = prod_id,
                cajas          = cajas,
                precio_unitario= precio_unitario,
                subtotal       = subtotal
            )
            db.session.add(detalle)
            idx += 1

        db.session.commit()

        # Actualizar total del pedido
        total = db.session.query(
            func.coalesce(func.sum(DetallePedido.subtotal), 0)
        ).filter_by(pedido_id=pedido.id).scalar()
        
        if hasattr(pedido, 'total'):
            pedido.total = total
            db.session.commit()

        flash('Pedido actualizado.', 'success')
        return redirect(url_for('lista_pedidos'))

    # ----------- pre-cargar detalles -----------
    productos_pedido = [{
        'id'     : d.producto.id,
        'nombre' : d.producto.nombre,
        'cajas'  : d.cajas,
        'precio' : float(d.precio_unitario)   # ← necesario para que la tabla se pinte
    } for d in pedido.detalles]

    return render_template(
        'pedido_form.html',
        clientes        = clientes,
        productos       = productos_dicts,
        pedido          = pedido,
        productos_pedido= productos_pedido
    )




@app.route('/pedidos/<int:pedido_id>/eliminar', methods=['POST'])
@login_required
def eliminar_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    db.session.delete(pedido)
    db.session.commit()
    flash('Pedido eliminado.', 'success')
    return redirect(url_for('lista_pedidos'))


# ------------------------------------------------------------
#  Detalles de un pedido (agregar / ver / eliminar líneas)
# ------------------------------------------------------------
@app.route('/pedidos/<int:pedido_id>/detalles', methods=['GET', 'POST'])
@login_required
def detalles_pedido(pedido_id):
    # ── 1) Traer cabecera y productos ─────────────────────────
    pedido    = Pedido.query.get_or_404(pedido_id)
    productos = Producto.query.all()

    # ── 2) Alta de un nuevo detalle ───────────────────────────
    if request.method == 'POST':
        producto_id       = int(request.form['producto_id'])
        peso              = float(request.form.get('peso', 0)  or 0)
        cajas             = int  (request.form.get('cajas', 0) or 0)   # reservado
        lote              = request.form['lote']
        fecha_fabricacion = request.form['fecha_fabricacion']
        fecha_expiracion  = request.form['fecha_expiracion']

        # -------- Obtener precio unitario según la jerarquía --------
        precio_unitario = obtener_precio_producto_cliente(
                              pedido.cliente_id,   # 1️⃣ precio específico / lista cliente
                              producto_id,
                              'jomar'
                          )
        if precio_unitario is None:
            # 2️⃣ (fallback) lista de precios por defecto
            precio_unitario = obtener_precio_default_producto(
                                  producto_id, 'jomar'
                              ) or 0
        
        print(f"DEBUG: Cliente {pedido.cliente_id}, Producto {producto_id}")
        print(f"DEBUG: Precio obtenido: {precio_unitario}")
        # ------------------------------------------------------------

        cantidad = cajas if cajas else peso   # si se usan cajas en el futuro
        subtotal = round(precio_unitario * cantidad, 2)

        # -------- Crear y guardar el detalle --------
        detalle = DetallePedido(
            pedido_id        = pedido.id,
            producto_id      = producto_id,
            cajas            = cajas,
            peso             = peso,
            lote             = lote,
            fecha_fabricacion= fecha_fabricacion,
            fecha_expiracion = fecha_expiracion,
            precio_unitario  = precio_unitario,
            subtotal         = subtotal
        )
        db.session.add(detalle)
        db.session.commit()

        flash('Detalle agregado.', 'success')
        return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

    # ── 3) GET: mostrar plantilla ─────────────────────────────
    return render_template('detalles_pedido.html',
                           pedido   = pedido,
                           productos= productos)


@app.route('/detalles_pedido/<int:detalle_id>/eliminar', methods=['POST'])
@login_required
def eliminar_detalle_pedido(detalle_id):
    detalle = DetallePedido.query.get_or_404(detalle_id)
    pedido_id = detalle.pedido_id
    db.session.delete(detalle)
    db.session.commit()
    flash('Detalle eliminado.', 'success')
    return redirect(url_for('detalles_pedido', pedido_id=pedido_id))

# ---------------------------------------------------------------------
# Generar etiquetas a partir de los DetallePedido de un pedido concreto
# ---------------------------------------------------------------------
@app.route('/generar_etiqueta_detalle/<int:pedido_id>', methods=['POST'])
@login_required
def generar_etiqueta_detalle(pedido_id):
    """
    Genera un PDF con etiquetas (mismo formato que en Facturación)
    pero usando los DetallePedido de un pedido.
    El formulario envía:
        - fecha_inicio  (YYYY-MM-DD)
        - fecha_fin     (YYYY-MM-DD)
    """
    try:
        pedido = Pedido.query.get_or_404(pedido_id)

        # --------- parámetros del formulario ----------
        fecha_ini = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')
        if not fecha_ini or not fecha_fin:
            return jsonify({"error": "Debe indicar fecha de inicio y fin"}), 400

        fi = datetime.strptime(fecha_ini, '%Y-%m-%d')
        ff = datetime.strptime(fecha_fin, '%Y-%m-%d')

        # --------- filtrar los detalles ----------
        detalles = (DetallePedido.query
                    .filter_by(pedido_id=pedido_id)
                    .filter(DetallePedido.fecha_fabricacion >= fecha_ini)
                    .filter(DetallePedido.fecha_fabricacion <= fecha_fin)
                    .all())

        if not detalles:
            return jsonify({"error": "No hay detalles en ese rango"}), 404

        # --------- PDF de etiquetas ----------
        output = BytesIO()
        c = canvas.Canvas(output, pagesize=A4)

        etiqueta_ancho = 100.16 / 25.4 * inch   # 4″ × 2″ (igual que facturación)
        etiqueta_alto  =  50.80 / 25.4 * inch
        page_w, page_h = A4
        x_offset       = (page_w - etiqueta_ancho) / 2
        y_top          = page_h - etiqueta_alto + 3
        y_bottom       = y_top - etiqueta_alto - 3
        por_pagina     = 2
        contador       = 0

        logo_path = os.path.join(basedir, 'static', 'logo_etiquetas.png')

        for d in detalles:
            # posición vertical alterna (arriba/abajo)
            y = y_top if contador % por_pagina == 0 else y_bottom

            # -------- datos --------
            cli = pedido.cliente.nombre
            prod = d.producto.nombre if d.producto else "N/A"
            temp = d.producto.temperatura or "N/A"
            peso = d.peso or d.cajas or 0

            # -------- dibujo --------
            # LOGO
            if os.path.exists(logo_path):
                c.drawImage(logo_path, x_offset + 10, y + 30,
                            width=1.2 * inch, height=1.2 * inch)

            c.setFont("Helvetica-Bold", 10)
            lbl_x = x_offset + 2.8 * inch
            val_x = lbl_x + 0.2 * inch

            c.drawRightString(lbl_x, y + 1.70 * inch, "Client:")
            c.drawRightString(lbl_x, y + 1.50 * inch, "Lot:")
            c.drawRightString(lbl_x, y + 1.30 * inch, "Manufactured:")
            c.drawRightString(lbl_x, y + 1.10 * inch, "Expiration:")
            c.drawRightString(lbl_x, y + 0.90 * inch, "When Kept at:")

            c.drawString(val_x, y + 1.70 * inch, cli)
            c.drawString(val_x, y + 1.50 * inch, d.lote or "")
            c.drawString(val_x, y + 1.30 * inch, d.fecha_fabricacion or "")
            c.drawString(val_x, y + 1.10 * inch, d.fecha_expiracion  or "")
            c.drawString(val_x, y + 0.90 * inch, temp)

            c.setFont("Helvetica-Bold", 14)
            c.drawRightString(lbl_x, y + 0.50 * inch, "Net Weight:")
            c.drawString(val_x,  y + 0.50 * inch, f"{peso:.2f}")

            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(x_offset + etiqueta_ancho / 2,
                                y + 0.15 * inch, prod)

            contador += 1
            if contador % por_pagina == 0:
                c.showPage()

        if contador % por_pagina != 0:
            c.showPage()

        c.save()
        output.seek(0)

        nombre_cliente = pedido.cliente.nombre.replace(" ", "_").replace("/", "-")
        filename = f"etiquetas_pedido_{pedido_id}_{nombre_cliente}.pdf"
        return send_file(output,
                         as_attachment=True,
                         download_name=filename,
                         mimetype="application/pdf")

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/pedidos/<int:pedido_id>/preparar', methods=['GET', 'POST'])
@login_required
def preparar_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    if request.method == 'POST':
        for detalle in pedido.detalles:
            entregadas = request.form.get(f'entregadas_{detalle.id}', type=int)
            peso_real = request.form.get(f'peso_{detalle.id}', type=float)
            lote = request.form.get(f'lote_{detalle.id}', '')
            fab = request.form.get(f'fab_{detalle.id}', '')
            exp = request.form.get(f'exp_{detalle.id}', '')
            detalle.cantidad_cajas = entregadas
            if detalle.producto.se_pesa:
                detalle.peso = peso_real
            detalle.lote = lote
            detalle.fecha_fabricacion = fab
            detalle.fecha_expiracion = exp
        pedido.estado = 'listo'
        db.session.commit()
        flash('Pedido preparado correctamente', 'success')
        return redirect(url_for('lista_pedidos'))
    return render_template('preparar_pedido.html', pedido=pedido)

N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL")  # ponlo en tu .env

@app.route('/pedidos/<int:pedido_id>/facturar', methods=['POST'])
@login_required
def facturar_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)

    # Sólo facturar si aún no fue facturado
    if pedido.estado == 'facturado':
        flash('El pedido ya está facturado.', 'info')
        return redirect(url_for('lista_pedidos'))

    payload = pedido_a_json(pedido)

    try:
        resp = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        flash(f'Error al enviar a n8n: {e}', 'danger')
        return redirect(url_for('lista_pedidos'))

    # Marcar como facturado si todo fue bien
    pedido.estado = 'facturado'
    db.session.commit()
    flash('Factura generada correctamente en QuickBooks.', 'success')
    return redirect(url_for('lista_pedidos'))
############################################
# RUTAS PARA SISTEMA DE PRECIOS
############################################

@app.route('/precios')
@login_required
def mostrar_precios():
    """Página principal del sistema de precios"""
    listas_precio = ListaPrecio.query.filter_by(activa=True).all()
    return render_template('precios/index.html', listas_precio=listas_precio)

# ---- LISTAS DE PRECIOS ----

@app.route('/precios/listas')
@login_required
def listas_precios():
    """Mostrar todas las listas de precios"""
    listas = ListaPrecio.query.order_by(ListaPrecio.es_default.desc(), ListaPrecio.nombre).all()
    return render_template('precios/listas.html', listas=listas)

@app.route('/precios/listas/nueva', methods=['GET', 'POST'])
@login_required
def nueva_lista_precio():
    """Crear nueva lista de precios"""
    if request.method == 'POST':
        try:
            nombre = request.form['nombre']
            descripcion = request.form.get('descripcion', '')
            
            nueva_lista = ListaPrecio(
                nombre=nombre,
                descripcion=descripcion
            )
            
            db.session.add(nueva_lista)
            db.session.commit()
            
            flash('Lista de precios creada exitosamente', 'success')
            return redirect(url_for('listas_precios'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la lista de precios: {str(e)}', 'error')
    
    return render_template('precios/lista_form.html')

@app.route('/precios/listas/<int:lista_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_lista_precio(lista_id):
    """Editar lista de precios"""
    lista = ListaPrecio.query.get_or_404(lista_id)
    
    if request.method == 'POST':
        try:
            lista.nombre = request.form['nombre']
            lista.descripcion = request.form.get('descripcion', '')
            
            db.session.commit()
            flash('Lista de precios actualizada exitosamente', 'success')
            return redirect(url_for('listas_precios'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la lista de precios: {str(e)}', 'error')
    
    return render_template('precios/lista_form.html', lista=lista)

@app.route('/precios/listas/<int:lista_id>/eliminar', methods=['POST'])
@login_required
def eliminar_lista_precio(lista_id):
    """Eliminar lista de precios"""
    lista = ListaPrecio.query.get_or_404(lista_id)
    
    if lista.es_default:
        return jsonify({'error': 'No se puede eliminar la lista de precios por defecto'}), 400
    
    try:
        db.session.delete(lista)
        db.session.commit()
        return jsonify({'message': 'Lista de precios eliminada exitosamente'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error al eliminar la lista: {str(e)}'}), 500

# ---- PRECIOS POR PRODUCTO EN LISTAS ----

@app.route('/precios/listas/<int:lista_id>/productos')
@login_required
def precios_lista_productos(lista_id):
    """Gestionar precios de productos en una lista específica"""
    lista = ListaPrecio.query.get_or_404(lista_id)
    productos = Producto.query.all()
    
    # Obtener precios existentes
    precios_existentes = db.session.query(PrecioProducto, Producto).join(
        Producto, PrecioProducto.producto_id == Producto.id
    ).filter(PrecioProducto.lista_precio_id == lista_id).all()
    
    return render_template('precios/lista_productos.html', 
                         lista=lista, 
                         productos=productos,
                         precios_existentes=precios_existentes)

@app.route('/precios/listas/<int:lista_id>/productos', methods=['POST'])
@login_required
def crear_precio_producto(lista_id):
    """Crear o actualizar precio de un producto en una lista"""
    try:
        producto_id = request.form['producto_id']
        precio_base = float(request.form['precio_base'])
        margen_jomar = float(request.form.get('margen_jomar', 1.0))
        margen_retail = float(request.form.get('margen_retail', 1.2))
        
        # Verificar si ya existe
        precio_existente = PrecioProducto.query.filter_by(
            lista_precio_id=lista_id,
            producto_id=producto_id
        ).first()
        
        if precio_existente:
            # Actualizar
            precio_existente.precio_base = precio_base
            precio_existente.margen_jomar = margen_jomar
            precio_existente.margen_retail = margen_retail
            precio_existente.calcular_precios()
            precio_existente.fecha_actualizacion = datetime.utcnow()
        else:
            # Crear nuevo
            nuevo_precio = PrecioProducto(
                lista_precio_id=lista_id,
                producto_id=producto_id,
                precio_base=precio_base,
                margen_jomar=margen_jomar,
                margen_retail=margen_retail
            )
            nuevo_precio.calcular_precios()
            db.session.add(nuevo_precio)
        
        db.session.commit()
        return jsonify({'message': 'Precio actualizado exitosamente'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error al actualizar precio: {str(e)}'}), 500

@app.route('/precios/productos/<int:precio_id>/eliminar', methods=['DELETE'])
@login_required
def eliminar_precio_producto(precio_id):
    """Eliminar precio de producto"""
    try:
        precio = PrecioProducto.query.get_or_404(precio_id)
        db.session.delete(precio)
        db.session.commit()
        return jsonify({'message': 'Precio eliminado exitosamente'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error al eliminar precio: {str(e)}'}), 500

# ---- ASIGNACIÓN DE LISTAS A CLIENTES ----

@app.route('/precios/clientes')
@login_required
def precios_clientes():
    """Gestionar listas de precios por cliente"""
    clientes = Cliente.query.all()
    listas = ListaPrecio.query.filter_by(activa=True).all()
    
    # Obtener asignaciones existentes
    asignaciones = db.session.query(ClienteListaPrecio, Cliente, ListaPrecio).join(
        Cliente, ClienteListaPrecio.cliente_id == Cliente.id
    ).join(
        ListaPrecio, ClienteListaPrecio.lista_precio_id == ListaPrecio.id
    ).filter(ClienteListaPrecio.activa == True).all()
    
    return render_template('precios/clientes.html', 
                         clientes=clientes, 
                         listas=listas,
                         asignaciones=asignaciones)

@app.route('/precios/clientes/asignar', methods=['POST'])
@login_required
def asignar_lista_cliente():
    """Asignar lista de precios a cliente"""
    try:
        cliente_id = request.form['cliente_id']
        lista_precio_id = request.form['lista_precio_id']
        
        # Verificar si ya existe una asignación activa
        asignacion_existente = ClienteListaPrecio.query.filter_by(
            cliente_id=cliente_id,
            activa=True
        ).first()
        
        if asignacion_existente:
            # Desactivar la asignación anterior
            asignacion_existente.activa = False
        
        # Crear nueva asignación
        nueva_asignacion = ClienteListaPrecio(
            cliente_id=cliente_id,
            lista_precio_id=lista_precio_id
        )
        
        db.session.add(nueva_asignacion)
        db.session.commit()
        
        return jsonify({'message': 'Lista de precios asignada exitosamente'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error al asignar lista: {str(e)}'}), 500

@app.route('/precios/clientes/<int:asignacion_id>/eliminar', methods=['DELETE'])
@login_required
def eliminar_asignacion_cliente(asignacion_id):
    """Eliminar asignación de lista de precios a cliente"""
    try:
        asignacion = ClienteListaPrecio.query.get_or_404(asignacion_id)
        db.session.delete(asignacion)
        db.session.commit()
        return jsonify({'message': 'Asignación eliminada exitosamente'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error al eliminar asignación: {str(e)}'}), 500

# ---- PRECIOS ESPECÍFICOS CLIENTE-PRODUCTO ----

@app.route('/precios/cliente-producto')
@login_required
def precios_cliente_producto():
    """Gestionar precios específicos por cliente-producto"""
    clientes = Cliente.query.all()
    productos = Producto.query.all()
    
    # Obtener precios específicos existentes
    precios_especificos = db.session.query(PrecioClienteProducto, Cliente, Producto).join(
        Cliente, PrecioClienteProducto.cliente_id == Cliente.id
    ).join(
        Producto, PrecioClienteProducto.producto_id == Producto.id
    ).filter(PrecioClienteProducto.activo == True).all()
    
    return render_template('precios/cliente_producto.html',
                         clientes=clientes,
                         productos=productos,
                         precios_especificos=precios_especificos)

@app.route('/precios/cliente-producto', methods=['POST'])
@login_required
def crear_precio_cliente_producto():
    """Crear precio específico cliente-producto"""
    try:
        cliente_id = request.form['cliente_id']
        producto_id = request.form['producto_id']
        precio_base = float(request.form['precio_base'])
        margen_jomar = float(request.form.get('margen_jomar', 1.0))
        margen_retail = float(request.form.get('margen_retail', 1.2))
        
        # Verificar si ya existe
        precio_existente = PrecioClienteProducto.query.filter_by(
            cliente_id=cliente_id,
            producto_id=producto_id
        ).first()
        
        if precio_existente:
            # Actualizar
            precio_existente.precio_base = precio_base
            precio_existente.margen_jomar = margen_jomar
            precio_existente.margen_retail = margen_retail
            precio_existente.calcular_precios()
            precio_existente.fecha_actualizacion = datetime.utcnow()
        else:
            # Crear nuevo
            nuevo_precio = PrecioClienteProducto(
                cliente_id=cliente_id,
                producto_id=producto_id,
                precio_base=precio_base,
                margen_jomar=margen_jomar,
                margen_retail=margen_retail
            )
            nuevo_precio.calcular_precios()
            db.session.add(nuevo_precio)
        
        db.session.commit()
        return jsonify({'message': 'Precio específico actualizado exitosamente'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error al actualizar precio específico: {str(e)}'}), 500

@app.route('/precios/cliente-producto/<int:precio_id>/eliminar', methods=['DELETE'])
@login_required
def eliminar_precio_cliente_producto(precio_id):
    """Eliminar precio específico cliente-producto"""
    try:
        precio = PrecioClienteProducto.query.get_or_404(precio_id)
        db.session.delete(precio)
        db.session.commit()
        return jsonify({'message': 'Precio específico eliminado exitosamente'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error al eliminar precio específico: {str(e)}'}), 500

# ---- API PARA OBTENER PRECIOS ----

# 1. Agregar esta nueva ruta API para obtener precios por cliente
@app.route('/api/precios/cliente/<int:cliente_id>/productos')
@login_required
def api_precios_cliente_productos(cliente_id):
    """API para obtener precios de todos los productos para un cliente específico"""
    productos = Producto.query.all()
    resultado = []
    
    for producto in productos:
        precio_jomar = obtener_precio_producto_cliente(cliente_id, producto.id, 'jomar')
        if precio_jomar is None:
            precio_jomar = obtener_precio_default_producto(producto.id, 'jomar') or 0
        
        resultado.append({
            'id': producto.id,
            'nombre': producto.nombre,
            'precio': float(precio_jomar)
        })
    
    return jsonify(resultado)

@app.route('/api/precios/lista/<int:lista_id>')
@login_required
def api_precios_lista(lista_id):
    """API para obtener todos los precios de una lista"""
    precios = db.session.query(PrecioProducto, Producto).join(
        Producto, PrecioProducto.producto_id == Producto.id
    ).filter(
        PrecioProducto.lista_precio_id == lista_id,
        PrecioProducto.activo == True
    ).all()
    
    resultado = []
    for precio, producto in precios:
        resultado.append({
            'producto_id': producto.id,
            'producto_nombre': producto.nombre,
            'precio_base': precio.precio_base,
            'precio_jomar': precio.precio_jomar,
            'precio_retail': precio.precio_retail,
            'margen_jomar': precio.margen_jomar,
            'margen_retail': precio.margen_retail
        })
    
    return jsonify(resultado)

@app.route('/api/precios/cliente/<int:cliente_id>')
@login_required
def api_precios_cliente(cliente_id):
    """API para obtener todos los precios disponibles para un cliente"""
    productos = Producto.query.all()
    resultado = []
    
    for producto in productos:
        precio_base = obtener_precio_producto_cliente(cliente_id, producto.id, 'base')
        precio_jomar = obtener_precio_producto_cliente(cliente_id, producto.id, 'jomar')
        precio_retail = obtener_precio_producto_cliente(cliente_id, producto.id, 'retail')
        
        if precio_base is not None:
            resultado.append({
                'producto_id': producto.id,
                'producto_nombre': producto.nombre,
                'precio_base': precio_base,
                'precio_jomar': precio_jomar,
                'precio_retail': precio_retail
            })
    
    return jsonify(resultado)

############################################
# Rutas de Productos
############################################


@app.route('/productos', methods=['GET', 'POST'])
@login_required
def productos():
    if request.method == 'POST':
        # Crear o actualizar producto
        nombre      = request.form['nombre']
        descripcion = request.form.get('descripcion', '')
        temperatura = request.form.get('temperatura', '')
        qbo_id      = request.form.get('qbo_id')
        tax_rate    = float(request.form.get('tax_rate', 0.0))

        nuevo = Producto(
            nombre=nombre,
            descripcion=descripcion,
            temperatura=temperatura,
            qbo_id=qbo_id,
            tax_rate=tax_rate
        )
        db.session.add(nuevo)
        db.session.commit()
        flash('Producto creado exitosamente.', 'success')
        return redirect(url_for('productos'))

    # GET → listamos todos los productos ordenados
    todos = Producto.query.order_by(Producto.id.asc()).all()
    return render_template('productos.html', productos=todos)





@app.route('/productos/<int:producto_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    if request.method == 'POST':
        producto.nombre      = request.form['nombre']
        producto.descripcion = request.form.get('descripcion', '')
        producto.temperatura = request.form.get('temperatura', '')
        producto.qbo_id      = request.form.get('qbo_id')
        producto.tax_rate    = float(request.form.get('tax_rate', 0.0))
        db.session.commit()
        flash('Producto actualizado correctamente.', 'success')
        return redirect(url_for('productos'))

    return render_template('editar_producto.html', producto=producto)




@app.route('/api/productos', methods=['GET'])
@login_required
def obtener_productos_api():
    productos = Producto.query.order_by(Producto.id).all()
    productos_data = []
    for p in productos:
        precio = obtener_precio_default_producto(p.id, 'jomar')
        productos_data.append({
            "id"         : p.id,
            "nombre"     : p.nombre,
            "descripcion": p.descripcion,
            "temperatura": p.temperatura,
            "qbo_id"     : p.qbo_id,
            "tax_rate"   : p.tax_rate,  # Nueva línea
            "precio"     : float(precio or 0)
        })
    return jsonify(productos_data)


@app.route('/productos/<int:producto_id>/eliminar', methods=['POST'])
@login_required
def eliminar_producto(producto_id):
    try:
        producto = Producto.query.get_or_404(producto_id)
        db.session.delete(producto)
        db.session.commit()
        return jsonify({'message': 'Producto eliminado correctamente.'}), 200
    except Exception as e:
        app.logger.error(f"Error al eliminar el producto: {e}")
        return jsonify({'error': 'Error al eliminar el producto.'}), 500



@app.before_request
def override_method():
    if request.method == 'POST' and '_method' in request.form:
        method = request.form['_method'].upper()
        if method in ['PUT', 'DELETE']:
            request.environ['REQUEST_METHOD'] = method


# Rutas para Recepciones
@app.route('/recepciones')
@login_required
def mostrar_recepciones():
    productos = Producto.query.all()
    recepciones = Recepcion.query.all()
    ultima_recepcion = Recepcion.query.order_by(Recepcion.id.desc()).first()
    return render_template('recepciones.html', productos=productos, recepciones=recepciones, ultima_recepcion=ultima_recepcion)

@app.route('/api/recepciones', methods=['GET'])
@login_required
def obtener_recepciones_api():
    recepciones = Recepcion.query.order_by(Recepcion.id.desc()).limit(20).all()
    recepciones_data = [{
        'id': r.id,
        'producto_id': r.producto_id,
        'producto': r.producto.nombre if r.producto else 'undefined',
        'peso': r.peso,
        'recibido_en': r.recibido_en.strftime('%Y-%m-%d') if r.recibido_en else 'No disponible',
        'proveedor': r.proveedor,
        'numero_factura': r.numero_factura
    } for r in recepciones]
    return jsonify(recepciones_data)

@app.route('/recepciones', methods=['POST'])
@login_required
def crear_recepcion():
    try:
        producto_id = request.form['producto_id']
        peso = request.form['peso']
        proveedor = request.form['proveedor']
        numero_factura = request.form['numero_factura']
        fecha_recepcion = request.form['fecha_recepcion']
        try:
            recibido_en = datetime.strptime(fecha_recepcion, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido. Debe ser YYYY-MM-DD"}), 400
        nueva_recepcion = Recepcion(
            producto_id=producto_id,
            peso=peso,
            proveedor=proveedor,
            numero_factura=numero_factura,
            recibido_en=recibido_en
        )
        db.session.add(nueva_recepcion)
        db.session.commit()
        recepcion_data = nueva_recepcion.to_dict()
        return jsonify({
            "message": "Recepción registrada exitosamente",
            "recepcion": recepcion_data
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al registrar la recepción: {str(e)}"}), 500

@app.route('/recepciones/<int:id>', methods=['DELETE'])
@login_required
def eliminar_recepcion(id):
    recepcion = Recepcion.query.get_or_404(id)
    try:
        db.session.delete(recepcion)
        db.session.commit()
        return jsonify({"message": "Recepción eliminada con éxito"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar la recepción: {str(e)}"}), 500

# Rutas para Facturación
@app.route('/facturacion', methods=['GET', 'POST'])
@login_required
def facturacion():
    if request.method == 'GET':
        productos = Producto.query.all()
        clientes = Cliente.query.all()
        today = datetime.utcnow().date()
        previous_data = {
            'producto_id': session.get('producto_id', ''),
            'cliente_id': session.get('cliente_id', ''),
            'lote': session.get('lote', ''),
            'fecha_fabricacion': session.get('fecha_fabricacion', '')
        }
        if previous_data['cliente_id']:
            facturaciones = Facturacion.query.filter_by(cliente_id=previous_data['cliente_id']) \
                .filter(Facturacion.fecha_registro >= today) \
                .order_by(Facturacion.fecha_registro.desc()).all()
        else:
            facturaciones = []
        return render_template('facturacion.html', 
                               facturaciones=facturaciones, 
                               productos=productos, 
                               clientes=clientes,
                               previous_data=previous_data)
    return registrar_facturacion()

@app.route('/ultimos_facturaciones', methods=['GET'])
@login_required
def ultimos_facturaciones():
    cliente_id = request.args.get('cliente_id', type=int)
    hoy = datetime.utcnow().date()
    if cliente_id:
        facturaciones = db.session.query(Facturacion.id, Facturacion.peso, Facturacion.lote, 
                                         Facturacion.fecha_fabricacion, Facturacion.fecha_expiracion, 
                                         Facturacion.fecha_registro, Producto.nombre.label('producto_nombre'),
                                         Cliente.nombre.label('cliente_nombre')).\
            join(Producto, Facturacion.producto_id == Producto.id).\
            join(Cliente, Facturacion.cliente_id == Cliente.id).\
            filter(Facturacion.cliente_id == cliente_id).\
            filter(Facturacion.fecha_registro >= hoy).\
            order_by(Facturacion.fecha_registro.desc()).all()
    else:
        facturaciones = db.session.query(Facturacion.id, Facturacion.peso, Facturacion.lote, 
                                         Facturacion.fecha_fabricacion, Facturacion.fecha_expiracion, 
                                         Facturacion.fecha_registro, Producto.nombre.label('producto_nombre'),
                                         Cliente.nombre.label('cliente_nombre')).\
            join(Producto, Facturacion.producto_id == Producto.id).\
            join(Cliente, Facturacion.cliente_id == Cliente.id).\
            order_by(Facturacion.fecha_registro.desc()).limit(20).all()
    return jsonify([{
        'id': facturacion.id,
        'producto': facturacion.producto_nombre,
        'cliente': facturacion.cliente_nombre,
        'peso': facturacion.peso,
        'lote': facturacion.lote,
        'fecha_fabricacion': facturacion.fecha_fabricacion,
        'fecha_expiracion': facturacion.fecha_expiracion,
        'fecha_registro': facturacion.fecha_registro.strftime('%Y-%m-%d %H:%M')
    } for facturacion in facturaciones])

@app.route('/facturacion/registrar', methods=['POST'])
@login_required
def registrar_facturacion():
    try:
        producto_id = request.form['producto_id']
        cliente_id = request.form['cliente_id']
        peso = request.form['peso']
        lote = request.form['lote']
        fecha_fabricacion = request.form['fecha_fabricacion']
        fecha_fabricacion_date = datetime.strptime(fecha_fabricacion, '%Y-%m-%d')
        fecha_expiracion = fecha_fabricacion_date + timedelta(days=365)
        session['producto_id'] = producto_id
        session['cliente_id'] = cliente_id
        session['lote'] = lote
        session['fecha_fabricacion'] = fecha_fabricacion
        nueva_facturacion = Facturacion(
            producto_id=producto_id,
            cliente_id=cliente_id,
            peso=peso,
            lote=lote,
            fecha_fabricacion=fecha_fabricacion,
            fecha_expiracion=fecha_expiracion.strftime('%Y-%m-%d'),
            fecha_registro=datetime.utcnow()
        )
        db.session.add(nueva_facturacion)
        db.session.commit()
        return jsonify({"message": "Peso registrado exitosamente"}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/facturacion/eliminar/<int:id>', methods=['DELETE'])
@login_required
def eliminar_facturacion(id):
    try:
        facturacion = Facturacion.query.get_or_404(id)
        db.session.delete(facturacion)
        db.session.commit()
        return jsonify({"message": "Facturación eliminada exitosamente"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# Rutas para Importaciones, Reportes y Etiquetas
@app.route('/formulario_importacion')
@login_required
def formulario_importacion():
    productos = Producto.query.all()
    facturas = db.session.query(
        Importacion.numero_factura,
        func.count(Importacion.id).label('cantidad_productos'),
        func.sum(Importacion.cantidad_total).label('cantidad_total'),
        func.sum(Importacion.precio_fob_unidad * Importacion.cantidad_total).label('total_fob'),
        func.sum(Importacion.flete).label('total_flete'),
        func.sum(Importacion.arancel).label('total_arancel'),
        func.sum(Importacion.costo_aduana).label('total_costo_aduana'),
        func.sum(Importacion.precio_jomar * Importacion.cantidad_total).label('total_precio_jomar'),
        func.max(Importacion.fecha_importacion).label('fecha_importacion')
    ).group_by(Importacion.numero_factura).all()
    return render_template('formulario_importacion.html', productos=productos, facturas=facturas)

@app.route('/registrar_importacion', methods=['POST'])
@login_required
def registrar_importacion():
    try:
        numero_factura = request.form.get('numero_factura')
        proveedor = request.form.get('proveedor')
        moneda = request.form.get('moneda')
        tipo_cambio_ang = float(request.form.get('tipo_cambio_ang') or 0)
        flete_total = float(request.form.get('flete_total') or 0)
        gastos_agente_aduanal = float(request.form.get('gastos_agente_aduanal') or 0)
        arancel_porcentaje = float(request.form.get('arancel') or 0) / 100
        ob_porcentaje = float(request.form.get('ob') or 0) / 100
        flete_local_total = float(request.form.get('flete_local') or 0)
        fecha_importacion_str = request.form.get('fecha_importacion')
        if fecha_importacion_str:
            fecha_importacion = datetime.strptime(fecha_importacion_str, '%Y-%m-%d')
        else:
            fecha_importacion = datetime.utcnow()
        productos = []
        print("Datos recibidos del formulario:")
        print(request.form)
        total_fob_general = 0
        total_cif_ang_general = 0
        num_productos = len([key for key in request.form.keys() if 'productos' in key and '[producto]' in key])
        for i in range(num_productos):
            qty_total = float(request.form.get(f'productos[{i}][qty_total]', 0))
            price_fob = float(request.form.get(f'productos[{i}][price_fob]', 0))
            total_fob = qty_total * price_fob
            total_fob_general += total_fob
        for i in range(num_productos):
            qty_total = float(request.form.get(f'productos[{i}][qty_total]', 0))
            price_fob = float(request.form.get(f'productos[{i}][price_fob]', 0))
            total_fob = qty_total * price_fob
            flete_proporcional = (total_fob / total_fob_general) * flete_total if total_fob_general > 0 else 0
            total_cif = total_fob + flete_proporcional
            cif_ang = total_cif * tipo_cambio_ang
            total_cif_ang_general += cif_ang
        for i in range(num_productos):
            producto_id = int(request.form.get(f'productos[{i}][producto]', 0))
            und_caja = int(request.form.get(f'productos[{i}][und_caja]', 1))
            qty_total = float(request.form.get(f'productos[{i}][qty_total]', 0))
            price_fob = float(request.form.get(f'productos[{i}][price_fob]', 0))
            total_fob = qty_total * price_fob
            flete_proporcional = (total_fob / total_fob_general) * flete_total if total_fob_general > 0 else 0
            total_cif = total_fob + flete_proporcional
            cif_ang = total_cif * tipo_cambio_ang
            arancel_ang = cif_ang * arancel_porcentaje
            ob_ang = cif_ang * ob_porcentaje
            ob_45 = ob_ang * 0.045
            flete_local_proporcional = (cif_ang / total_cif_ang_general) * flete_local_total if total_cif_ang_general > 0 else 0
            gastos_aduanal_proporcional = (cif_ang / total_cif_ang_general) * gastos_agente_aduanal if total_cif_ang_general > 0 else 0
            costo_total_almacen_producto = cif_ang + arancel_ang + ob_ang + gastos_aduanal_proporcional + flete_local_proporcional - ob_45
            total_unidades = qty_total * und_caja
            costo_por_unidad_ang = costo_total_almacen_producto / total_unidades if total_unidades > 0 else 0
            precio_jomar = costo_por_unidad_ang
            precio_retail = precio_jomar * 1.2
            nueva_importacion = Importacion(
                numero_factura=numero_factura,
                producto_id=producto_id,
                cantidad_cajas=und_caja,
                cantidad_total=qty_total,
                precio_fob_unidad=price_fob,
                flete=flete_proporcional,
                arancel=arancel_ang,
                costo_aduana=gastos_aduanal_proporcional,
                precio_jomar=precio_jomar,
                precio_retail=precio_retail,
                fecha_importacion=fecha_importacion,
                cif_ang=cif_ang,
                ob_ang=ob_ang,
                flete_local=flete_local_proporcional,
                costo_total_almacen=costo_total_almacen_producto
            )
            db.session.add(nueva_importacion)
            productos.append(nueva_importacion)
            print(f"Procesando producto índice: {i}")
            print(f"Producto ID: {producto_id}")
            print(f"Cantidad Total: {qty_total}")
            print(f"Precio FOB: {price_fob}")
            print(f"Total FOB: {total_fob}")
            print(f"Flete Proporcional: {flete_proporcional}")
            print(f"Total CIF: {total_cif}")
            print(f"CIF ANG: {cif_ang}")
            print(f"Arancel ANG: {arancel_ang}")
            print(f"OB ANG: {ob_ang}")
            print(f"OB Dev 4.5%: {ob_45}")
            print(f"Flete Local Proporcional: {flete_local_proporcional}")
            print(f"Gastos Aduanal Proporcional: {gastos_aduanal_proporcional}")
            print(f"Costo Total Almacén: {costo_total_almacen_producto}")
            print(f"Costo Unidad ANG: {costo_por_unidad_ang}")
            print(f"Precio Jomar: {precio_jomar}")
            print(f"Precio Retail: {precio_retail}")
            print("-------------------------------------------")
        if not productos:
            flash("No se han proporcionado productos para la importación", "danger")
            return redirect(url_for('formulario_importacion'))
        db.session.commit()
        print(f"Importación registrada con {len(productos)} productos.")
        flash("Importación registrada exitosamente", "success")
        return redirect(url_for('formulario_importacion'))
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        print(f"Error al registrar la importación: {e}")
        flash(f"Error al registrar la importación: {e}", "danger")
        return redirect(url_for('formulario_importacion'))

@app.route('/reporte_factura/<numero_factura>', methods=['GET'])
@login_required
def reporte_factura(numero_factura):
    importaciones = db.session.query(Importacion, Producto).join(Producto).filter(Importacion.numero_factura == numero_factura).all()
    if not importaciones:
        return "No se encontraron importaciones para el número de factura proporcionado.", 404
    fecha_importacion = importaciones[0][0].fecha_importacion.strftime('%d/%m/%Y')
    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.25 * inch,
        rightMargin=0.25 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch
    )
    elements = []
    styles = getSampleStyleSheet()
    styleTitle = styles['Title']
    styleTitle.alignment = TA_LEFT
    style_cell = ParagraphStyle(
        name='CellStyle',
        fontSize=7,
        alignment=TA_CENTER,
        leading=8
    )
    style_header = ParagraphStyle(
        name='HeaderStyle',
        fontSize=7,
        alignment=TA_CENTER,
        leading=8,
        textColor=colors.whitesmoke,
        backColor=colors.grey
    )
    logo_path = os.path.join(basedir, 'static', 'logo_etiquetas.png')
    if os.path.exists(logo_path):
        logo_width = 50
        logo_height = 50
        logo = Image(logo_path, width=logo_width, height=logo_height)
        titulo_text = f"Reporte de Importación - Factura {numero_factura}"
        titulo = Paragraph(titulo_text, styleTitle)
        desired_indent = 1.0 * inch
        data_title = [['', logo, titulo]]
        table_title = Table(
            data_title,
            colWidths=[desired_indent, logo_width, None]
        )
        table_title_style = TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ])
        table_title.setStyle(table_title_style)
        table_title.hAlign = 'LEFT'
        elements.append(table_title)
    else:
        desired_indent = 1.0 * inch
        titulo = Paragraph(f"Reporte de Importación - Factura {numero_factura}", styleTitle)
        data_title = [['', titulo]]
        table_title = Table(
            data_title,
            colWidths=[desired_indent, None]
        )
        table_title.hAlign = 'LEFT'
        elements.append(table_title)
    style_fecha = ParagraphStyle(
        name='FechaStyle',
        fontSize=9,
        alignment=TA_LEFT,
        leading=12,
        leftIndent=1.0 * inch
    )
    fecha_paragraph = Paragraph(f"Fecha de Importación: {fecha_importacion}", style_fecha)
    elements.append(fecha_paragraph)
    elements.append(Spacer(1, 12))
    data = [[
        Paragraph("Producto", style_header),
        Paragraph("Qty", style_header),
        Paragraph("P FOB", style_header),
        Paragraph("T FOB", style_header),
        Paragraph("Flete", style_header),
        Paragraph("T CIF", style_header),
        Paragraph("CIF ANG", style_header),
        Paragraph("Arancel", style_header),
        Paragraph("OB ANG", style_header),
        Paragraph("OB 4.5%", style_header),
        Paragraph("GAA", style_header),
        Paragraph("Costo Alm.", style_header),
        Paragraph("Costo/U ANG", style_header)
    ]]
    total_qty = 0
    total_fob = 0
    total_flete = 0
    total_cif = 0
    total_cif_ang = 0
    total_arancel = 0
    total_ob_ang = 0
    total_ob_45 = 0
    total_gastos_agente_aduanal = 0
    total_costo_total_almacen = 0
    for imp, prod in importaciones:
        total_qty += imp.cantidad_total
        total_fob_producto = imp.cantidad_total * imp.precio_fob_unidad
        total_fob += total_fob_producto
        total_flete += imp.flete
        total_cif_producto = total_fob_producto + imp.flete
        total_cif += total_cif_producto
        total_cif_ang += imp.cif_ang or 0
        total_arancel += imp.arancel or 0
        total_ob_ang += imp.ob_ang or 0
        ob_dev_45 = (imp.ob_ang or 0) * 0.5
        total_ob_45 += ob_dev_45
        total_gastos_agente_aduanal += imp.costo_aduana or 0
        costo_total_almacen_producto = (
            (imp.cif_ang or 0) +
            (imp.arancel or 0) +
            (imp.ob_ang or 0) +
            (imp.costo_aduana or 0) +
            (imp.flete_local or 0) -
            ob_dev_45
        )
        total_costo_total_almacen += costo_total_almacen_producto
        unidades_por_caja = imp.cantidad_cajas or 1
        cantidad_total_unidades = imp.cantidad_total * unidades_por_caja
        if cantidad_total_unidades > 0:
            costo_por_unidad_ang = costo_total_almacen_producto / cantidad_total_unidades
        else:
            costo_por_unidad_ang = 0
        precio_jomar = costo_por_unidad_ang
        precio_retail = precio_jomar * 1.2
        data.append([
            Paragraph(prod.nombre, style_cell),
            Paragraph("{:,.2f}".format(imp.cantidad_total), style_cell),
            Paragraph("{:,.2f}".format(imp.precio_fob_unidad), style_cell),
            Paragraph("{:,.2f}".format(total_fob_producto), style_cell),
            Paragraph("{:,.2f}".format(imp.flete), style_cell),
            Paragraph("{:,.2f}".format(total_cif_producto), style_cell),
            Paragraph("{:,.2f}".format(imp.cif_ang or 0), style_cell),
            Paragraph("{:,.2f}".format(imp.arancel or 0), style_cell),
            Paragraph("{:,.2f}".format(imp.ob_ang or 0), style_cell),
            Paragraph("{:,.2f}".format(ob_dev_45), style_cell),
            Paragraph("{:,.2f}".format(imp.costo_aduana or 0), style_cell),
            Paragraph("{:,.2f}".format(costo_total_almacen_producto), style_cell),
            Paragraph("{:,.2f}".format(costo_por_unidad_ang), style_cell)
        ])
    data.append([
        Paragraph("Totales", style_header),
        Paragraph("{:,.2f}".format(total_qty), style_header),
        Paragraph("", style_header),
        Paragraph("{:,.2f}".format(total_fob), style_header),
        Paragraph("{:,.2f}".format(total_flete), style_header),
        Paragraph("{:,.2f}".format(total_cif), style_header),
        Paragraph("{:,.2f}".format(total_cif_ang), style_header),
        Paragraph("{:,.2f}".format(total_arancel), style_header),
        Paragraph("{:,.2f}".format(total_ob_ang), style_header),
        Paragraph("{:,.2f}".format(total_ob_45), style_header),
        Paragraph("{:,.2f}".format(total_gastos_agente_aduanal), style_header),
        Paragraph("{:,.2f}".format(total_costo_total_almacen), style_header),
        Paragraph("", style_header)
    ])
    column_widths = [
        2.0 * inch,
        0.5 * inch,
        0.5 * inch,
        0.6 * inch,
        0.5 * inch,
        0.6 * inch,
        0.6 * inch,
        0.6 * inch,
        0.6 * inch,
        0.6 * inch,
        0.6 * inch,
        0.6 * inch,
        0.8 * inch
    ]
    total_column_width = sum(column_widths)
    usable_width = page_width - doc.leftMargin - doc.rightMargin
    if total_column_width > usable_width:
        scale_factor = usable_width / total_column_width
        column_widths = [width * scale_factor for width in column_widths]
    table = Table(data, colWidths=column_widths, repeatRows=1)
    table_style = TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('LEFTPADDING', (0, 0), (-1, -1), 1),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ])
    for row_num in range(1, len(data) - 1):
        if (row_num % 2) == 1:
            bg_color = colors.HexColor('#f2f2f2')
            table_style.add('BACKGROUND', (0, row_num), (-1, row_num), bg_color)
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 12))
    doc.build(elements)
    output.seek(0)
    nombre_archivo = f"reporte_factura_{numero_factura}.pdf"
    return send_file(
        output,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype='application/pdf'
    )

# app.py
@app.route('/clientes', methods=['GET'])
@login_required
def mostrar_clientes():
    # ↓↓↓  ahora vienen ordenados de menor a mayor ID
    clientes = (Cliente
                .query
                .order_by(Cliente.id.asc())   # o .desc() si los quieres al revés
                .all())

    return render_template('clientes.html', clientes=clientes)


@app.route('/clientes/nuevo', methods=['POST'])
@login_required
def nuevo_cliente():
    try:
        nombre  = request.form['nombre']
        qbo_id  = request.form.get('qbo_id') or None          # ← 🆕
        
        # Evitar duplicados
        if qbo_id and Cliente.query.filter_by(qbo_id=qbo_id).first():
            return jsonify({"error": "Ya existe un cliente con ese QBO ID"}), 400
        
        nuevo_cliente = Cliente(nombre=nombre, qbo_id=qbo_id) # ← 🆕
        db.session.add(nuevo_cliente)
        db.session.commit()
        return jsonify({
            "message": "Cliente registrado exitosamente",
            "cliente": nuevo_cliente.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@app.route('/clientes/<int:cliente_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)

    if request.method == 'POST':
        try:
            cliente.nombre = request.form['nombre']
            qbo_id         = request.form.get('qbo_id') or None

            # Verificar unicidad si cambió
            if qbo_id != cliente.qbo_id and qbo_id \
                    and Cliente.query.filter_by(qbo_id=qbo_id).first():
                flash('Ya existe otro cliente con ese QBO ID', 'danger')
                return redirect(url_for('editar_cliente', cliente_id=cliente.id))
            
            cliente.qbo_id = qbo_id
            db.session.commit()
            flash('Cliente actualizado', 'success')
            return redirect(url_for('mostrar_clientes'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
            return redirect(url_for('mostrar_clientes'))

    # GET
    return render_template('cliente_form.html', cliente=cliente)

@app.route('/clientes/<int:cliente_id>', methods=['DELETE'])
@login_required
def eliminar_cliente(cliente_id):
    try:
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404
        db.session.delete(cliente)
        db.session.commit()
        return jsonify({"message": "Cliente eliminado exitosamente"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/generar_reporte', methods=['GET'])
@login_required
def generar_reporte():
    try:
        numero_factura = request.args.get('numero_factura')
        proveedor = request.args.get('proveedor')
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        query = Recepcion.query
        if numero_factura:
            query = query.filter_by(numero_factura=numero_factura)
        if proveedor:
            query = query.filter_by(proveedor=proveedor)
        if fecha_inicio:
            query = query.filter(Recepcion.recibido_en >= fecha_inicio)
        if fecha_fin:
            query = query.filter(Recepcion.recibido_en <= fecha_fin)
        recepciones = query.all()
        data = [{
            'Producto': r.producto.nombre if r.producto else 'undefined',
            'Peso': r.peso,
            'Proveedor': r.proveedor,
            'Número de Factura': r.numero_factura,
            'Fecha de Recepción': r.recibido_en.strftime('%Y-%m-%d')
        } for r in recepciones]
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Reporte')
        bold_blue_format = workbook.add_format({'bold': True, 'color': 'blue'})
        bold_red_format = workbook.add_format({'bold': True, 'color': 'red'})
        bold_black_format = workbook.add_format({'bold': True, 'color': 'black'})
        number_format = workbook.add_format({'num_format': '0.00'})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
        alignment = workbook.add_format({'align': 'left'})
        worksheet.write('A1', "Proveedor:", bold_blue_format)
        worksheet.write('B1', proveedor, bold_black_format)
        worksheet.write('A2', "Factura", bold_blue_format)
        worksheet.write('B2', numero_factura, bold_black_format)
        worksheet.write('A3', "Fecha", bold_blue_format)
        worksheet.write('B3', fecha_inicio, bold_black_format)
        worksheet.write('A5', "Resumen de Productos", bold_blue_format)
        resumen_df = pd.DataFrame(data).groupby('Producto')['Peso'].sum().reset_index()
        resumen_df.columns = ['Producto', 'Peso Total']
        worksheet.write('A7', "Producto", bold_blue_format)
        worksheet.write('B7', "Peso Total", bold_blue_format)
        total_peso = resumen_df['Peso Total'].sum()
        row = 8
        for idx, item in resumen_df.iterrows():
            worksheet.write(row, 0, item['Producto'], bold_black_format)
            worksheet.write(row, 1, item['Peso Total'], number_format)
            row += 1
        worksheet.write(row, 0, "Total", bold_blue_format)
        worksheet.write(row, 1, total_peso, bold_blue_format)
        row += 2
        worksheet.write(row, 0, "Detalles de Recepciones", bold_blue_format)
        row += 1
        worksheet.write(row, 0, "Producto", bold_blue_format)
        worksheet.write(row, 1, "Peso", bold_blue_format)
        worksheet.write(row, 2, "Fecha", bold_blue_format)
        worksheet.write(row, 3, "Proveedor", bold_blue_format)
        worksheet.write(row, 4, "Número de Factura", bold_blue_format)
        row += 1
        for r in data:
            worksheet.write(row, 0, r['Producto'], bold_black_format)
            worksheet.write(row, 1, r['Peso'], number_format)
            worksheet.write(row, 2, r['Fecha de Recepción'], date_format)
            worksheet.write(row, 3, r['Proveedor'], bold_black_format)
            worksheet.write(row, 4, r['Número de Factura'], bold_black_format)
            row += 1
        workbook.close()
        output.seek(0)
        nombre_archivo = f"reporte_recepciones_{numero_factura}.xlsx"
        return send_file(output, as_attachment=True, download_name=nombre_archivo, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        print(f"Error al generar el reporte: {e}")
        return jsonify({'error': str(e)}), 500

try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    print("No se pudo configurar el locale 'en_US.UTF-8'. Se usará el formato de números por defecto.")

@app.route('/generar_reporte_pesos', methods=['GET'])
@login_required
def generar_reporte_pesos():
    cliente_nombre = request.args.get('cliente')
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    fecha_inicio_date = datetime.strptime(fecha_inicio, '%Y-%m-%d')
    fecha_fin_date = datetime.strptime(fecha_fin, '%Y-%m-%d')
    facturaciones = Facturacion.query.join(Cliente).filter(
        Cliente.nombre == cliente_nombre,
        Facturacion.fecha_registro.between(fecha_inicio_date, fecha_fin_date)
    ).all()
    if not facturaciones:
        return jsonify({'error': 'No se encontraron pesos registrados para el cliente y rango de fechas especificados'}), 404
    wb = openpyxl.Workbook()
    ws = wb.active
    bold_font = Font(bold=True, color="0000FF")
    red_bold_font = Font(bold=True, color="FF0000")
    alignment = Alignment(horizontal="left")
    ws['A1'] = "Cliente:"
    ws['B1'] = cliente_nombre
    ws['A2'] = "Fecha de Registro:"
    ws['B2'] = f"{fecha_inicio} - {fecha_fin}"
    ws['A1'].font = bold_font
    ws['A2'].font = bold_font
    ws['A1'].alignment = alignment
    ws['A2'].alignment = alignment
    row = 4
    producto_grupo = {}
    for facturacion in facturaciones:
        producto = facturacion.producto.nombre
        if (producto not in producto_grupo):
            producto_grupo[producto] = []
        producto_grupo[producto].append(f"{facturacion.peso:.2f}")
    total_general = 0
    producto_index = 1
    for producto, pesos in producto_grupo.items():
        ws[f'A{row}'] = f"Producto {producto_index}:"
        ws[f'B{row}'] = producto
        ws[f'A{row}'].font = bold_font
        ws[f'B{row}'].font = bold_font
        row += 1
        ws[f'A{row}'] = "Pesos:"
        ws[f'A{row}'].font = bold_font
        col = 'B'
        total_producto = 0
        count = 0
        for peso in pesos:
            ws[f'{col}{row}'] = peso
            total_producto += float(peso)
            col = chr(ord(col) + 1)
            count += 1
            if count % 3 == 0:
                row += 1
                col = 'B'
        row += 1
        ws[f'A{row}'] = "Total:"
        ws[f'B{row}'] = f"{total_producto:.2f}"
        ws[f'A{row}'].font = red_bold_font
        ws[f'B{row}'].font = red_bold_font
        total_general += total_producto
        row += 2
        producto_index += 1
    ws[f'A{row}'] = "Total General:"
    ws[f'B{row}'] = f"{total_general:.2f}"
    ws[f'A{row}'].font = red_bold_font
    ws[f'B{row}'].font = red_bold_font
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    nombre_archivo_cliente = cliente_nombre.replace(" ", "_").replace("/", "_")
    nombre_archivo = f"reporte_pesos_{nombre_archivo_cliente}_{fecha_inicio}_a_{fecha_fin}.xlsx"
    return send_file(output, as_attachment=True, download_name=nombre_archivo, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route('/generar_etiqueta', methods=['POST'])
@login_required
def generar_etiqueta():
    try:
        cliente_nombre = request.form.get('cliente')
        fecha_inicio = request.form.get('fecha_inicio')
        fecha_fin = request.form.get('fecha_fin')
        if not cliente_nombre or not fecha_inicio or not fecha_fin:
            return jsonify({"error": "Todos los campos son obligatorios"}), 400
        fecha_inicio_date = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        fecha_fin_date = datetime.strptime(fecha_fin, '%Y-%m-%d')
        facturaciones = Facturacion.query.join(Cliente).filter(
            Cliente.nombre == cliente_nombre,
            Facturacion.fecha_registro.between(fecha_inicio_date, fecha_fin_date)
        ).all()
        if not facturaciones:
            return jsonify({"error": "No se encontraron facturaciones para los criterios seleccionados"}), 404
        output = BytesIO()
        page_width, page_height = A4
        etiqueta_ancho = 100.16 / 25.4 * inch
        etiqueta_alto = 50.8 / 25.4 * inch
        x_offset = (page_width - etiqueta_ancho) / 2
        y_offset_top = page_height - etiqueta_alto + 3
        y_offset_bottom = y_offset_top - etiqueta_alto - 3
        c = canvas.Canvas(output, pagesize=A4)
        etiquetas_por_pagina = 2
        etiqueta_contador = 0
        basedir = os.path.abspath(os.path.dirname(__file__))
        logo_path = os.path.join(basedir, 'static', 'logo_etiquetas.png')
        if not os.path.exists(logo_path):
            return jsonify({"error": f"El archivo {logo_path} no existe"}), 500
        for facturacion in facturaciones:
            producto = facturacion.producto
            cliente_nombre = facturacion.cliente.nombre if facturacion.cliente else "N/A"
            producto_nombre = producto.nombre if producto else "N/A"
            temperatura = producto.temperatura if producto and producto.temperatura else "N/A"
            if etiqueta_contador % etiquetas_por_pagina == 0:
                y_offset = y_offset_top
            else:
                y_offset = y_offset_bottom
            shift_left = 25
            logo_shift_up = 20
            logo_shift_right = 20
            c.drawImage(logo_path, x_offset + 10 - shift_left + logo_shift_right, y_offset + 30 + logo_shift_up, width=1.2 * inch, height=1.2 * inch)
            c.setFont("Helvetica-Bold", 10)
            label_x = x_offset + 2.8 * inch - shift_left
            value_x = label_x + 0.2 * inch
            c.drawRightString(label_x, y_offset + 1.7 * inch, "Client:")
            c.drawRightString(label_x, y_offset + 1.5 * inch, "Lot:")
            c.drawRightString(label_x, y_offset + 1.3 * inch, "Manufactured:")
            c.drawRightString(label_x, y_offset + 1.1 * inch, "Expiration:")
            c.drawRightString(label_x, y_offset + 0.9 * inch, "When Kept at:")
            c.drawString(value_x, y_offset + 1.7 * inch, cliente_nombre)
            c.drawString(value_x, y_offset + 1.5 * inch, facturacion.lote)
            c.drawString(value_x, y_offset + 1.3 * inch, facturacion.fecha_fabricacion)
            c.drawString(value_x, y_offset + 1.1 * inch, facturacion.fecha_expiracion)
            c.drawString(value_x, y_offset + 0.9 * inch, temperatura)
            c.setFont("Helvetica-Bold", 14)
            c.drawRightString(label_x, y_offset + 0.5 * inch, f"Net Weight:")
            c.drawString(value_x, y_offset + 0.5 * inch, f"{facturacion.peso:.2f}")
            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(x_offset + (etiqueta_ancho / 2), y_offset + 0.15 * inch, producto_nombre)
            etiqueta_contador += 1
            if etiqueta_contador % etiquetas_por_pagina == 0:
                c.showPage()
        if etiqueta_contador % etiquetas_por_pagina != 0:
            c.showPage()
        c.save()
        output.seek(0)
        cliente_filename = cliente_nombre.replace(" ", "_").replace("/", "-")
        return send_file(output, as_attachment=True, download_name=f"etiquetas_{cliente_filename}.pdf", mimetype="application/pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/etiquetas_vencimiento', methods=['GET', 'POST'])
@login_required
def etiquetas_vencimiento():
    if request.method == 'POST':
        producto_id = request.form['producto_id']
        fecha_fabricacion = request.form['fecha_fabricacion']
        lote = request.form['lote']
        cantidad_etiquetas = int(request.form['cantidad_etiquetas'])
        fecha_fabricacion_date = datetime.strptime(fecha_fabricacion, '%Y-%m-%d')
        fecha_expiracion = fecha_fabricacion_date + timedelta(days=365)
        producto = Producto.query.get(producto_id)
        datos_producto = {
            "nombre_producto": producto.nombre,
            "lote": lote,
            "fecha_fabricacion": fecha_fabricacion_date.strftime('%d/%m/%Y'),
            "fecha_expiracion": fecha_expiracion.strftime('%d/%m/%Y'),
            "temperatura": producto.temperatura
        }
        return generar_pdf_etiquetas(datos_producto, cantidad_etiquetas)
    productos = Producto.query.all()
    return render_template('form_generar_etiquetas.html', productos=productos)

def generar_pdf_etiquetas(datos, cantidad):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    etiqueta_ancho = 1.8 * inch
    etiqueta_alto = 0.8 * inch
    margen_horizontal = 0.2 * inch
    margen_vertical = 0.1 * inch
    separacion_grupos = 0.3 * inch
    radio_esquinas = 0.1 * inch
    x_offset_start = (A4[0] - 2 * etiqueta_ancho - margen_horizontal) / 2
    y_offset_start = A4[1] - inch
    etiquetas_por_grupo = 4
    etiquetas_por_pagina = 8
    etiqueta_contador = 0
    while cantidad > 0:
        for fila in range(2):
            y_offset = y_offset_start - fila * (2 * etiqueta_alto + margen_vertical + separacion_grupos if fila == 1 else 0)
            for sub_fila in range(2):
                for sub_columna in range(2):
                    if cantidad <= 0:
                        break
                    etiqueta_x = x_offset_start + sub_columna * (etiqueta_ancho + margen_horizontal)
                    etiqueta_y = y_offset - sub_fila * (etiqueta_alto + margen_vertical)
                    c.roundRect(etiqueta_x, etiqueta_y, etiqueta_ancho, etiqueta_alto, radius=radio_esquinas)
                    dibujar_etiqueta(c, etiqueta_x, etiqueta_y, etiqueta_ancho, etiqueta_alto, datos)
                    etiqueta_contador += 1
                    cantidad -= 1
        if cantidad > 0:
            c.showPage()
    c.save()
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="etiquetas_vencimiento.pdf", mimetype='application/pdf')

def dibujar_etiqueta(c, x_offset, y_offset, etiqueta_ancho, etiqueta_alto, datos):
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x_offset + etiqueta_ancho / 2, y_offset + etiqueta_alto - 0.15 * inch, datos["nombre_producto"])
    c.setFont("Helvetica", 7)
    label_x = x_offset + 0.1 * inch
    value_x = x_offset + etiqueta_ancho - 0.1 * inch
    line_height = 0.14 * inch
    c.drawString(label_x, y_offset + etiqueta_alto - 0.3 * inch, "Lot:")
    c.drawRightString(value_x, y_offset + etiqueta_alto - 0.3 * inch, datos['lote'])
    c.drawString(label_x, y_offset + etiqueta_alto - (0.3 * inch + line_height), "Manufactured:")
    c.drawRightString(value_x, y_offset + etiqueta_alto - (0.3 * inch + line_height), datos['fecha_fabricacion'])
    c.drawString(label_x, y_offset + etiqueta_alto - (0.3 * inch + 2 * line_height), "Expiration:")
    c.drawRightString(value_x, y_offset + etiqueta_alto - (0.3 * inch + 2 * line_height), datos['fecha_expiracion'])
    c.drawString(label_x, y_offset + etiqueta_alto - (0.3 * inch + 3 * line_height), "When Kept at:")
    c.drawRightString(value_x, y_offset + etiqueta_alto - (0.3 * inch + 3 * line_height), datos['temperatura'])


try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    print("No se pudo configurar el locale 'en_US.UTF-8'. Se usará el formato de números por defecto.")

if __name__ == '__main__':
    # Configuración para desarrollo local
    if os.environ.get('FLASK_ENV') == 'development':
        ip_servidor = obtener_ip_servidor()
        print(f"La aplicación está disponible en la IP: {ip_servidor}:{5002}")
        app.run(debug=True, host='0.0.0.0', port=5002)
    else:
        # Configuración para producción (Heroku)
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=False)