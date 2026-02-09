import os
import calendar
import secrets
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, send_file, jsonify, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, and_
from sqlalchemy.orm import joinedload
import io
from flask import make_response
import csv
import tempfile
import logging
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta, date, timezone
from dateutil.relativedelta import relativedelta
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
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
# from models.extensions import db  # Comentado para evitar conflictos
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import datetime, date, timedelta, timezone
from urllib.parse import urlparse, urljoin
from markupsafe import Markup
from utils.label_utils import (
    draw_order_label, draw_expiration_label, get_logo_path,
    create_single_label_pdf, create_letter_page_pdf, get_centered_x,
    LABEL_WIDTH, LABEL_HEIGHT,
    create_a4_page_pdf, get_a4_label_positions, draw_order_label_a4
)
try:
    from flask_wtf import CSRFProtect
except ImportError:  # fallback if not installed; user should install Flask-WTF
    CSRFProtect = None
try:
    from flask_talisman import Talisman
except ImportError:
    Talisman = None

app = Flask(__name__)

# --- SECRET KEY (con fallback seguro) ---
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    import warnings
    warnings.warn(
        "SECRET_KEY not set! Using random key. Sessions will not persist across restarts. "
        "Set SECRET_KEY with: heroku config:set SECRET_KEY=$(python -c \"import secrets; print(secrets.token_hex(32))\")",
        RuntimeWarning
    )
    _secret_key = secrets.token_hex(32)
app.config["SECRET_KEY"] = _secret_key

basedir = os.path.abspath(os.path.dirname(__file__))

uri = os.environ.get("DATABASE_URL", "sqlite:///local.db")
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar SQLAlchemy directamente (sin models.extensions)
db = SQLAlchemy(app)

# Cookies / sesión
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# En Heroku vas por HTTPS (tls=true en logs)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['REMEMBER_COOKIE_SECURE'] = True
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'

# SQLAlchemy ya inicializado arriba

migrate = Migrate(app, db)

# CSRF (Flask-WTF)
if CSRFProtect:
    csrf = CSRFProtect(app)

# Configuración de seguridad con Talisman (HSTS, CSP, etc.)
# Solo activa Talisman en producción (cuando uses HTTPS real)
if Talisman and os.environ.get("FLASK_ENV") == "production":
    # NOTA: 'unsafe-inline' en script-src y style-src es necesario para compatibilidad
    # con librerías legacy. Se recomienda migrar gradualmente a nonces/hashes.
    # Para usar nonces, agregar 'script-src' y 'style-src' a content_security_policy_nonce_in
    talisman_policy = {
        'default-src': ["'self'"],
        'script-src': [
            "'self'",
            "'unsafe-inline'",  # TODO: Migrar a nonces para mayor seguridad
            'https://cdn.jsdelivr.net',
            'https://code.jquery.com',
            'https://cdnjs.cloudflare.com'
        ],
        'style-src': [
            "'self'",
            "'unsafe-inline'",  # TODO: Migrar a nonces para mayor seguridad
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com'
        ],
        'img-src': ["'self'", 'data:', 'blob:'],
        'font-src': ["'self'", 'data:', 'https://cdnjs.cloudflare.com'],
        'connect-src': [
            "'self'",
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com',
            'https://code.jquery.com'
        ],
        'style-src-attr': ["'unsafe-inline'"],  # Necesario para estilos inline en atributos
        'frame-ancestors': ["'none'"],  # Prevenir clickjacking
        'base-uri': ["'self'"],  # Prevenir inyección de base URI
        'form-action': ["'self'"],  # Restringir destinos de formularios
        'object-src': ["'none'"]  # Bloquear plugins (Flash, Java, etc.)
    }
    Talisman(
        app,
        content_security_policy=talisman_policy,
        content_security_policy_nonce_in=[],
        # Configuración HSTS - forzar HTTPS por 1 año
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,  # 1 año
        strict_transport_security_include_subdomains=True,
        strict_transport_security_preload=True,
        # Otras protecciones
        force_https=True,
        session_cookie_secure=True,
        session_cookie_http_only=True,
        # X-Frame-Options (adicional a CSP frame-ancestors)
        frame_options='DENY'
    )


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Credenciales legacy - SOLO usar si se configuran explícitamente las variables de entorno
# Se recomienda migrar a Vendedor y deshabilitar el usuario legacy
DEFAULT_USERNAME = os.environ.get("DEFAULT_USERNAME")
DEFAULT_PASSWORD = os.environ.get("DEFAULT_PASSWORD")
_LEGACY_USER_ENABLED = DEFAULT_USERNAME is not None and DEFAULT_PASSWORD is not None

class DefaultUser(UserMixin):
    def __init__(self, username):
        self.id = username

from utils.filters import kpi_tag
app.jinja_env.filters['kpi_tag'] = kpi_tag

class Vendedor(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Información personal
    nombre_completo = db.Column(db.String(200), nullable=False)
    telefono = db.Column(db.String(20))
    fecha_ingreso = db.Column(db.Date, default=datetime.utcnow)
    
    # Relaciones organizacionales
    rol_id = db.Column(db.Integer, db.ForeignKey('rol.id'), nullable=False)
    territorio_id = db.Column(db.Integer, db.ForeignKey('territorio.id'))
    supervisor_id = db.Column(db.Integer, db.ForeignKey('vendedor.id'))
    
    # Estado y actividad
    activo = db.Column(db.Boolean, default=True)
    ultimo_login = db.Column(db.DateTime)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    supervisor = db.relationship('Vendedor', remote_side=[id], backref='subordinados')
    clientes_asignados = db.relationship('ClienteVendedor', back_populates='vendedor', 
                                       cascade="all, delete-orphan")
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def tiene_permiso(self, permiso_nombre, tipo_acceso='leer'):
        """Verifica si el vendedor tiene un permiso específico"""
        if not self.activo:
            return False
        
        # Definir permisos específicos por rol
        permisos_por_rol = {
                'super_admin': {
                    'productos': ['leer', 'crear', 'editar', 'eliminar'],
                    'clientes': ['leer', 'crear', 'editar', 'eliminar'],
                    'pedidos': ['leer', 'crear', 'editar', 'eliminar'],
                    'vendedores': ['leer', 'crear', 'editar', 'eliminar'],
                    'precios': ['leer', 'crear', 'editar', 'eliminar'],
                    'reportes': ['leer', 'crear', 'editar', 'eliminar'],
                    'importaciones': ['leer', 'crear', 'editar', 'eliminar'],
                    'facturacion': ['leer', 'crear', 'editar', 'eliminar'],
                },
                'supervisor': {
                    'productos': ['leer'],
                    'clientes': ['leer', 'editar'],
                    'pedidos': ['leer', 'crear', 'editar'],
                    'vendedores': ['leer'],
                    'precios': ['leer'],
                    'reportes': ['leer'],
                    'importaciones': [],
                    'facturacion': ['leer'],
                },
                'vendedor': {
                    'productos': ['leer'],
                    'clientes': ['leer', 'editar'],
                    'pedidos': ['leer', 'crear', 'editar'],
                    'vendedores': [],
                    'precios': ['leer'],
                    'reportes': [],
                    'importaciones': [],
                    'facturacion': [],
                }
            }
        
        permisos_rol = permisos_por_rol.get(self.rol.nombre, {})
        permisos_recurso = permisos_rol.get(permiso_nombre, [])
        
        return tipo_acceso in permisos_recurso
    
    def puede_editar_pedido(self, pedido):
        """Verifica si el vendedor puede editar un pedido específico"""
        if self.rol.nombre == 'super_admin':
            return True
        
        # Verificar si el pedido es de un cliente asignado al vendedor
        return self.puede_ver_cliente(pedido.cliente_id)
    
    def puede_crear_pedido_para_cliente(self, cliente_id):
        """Verifica si el vendedor puede crear pedidos para un cliente específico"""
        if self.rol.nombre == 'super_admin':
            return True
        
        return self.puede_ver_cliente(cliente_id)

    
    def puede_ver_cliente(self, cliente_id):
        """Verifica si el vendedor puede ver un cliente específico"""
        if self.rol.nombre == 'super_admin':
            return True
            
        asignacion = ClienteVendedor.query.filter_by(
            cliente_id=cliente_id, 
            vendedor_id=self.id, 
            activo=True
        ).first()
        
        return asignacion is not None
    
    def obtener_clientes_visibles(self):
        """Obtiene todos los clientes que el vendedor puede ver"""
        if self.rol.nombre == 'super_admin':
            return Cliente.query.all()
        
        # Clientes asignados directamente
        clientes_directos = db.session.query(Cliente).join(ClienteVendedor).filter(
            ClienteVendedor.vendedor_id == self.id,
            ClienteVendedor.activo == True
        ).all()
        
        return clientes_directos
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'nombre_completo': self.nombre_completo,
            'telefono': self.telefono,
            'rol': self.rol.nombre if self.rol else None,
            'territorio': self.territorio.nombre if self.territorio else None,
            'activo': self.activo,
            'ultimo_login': self.ultimo_login.isoformat() if self.ultimo_login else None
        }
    
    def __repr__(self):
        return f'<Vendedor {self.username}>'
    
@login_manager.user_loader
def load_user(user_id: str):
    """Reconstruye el usuario desde la cookie de sesión."""
    if not user_id:
        app.logger.warning("[login] user_loader: user_id vacío o None")
        return None

    # 1) Fallback de compatibilidad (usuario por defecto)
    if user_id == DEFAULT_USERNAME:
        app.logger.debug(f"[login] user_loader: DefaultUser={user_id}")
        return DefaultUser(DEFAULT_USERNAME)

    # 2) Intento como Vendedor (id numérico)
    try:
        vid = int(user_id)
    except (TypeError, ValueError):
        app.logger.warning(f"[login] user_loader: user_id no numérico: {user_id!r}")
        return None

    vendedor = db.session.get(Vendedor, vid)
    if vendedor and vendedor.activo:
        app.logger.debug(f"[login] user_loader: Vendedor id={vid} OK")
        return vendedor

    app.logger.info(f"[login] user_loader: Vendedor id={vid} no encontrado o inactivo")
    return None


@app.route('/_csrf_ping', methods=['POST'])
def csrf_ping():
    return jsonify({'ok': True}), 200  # ← Cambiar a esto


def _is_safe_next(target: str) -> bool:
    """Evita open redirects; acepta solo URLs del mismo host."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (test_url.scheme in ("http", "https")) and (ref_url.netloc == test_url.netloc)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Si ya está autenticado, respeta 'next' y si no, al dashboard
    if current_user.is_authenticated:
        next_url = request.args.get('next')
        if not _is_safe_next(next_url):
            next_url = url_for('dashboard')
        return redirect(next_url)

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        remember_me = bool(request.form.get('remember_me'))  # checkbox → bool
        # 'next' puede venir por query o por form (hidden)
        next_url = request.form.get('next') or request.args.get('next')

        # 1) Intentar login como Vendedor
        vendedor = Vendedor.query.filter_by(username=username, activo=True).first()
        if vendedor and vendedor.check_password(password):
            vendedor.ultimo_login = datetime.utcnow()
            db.session.commit()
            login_user(vendedor, remember=remember_me)
            flash(f"¡Bienvenido, {vendedor.nombre_completo}!", "success")
            if not _is_safe_next(next_url):
                next_url = url_for('dashboard')
            return redirect(next_url)

        # 2) Fallback legacy (usuario por defecto) - SOLO si está explícitamente habilitado
        if _LEGACY_USER_ENABLED and username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
            user = DefaultUser(username)
            login_user(user, remember=remember_me)
            app.logger.warning(f"Legacy user login from IP: {request.remote_addr}")
            flash("Inicio de sesión exitoso (modo compatibilidad). Se recomienda migrar a un usuario Vendedor.", "warning")
            if not _is_safe_next(next_url):
                next_url = url_for('dashboard')
            return redirect(next_url)

        # 3) Credenciales inválidas
        flash("Credenciales inválidas", "danger")

    # GET o POST fallido → mostrar login
    # Mantén 'next' en la query para que el form lo preserve
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
    # Permitir específicamente el endpoint de CSRF
    if request.endpoint == 'csrf_ping':
        return
        
    if request.endpoint and not any(request.endpoint.startswith(ep) for ep in allowed_endpoints):
        if not current_user.is_authenticated:
            return redirect(url_for('login', next=request.url))
        
def log_vendedor_action():
    """Registra las acciones de los vendedores para auditoría"""
    if request.method in ['POST', 'PUT', 'DELETE'] and current_user.is_authenticated:
        if isinstance(current_user, Vendedor):
            app.logger.info(f"[AUDIT] Vendedor: {current_user.username} - "
                           f"Acción: {request.method} - URL: {request.url}")


# En lugar de @app.route('/dashboard')
# Reemplazar la función dashboard_vendedor en app.py con esta versión optimizada
@app.context_processor
def inject_permissions():
    """Inyecta funciones de verificación de permisos en los templates"""
    def puede_crear(recurso):
        if not current_user.is_authenticated:
            return False
        if not isinstance(current_user, Vendedor):
            return True  # Usuario legacy tiene todos los permisos
        return current_user.tiene_permiso(recurso, 'crear')
    
    def puede_editar(recurso):
        if not current_user.is_authenticated:
            return False
        if not isinstance(current_user, Vendedor):
            return True
        return current_user.tiene_permiso(recurso, 'editar')
    
    def puede_eliminar(recurso):
        if not current_user.is_authenticated:
            return False
        if not isinstance(current_user, Vendedor):
            return True
        return current_user.tiene_permiso(recurso, 'eliminar')
    
    return dict(
        puede_crear=puede_crear,
        puede_editar=puede_editar,
        puede_eliminar=puede_eliminar
    )
@app.route('/dashboard_vendedor')
@login_required
def dashboard_vendedor():
    """Dashboard optimizado con funcionalidades específicas para administradores y vendedores"""
    
    # Verificar si es vendedor del nuevo sistema
    if not isinstance(current_user, Vendedor):
        # Usuario del sistema anterior - redirigir a index
        return redirect(url_for('index'))
    
    try:
        # Fechas para análisis
        hoy = datetime.now().date()
        inicio_mes = hoy.replace(day=1)
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        hace_30_dias = hoy - timedelta(days=30)
        
        # Variables base
        context = {
            'vendedor': current_user,
            'fecha_actual': hoy,
            'fecha_sistema': 'Enero 2025',
            # Valores por defecto para evitar Undefined en templates
            'tendencia_semanal': [],
            'estados_pedidos': [],
            'kpi_weekly': []
        }
        
        # ===== MÉTRICAS ESPECÍFICAS PARA ADMINISTRADOR =====
        if current_user.rol.nombre == 'super_admin':
            
            # 1. MÉTRICAS GENERALES DEL SISTEMA
            total_vendedores = Vendedor.query.filter_by(activo=True).count()
            total_clientes = Cliente.query.count()
            total_productos = Producto.query.count()
            
            # 2. MÉTRICAS DE VENTAS GLOBALES (OPTIMIZADO)
            # Consulta optimizada para ventas del mes usando agregación SQL
            ventas_totales = db.session.query(
                func.coalesce(func.sum(DetallePedido.subtotal), 0)
            ).join(Pedido).filter(
                Pedido.fecha_pedido >= inicio_mes
            ).scalar()
            
            # Consulta optimizada para ventas del día usando agregación SQL
            ventas_hoy = db.session.query(
                func.coalesce(func.sum(DetallePedido.subtotal), 0)
            ).join(Pedido).filter(
                Pedido.fecha_pedido >= hoy,
                Pedido.fecha_pedido < hoy + timedelta(days=1)
            ).scalar()
            
            # Conteo de pedidos optimizado
            pedidos_mes_count = Pedido.query.filter(Pedido.fecha_pedido >= inicio_mes).count()
            pedidos_hoy_count = Pedido.query.filter(
                Pedido.fecha_pedido >= hoy,
                Pedido.fecha_pedido < hoy + timedelta(days=1)
            ).count()
            
            # 3. MÉTRICAS DE EFICIENCIA
            pedidos_pendientes = Pedido.query.filter_by(estado='pendiente').count()
            pedidos_facturados = Pedido.query.filter_by(estado='facturado').count()
            pedidos_totales = Pedido.query.count()
            
            # Calcular eficiencia del sistema (% de pedidos completados)
            if pedidos_totales > 0:
                eficiencia_sistema = (pedidos_facturados / pedidos_totales) * 100
            else:
                eficiencia_sistema = 95.8  # Valor por defecto
            
            # 4. ANÁLISIS DE TENDENCIAS
            # Pedidos por vendedor (top 5)
            vendedores_performance = db.session.query(
                Vendedor.nombre_completo,
                func.count(Pedido.id).label('total_pedidos'),
                func.coalesce(func.sum(DetallePedido.subtotal), 0).label('ventas_total')
            ).outerjoin(
                ClienteVendedor, Vendedor.id == ClienteVendedor.vendedor_id
            ).outerjoin(
                Pedido, ClienteVendedor.cliente_id == Pedido.cliente_id
            ).outerjoin(
                DetallePedido, Pedido.id == DetallePedido.pedido_id
            ).filter(
                Pedido.fecha_pedido >= hace_30_dias
            ).group_by(
                Vendedor.id, Vendedor.nombre_completo
            ).order_by(
                func.coalesce(func.sum(DetallePedido.subtotal), 0).desc()
            ).limit(5).all()
            
            # 5. ALERTAS DEL SISTEMA
            alertas_sistema = []
            
            # Alerta por pedidos pendientes
            if pedidos_pendientes > 10:
                alertas_sistema.append({
                    'tipo': 'warning',
                    'titulo': 'Alto volumen de pedidos pendientes',
                    'mensaje': f'{pedidos_pendientes} pedidos requieren atención',
                    'accion': '/pedidos?estado=pendiente'
                })
            
            # Alerta por productos sin precio
            productos_sin_precio = Producto.query.outerjoin(PrecioProducto).filter(
                PrecioProducto.id.is_(None)
            ).count()
            
            if productos_sin_precio > 0:
                alertas_sistema.append({
                    'tipo': 'info',
                    'titulo': 'Productos sin precios configurados',
                    'mensaje': f'{productos_sin_precio} productos requieren configuración de precios',
                    'accion': '/precios'
                })
            
            # 6. MÉTRICAS FINANCIERAS ADICIONALES (OPTIMIZADO)
            # Facturación del mes anterior para comparación
            inicio_mes_anterior = (inicio_mes - timedelta(days=1)).replace(day=1)
            fin_mes_anterior = inicio_mes - timedelta(days=1)
            
            # Consulta optimizada para ventas del mes anterior
            ventas_mes_anterior = db.session.query(
                func.coalesce(func.sum(DetallePedido.subtotal), 0)
            ).join(Pedido).filter(
                Pedido.fecha_pedido >= inicio_mes_anterior,
                Pedido.fecha_pedido <= fin_mes_anterior
            ).scalar()
            
            # Calcular crecimiento
            if ventas_mes_anterior > 0:
                crecimiento_ventas = ((ventas_totales - ventas_mes_anterior) / ventas_mes_anterior) * 100
            else:
                crecimiento_ventas = 0
            
            # Actualizar contexto para administrador
            context.update({
                'total_vendedores': total_vendedores,
                'total_clientes': total_clientes,
                'total_productos': total_productos,
                'ventas_totales': ventas_totales,
                'ventas_hoy': ventas_hoy,
                'total_pedidos': pedidos_pendientes,
                'pedidos_hoy': pedidos_hoy_count,
                'eficiencia_sistema': round(eficiencia_sistema, 1),
                'crecimiento_ventas': round(crecimiento_ventas, 1),
                'vendedores_performance': vendedores_performance,
                'alertas_sistema': alertas_sistema,
                'pedidos_facturados': pedidos_facturados,
                'pedidos_totales': pedidos_totales
            })
            
        else:
            # ===== MÉTRICAS ESPECÍFICAS PARA VENDEDOR REGULAR =====
            
            # 1. Obtener clientes asignados al vendedor
            clientes_vendedor = current_user.obtener_clientes_visibles()
            clientes_ids = [c.id for c in clientes_vendedor]
            
            # 2. Métricas del vendedor (OPTIMIZADO)
            if clientes_ids:
                # Ventas del día para el vendedor usando agregación SQL
                ventas_vendedor_hoy = db.session.query(
                    func.coalesce(func.sum(DetallePedido.subtotal), 0)
                ).join(Pedido).filter(
                    Pedido.cliente_id.in_(clientes_ids),
                    Pedido.fecha_pedido >= hoy,
                    Pedido.fecha_pedido < hoy + timedelta(days=1)
                ).scalar()
                
                # Ventas del mes para el vendedor usando agregación SQL
                ventas_vendedor_mes = db.session.query(
                    func.coalesce(func.sum(DetallePedido.subtotal), 0)
                ).join(Pedido).filter(
                    Pedido.cliente_id.in_(clientes_ids),
                    Pedido.fecha_pedido >= inicio_mes
                ).scalar()
                
                # Conteo de pedidos del día
                pedidos_hoy_count = Pedido.query.filter(
                    Pedido.cliente_id.in_(clientes_ids),
                    Pedido.fecha_pedido >= hoy,
                    Pedido.fecha_pedido < hoy + timedelta(days=1)
                ).count()
            else:
                ventas_vendedor_hoy = 0
                ventas_vendedor_mes = 0
                pedidos_hoy_count = 0
            
            # 4. Estadísticas del vendedor
            pedidos_pendientes_vendedor = 0
            if clientes_ids:
                pedidos_pendientes_vendedor = Pedido.query.filter(
                    Pedido.cliente_id.in_(clientes_ids),
                    Pedido.estado == 'pendiente'
                ).count()
            
            # Actualizar contexto para vendedor
            context.update({
                'clientes_asignados': len(clientes_vendedor),
                'pedidos_hoy': pedidos_hoy_count,
                'ventas_hoy': ventas_vendedor_hoy,
                'ventas_mes': ventas_vendedor_mes,
                'pedidos_pendientes': pedidos_pendientes_vendedor,
                'total_pedidos': pedidos_pendientes_vendedor
            })
        
        # Renderizar template apropiado
        return render_template('dashboard_vendedor.html', **context)
        
    except Exception as e:
        app.logger.error(f"Error en dashboard_vendedor: {e}", exc_info=True)
        
        flash('Error al cargar el dashboard. Contacte al administrador.', 'error')
        
        # Contexto mínimo en caso de error
        context = {
            'vendedor': current_user,
            'fecha_actual': datetime.now().date(),
            'total_vendedores': 0,
            'ventas_totales': 0,
            'total_pedidos': 0,
            'eficiencia_sistema': 0,
            'pedidos_hoy': 0,
            'ventas_hoy': 0
        }
        
        return render_template('dashboard_vendedor.html', **context)

# Función auxiliar para obtener métricas del sistema (opcional)
def obtener_metricas_sistema():
    """Función auxiliar para obtener métricas del sistema de forma centralizada"""
    try:
        hoy = datetime.now().date()
        inicio_mes = hoy.replace(day=1)
        
        metricas = {
            'total_vendedores': Vendedor.query.filter_by(activo=True).count(),
            'total_clientes': Cliente.query.count(),
            'total_productos': Producto.query.count(),
            'pedidos_pendientes': Pedido.query.filter_by(estado='pendiente').count(),
            'pedidos_facturados': Pedido.query.filter_by(estado='facturado').count(),
        }
        
        # Calcular ventas del mes
        pedidos_mes = Pedido.query.filter(Pedido.fecha_pedido >= inicio_mes).all()
        ventas_mes = 0
        for pedido in pedidos_mes:
            for detalle in pedido.detalles:
                if detalle.subtotal:
                    ventas_mes += float(detalle.subtotal)
        
        metricas['ventas_mes'] = ventas_mes
        metricas['total_pedidos'] = Pedido.query.count()
        
        if metricas['total_pedidos'] > 0:
            metricas['eficiencia'] = (metricas['pedidos_facturados'] / metricas['total_pedidos']) * 100
        else:
            metricas['eficiencia'] = 95.8
        
        return metricas
        
    except Exception as e:
        app.logger.error(f"Error obteniendo métricas del sistema: {e}")
        return {
            'total_vendedores': 0,
            'total_clientes': 0,
            'total_productos': 0,
            'pedidos_pendientes': 0,
            'pedidos_facturados': 0,
            'ventas_mes': 0,
            'total_pedidos': 0,
            'eficiencia': 0
        }

# Ruta adicional para API de métricas (útil para actualizaciones en tiempo real)
@app.route('/api/dashboard/metricas')
@login_required
def api_dashboard_metricas():
    """API para obtener métricas del dashboard en tiempo real"""
    
    if not isinstance(current_user, Vendedor):
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        if current_user.rol.nombre == 'super_admin':
            metricas = obtener_metricas_sistema()
        else:
            # Métricas específicas del vendedor
            clientes_vendedor = current_user.obtener_clientes_visibles()
            clientes_ids = [c.id for c in clientes_vendedor]
            
            hoy = datetime.now().date()
            pedidos_hoy = 0
            ventas_hoy = 0
            
            if clientes_ids:
                pedidos_vendedor_hoy = Pedido.query.filter(
                    Pedido.cliente_id.in_(clientes_ids),
                    Pedido.fecha_pedido >= hoy
                ).all()
                
                pedidos_hoy = len(pedidos_vendedor_hoy)
                for pedido in pedidos_vendedor_hoy:
                    for detalle in pedido.detalles:
                        if detalle.subtotal:
                            ventas_hoy += float(detalle.subtotal)
            
            metricas = {
                'clientes_asignados': len(clientes_vendedor),
                'pedidos_hoy': pedidos_hoy,
                'ventas_hoy': ventas_hoy,
                'pedidos_pendientes': Pedido.query.filter(
                    Pedido.cliente_id.in_(clientes_ids),
                    Pedido.estado == 'pendiente'
                ).count() if clientes_ids else 0
            }
        
        return jsonify(metricas)
        
    except Exception as e:
        app.logger.error(f"Error en API de métricas: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

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
    se_pesa = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'temperatura': self.temperatura,
            'qbo_id': self.qbo_id,
            'tax_rate': self.tax_rate,
            'se_pesa': self.se_pesa
        }

class Cliente(db.Model):
    __tablename__ = 'cliente'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    territorio_id = db.Column(db.Integer,
                              db.ForeignKey('territorio.id'))      
    territorio  = db.relationship('Territorio', backref='clientes') 
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
    fecha_facturacion = db.Column(db.DateTime, nullable=True)
    estado = db.Column(db.String(30), default="pendiente", nullable=False)
    notas = db.Column(db.Text, nullable=True)
    invoice_id_qbo = db.Column(db.String(100), nullable=True)
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
    es_linea_pedido = db.Column(db.Boolean, default=True, nullable=False)


    def __repr__(self):
        return f'<DetallePedido {self.id} - Producto {self.producto.nombre} - Peso {self.peso}>'

############################################
# MODELOS MULTI-VENDEDOR (AGREGAR AL FINAL DE APP.PY)
############################################

class Rol(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    nivel_jerarquia = db.Column(db.Integer, default=0)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    vendedores = db.relationship('Vendedor', backref='rol', lazy=True)
    permisos = db.relationship('RolPermiso', back_populates='rol', cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Rol {self.nombre}>'

class Permiso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    categoria = db.Column(db.String(50))
    recurso = db.Column(db.String(100))
    
    def __repr__(self):
        return f'<Permiso {self.nombre}>'

class RolPermiso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rol_id = db.Column(db.Integer, db.ForeignKey('rol.id'), nullable=False)
    permiso_id = db.Column(db.Integer, db.ForeignKey('permiso.id'), nullable=False)
    
    # Tipos de acceso CRUD
    puede_leer = db.Column(db.Boolean, default=True)
    puede_crear = db.Column(db.Boolean, default=False)
    puede_editar = db.Column(db.Boolean, default=False)
    puede_eliminar = db.Column(db.Boolean, default=False)
    
    # Relaciones
    rol = db.relationship('Rol', back_populates='permisos')
    permiso = db.relationship('Permiso')
    
    __table_args__ = (db.UniqueConstraint('rol_id', 'permiso_id', name='unique_rol_permiso'),)

class Territorio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    tipo = db.Column(db.String(50))
    coordenadas = db.Column(db.JSON)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    vendedores = db.relationship('Vendedor', backref='territorio', lazy=True)
    
    def __repr__(self):
        return f'<Territorio {self.nombre}>'



class ClienteVendedor(db.Model):
    __tablename__ = 'cliente_vendedor'        #  ← bueno especificarlo

    id          = db.Column(db.Integer, primary_key=True)
    cliente_id  = db.Column(db.Integer, db.ForeignKey('cliente.id'),  nullable=False)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=False)

    # Config asignación
    tipo_asignacion     = db.Column(db.String(50), default='principal')
    fecha_inicio        = db.Column(db.Date, default=datetime.utcnow)
    fecha_fin           = db.Column(db.Date)
    activo              = db.Column(db.Boolean, default=True)
    porcentaje_comision = db.Column(db.Float, default=100.0)

    # Relaciones
    cliente  = db.relationship('Cliente',
                               backref='vendedores_asignados')
    vendedor = db.relationship('Vendedor',
                               back_populates='clientes_asignados')

    # ───────── helpers ─────────
    @classmethod
    def asignar(cls, cliente_id: int, vendedor_id: int):
        """Asigna (o reactiva) un cliente a un vendedor."""
        asign = cls.query.filter_by(cliente_id=cliente_id,
                                    vendedor_id=vendedor_id).first()
        if asign:
            asign.activo       = True
            asign.fecha_inicio = date.today()
        else:
            asign = cls(cliente_id=cliente_id,
                        vendedor_id=vendedor_id,
                        activo=True,
                        fecha_inicio=date.today())
            db.session.add(asign)
        db.session.commit()
        return asign

    @classmethod
    def desasignar(cls, asign_id: int):
        asign = cls.query.get_or_404(asign_id)
        asign.activo    = False
        asign.fecha_fin = date.today()
        db.session.commit()
        return asign

    def __repr__(self):
        return f'<ClienteVendedor {self.cliente_id}-{self.vendedor_id}>'


############################################
# DECORADORES Y FUNCIONES DE SEGURIDAD
############################################

# 2. DECORADOR MEJORADO PARA VERIFICAR PERMISOS
def requiere_permiso_recurso(recurso, tipo_acceso='leer'):
    """Decorador mejorado para verificar permisos sobre recursos específicos"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Debes iniciar sesión para acceder a esta página', 'warning')
                return redirect(url_for('login'))
                
            # Si es el usuario legacy, permitir acceso
            if not isinstance(current_user, Vendedor):
                return f(*args, **kwargs)
                
            # Verificar permiso sobre el recurso
            if not current_user.tiene_permiso(recurso, tipo_acceso):
                flash(f'No tienes permisos para {tipo_acceso} {recurso}', 'error')
                return redirect(url_for('index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def requiere_rol(roles_permitidos):
    """Decorador para verificar roles específicos"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            
            if not isinstance(current_user, Vendedor):
                # Si es el usuario por defecto del sistema anterior
                return f(*args, **kwargs)
            
            if current_user.rol.nombre not in roles_permitidos:
                flash("No tienes autorización para acceder a esta función", "error")
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def obtener_vendedor_actual():
    """Obtiene el vendedor actual o None si es usuario legacy"""
    if isinstance(current_user, Vendedor):
        return current_user
    return None
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
    # 1. Verificar precio específico cliente-producto
    precio_especifico = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id,
        producto_id=producto_id,
        activo=True
    ).first()

    if precio_especifico:
        if tipo_precio == 'base':
            precio = precio_especifico.precio_base
        elif tipo_precio == 'jomar':
            precio = precio_especifico.precio_jomar
        elif tipo_precio == 'retail':
            precio = precio_especifico.precio_retail
        return precio

    # 2. Verificar lista de precios del cliente
    cliente_lista = ClienteListaPrecio.query.filter_by(
        cliente_id=cliente_id,
        activa=True
    ).first()

    if cliente_lista:
        precio_lista = PrecioProducto.query.filter_by(
            lista_precio_id=cliente_lista.lista_precio_id,
            producto_id=producto_id,
            activo=True
        ).first()

        if precio_lista:
            if tipo_precio == 'base':
                precio = precio_lista.precio_base
            elif tipo_precio == 'jomar':
                precio = precio_lista.precio_jomar
            elif tipo_precio == 'retail':
                precio = precio_lista.precio_retail
            return precio

    # 3. Usar lista de precios por defecto
    lista_default = ListaPrecio.query.filter_by(es_default=True, activa=True).first()
    if lista_default:
        precio_default = PrecioProducto.query.filter_by(
            lista_precio_id=lista_default.id,
            producto_id=producto_id,
            activo=True
        ).first()

        if precio_default:
            if tipo_precio == 'base':
                precio = precio_default.precio_base
            elif tipo_precio == 'jomar':
                precio = precio_default.precio_jomar
            elif tipo_precio == 'retail':
                precio = precio_default.precio_retail
            return precio

    return None

def obtener_precio_default_producto(producto_id, tipo_precio='base'):
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
        # Story 3-0: filtrar líneas según tipo de producto
        # se_pesa=True (manufactura): solo líneas de preparación (es_linea_pedido=False)
        # se_pesa=False (importación): solo línea original del pedido (es_linea_pedido=True)
        if d.producto.se_pesa and d.es_linea_pedido:
            continue
        if not d.producto.se_pesa and not d.es_linea_pedido:
            continue

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
            "tax_rate"      : d.producto.tax_rate
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


@app.route('/home')
@login_required
def home():
    """Ruta de inicio unificada tras login.
    Ahora redirige a '/'.
    """
    return redirect(url_for('index'))


@app.route('/admin/vendedores')
@login_required
@requiere_rol(['super_admin'])
def gestionar_vendedores():
    vendedores = Vendedor.query.all()
    roles = Rol.query.filter_by(activo=True).all()
    territorios = Territorio.query.filter_by(activo=True).all()
    
    return render_template('admin/vendedores.html', 
                         vendedores=vendedores, 
                         roles=roles, 
                         territorios=territorios)

@app.route('/admin/vendedores/nuevo', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def crear_vendedor():
    """Crear nuevo vendedor - maneja GET (mostrar formulario) y POST (procesar datos)"""
    
    # ====== MANEJAR GET REQUEST (mostrar formulario) ======
    if request.method == 'GET':
        try:
            # Obtener datos necesarios para el formulario
            roles = Rol.query.filter_by(activo=True).all()
            territorios = Territorio.query.filter_by(activo=True).all()
            vendedores = Vendedor.query.filter_by(activo=True).all()  # Para supervisor dropdown
            
            # Si tienes un template específico, úsalo:
            # return render_template('admin/vendedor_form.html', 
            #                      roles=roles, 
            #                      territorios=territorios,
            #                      vendedores=vendedores)
            
            # OPCIÓN 1: Redirigir a gestión con mensaje informativo
            flash('Utilice el formulario en la página de gestión de vendedores para crear un nuevo vendedor', 'info')
            return redirect(url_for('gestionar_vendedores'))
            
            # OPCIÓN 2: Si quieres mostrar un formulario simple aquí
            # return f"""
            # <h1>Crear Nuevo Vendedor</h1>
            # <form method="POST">
            #     <p>Username: <input type="text" name="username" required></p>
            #     <p>Email: <input type="email" name="email" required></p>
            #     <p>Nombre: <input type="text" name="nombre_completo" required></p>
            #     <p>Teléfono: <input type="text" name="telefono"></p>
            #     <p>Password: <input type="password" name="password" required></p>
            #     <p>Rol: <select name="rol_id" required>
            #         {''.join([f'<option value="{r.id}">{r.nombre}</option>' for r in roles])}
            #     </select></p>
            #     <p>Territorio: <select name="territorio_id">
            #         <option value="">Sin territorio</option>
            #         {''.join([f'<option value="{t.id}">{t.nombre}</option>' for t in territorios])}
            #     </select></p>
            #     <p><button type="submit">Crear Vendedor</button></p>
            # </form>
            # <a href="{url_for('gestionar_vendedores')}">← Volver</a>
            # """
            
        except Exception as e:
            app.logger.error(f'Error al cargar el formulario: {e}')
            flash('Error al cargar el formulario. Intente de nuevo.', 'error')
            return redirect(url_for('gestionar_vendedores'))
    
    # ====== MANEJAR POST REQUEST (procesar formulario) ======
    elif request.method == 'POST':
        try:
            # Obtener datos del formulario
            username = request.form.get('username')
            email = request.form.get('email')
            nombre_completo = request.form.get('nombre_completo')
            telefono = request.form.get('telefono')
            password = request.form.get('password')
            rol_id = request.form.get('rol_id')
            territorio_id = request.form.get('territorio_id')
            
            # Validaciones básicas
            if not username or not email or not nombre_completo or not password or not rol_id:
                flash("Todos los campos obligatorios deben ser completados", "error")
                return redirect(url_for('crear_vendedor'))
            
            # Verificar que el username no exista
            vendedor_existente = Vendedor.query.filter_by(username=username).first()
            if vendedor_existente:
                flash("El nombre de usuario ya existe", "error")
                return redirect(url_for('crear_vendedor'))
            
            # Verificar que el email no exista
            email_existente = Vendedor.query.filter_by(email=email).first()
            if email_existente:
                flash("El email ya está registrado", "error")
                return redirect(url_for('crear_vendedor'))
            
            # Verificar que el rol existe
            rol_valido = Rol.query.get(rol_id)
            if not rol_valido:
                flash("El rol seleccionado no es válido", "error")
                return redirect(url_for('crear_vendedor'))
            
            # Verificar territorio si se proporcionó
            if territorio_id:
                territorio_valido = Territorio.query.get(territorio_id)
                if not territorio_valido:
                    flash("El territorio seleccionado no es válido", "error")
                    return redirect(url_for('crear_vendedor'))
            
            # Crear nuevo vendedor
            nuevo_vendedor = Vendedor(
                username=username,
                email=email,
                nombre_completo=nombre_completo,
                telefono=telefono,
                rol_id=int(rol_id),
                territorio_id=int(territorio_id) if territorio_id else None,
                fecha_ingreso=date.today(),
                activo=True
            )
            
            # Establecer password hasheado
            nuevo_vendedor.set_password(password)
            
            # Guardar en base de datos
            db.session.add(nuevo_vendedor)
            db.session.commit()
            
            flash(f'Vendedor {nombre_completo} creado exitosamente', 'success')
            return redirect(url_for('gestionar_vendedores'))
            
        except ValueError as ve:
            db.session.rollback()
            app.logger.warning(f'Error de validación al crear vendedor: {ve}')
            flash('Error en los datos proporcionados. Verifique los campos.', 'error')
            return redirect(url_for('crear_vendedor'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error al crear vendedor: {e}')
            flash('Error al crear vendedor. Intente de nuevo.', 'error')
            return redirect(url_for('crear_vendedor'))
    
    # ====== FALLBACK (no debería llegar aquí) ======
    else:
        flash("Método no permitido", "error")
        return redirect(url_for('gestionar_vendedores'))

@app.route('/admin/asignar_cliente', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def asignar_cliente():
    
    # Obtener vendedores activos
    vendedores = (Vendedor.query
                  .filter_by(activo=True)
                  .order_by(Vendedor.nombre_completo)
                  .all())
    
    # Obtener clientes SIN ASIGNAR
    clientes_sin_asignar = db.session.query(Cliente).outerjoin(
        ClienteVendedor,
        db.and_(
            Cliente.id == ClienteVendedor.cliente_id,
            ClienteVendedor.activo == True
        )
    ).filter(
        ClienteVendedor.id.is_(None)
    ).order_by(Cliente.nombre).all()

    if request.method == 'POST':
        try:
            ClienteVendedor.asignar(
                cliente_id=int(request.form['cliente_id']),
                vendedor_id=int(request.form['vendedor_id'])
            )
            flash('Cliente asignado correctamente', 'success')
            return redirect(url_for('asignar_cliente'))
        except Exception as e:
            app.logger.error(f'Error al asignar cliente: {e}')
            flash('Error al asignar cliente. Intente de nuevo.', 'error')
    
    return render_template('admin/clientes_vendedores.html',
                           clientes_sin_asignar=clientes_sin_asignar,  # ← Variable correcta
                           vendedores=vendedores)



@app.route('/api/clientes/sin-asignar')
@login_required
@requiere_rol(['super_admin'])
def api_clientes_sin_asignar():
    """
    Devuelve los clientes que no tienen asignación activa
    """
    try:
        # Obtener todos los clientes
        todos_los_clientes = Cliente.query.all()

        # Obtener IDs de clientes que SÍ tienen asignación activa
        clientes_asignados_ids = db.session.query(ClienteVendedor.cliente_id).filter_by(activo=True).distinct().all()
        clientes_asignados_ids = [row[0] for row in clientes_asignados_ids]

        # Filtrar clientes que NO están en la lista de asignados
        clientes_sin_asignar = [c for c in todos_los_clientes if c.id not in clientes_asignados_ids]

        resultado = [{'id': c.id, 'nombre': c.nombre} for c in clientes_sin_asignar]
        return jsonify(resultado)

    except Exception as e:
        app.logger.error(f"Error en api_clientes_sin_asignar: {e}", exc_info=True)
        return jsonify([]), 200  



# ---------- Asignar ----------
@app.route('/api/asignaciones', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def api_asignar_cliente():
    data = request.get_json(force=True)
    try:
        asign = ClienteVendedor.asignar(
            cliente_id  = int(data['cliente_id']),
            vendedor_id = int(data['vendedor_id'])
        )
        return jsonify({'success': True, 'asign_id': asign.id})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error en operación: {e}')
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 400


# ---------- Desasignar ----------
@app.route('/api/asignaciones/<int:asign_id>', methods=['DELETE'])
@login_required
@requiere_rol(['super_admin'])
def api_desasignar_cliente(asign_id):
    try:
        ClienteVendedor.desasignar(asign_id)
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error en operación: {e}')
        return jsonify({'success': False, 'error': 'Error interno del servidor'}), 400

@app.route('/api/vendedores/<int:v_id>/clientes')
@login_required
@requiere_rol(['super_admin'])
def api_clientes_del_vendedor(v_id):
    """
    Devuelve (JSON) los clientes activos asignados a un vendedor.
    """
    try:
        # Verificar que el vendedor existe
        vendedor = Vendedor.query.get(v_id)
        if not vendedor:
            return jsonify({'error': 'Vendedor no encontrado'}), 404

        # Obtener asignaciones activas del vendedor con información del cliente
        asignaciones = db.session.query(
            ClienteVendedor, Cliente
        ).join(
            Cliente, ClienteVendedor.cliente_id == Cliente.id
        ).filter(
            ClienteVendedor.vendedor_id == v_id,
            ClienteVendedor.activo == True
        ).order_by(Cliente.nombre).all()

        # Formatear respuesta - CORREGIDO: usar fecha_inicio en lugar de fecha_asignacion
        resultado = []
        for asignacion, cliente in asignaciones:
            resultado.append({
                'id': cliente.id,
                'nombre': cliente.nombre,
                'asign_id': asignacion.id,
                'fecha_asignacion': asignacion.fecha_inicio.strftime('%Y-%m-%d') if asignacion.fecha_inicio else None
            })

        return jsonify(resultado)

    except Exception as e:
        app.logger.error(f"Error en api_clientes_del_vendedor: {e}", exc_info=True)
        return jsonify({'error': 'Error interno del servidor'}), 500

        # ===== RUTAS ADMINISTRATIVAS ADICIONALES =====

@app.route('/admin/reportes')
@login_required
@requiere_rol(['super_admin'])
def admin_reportes():
    """Página de reportes avanzados para administradores"""
    try:
        # Obtener datos para reportes
        hoy = datetime.now().date()
        inicio_mes = hoy.replace(day=1)
        hace_30_dias = hoy - timedelta(days=30)
        
        # Reporte de ventas por vendedor
        ventas_por_vendedor = db.session.query(
            Vendedor.nombre_completo,
            Vendedor.username,
            func.count(Pedido.id).label('total_pedidos'),
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('ventas_total')
        ).outerjoin(
            ClienteVendedor, Vendedor.id == ClienteVendedor.vendedor_id
        ).outerjoin(
            Pedido, ClienteVendedor.cliente_id == Pedido.cliente_id
        ).outerjoin(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).filter(
            Vendedor.activo == True,
            Pedido.fecha_pedido >= hace_30_dias
        ).group_by(
            Vendedor.id, Vendedor.nombre_completo, Vendedor.username
        ).order_by(
            func.coalesce(func.sum(DetallePedido.subtotal), 0).desc()
        ).all()
        
        # Reporte de productos más vendidos
        productos_mas_vendidos = db.session.query(
            Producto.nombre,
            func.sum(DetallePedido.cajas).label('total_cajas'),
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('ingresos_total')
        ).join(
            DetallePedido, Producto.id == DetallePedido.producto_id
        ).join(
            Pedido, DetallePedido.pedido_id == Pedido.id
        ).filter(
            Pedido.fecha_pedido >= hace_30_dias
        ).group_by(
            Producto.id, Producto.nombre
        ).order_by(
            func.sum(DetallePedido.cajas).desc()
        ).limit(10).all()
        
        # Reporte de clientes más activos
        clientes_mas_activos = db.session.query(
            Cliente.nombre,
            func.count(Pedido.id).label('total_pedidos'),
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('compras_total')
        ).join(
            Pedido, Cliente.id == Pedido.cliente_id
        ).join(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).filter(
            Pedido.fecha_pedido >= hace_30_dias
        ).group_by(
            Cliente.id, Cliente.nombre
        ).order_by(
            func.coalesce(func.sum(DetallePedido.subtotal), 0).desc()
        ).limit(10).all()
        
        return render_template('admin/reportes.html',
                             ventas_por_vendedor=ventas_por_vendedor,
                             productos_mas_vendidos=productos_mas_vendidos,
                             clientes_mas_activos=clientes_mas_activos,
                             fecha_inicio=hace_30_dias,
                             fecha_fin=hoy)
        
    except Exception as e:
        app.logger.error(f"Error en admin_reportes: {e}")
        flash('Error al cargar los reportes', 'error')
        return redirect(url_for('index'))

@app.route('/admin/analytics')
@login_required
@requiere_rol(['super_admin'])
def admin_analytics():
    """Página de analytics avanzados"""
    try:
        # Datos para gráficos y análisis
        hoy = datetime.now().date()
        hace_90_dias = hoy - timedelta(days=90)
        
        # Tendencia de ventas últimos 90 días (por semanas)
        tendencia_ventas = []
        for i in range(12):  # 12 semanas
            inicio_semana = hace_90_dias + timedelta(weeks=i)
            fin_semana = inicio_semana + timedelta(days=6)
            
            ventas_semana = db.session.query(
                func.coalesce(func.sum(DetallePedido.subtotal), 0)
            ).join(
                Pedido, DetallePedido.pedido_id == Pedido.id
            ).filter(
                Pedido.fecha_pedido >= inicio_semana,
                Pedido.fecha_pedido <= fin_semana
            ).scalar()
            
            tendencia_ventas.append({
                'semana': inicio_semana.strftime('%d/%m'),
                'ventas': float(ventas_semana or 0)
            })
        
        # Distribución de pedidos por estado
        estados_pedidos = db.session.query(
            Pedido.estado,
            func.count(Pedido.id).label('cantidad')
        ).group_by(Pedido.estado).all()
        
        # Eficiencia por vendedor
        eficiencia_vendedores = db.session.query(
            Vendedor.nombre_completo,
            func.count(Pedido.id).label('pedidos_totales'),
            func.sum(
                db.case([(Pedido.estado == 'facturado', 1)], else_=0)
            ).label('pedidos_facturados')
        ).outerjoin(
            ClienteVendedor, Vendedor.id == ClienteVendedor.vendedor_id
        ).outerjoin(
            Pedido, ClienteVendedor.cliente_id == Pedido.cliente_id
        ).filter(
            Vendedor.activo == True
        ).group_by(
            Vendedor.id, Vendedor.nombre_completo
        ).having(
            func.count(Pedido.id) > 0
        ).all()
        
        return render_template('admin/analytics.html',
                             tendencia_ventas=tendencia_ventas,
                             estados_pedidos=estados_pedidos,
                             eficiencia_vendedores=eficiencia_vendedores)
        
    except Exception as e:
        app.logger.error(f"Error en admin_analytics: {e}")
        flash('Error al cargar analytics', 'error')
        return redirect(url_for('index'))

@app.route('/admin/configuracion')
@login_required
@requiere_rol(['super_admin'])
def admin_configuracion():
    """Página de configuración del sistema"""
    return render_template('admin/configuracion.html')

@app.route('/admin/clientes-vendedores')
@login_required
@requiere_rol(['super_admin'])
def admin_clientes_vendedores():
    """Gestión de asignaciones cliente-vendedor"""
    try:
        # Obtener todas las asignaciones activas
        asignaciones = db.session.query(
            ClienteVendedor,
            Cliente.nombre.label('cliente_nombre'),
            Vendedor.nombre_completo.label('vendedor_nombre')
        ).join(
            Cliente, ClienteVendedor.cliente_id == Cliente.id
        ).join(
            Vendedor, ClienteVendedor.vendedor_id == Vendedor.id
        ).filter(
            ClienteVendedor.activo == True
        ).all()
        
        # Clientes sin asignar
        clientes_sin_asignar = db.session.query(Cliente).outerjoin(
            ClienteVendedor,
            db.and_(
                Cliente.id == ClienteVendedor.cliente_id,
                ClienteVendedor.activo == True
            )
        ).filter(
            ClienteVendedor.id.is_(None)
        ).all()
        
        # Vendedores activos
        vendedores = Vendedor.query.filter_by(activo=True).all()
        
        return render_template('admin/clientes_vendedores.html',
                             asignaciones=asignaciones,
                             clientes_sin_asignar=clientes_sin_asignar,
                             vendedores=vendedores)
        
    except Exception as e:
        app.logger.error(f"Error en admin_clientes_vendedores: {e}")
        flash('Error al cargar asignaciones', 'error')
        return redirect(url_for('index'))

@app.route('/admin/exportar')
@login_required
@requiere_rol(['super_admin'])
def admin_exportar():
    """Página de exportación de datos"""
    return render_template('admin/exportar.html')

@app.route('/admin/exportar/ventas')
@login_required
@requiere_rol(['super_admin'])
def exportar_ventas():
    """Exportar datos de ventas a Excel"""
    try:
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        
        if not fecha_inicio or not fecha_fin:
            flash('Debe especificar fechas de inicio y fin', 'error')
            return redirect(url_for('admin_exportar'))
        
        inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        # Consulta de ventas detalladas
        ventas_detalle = db.session.query(
            Pedido.id.label('pedido_id'),
            Pedido.fecha_pedido,
            Cliente.nombre.label('cliente'),
            Producto.nombre.label('producto'),
            DetallePedido.cajas,
            DetallePedido.precio_unitario,
            DetallePedido.subtotal,
            Vendedor.nombre_completo.label('vendedor')
        ).join(
            Cliente, Pedido.cliente_id == Cliente.id
        ).join(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).join(
            Producto, DetallePedido.producto_id == Producto.id
        ).outerjoin(
            ClienteVendedor, Cliente.id == ClienteVendedor.cliente_id
        ).outerjoin(
            Vendedor, ClienteVendedor.vendedor_id == Vendedor.id
        ).filter(
            Pedido.fecha_pedido >= inicio,
            Pedido.fecha_pedido <= fin
        ).order_by(
            Pedido.fecha_pedido.desc()
        ).all()
        
        # Crear Excel
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Reporte de Ventas')
        
        # Formatos
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#3498db',
            'color': 'white',
            'align': 'center'
        })
        
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        money_format = workbook.add_format({'num_format': '$#,##0.00'})
        
        # Encabezados
        headers = ['Pedido ID', 'Fecha', 'Cliente', 'Producto', 'Cajas', 
                  'Precio Unitario', 'Subtotal', 'Vendedor']
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Datos
        total_ventas = 0
        for row, venta in enumerate(ventas_detalle, 1):
            worksheet.write(row, 0, venta.pedido_id)
            worksheet.write(row, 1, venta.fecha_pedido, date_format)
            worksheet.write(row, 2, venta.cliente)
            worksheet.write(row, 3, venta.producto)
            worksheet.write(row, 4, venta.cajas or 0)
            worksheet.write(row, 5, float(venta.precio_unitario or 0), money_format)
            worksheet.write(row, 6, float(venta.subtotal or 0), money_format)
            worksheet.write(row, 7, venta.vendedor or 'Sin asignar')
            
            total_ventas += float(venta.subtotal or 0)
        
        # Total
        last_row = len(ventas_detalle) + 1
        worksheet.write(last_row, 5, 'TOTAL:', header_format)
        worksheet.write(last_row, 6, total_ventas, money_format)
        
        workbook.close()
        output.seek(0)
        
        filename = f"ventas_{fecha_inicio}_a_{fecha_fin}.xlsx"
        return send_file(output, as_attachment=True, download_name=filename,
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
    except Exception as e:
        app.logger.error(f"Error exportando ventas: {e}")
        flash('Error al exportar datos de ventas', 'error')
        return redirect(url_for('admin_exportar'))

@app.route('/admin/backup')
@login_required
@requiere_rol(['super_admin'])
def admin_backup():
    """Página de gestión de backups"""
    return render_template('admin/backup.html')

@app.route('/admin/logs')
@login_required
@requiere_rol(['super_admin'])
def admin_logs():
    """Página de visualización de logs del sistema"""
    try:
        # Logs simulados - en producción conectarías con archivos de log reales
        logs_ejemplo = [
            {
                'timestamp': datetime.now() - timedelta(minutes=5),
                'nivel': 'INFO',
                'mensaje': 'Usuario admin inició sesión',
                'usuario': current_user.username
            },
            {
                'timestamp': datetime.now() - timedelta(hours=1),
                'nivel': 'SUCCESS',
                'mensaje': 'Pedido #123 facturado correctamente',
                'usuario': 'sistema'
            },
            {
                'timestamp': datetime.now() - timedelta(hours=2),
                'nivel': 'WARNING',
                'mensaje': 'Intento de acceso con credenciales incorrectas',
                'usuario': 'desconocido'
            }
        ]
        
        return render_template('admin/logs.html', logs=logs_ejemplo)
        
    except Exception as e:
        app.logger.error(f"Error en admin_logs: {e}")
        flash('Error al cargar logs', 'error')
        return redirect(url_for('index'))

@app.route('/admin/roles')
@login_required
@requiere_rol(['super_admin'])
def admin_roles():
    """Gestión de roles y permisos"""
    try:
        roles = Rol.query.filter_by(activo=True).all()
        permisos = Permiso.query.all()
        
        return render_template('admin/roles.html', roles=roles, permisos=permisos)
        
    except Exception as e:
        app.logger.error(f"Error en admin_roles: {e}")
        flash('Error al cargar roles', 'error')
        return redirect(url_for('index'))

@app.route('/admin/roles/nuevo', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def crear_rol():
    """Crear nuevo rol"""
    if request.method == 'POST':
        try:
            nombre = request.form['nombre']
            descripcion = request.form.get('descripcion', '')
            nivel_jerarquia = int(request.form.get('nivel_jerarquia', 0))
            
            nuevo_rol = Rol(
                nombre=nombre,
                descripcion=descripcion,
                nivel_jerarquia=nivel_jerarquia
            )
            
            db.session.add(nuevo_rol)
            db.session.commit()
            
            flash(f'Rol {nombre} creado exitosamente', 'success')
            return redirect(url_for('admin_roles'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error al crear rol: {e}')
            flash('Error al crear rol. Intente de nuevo.', 'error')

    return render_template('admin/rol_form.html')

# ===== API ENDPOINTS PARA DASHBOARD =====

@app.route('/api/admin/stats')
@login_required
@requiere_rol(['super_admin'])
def api_admin_stats():
    """API para obtener estadísticas en tiempo real para el dashboard admin"""
    try:
        hoy = datetime.now().date()
        inicio_mes = hoy.replace(day=1)
        
        stats = {
            'vendedores_activos': Vendedor.query.filter_by(activo=True).count(),
            'clientes_totales': Cliente.query.count(),
            'pedidos_hoy': Pedido.query.filter(
                Pedido.fecha_pedido >= hoy
            ).count(),
            'pedidos_pendientes': Pedido.query.filter_by(estado='pendiente').count(),
            'ventas_mes': 0
        }
        
        # Calcular ventas del mes
        pedidos_mes = Pedido.query.filter(Pedido.fecha_pedido >= inicio_mes).all()
        for pedido in pedidos_mes:
            for detalle in pedido.detalles:
                if detalle.subtotal:
                    stats['ventas_mes'] += float(detalle.subtotal)
        
        return jsonify(stats)
        
    except Exception as e:
        app.logger.error(f"Error en API admin stats: {e}")
        return jsonify({'error': 'Error interno'}), 500

@app.route('/api/admin/performance')
@login_required
@requiere_rol(['super_admin'])
def api_admin_performance():
    """API para obtener datos de performance de vendedores"""
    try:
        hace_30_dias = datetime.now().date() - timedelta(days=30)
        
        performance = db.session.query(
            Vendedor.nombre_completo,
            Vendedor.username,
            func.count(Pedido.id).label('pedidos'),
            func.coalesce(func.sum(DetallePedido.subtotal), 0).label('ventas')
        ).outerjoin(
            ClienteVendedor, Vendedor.id == ClienteVendedor.vendedor_id
        ).outerjoin(
            Pedido, ClienteVendedor.cliente_id == Pedido.cliente_id
        ).outerjoin(
            DetallePedido, Pedido.id == DetallePedido.pedido_id
        ).filter(
            Vendedor.activo == True,
            Pedido.fecha_pedido >= hace_30_dias
        ).group_by(
            Vendedor.id, Vendedor.nombre_completo, Vendedor.username
        ).order_by(
            func.coalesce(func.sum(DetallePedido.subtotal), 0).desc()
        ).limit(5).all()
        
        resultado = []
        for p in performance:
            resultado.append({
                'vendedor': p.nombre_completo,
                'username': p.username,
                'pedidos': p.pedidos,
                'ventas': float(p.ventas or 0)
            })
        
        return jsonify(resultado)
        
    except Exception as e:
        app.logger.error(f"Error en API performance: {e}")
        return jsonify({'error': 'Error interno'}), 500

# ===== RUTAS DE GESTIÓN DE TERRITORIOS =====

@app.route('/admin/territorios')
@login_required
@requiere_rol(['super_admin'])
def admin_territorios():
    """Gestión de territorios"""
    territorios = Territorio.query.filter_by(activo=True).all()
    return render_template('admin/territorios.html', territorios=territorios)

@app.route('/admin/territorios/nuevo', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def crear_territorio():
    """Crear nuevo territorio"""
    if request.method == 'POST':
        try:
            nombre = request.form['nombre']
            descripcion = request.form.get('descripcion', '')
            tipo = request.form.get('tipo', 'geografico')
            
            nuevo_territorio = Territorio(
                nombre=nombre,
                descripcion=descripcion,
                tipo=tipo
            )
            
            db.session.add(nuevo_territorio)
            db.session.commit()
            
            flash(f'Territorio {nombre} creado exitosamente', 'success')
            return redirect(url_for('admin_territorios'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error al crear territorio: {e}')
            flash('Error al crear territorio. Intente de nuevo.', 'error')

    return render_template('admin/territorio_form.html')

@app.route('/admin/territorios/asignar_cliente', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def asignar_cliente_territorio():
    try:
        cliente_id    = int(request.form['cliente_id'])
        territorio_id = int(request.form['territorio_id'])

        cliente = Cliente.query.get_or_404(cliente_id)
        cliente.territorio_id = territorio_id
        db.session.commit()

        flash('Territorio asignado al cliente', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error al asignar territorio al cliente: {e}')
        flash('Error al asignar territorio. Intente de nuevo.', 'danger')
    return redirect(url_for('admin_clientes_vendedores'))

@app.route('/admin/vendedores/<int:v_id>/territorio', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def actualizar_territorio_vendedor(v_id):
    """
    Cambia el territorio de un vendedor.
    Se recibe territorio_id desde el formulario.
    """
    try:
        territorio_id = request.form.get('territorio_id') or None  # '' → None
        vendedor = Vendedor.query.get_or_404(v_id)

        # actualizar (permite dejarlo sin territorio)
        vendedor.territorio_id = int(territorio_id) if territorio_id else None
        db.session.commit()

        flash('Territorio del vendedor actualizado', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error al actualizar territorio del vendedor: {e}')
        flash('Error al actualizar territorio. Intente de nuevo.', 'danger')

    return redirect(url_for('gestionar_vendedores'))

# ===== WEBHOOKS Y INTEGRACIONES =====

@app.route('/webhook/actualizacion-precios', methods=['POST'])
def webhook_actualizacion_precios():
    """Webhook para actualizaciones automáticas de precios desde sistemas externos"""
    try:
        data = request.get_json()
        
        # Validar webhook (en producción añadir autenticación)
        if not data or 'productos' not in data:
            return jsonify({'error': 'Datos inválidos'}), 400
        
        productos_actualizados = 0
        
        for item in data['productos']:
            producto_id = item.get('producto_id')
            nuevo_precio = item.get('precio_jomar')
            
            if producto_id and nuevo_precio:
                # Actualizar precio en lista por defecto
                lista_default = ListaPrecio.query.filter_by(es_default=True).first()
                if lista_default:
                    precio = PrecioProducto.query.filter_by(
                        lista_precio_id=lista_default.id,
                        producto_id=producto_id
                    ).first()
                    
                    if precio:
                        precio.precio_jomar = nuevo_precio
                        precio.fecha_actualizacion = datetime.utcnow()
                        productos_actualizados += 1
        
        if productos_actualizados > 0:
            db.session.commit()
        
        return jsonify({
            'success': True,
            'productos_actualizados': productos_actualizados
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error en webhook precios: {e}")
        return jsonify({'error': 'Error interno'}), 500


@app.route('/dashboard')
@login_required
def dashboard():
    app.logger.info("[/dashboard] entrando")
    """Dashboard optimizado con KPIs de ventas y nivel de servicio"""
    try:
        # Verificación de dependencias críticas
        if not db or not Pedido:
            app.logger.error("Dependencias críticas no disponibles")
            raise Exception("Base de datos no inicializada")
            
        app.logger.info("Iniciando cálculo de dashboard...")
        # === FECHAS DE REFERENCIA ===
        hoy = datetime.now().date()
        inicio_mes = hoy.replace(day=1)
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        hace_30_dias = hoy - timedelta(days=30)
        hace_8_semanas = hoy - timedelta(weeks=8)
        # Mes anterior (mismo rango de días para comparación justa)
        fin_mes_anterior = inicio_mes - timedelta(days=1)
        inicio_mes_anterior = fin_mes_anterior.replace(day=1)

        # === CLIENTE EXCLUIDO (ALMACÉN INTERNO) ===
        # AL01 es usado para registrar pesos e imprimir etiquetas de almacén, no son pedidos reales
        cliente_almacen = Cliente.query.filter_by(nombre='AL01').first()
        cliente_almacen_id = cliente_almacen.id if cliente_almacen else None

        # Helper para filtrar pedidos excluyendo AL01
        def filtro_sin_almacen():
            if cliente_almacen_id:
                return Pedido.cliente_id != cliente_almacen_id
            return True  # Si no existe AL01, no filtrar nada

        # === CONSULTAS ROBUSTAS PARA PRODUCCIÓN ===
        try:
            # Consultas simples sin eager loading para evitar problemas en Heroku
            # NOTA: Se excluye cliente AL01 (almacén interno) de todos los cálculos
            base_query = Pedido.query.filter(filtro_sin_almacen())
            pedidos_mes_list = base_query.filter(Pedido.fecha_pedido >= inicio_mes).all()
            pedidos_semana_list = base_query.filter(Pedido.fecha_pedido >= inicio_semana).all()
            pedidos_30_dias = base_query.filter(Pedido.fecha_pedido >= hace_30_dias).all()
            pedidos_mes_anterior_list = base_query.filter(
                Pedido.fecha_pedido >= inicio_mes_anterior,
                Pedido.fecha_pedido <= fin_mes_anterior
            ).all()
            
            app.logger.info(f"Datos cargados: {len(pedidos_mes_list)} pedidos mes, {len(pedidos_semana_list)} semana, {len(pedidos_30_dias)} últimos 30 días")
        except Exception as e:
            app.logger.error(f"Error en consultas dashboard: {e}")
            # Fallback con datos vacíos
            pedidos_mes_list = []
            pedidos_semana_list = []
            pedidos_30_dias = []

        # === CÁLCULOS ROBUSTOS DE VENTAS ===
        try:
            ventas_mes = 0
            for p in pedidos_mes_list:
                try:
                    for d in p.detalles:
                        if d.subtotal:
                            ventas_mes += float(d.subtotal)
                except (AttributeError, ValueError, TypeError) as e:
                    app.logger.warning(f"Error en cálculo ventas mes, pedido {p.id}: {e}")
                    continue
            
            ventas_semana = 0
            for p in pedidos_semana_list:
                try:
                    for d in p.detalles:
                        if d.subtotal:
                            ventas_semana += float(d.subtotal)
                except (AttributeError, ValueError, TypeError) as e:
                    app.logger.warning(f"Error en cálculo ventas semana, pedido {p.id}: {e}")
                    continue
            
            ventas_mes_anterior = 0
            for p in pedidos_mes_anterior_list:
                try:
                    for d in p.detalles:
                        if d.subtotal:
                            ventas_mes_anterior += float(d.subtotal)
                except (AttributeError, ValueError, TypeError):
                    continue
            pedidos_mes_anterior = len(pedidos_mes_anterior_list)

            # Consulta robusta para pedidos pendientes (excluyendo AL01)
            pendientes_query = Pedido.query.filter_by(estado='pendiente')
            if cliente_almacen_id:
                pendientes_query = pendientes_query.filter(Pedido.cliente_id != cliente_almacen_id)
            pedidos_pendientes = pendientes_query.count()
            
        except Exception as e:
            app.logger.error(f"Error en cálculos de ventas: {e}")
            ventas_mes = 0
            ventas_semana = 0
            ventas_mes_anterior = 0
            pedidos_mes_anterior = 0
            pedidos_pendientes = 0

        # === KPIs OPTIMIZADOS DE NIVEL DE SERVICIO (MES EN CURSO) ===
        # NOTA: Todos los KPIs ahora se calculan sobre el mes en curso

        # Función helper para calcular KPIs de un período
        def calcular_kpis_periodo(pedidos_periodo):
            """Calcula todos los KPIs para un período dado"""
            if not pedidos_periodo:
                return {
                    'order_completion_rate': 0, 'otd_rate': 0,
                    'lead_time': 0, 'total_pedidos': 0, 'ventas': 0
                }

            # Pedidos facturados del período
            facturados = [p for p in pedidos_periodo if p.estado == 'facturado' and p.fecha_facturacion]

            # Lead times
            lead_times_p = []
            for p in facturados:
                dias = (p.fecha_facturacion.date() - p.fecha_pedido.date()).days
                if dias >= 0:
                    lead_times_p.append(dias)

            # Order Completion Rate (antes Fill Rate — misma fórmula, nombre honesto)
            estados = {'facturado': 0, 'pendiente': 0, 'preparado': 0}
            for p in pedidos_periodo:
                estado = p.estado or 'otros'
                if estado in estados:
                    estados[estado] += 1
            completos = estados['facturado']
            total_eval = completos + estados['pendiente'] + estados['preparado']
            order_completion_rate_p = (completos / total_eval * 100) if total_eval > 0 else 0

            # OTD Rate corregido — incluye pendientes vencidos como "fuera de tiempo"
            a_tiempo = sum(1 for lt in lead_times_p if lt <= 2)
            pendientes_vencidos = sum(
                1 for p in pedidos_periodo
                if p.estado in ('pendiente', 'preparado')
                and (hoy - p.fecha_pedido.date()).days > 2
            )
            total_otd = len(lead_times_p) + pendientes_vencidos
            otd_p = (a_tiempo / total_otd * 100) if total_otd > 0 else 100

            # Ventas del período
            total_p = len(pedidos_periodo)
            ventas_p = sum(
                sum(float(d.subtotal or 0) for d in p.detalles)
                for p in pedidos_periodo if p.estado == 'facturado'
            )

            return {
                'order_completion_rate': round(order_completion_rate_p, 1),
                'otd_rate': round(otd_p, 1),
                'lead_time': round(sum(lead_times_p) / len(lead_times_p), 1) if lead_times_p else 0,
                'total_pedidos': total_p,
                'ventas': ventas_p
            }

        # Calcular KPIs del mes en curso
        kpis_mes_actual = calcular_kpis_periodo(pedidos_mes_list)

        # Extraer valores para compatibilidad con template existente
        pedidos_facturados = [p for p in pedidos_mes_list if p.estado == 'facturado' and p.fecha_facturacion]
        lead_times = [dias for p in pedidos_facturados if p.fecha_facturacion
                     for dias in [(p.fecha_facturacion.date() - p.fecha_pedido.date()).days]
                     if dias >= 0]
        lead_time_promedio = kpis_mes_actual['lead_time']
        order_completion_rate = kpis_mes_actual['order_completion_rate']
        otd_rate = kpis_mes_actual['otd_rate']

        # === HISTÓRICO DE KPIs (ÚLTIMOS 6 MESES) ===
        kpis_historicos = []
        for i in range(6):
            # Calcular inicio y fin de cada mes
            if i == 0:
                mes_inicio = inicio_mes
                mes_fin = hoy
            else:
                # Mes anterior
                primer_dia_mes_actual = inicio_mes
                for _ in range(i):
                    primer_dia_mes_actual = (primer_dia_mes_actual - timedelta(days=1)).replace(day=1)
                mes_inicio = primer_dia_mes_actual
                # Último día del mes
                if mes_inicio.month == 12:
                    mes_fin = mes_inicio.replace(year=mes_inicio.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    mes_fin = mes_inicio.replace(month=mes_inicio.month + 1, day=1) - timedelta(days=1)

            # Obtener pedidos del mes (excluyendo AL01)
            hist_query = Pedido.query.filter(
                Pedido.fecha_pedido >= mes_inicio,
                Pedido.fecha_pedido <= mes_fin
            )
            if cliente_almacen_id:
                hist_query = hist_query.filter(Pedido.cliente_id != cliente_almacen_id)
            pedidos_mes_hist = hist_query.all()

            # Calcular KPIs
            kpis = calcular_kpis_periodo(pedidos_mes_hist)
            kpis['mes'] = mes_inicio.strftime('%b %Y')
            kpis['mes_num'] = mes_inicio.month
            kpis['año'] = mes_inicio.year
            kpis_historicos.append(kpis)

        # Invertir para que el más antiguo esté primero
        kpis_historicos.reverse()

        # Perfect order rate del mes actual (simplificado: solo OTD)
        perfect_orders = sum(1 for lt in lead_times if lt <= 2)
        pendientes_vencidos_mes = sum(
            1 for p in pedidos_mes_list
            if p.estado in ('pendiente', 'preparado')
            and (hoy - p.fecha_pedido.date()).days > 2
        )
        total_evaluado_por = len(pedidos_facturados) + pendientes_vencidos_mes
        perfect_order_rate = (
            (perfect_orders / total_evaluado_por * 100)
            if total_evaluado_por > 0 else 0
        )

        # 6. Customer engagement optimizado
        clientes_activos_ids = {p.cliente_id for p in pedidos_mes_list if p.cliente_id}
        clientes_activos_mes = len(clientes_activos_ids)
        
        # Cache de total de clientes para evitar query innecesaria (excluyendo AL01)
        clientes_query = Cliente.query
        if cliente_almacen_id:
            clientes_query = clientes_query.filter(Cliente.id != cliente_almacen_id)
        total_clientes = clientes_query.count()
        customer_engagement = (
            (clientes_activos_mes / total_clientes * 100) 
            if total_clientes > 0 else 0
        )

        # === ANÁLISIS OPTIMIZADO DE PRODUCTOS (MES EN CURSO) ===
        productos_ventas = {}
        max_ingresos = 0  # Tracking del máximo para optimizar (por valor facturado)

        for p in pedidos_mes_list:  # Cambiado de pedidos_30_dias a mes en curso
            pedido_id = p.id
            for d in p.detalles:
                # Verificar que existe el producto
                if not d.producto or not d.producto.nombre:
                    app.logger.warning(f'Detalle sin producto válido en pedido {pedido_id}')
                    continue

                nombre = d.producto.nombre
                cajas_detalle = d.cajas or 0
                peso_detalle = d.peso or 0
                ingresos_detalle = float(d.subtotal or 0)

                if nombre not in productos_ventas:
                    productos_ventas[nombre] = {
                        'cajas': 0,
                        'peso': 0,
                        'ingresos': 0,
                        'pedidos': set()
                    }

                # Actualizar datos del producto
                productos_ventas[nombre]['cajas'] += cajas_detalle
                productos_ventas[nombre]['peso'] += peso_detalle
                productos_ventas[nombre]['ingresos'] += ingresos_detalle
                productos_ventas[nombre]['pedidos'].add(pedido_id)
                
                # Tracking optimizado del máximo (por valor facturado)
                if productos_ventas[nombre]['ingresos'] > max_ingresos:
                    max_ingresos = productos_ventas[nombre]['ingresos']

        # Optimización: Convertir sets a contadores en una pasada
        for datos in productos_ventas.values():
            datos['pedidos'] = len(datos['pedidos'])

        # Top productos con manejo robusto
        try:
            if productos_ventas:
                # Usar sorted (más compatible) en lugar de heapq
                # Ordenar por valor facturado (ingresos) en lugar de cantidad de cajas
                top_productos_raw = sorted(
                    productos_ventas.items(),
                    key=lambda x: x[1]['ingresos'],
                    reverse=True
                )[:5]
            else:
                top_productos_raw = []
        except Exception as e:
            app.logger.error(f"Error en top productos: {e}")
            top_productos_raw = []

        # Convertir a formato optimizado para el template
        top_productos = [
            {
                'nombre': nombre,
                'total_vendido': round(datos['ingresos'], 2),  # Usar ingresos para ordenamiento visual
                'cajas': datos['cajas'],
                'peso': round(datos['peso'], 2),
                'ingresos': round(datos['ingresos'], 2),
                'pedidos': datos['pedidos']
            }
            for nombre, datos in top_productos_raw
        ]

        # Usar el máximo precalculado (por valor facturado)
        max_ventas = max_ingresos if max_ingresos > 0 else 1

        # === ANÁLISIS DE CLIENTES (MES EN CURSO) ===
        clientes_ventas = {}
        for p in pedidos_mes_list:  # Cambiado de pedidos_30_dias a mes en curso
            # Verificar que existe el cliente
            if not p.cliente:
                app.logger.warning(f'Pedido sin cliente: {p.id}')
                continue
            
            nombre = p.cliente.nombre
            if nombre not in clientes_ventas:
                clientes_ventas[nombre] = {'pedidos': 0, 'total': 0, 'ultimo_pedido': None}
            clientes_ventas[nombre]['pedidos'] += 1
            clientes_ventas[nombre]['total'] += sum(
                float(d.subtotal or 0) for d in p.detalles
            )
            if (
                not clientes_ventas[nombre]['ultimo_pedido']
                or p.fecha_pedido > clientes_ventas[nombre]['ultimo_pedido']
            ):
                clientes_ventas[nombre]['ultimo_pedido'] = p.fecha_pedido

        top_clientes = sorted(
            clientes_ventas.items(), key=lambda x: x[1]['total'], reverse=True
        )[:5]

        # === TENDENCIA SEMANAL (excluyendo AL01) — 26 semanas (6 meses) ===
        tendencia_semanal = []
        for i in range(26):
            inicio_i = hoy - timedelta(days=hoy.weekday() + 7 * i)
            fin_i = inicio_i + timedelta(days=6)
            semana_query = Pedido.query.filter(
                db.func.date(Pedido.fecha_pedido) >= inicio_i,
                db.func.date(Pedido.fecha_pedido) <= fin_i
            )
            if cliente_almacen_id:
                semana_query = semana_query.filter(Pedido.cliente_id != cliente_almacen_id)
            pedidos_semana_i = semana_query.all()
            ventas_semana_i = sum(
                sum(float(d.subtotal or 0) for d in p.detalles) for p in pedidos_semana_i
            )
            tendencia_semanal.append(
                {
                    'semana': inicio_i.strftime('%d/%m'),
                    'ventas': ventas_semana_i,
                    'pedidos': len(pedidos_semana_i),
                }
            )
        tendencia_semanal.reverse()

        # === ESTADOS DE PEDIDOS ===
        estados_count = {}
        for p in pedidos_30_dias:
            estado = p.estado or 'sin_estado'  # Manejar estados nulos
            estados_count[estado] = estados_count.get(estado, 0) + 1

        # Asegurar que siempre tengamos datos básicos
        estados_pedidos = {
            'pendiente': estados_count.get('pendiente', 0),
            'preparado': estados_count.get('preparado', 0),
            'facturado': estados_count.get('facturado', 0),
            **{k: v for k, v in estados_count.items() if k not in ['pendiente', 'preparado', 'facturado']}
        }

        # === PEDIDOS RECIENTES (excluyendo AL01) ===
        recientes_query = Pedido.query
        if cliente_almacen_id:
            recientes_query = recientes_query.filter(Pedido.cliente_id != cliente_almacen_id)
        pedidos_recientes_data = recientes_query.order_by(
            Pedido.fecha_pedido.desc()
        ).limit(10).all()

        # === VENTAS DIARIAS (excluyendo AL01) ===
        ventas_dias = []
        for i in range(7):
            dia = hoy - timedelta(days=i)
            dia_query = Pedido.query.filter(
                db.func.date(Pedido.fecha_pedido) == dia
            )
            if cliente_almacen_id:
                dia_query = dia_query.filter(Pedido.cliente_id != cliente_almacen_id)
            pedidos_dia = dia_query.all()
            total_dia = sum(
                sum(float(d.subtotal or 0) for d in p.detalles)
                for p in pedidos_dia
            )
            ventas_dias.append({
                'fecha': dia.strftime('%d/%m'),
                'ventas': total_dia,
                'pedidos': len(pedidos_dia)
            })
        ventas_dias.reverse()

        # === CALCULAR PORCENTAJE DE META ===
        try:
            meta_mensual = float(os.environ.get('MONTHLY_SALES_TARGET', '120000'))
        except (ValueError, TypeError):
            meta_mensual = 120000.0
        porcentaje_meta = (ventas_mes / meta_mensual * 100) if meta_mensual > 0 else 0

        # === PROYECCIÓN DE VENTAS A FIN DE MES ===
        dias_transcurridos = hoy.day
        dias_total_mes = calendar.monthrange(hoy.year, hoy.month)[1]
        if dias_transcurridos >= 2:
            proyeccion_ventas = ventas_mes / dias_transcurridos * dias_total_mes
        else:
            proyeccion_ventas = 0
        porcentaje_proyeccion = (proyeccion_ventas / meta_mensual * 100) if meta_mensual > 0 else 0

        # === TIEMPO DE RESPUESTA POR CLIENTE ===
        tiempos_respuesta_cliente = {}
        for p in pedidos_30_dias:
            if p.cliente and p.fecha_facturacion:
                nombre_cliente = p.cliente.nombre
                tiempo = (p.fecha_facturacion.date() - p.fecha_pedido.date()).days
                if nombre_cliente not in tiempos_respuesta_cliente:
                    tiempos_respuesta_cliente[nombre_cliente] = []
                tiempos_respuesta_cliente[nombre_cliente].append(tiempo)
        
        # Calcular promedios
        tiempo_respuesta_data = []
        for cliente, tiempos in tiempos_respuesta_cliente.items():
            tiempo_respuesta_data.append({
                'cliente': cliente,
                'promedio': round(sum(tiempos) / len(tiempos), 1),
                'pedidos': len(tiempos)
            })
        tiempo_respuesta_data = sorted(tiempo_respuesta_data, key=lambda x: x['promedio'])[:10]

        # === RENDER ===
        return render_template(
            'dashboard.html',
            # Métricas principales
            ventas_mes=ventas_mes,
            pedidos_mes=len(pedidos_mes_list),
            ventas_semana=ventas_semana,
            pedidos_semana=len(pedidos_semana_list),
            ventas_mes_anterior=ventas_mes_anterior,
            pedidos_mes_anterior=pedidos_mes_anterior,
            pedidos_pendientes=pedidos_pendientes,
            meta_mensual=meta_mensual,
            porcentaje_meta=porcentaje_meta,
            proyeccion_ventas=round(proyeccion_ventas, 2),
            porcentaje_proyeccion=round(porcentaje_proyeccion, 1),
            dias_total_mes=dias_total_mes,
            
            # KPIs de servicio (actualizados)
            lead_time_promedio=round(lead_time_promedio, 1),
            order_completion_rate=round(order_completion_rate, 1),
            otd_rate=round(otd_rate, 1),
            perfect_order_rate=round(perfect_order_rate, 1),
            customer_engagement=round(customer_engagement, 1),
            
            # Datos para gráficos
            top_clientes=top_clientes,
            top_productos=top_productos,
            max_ventas=max_ventas,
            estados_pedidos=estados_pedidos,
            tendencia_semanal=tendencia_semanal,
            pedidos_recientes=pedidos_recientes_data,
            fecha_actual=hoy,
            ventas_dias=ventas_dias,
            tiempo_respuesta_data=tiempo_respuesta_data,

            # Histórico de KPIs (últimos 6 meses)
            kpis_historicos=kpis_historicos,

            # Configuración
            moneda='XCG'
        )

    except Exception as e:
        app.logger.exception(f'Error crítico en /dashboard: {e}')
        
        # Datos de fallback para evitar error 500
        try:
            _fallback_meta = float(os.environ.get('MONTHLY_SALES_TARGET', '120000'))
        except (ValueError, TypeError):
            _fallback_meta = 120000.0
        fallback_data = {
            'ventas_mes': 0,
            'pedidos_mes': 0,
            'ventas_semana': 0,
            'pedidos_semana': 0,
            'pedidos_pendientes': 0,
            'meta_mensual': _fallback_meta,
            'porcentaje_meta': 0,
            'proyeccion_ventas': 0,
            'porcentaje_proyeccion': 0,
            'ventas_mes_anterior': 0,
            'pedidos_mes_anterior': 0,
            'dias_total_mes': calendar.monthrange(datetime.now().year, datetime.now().month)[1],
            'lead_time_promedio': 0,
            'order_completion_rate': 0,
            'otd_rate': 0,
            'perfect_order_rate': 0,
            'customer_engagement': 0,
            'top_clientes': [],
            'top_productos': [],
            'max_ventas': 1,
            'estados_pedidos': {'pendiente': 0, 'preparado': 0, 'facturado': 0},
            'tendencia_semanal': [],
            'pedidos_recientes': [],
            'fecha_actual': datetime.now().date(),
            'ventas_dias': [],
            'tiempo_respuesta_data': [],
            'kpis_historicos': [],
            'moneda': 'XCG'
        }
        
        try:
            return render_template('dashboard.html', **fallback_data)
        except Exception as template_error:
            app.logger.error(f'Error incluso con datos de fallback: {template_error}')
            from flask import abort
            abort(500)


@app.route('/pedidos')
@login_required
@requiere_permiso_recurso('pedidos', 'leer')
def lista_pedidos():
    # Parámetros de paginación
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)  # Máximo 100 por página

    # Subquery para calcular totales
    totales_subq = db.session.query(
        DetallePedido.pedido_id,
        func.coalesce(func.sum(DetallePedido.subtotal), 0).label('total_calculado')
    ).group_by(DetallePedido.pedido_id).subquery()

    # Query base con eager loading de Cliente para evitar N+1
    base_query = db.session.query(
        Pedido,
        func.coalesce(totales_subq.c.total_calculado, 0).label('total_calculado')
    ).outerjoin(
        totales_subq, Pedido.id == totales_subq.c.pedido_id
    ).options(
        joinedload(Pedido.cliente)
    ).filter(
        Pedido.estado != 'entregado'
    )

    # Orden: 1) Estado (pendientes primero), 2) Fecha desc, 3) ID desc
    orden_optimizado = [
        db.case((Pedido.estado == 'pendiente', 0), else_=1),
        db.case((Pedido.fecha_pedido.is_(None), 1), else_=0),
        Pedido.fecha_pedido.desc(),
        Pedido.id.desc(),
    ]

    # Filtrar por permisos del usuario
    if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
        clientes_ids = [c.id for c in current_user.obtener_clientes_visibles()]
        if not clientes_ids:
            # Sin clientes asignados - retornar vacío con paginación mock
            return render_template('pedidos.html', pedidos=[], pagination=None)
        base_query = base_query.filter(Pedido.cliente_id.in_(clientes_ids))

    # Aplicar ordenamiento
    base_query = base_query.order_by(*orden_optimizado)

    # Contar total para paginación
    total_count = base_query.count()
    total_pages = (total_count + per_page - 1) // per_page

    # Aplicar paginación manual (offset/limit)
    pedidos_query = base_query.offset((page - 1) * per_page).limit(per_page).all()

    # Agregar el total calculado como atributo a cada pedido
    pedidos = []
    for pedido, total in pedidos_query:
        pedido.total_calculado = float(total)
        pedidos.append(pedido)

    # Info de paginación para el template
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None,
    }

    return render_template('pedidos.html', pedidos=pedidos, pagination=pagination)



@app.route('/pedidos/nuevo', methods=['GET', 'POST'])
@login_required
@requiere_permiso_recurso('pedidos', 'crear')
def nuevo_pedido():
    # Obtener clientes según el vendedor
    if not isinstance(current_user, Vendedor):
        # Usuario del sistema anterior - todos los clientes
        clientes = Cliente.query.all()
    else:
        if current_user.rol.nombre == 'super_admin':
            # Super admin ve todos los clientes
            clientes = Cliente.query.all()
        else:
            # Vendedor regular: solo sus clientes asignados
            clientes = current_user.obtener_clientes_visibles()

    productos = Producto.query.all()

    # Enviamos al front-end cada producto con su precio (lista default)
    productos_dicts = [{
        'id'    : p.id,
        'nombre': p.nombre,
        'precio': float(
            obtener_precio_default_producto(p.id, 'base') or 0
        )
    } for p in productos]

    if request.method == 'POST':
        # 1) Cabecera
        cliente_id = int(request.form['cliente_id'])
        
        # VERIFICAR QUE EL VENDEDOR PUEDE CREAR PEDIDOS PARA ESTE CLIENTE
        if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
            clientes_permitidos_ids = [c.id for c in current_user.obtener_clientes_visibles()]
            if cliente_id not in clientes_permitidos_ids:
                flash('No tienes permisos para crear pedidos para este cliente', 'error')
                return redirect(url_for('nuevo_pedido'))
        
        notas = request.form.get('notas')
        pedido = Pedido(cliente_id=cliente_id, notas=notas)
        db.session.add(pedido)
        db.session.commit()

        # 2) Detalle (resto del código igual)
        idx = 0
        while f'productos[{idx}][id]' in request.form:
            prod_id = int(request.form.get(f'productos[{idx}][id]'))
            cajas = int(request.form.get(f'productos[{idx}][cajas]', 0))

            precio_raw = request.form.get(f'productos[{idx}][precio]')
            if precio_raw:
                precio_unitario = Decimal(precio_raw)
            else:
                precio_cliente = obtener_precio_producto_cliente(cliente_id, prod_id, 'base')
                if precio_cliente is not None:
                    precio_unitario = Decimal(precio_cliente)
                else:
                    precio_def = obtener_precio_default_producto(prod_id, 'base')
                    precio_unitario = Decimal(precio_def) if precio_def is not None else Decimal('0')

            subtotal = precio_unitario * cajas

            detalle = DetallePedido(
                pedido_id=pedido.id,
                producto_id=prod_id,
                cajas=cajas,
                precio_unitario=precio_unitario,
                subtotal=subtotal
            )
            db.session.add(detalle)
            idx += 1

        db.session.commit()

        # 3) Total del pedido
        total = db.session.query(
            func.coalesce(func.sum(DetallePedido.subtotal), 0)
        ).filter_by(pedido_id=pedido.id).scalar()
        
        if hasattr(pedido, 'total'):
            pedido.total = total
            db.session.commit()

        flash('Pedido creado con precios registrados.', 'success')
        return redirect(url_for('lista_pedidos'))

    return render_template(
        'pedido_form.html',
        clientes=clientes,
        productos=productos_dicts,
        pedido=None,
        productos_pedido=[]
    )

@app.route('/pedidos/<int:pedido_id>/editar', methods=['GET', 'POST'])
@login_required
@requiere_permiso_recurso('pedidos', 'editar')
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
                p.id, 'base'
            ) or obtener_precio_default_producto(p.id, 'base') or 0
        )
    } for p in productos]

    
    if request.method == 'POST':
        if isinstance(current_user, Vendedor) and not current_user.puede_editar_pedido(pedido):
            flash('No tienes permisos para editar este pedido', 'error')
            return redirect(url_for('lista_pedidos'))
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
                precio_cliente = obtener_precio_producto_cliente(pedido.cliente_id, prod_id, 'base')
                if precio_cliente is not None:
                    precio_unitario = Decimal(precio_cliente)
                else:
                    precio_def = obtener_precio_default_producto(prod_id, 'base')
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
@requiere_permiso_recurso('pedidos', 'eliminar')
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

    # ── Verificación de autorización IDOR ─────────────────────
    if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
        if not current_user.puede_ver_cliente(pedido.cliente_id):
            flash('No tienes permisos para acceder a este pedido', 'error')
            return redirect(url_for('lista_pedidos'))

    productos = Producto.query.all()

    # ── 2) Alta de un nuevo detalle ───────────────────────────
    if request.method == 'POST':
        # ── Inmutabilidad post-facturación ──────────────────────
        if pedido.estado == 'facturado':
            flash('No se puede agregar detalles a un pedido facturado', 'error')
            return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

        producto_id       = int(request.form['producto_id'])
        peso              = float(request.form.get('peso', 0)  or 0)
        cajas             = int  (request.form.get('cajas', 0) or 0)   # reservado
        lote              = request.form.get('lote', '').strip()
        fecha_fabricacion = request.form.get('fecha_fabricacion', '').strip()
        fecha_expiracion  = request.form.get('fecha_expiracion', '').strip()

        # ── Validación de trazabilidad obligatoria ──────────────
        if not all([lote, fecha_fabricacion, fecha_expiracion]):
            flash('Lote, fecha fabricación y fecha expiración son obligatorios', 'error')
            return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

        # -------- Obtener precio unitario según la jerarquía --------
        precio_unitario = obtener_precio_producto_cliente(
                              pedido.cliente_id,   # 1️⃣ precio específico / lista cliente
                              producto_id,
                              'base'
                          )
        if precio_unitario is None:
            # 2️⃣ (fallback) lista de precios por defecto
            precio_unitario = obtener_precio_default_producto(
                                  producto_id, 'base'
                              ) or 0
        
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
            subtotal         = subtotal,
            es_linea_pedido  = False
        )
        db.session.add(detalle)
        db.session.commit()

        flash('Detalle agregado.', 'success')
        return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

    # ── 3) GET: mostrar plantilla ─────────────────────────────
    # Ordenar detalles por nombre de producto y luego por id
    detalles_ordenados = sorted(pedido.detalles, key=lambda d: (d.producto.nombre, d.id))

    # Calcular conteo de registros por producto para mostrar "#/Total"
    # Excluir líneas originales del pedido (es_linea_pedido=True)
    conteo_por_producto = {}
    for detalle in detalles_ordenados:
        if detalle.es_linea_pedido:
            continue
        pid = detalle.producto_id
        conteo_por_producto[pid] = conteo_por_producto.get(pid, 0) + 1

    # Asignar índice a cada detalle para mostrar "1/3", "2/3", etc.
    indice_detalle = {}
    contador_temp = {}
    for detalle in detalles_ordenados:
        if detalle.es_linea_pedido:
            continue
        pid = detalle.producto_id
        contador_temp[pid] = contador_temp.get(pid, 0) + 1
        indice_detalle[detalle.id] = contador_temp[pid]

    return render_template('detalles_pedido.html',
                           pedido   = pedido,
                           productos= productos,
                           conteo_por_producto=conteo_por_producto,
                           indice_detalle=indice_detalle,
                           detalles_ordenados=detalles_ordenados)


@app.route('/detalles_pedido/<int:detalle_id>/eliminar', methods=['POST'])
@login_required
def eliminar_detalle_pedido(detalle_id):
    detalle = DetallePedido.query.get_or_404(detalle_id)
    pedido = Pedido.query.get_or_404(detalle.pedido_id)

    # ── Verificación de autorización IDOR ─────────────────────
    if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
        if not current_user.puede_ver_cliente(pedido.cliente_id):
            flash('No tienes permisos para eliminar este detalle', 'error')
            return redirect(url_for('lista_pedidos'))

    # ── Inmutabilidad post-facturación ─────────────────────────
    if pedido.estado == 'facturado':
        flash('No se puede eliminar un detalle de un pedido facturado', 'error')
        return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

    db.session.delete(detalle)
    db.session.commit()
    flash('Detalle eliminado.', 'success')
    return redirect(url_for('detalles_pedido', pedido_id=pedido.id))


@app.route('/detalles_pedido/<int:detalle_id>/editar', methods=['POST'])
@login_required
def editar_detalle_pedido(detalle_id):
    """Edita un detalle de pedido existente."""
    detalle = DetallePedido.query.get_or_404(detalle_id)
    pedido = Pedido.query.get_or_404(detalle.pedido_id)

    # ── Verificación de autorización IDOR ─────────────────────
    if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
        if not current_user.puede_ver_cliente(pedido.cliente_id):
            flash('No tienes permisos para editar este detalle', 'error')
            return redirect(url_for('lista_pedidos'))

    # ── Inmutabilidad post-facturación ─────────────────────────
    if pedido.estado == 'facturado':
        flash('No se puede editar un pedido facturado', 'error')
        return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

    # Obtener datos del formulario
    producto_id = request.form.get('producto_id', type=int)
    peso = request.form.get('peso', type=float)
    lote = request.form.get('lote', '').strip()
    fecha_fabricacion = request.form.get('fecha_fabricacion', '')
    fecha_expiracion = request.form.get('fecha_expiracion', '')

    # Validar datos
    if not all([producto_id, peso, lote, fecha_fabricacion, fecha_expiracion]):
        flash('Todos los campos son requeridos', 'error')
        return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

    # Actualizar el detalle
    detalle.producto_id = producto_id
    detalle.peso = peso
    detalle.lote = lote
    detalle.fecha_fabricacion = fecha_fabricacion
    detalle.fecha_expiracion = fecha_expiracion

    db.session.commit()
    flash('Detalle actualizado correctamente.', 'success')
    return redirect(url_for('detalles_pedido', pedido_id=pedido.id))


# ---------------------------------------------------------------------
# Generar etiquetas a partir de los DetallePedido de un pedido concreto
# -> Genera PDF 4" x 2", una etiqueta por página (para PDF Direct)
# ---------------------------------------------------------------------
@app.route('/generar_etiqueta_detalle/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def generar_etiqueta_detalle(pedido_id):
    """
    Genera un PDF con etiquetas 4x2 (una por página) para PDF Direct.
    Soporta GET y POST para mejor compatibilidad con iOS.
    """
    try:
        pedido = Pedido.query.get_or_404(pedido_id)

        # Obtener parámetros desde GET o POST
        fecha_ini = request.args.get('fecha_inicio') if request.method == 'GET' else request.form.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin') if request.method == 'GET' else request.form.get('fecha_fin')

        # Validar fechas
        if not fecha_ini or not fecha_fin:
            error_msg = "Debe indicar fecha de inicio y fin"
            if request.method == 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for('detalles_pedido', pedido_id=pedido_id))

        try:
            datetime.strptime(fecha_ini, '%Y-%m-%d')
            datetime.strptime(fecha_fin, '%Y-%m-%d')
        except ValueError:
            error_msg = "Formato de fecha inválido. Use YYYY-MM-DD"
            if request.method == 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"error": error_msg}), 400
            flash("Formato de fecha inválido", "danger")
            return redirect(url_for('detalles_pedido', pedido_id=pedido_id))

        # Filtrar los detalles (Story 3-0: excluir líneas originales del pedido)
        detalles = (DetallePedido.query
                    .filter_by(pedido_id=pedido_id)
                    .filter(DetallePedido.es_linea_pedido == False)
                    .filter(DetallePedido.fecha_fabricacion >= fecha_ini)
                    .filter(DetallePedido.fecha_fabricacion <= fecha_fin)
                    .order_by(DetallePedido.id.asc())
                    .all())

        if not detalles:
            error_msg = "No hay detalles en ese rango de fechas"
            if request.method == 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"error": error_msg}), 404
            flash(error_msg, "warning")
            return redirect(url_for('detalles_pedido', pedido_id=pedido_id))

        # Crear PDF
        output, c = create_single_label_pdf()
        logo_path = get_logo_path(basedir)
        cliente_nombre = pedido.cliente.nombre if getattr(pedido, "cliente", None) else ""

        for d in detalles:
            producto_nombre = d.producto.nombre if getattr(d, "producto", None) else "N/A"
            temperatura = getattr(d.producto, "temperatura", None) or "N/A"

            # Formatear peso: usar peso real si existe, sino cajas
            peso_float = float(d.peso or 0)
            if peso_float > 0:
                peso_val = f"{peso_float:.2f} kg"
            else:
                peso_val = f"{int(d.cajas or 0)} uds"

            # Formatear fechas
            f_fab = d.fecha_fabricacion
            f_exp = d.fecha_expiracion
            if hasattr(f_fab, "strftime"):
                f_fab = f_fab.strftime("%Y-%m-%d")
            if hasattr(f_exp, "strftime"):
                f_exp = f_exp.strftime("%Y-%m-%d")

            # Null safety para trazabilidad
            lote = d.lote or "N/A"
            f_fab = f_fab or "N/A"
            f_exp = f_exp or "N/A"

            draw_order_label(
                c, logo_path,
                client=cliente_nombre,
                product=producto_nombre,
                temperature=temperatura,
                lot=lote,
                mfg_date=f_fab,
                exp_date=f_exp,
                weight=peso_val
            )
            c.showPage()

        c.save()
        output.seek(0)

        # Nombre del archivo
        nombre_cliente = cliente_nombre.replace(" ", "_").replace("/", "-") or "cliente"
        filename = f"etiquetas_4x2_pedido_{pedido_id}_{nombre_cliente}.pdf"

        # Response con headers optimizados para iOS
        response = make_response(send_file(
            output,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        ))
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-Content-Type-Options'] = 'nosniff'

        return response

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error generando etiquetas: {e}")

        if request.method == 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "Error interno del servidor"}), 500

        flash("Error generando etiquetas. Intente de nuevo.", "danger")
        return redirect(url_for('detalles_pedido', pedido_id=pedido_id))


# ---------------------------------------------------------------------
# Generar etiquetas A4 (2 por página) a partir de los DetallePedido
# ---------------------------------------------------------------------
@app.route('/generar_etiqueta_detalle_a4/<int:pedido_id>', methods=['GET', 'POST'])
@login_required
def generar_etiqueta_detalle_a4(pedido_id):
    """
    Genera un PDF con etiquetas en formato A4 (2 etiquetas por página).
    """
    try:
        pedido = Pedido.query.get_or_404(pedido_id)

        # Obtener parámetros desde GET o POST
        fecha_ini = request.args.get('fecha_inicio') if request.method == 'GET' else request.form.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin') if request.method == 'GET' else request.form.get('fecha_fin')

        # Validar fechas
        if not fecha_ini or not fecha_fin:
            error_msg = "Debe indicar fecha de inicio y fin"
            if request.method == 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for('detalles_pedido', pedido_id=pedido_id))

        try:
            datetime.strptime(fecha_ini, '%Y-%m-%d')
            datetime.strptime(fecha_fin, '%Y-%m-%d')
        except ValueError:
            error_msg = "Formato de fecha inválido. Use YYYY-MM-DD"
            if request.method == 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"error": error_msg}), 400
            flash("Formato de fecha inválido", "danger")
            return redirect(url_for('detalles_pedido', pedido_id=pedido_id))

        # Filtrar los detalles (Story 3-0: excluir líneas originales del pedido)
        detalles = (DetallePedido.query
                    .filter_by(pedido_id=pedido_id)
                    .filter(DetallePedido.es_linea_pedido == False)
                    .filter(DetallePedido.fecha_fabricacion >= fecha_ini)
                    .filter(DetallePedido.fecha_fabricacion <= fecha_fin)
                    .order_by(DetallePedido.id.asc())
                    .all())

        if not detalles:
            error_msg = "No hay detalles en ese rango de fechas"
            if request.method == 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"error": error_msg}), 404
            flash(error_msg, "warning")
            return redirect(url_for('detalles_pedido', pedido_id=pedido_id))

        # Crear PDF A4
        output, c, page_width, page_height = create_a4_page_pdf()
        x_offset, y_top, y_bottom = get_a4_label_positions(page_width, page_height)
        logo_path = get_logo_path(basedir)
        cliente_nombre = pedido.cliente.nombre if getattr(pedido, "cliente", None) else ""

        etiqueta_contador = 0

        for d in detalles:
            producto_nombre = d.producto.nombre if getattr(d, "producto", None) else "N/A"
            temperatura = getattr(d.producto, "temperatura", None) or "N/A"

            # Formatear peso: usar peso real si existe, sino cajas
            peso_float = float(d.peso or 0)
            if peso_float > 0:
                peso_val = f"{peso_float:.2f} kg"
            else:
                peso_val = f"{int(d.cajas or 0)} uds"

            # Formatear fechas
            f_fab = d.fecha_fabricacion
            f_exp = d.fecha_expiracion
            if hasattr(d.fecha_fabricacion, "strftime"):
                f_fab = d.fecha_fabricacion.strftime("%Y-%m-%d")
            if hasattr(d.fecha_expiracion, "strftime"):
                f_exp = d.fecha_expiracion.strftime("%Y-%m-%d")

            # Null safety para trazabilidad
            lote = d.lote or "N/A"
            f_fab = f_fab or "N/A"
            f_exp = f_exp or "N/A"

            # Determinar posición (arriba o abajo)
            y_offset = y_top if etiqueta_contador % 2 == 0 else y_bottom

            draw_order_label_a4(
                c, logo_path, cliente_nombre, producto_nombre,
                temperatura, lote, f_fab, f_exp, peso_val,
                x_offset, y_offset
            )

            etiqueta_contador += 1

            # Nueva página después de 2 etiquetas
            if etiqueta_contador % 2 == 0:
                c.showPage()

        # Cerrar última página si quedó incompleta
        if etiqueta_contador % 2 != 0:
            c.showPage()

        c.save()
        output.seek(0)

        # Nombre del archivo
        nombre_cliente = (pedido.cliente.nombre if getattr(pedido, "cliente", None) else "cliente").replace(" ", "_").replace("/", "-")
        filename = f"etiquetas_A4_pedido_{pedido_id}_{nombre_cliente}.pdf"

        # Crear response
        response = make_response(send_file(
            output,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        ))

        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-Content-Type-Options'] = 'nosniff'

        return response

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error generando etiquetas A4: {e}")

        if request.method == 'GET' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "Error interno del servidor"}), 500

        flash("Error generando etiquetas A4. Intente de nuevo.", "danger")
        return redirect(url_for('detalles_pedido', pedido_id=pedido_id))


@app.route('/pedidos/<int:pedido_id>/preparar', methods=['GET', 'POST'])
@login_required
def preparar_pedido(pedido_id):
    """Deprecated: redirect to detalles_pedido (Story 3-0)."""
    return redirect(url_for('detalles_pedido', pedido_id=pedido_id), code=301)


@app.route('/pedidos/<int:pedido_id>/marcar_preparado', methods=['POST'])
@login_required
def marcar_preparado(pedido_id):
    """Valida trazabilidad y marca pedido como preparado (Story 3-0)."""
    pedido = Pedido.query.get_or_404(pedido_id)

    # ── Inmutabilidad post-facturación ─────────────────────────
    if pedido.estado == 'facturado':
        flash('No se puede modificar un pedido ya facturado', 'error')
        return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

    if pedido.estado == 'preparado':
        flash('El pedido ya está marcado como preparado', 'info')
        return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

    errores = []
    for detalle in pedido.detalles:
        if detalle.es_linea_pedido:
            # Línea original del vendedor: sin validación por ahora
            continue
        else:
            # Línea de preparación: requiere trazabilidad completa
            campos_faltantes = []
            if not detalle.lote:
                campos_faltantes.append('lote')
            if not detalle.fecha_fabricacion:
                campos_faltantes.append('fecha fabricación')
            if not detalle.fecha_expiracion:
                campos_faltantes.append('fecha expiración')
            if campos_faltantes:
                errores.append(f"{detalle.producto.nombre}: falta {', '.join(campos_faltantes)}")

    # Verificar que productos se_pesa tengan al menos una línea de preparación
    productos_pedido = set()
    productos_preparados = set()
    for detalle in pedido.detalles:
        if detalle.producto.se_pesa:
            if detalle.es_linea_pedido:
                productos_pedido.add(detalle.producto_id)
            else:
                productos_preparados.add(detalle.producto_id)
    sin_preparar = productos_pedido - productos_preparados
    for prod_id in sin_preparar:
        prod = Producto.query.get(prod_id)
        if prod:
            errores.append(f"{prod.nombre}: sin líneas de preparación (peso)")

    if errores:
        flash('No se puede marcar como preparado. Datos incompletos:', 'error')
        for err in errores:
            flash(err, 'error')
        return redirect(url_for('detalles_pedido', pedido_id=pedido.id))

    pedido.estado = 'preparado'
    db.session.commit()
    flash('Pedido marcado como preparado', 'success')
    return redirect(url_for('detalles_pedido', pedido_id=pedido.id))


N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL")  # ponlo en tu .env
try:
    N8N_WEBHOOK_TIMEOUT = int(os.environ.get("N8N_WEBHOOK_TIMEOUT", 30))
except (ValueError, TypeError):
    N8N_WEBHOOK_TIMEOUT = 30

@app.route('/pedidos/<int:pedido_id>/facturar', methods=['POST'])
@login_required
def facturar_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)

    # Sólo facturar si aún no fue facturado
    if pedido.estado == 'facturado':
        flash('El pedido ya está facturado.', 'info')
        return redirect(url_for('lista_pedidos'))

    # ── Validación de trazabilidad completa antes de facturar ──
    traz_errores = []
    for detalle in pedido.detalles:
        campos_faltantes = []
        if not detalle.lote:
            campos_faltantes.append('lote')
        if not detalle.fecha_fabricacion:
            campos_faltantes.append('fecha fabricación')
        if not detalle.fecha_expiracion:
            campos_faltantes.append('fecha expiración')
        if campos_faltantes:
            traz_errores.append(f"{detalle.producto.nombre}: falta {', '.join(campos_faltantes)}")
    if traz_errores:
        flash('No se puede facturar. Datos de trazabilidad incompletos:', 'error')
        for err in traz_errores:
            flash(err, 'error')
        return redirect(url_for('lista_pedidos'))

    payload = pedido_a_json(pedido)

    # ── Guard: verificar que N8N está configurado ──
    if not N8N_WEBHOOK_URL:
        app.logger.error(f'N8N_WEBHOOK_URL no configurada. No se puede facturar pedido {pedido_id}.')
        flash('Error de configuración: N8N_WEBHOOK_URL no está definida. Contacte al administrador.', 'danger')
        return redirect(url_for('lista_pedidos'))

    # ── Llamada al webhook N8N ──
    try:
        resp = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=N8N_WEBHOOK_TIMEOUT)
        resp.raise_for_status()
    except requests.Timeout:
        app.logger.error(f'Timeout al enviar pedido {pedido_id} a n8n ({N8N_WEBHOOK_TIMEOUT}s)')
        flash(f'Timeout — N8N no respondió en {N8N_WEBHOOK_TIMEOUT}s. Reintentar o verificar conexión.', 'danger')
        return redirect(url_for('lista_pedidos'))
    except requests.ConnectionError as e:
        app.logger.error(f'Error de conexión con n8n para pedido {pedido_id}: {e}')
        flash('Error de conexión con N8N. Verificar que el servicio está activo.', 'danger')
        return redirect(url_for('lista_pedidos'))
    except requests.HTTPError as e:
        err_resp = e.response
        status_code = err_resp.status_code
        try:
            error_body = err_resp.json()
            error_msg = error_body.get('message', error_body.get('error', str(error_body)))
        except Exception:
            error_msg = err_resp.text[:200] if err_resp.text else 'Sin detalle'
        app.logger.error(f'HTTP {status_code} de n8n para pedido {pedido_id}: {error_msg}')
        if 400 <= status_code < 500:
            flash(f'Error en facturación (HTTP {status_code}): {error_msg}', 'danger')
        else:
            flash('Error temporal en QuickBooks. Reintentar en unos momentos.', 'danger')
        return redirect(url_for('lista_pedidos'))
    except Exception as e:
        app.logger.error(f'Error inesperado al enviar pedido {pedido_id} a n8n: {e}')
        flash('Error al enviar a n8n. Intente de nuevo.', 'danger')
        return redirect(url_for('lista_pedidos'))

    # ── Extraer invoice_id de la respuesta N8N ──
    invoice_id = None
    try:
        resp_data = resp.json()
        invoice_id = resp_data.get('invoice_id')
    except Exception:
        app.logger.warning(f'No se pudo parsear JSON de respuesta n8n para pedido {pedido_id}')

    # ── Transacción atómica: marcar como facturado ──
    pedido.estado = 'facturado'
    pedido.invoice_id_qbo = invoice_id
    pedido.fecha_facturacion = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except Exception as e:
        app.logger.critical(f'CRITICAL: Webhook exitoso pero commit falló para pedido {pedido_id}: {e}')
        db.session.rollback()
        flash('Error interno al guardar. El pedido fue enviado a QuickBooks pero no se marcó como facturado. Contacte soporte.', 'danger')
        return redirect(url_for('lista_pedidos'))

    if invoice_id:
        flash(f'Factura generada: {invoice_id}', 'success')
    else:
        flash('Factura generada correctamente en QuickBooks.', 'success')
    return redirect(url_for('lista_pedidos'))
############################################
# RUTAS PARA SISTEMA DE PRECIOS
############################################

@app.route('/precios')
@login_required
@requiere_permiso_recurso('precios', 'leer')
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
            app.logger.error(f'Error al crear la lista de precios: {e}')
            flash('Error al crear la lista de precios. Intente de nuevo.', 'error')
    
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
            app.logger.error(f'Error al actualizar la lista de precios: {e}')
            flash('Error al actualizar la lista de precios. Intente de nuevo.', 'error')
    
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
        app.logger.error(f'Error al eliminar la lista: {e}')
        return jsonify({'error': 'Error al eliminar la lista'}), 500

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
        app.logger.error(f'Error al actualizar precio: {e}')
        return jsonify({'error': 'Error al actualizar precio'}), 500

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
        app.logger.error(f'Error al eliminar precio: {e}')
        return jsonify({'error': 'Error al eliminar precio'}), 500

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
        app.logger.error(f'Error al asignar lista: {e}')
        return jsonify({'error': 'Error al asignar lista'}), 500

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
        app.logger.error(f'Error al eliminar asignación: {e}')
        return jsonify({'error': 'Error al eliminar asignación'}), 500

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
        app.logger.error(f'Error al actualizar precio específico: {e}')
        return jsonify({'error': 'Error al actualizar precio'}), 500

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
        app.logger.error(f'Error al eliminar precio específico: {e}')
        return jsonify({'error': 'Error al eliminar precio'}), 500

# ---- API PARA OBTENER PRECIOS ----

@app.route('/api/precios/cliente/<int:cliente_id>/productos')
@login_required
def api_precios_cliente_productos(cliente_id):
    """API para obtener precios de todos los productos para un cliente específico"""
    resultado = []
    
    # 1. Primero buscar precios específicos cliente-producto
    precios_especificos = db.session.query(PrecioClienteProducto, Producto).join(
        Producto, PrecioClienteProducto.producto_id == Producto.id
    ).filter(
        PrecioClienteProducto.cliente_id == cliente_id,
        PrecioClienteProducto.activo == True
    ).all()
    
    productos_con_precio_especifico = set()
    
    for precio_esp, producto in precios_especificos:
        resultado.append({
            'id': producto.id,
            'nombre': producto.nombre,
            'precio': float(precio_esp.precio_base),
            'tipo_precio': 'específico',
            'precio_base': precio_esp.precio_base,
            'margen_jomar': precio_esp.margen_jomar,
            'margen_retail': precio_esp.margen_retail
        })
        productos_con_precio_especifico.add(producto.id)
    
    # 2. Buscar si el cliente tiene una lista asignada
    cliente_lista = ClienteListaPrecio.query.filter_by(
        cliente_id=cliente_id,
        activa=True
    ).first()
    
    if cliente_lista:
        # Solo obtener productos que están en la lista asignada al cliente
        precios_lista = db.session.query(PrecioProducto, Producto).join(
            Producto, PrecioProducto.producto_id == Producto.id
        ).filter(
            PrecioProducto.lista_precio_id == cliente_lista.lista_precio_id,
            PrecioProducto.activo == True,
            ~Producto.id.in_(productos_con_precio_especifico)  # Excluir los que ya tienen precio específico
        ).all()
        
        for precio_lista, producto in precios_lista:
            resultado.append({
                'id': producto.id,
                'nombre': producto.nombre,
                'precio': float(precio_lista.precio_base),
                'tipo_precio': 'lista_asignada',
                'precio_base': precio_lista.precio_base,
                'margen_jomar': precio_lista.margen_jomar,
                'margen_retail': precio_lista.margen_retail,
                'lista_nombre': cliente_lista.lista_precio.nombre
            })
    else:
        # Si no tiene lista asignada, usar lista por defecto
        lista_default = ListaPrecio.query.filter_by(es_default=True, activa=True).first()
        if lista_default:
            precios_default = db.session.query(PrecioProducto, Producto).join(
                Producto, PrecioProducto.producto_id == Producto.id
            ).filter(
                PrecioProducto.lista_precio_id == lista_default.id,
                PrecioProducto.activo == True,
                ~Producto.id.in_(productos_con_precio_especifico)  # Excluir los que ya tienen precio específico
            ).all()
            
            for precio_def, producto in precios_default:
                resultado.append({
                    'id': producto.id,
                    'nombre': producto.nombre,
                    'precio': float(precio_def.precio_base),
                    'tipo_precio': 'lista_default',
                    'precio_base': precio_def.precio_base,
                    'margen_jomar': precio_def.margen_jomar,
                    'margen_retail': precio_def.margen_retail,
                    'lista_nombre': lista_default.nombre
                })
    
    # Ordenar por nombre de producto
    resultado.sort(key=lambda x: x['nombre'])
    
    return jsonify(resultado)

# TAMBIÉN agregar esta nueva función para debugging:

@app.route('/api/precios/cliente/<int:cliente_id>/debug')
@login_required
def debug_precios_cliente(cliente_id):
    """API para debug - mostrar información detallada de precios de un cliente"""
    
    # Información del cliente
    cliente = Cliente.query.get_or_404(cliente_id)
    
    # Lista asignada al cliente
    cliente_lista = ClienteListaPrecio.query.filter_by(
        cliente_id=cliente_id,
        activa=True
    ).first()
    
    # Precios específicos
    precios_especificos_count = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id,
        activo=True
    ).count()
    
    debug_info = {
        'cliente': {
            'id': cliente.id,
            'nombre': cliente.nombre
        },
        'lista_asignada': None,
        'precios_especificos_count': precios_especificos_count
    }
    
    if cliente_lista:
        # Contar productos en la lista asignada
        productos_en_lista = PrecioProducto.query.filter_by(
            lista_precio_id=cliente_lista.lista_precio_id,
            activo=True
        ).count()
        
        debug_info['lista_asignada'] = {
            'id': cliente_lista.lista_precio_id,
            'nombre': cliente_lista.lista_precio.nombre,
            'productos_count': productos_en_lista,
            'es_default': cliente_lista.lista_precio.es_default
        }
    
    # Lista por defecto
    lista_default = ListaPrecio.query.filter_by(es_default=True, activa=True).first()
    if lista_default:
        productos_en_default = PrecioProducto.query.filter_by(
            lista_precio_id=lista_default.id,
            activo=True
        ).count()
        
        debug_info['lista_default'] = {
            'id': lista_default.id,
            'nombre': lista_default.nombre,
            'productos_count': productos_en_default
        }
    
    return jsonify(debug_info)

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
    resultado = []
    
    # 1. Precios específicos cliente-producto
    precios_especificos = db.session.query(PrecioClienteProducto, Producto).join(
        Producto, PrecioClienteProducto.producto_id == Producto.id
    ).filter(
        PrecioClienteProducto.cliente_id == cliente_id,
        PrecioClienteProducto.activo == True
    ).all()
    
    productos_procesados = set()
    
    for precio_esp, producto in precios_especificos:
        resultado.append({
            'producto_id': producto.id,
            'producto_nombre': producto.nombre,
            'precio_base': precio_esp.precio_base,
            'precio_jomar': precio_esp.precio_jomar,
            'precio_retail': precio_esp.precio_retail,
            'tipo_precio': 'específico',
            'margen_jomar': precio_esp.margen_jomar,
            'margen_retail': precio_esp.margen_retail
        })
        productos_procesados.add(producto.id)
    
    # 2. Productos de la lista asignada al cliente
    cliente_lista = ClienteListaPrecio.query.filter_by(
        cliente_id=cliente_id,
        activa=True
    ).first()
    
    if cliente_lista:
        precios_lista = db.session.query(PrecioProducto, Producto).join(
            Producto, PrecioProducto.producto_id == Producto.id
        ).filter(
            PrecioProducto.lista_precio_id == cliente_lista.lista_precio_id,
            PrecioProducto.activo == True,
            ~Producto.id.in_(productos_procesados)
        ).all()
        
        for precio_lista, producto in precios_lista:
            resultado.append({
                'producto_id': producto.id,
                'producto_nombre': producto.nombre,
                'precio_base': precio_lista.precio_base,
                'precio_jomar': precio_lista.precio_jomar,
                'precio_retail': precio_lista.precio_retail,
                'tipo_precio': 'lista_asignada',
                'margen_jomar': precio_lista.margen_jomar,
                'margen_retail': precio_lista.margen_retail,
                'lista_nombre': cliente_lista.lista_precio.nombre
            })
    
    return jsonify(resultado)

############################################
# Rutas de Productos
############################################


@app.route('/productos', methods=['GET', 'POST'])
@login_required
def productos():
    if request.method == 'POST':
        if isinstance(current_user, Vendedor) and not current_user.tiene_permiso('productos', 'crear'):
            return jsonify({'error': 'No tienes permisos para crear productos'}), 403
        try:
            nombre      = request.form['nombre']
            descripcion = request.form.get('descripcion', '')
            temperatura = request.form.get('temperatura', '')
            qbo_id      = request.form.get('qbo_id', '').strip() or None
            tax_rate    = float(request.form.get('tax_rate', 0.0))

            nuevo = Producto(
                nombre=nombre,
                descripcion=descripcion,
                temperatura=temperatura,
                qbo_id=qbo_id,
                tax_rate=tax_rate,
                se_pesa='se_pesa' in request.form
            )
            db.session.add(nuevo)
            db.session.commit()

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({
                    'message': 'Producto creado correctamente',
                    'producto': {
                        'id': nuevo.id,
                        'nombre': nuevo.nombre,
                        'descripcion': nuevo.descripcion,
                        'temperatura': nuevo.temperatura,
                        'qbo_id': nuevo.qbo_id,
                        'tax_rate': nuevo.tax_rate
                    }
                })
            else:
                flash('Producto creado exitosamente.', 'success')
                return redirect(url_for('productos'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error al crear producto: {e}")
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({'error': 'Error al crear el producto'}), 400
            flash('Error al crear el producto', 'danger')
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
        producto.qbo_id      = request.form.get('qbo_id', '').strip() or None
        producto.tax_rate    = float(request.form.get('tax_rate', 0.0))
        producto.se_pesa     = 'se_pesa' in request.form
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
        precio = obtener_precio_default_producto(p.id, 'base')
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
        app.logger.error(f'Error al registrar la recepción: {e}')
        return jsonify({"error": "Error al registrar la recepción"}), 500

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
        app.logger.error(f'Error al eliminar la recepción: {e}')
        return jsonify({"error": "Error al eliminar la recepción"}), 500

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
        return jsonify({'error': 'Error interno del servidor'}), 500
    
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
        return jsonify({"error": "Error interno del servidor"}), 500

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
        if not productos:
            flash("No se han proporcionado productos para la importación", "danger")
            return redirect(url_for('formulario_importacion'))
        db.session.commit()
        app.logger.info(f"Importación registrada con {len(productos)} productos.")
        flash("Importación registrada exitosamente", "success")
        return redirect(url_for('formulario_importacion'))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al registrar la importación: {e}", exc_info=True)
        flash("Error al registrar la importación. Intente de nuevo.", "danger")
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
    buffer.seek(0)
    nombre_archivo = f"reporte_factura_{numero_factura}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype='application/pdf'
    )

@app.route('/clientes', methods=['GET'])
@login_required
def mostrar_clientes():
    # Verificar si es vendedor del nuevo sistema
    if not isinstance(current_user, Vendedor):
        # Usuario del sistema anterior - mostrar todos
        clientes = (Cliente
                    .query
                    .order_by(Cliente.id.asc())
                    .all())
    else:
        # NUEVO: Filtrar por vendedor según su rol
        if current_user.rol.nombre == 'super_admin':
            # Super admin ve todos los clientes
            clientes = (Cliente
                        .query
                        .order_by(Cliente.id.asc())
                        .all())
        else:
            # Vendedor regular: solo ve SUS clientes asignados
            clientes = current_user.obtener_clientes_visibles()
            # Ordenar por ID para mantener consistencia
            clientes = sorted(clientes, key=lambda c: c.id)

    return render_template('clientes.html', clientes=clientes)


# TAMBIÉN modifica estas rutas si existen:

@app.route('/clientes/nuevo', methods=['POST'])
@login_required
@requiere_permiso_recurso('clientes', 'crear')
def nuevo_cliente():
    # VERIFICAR PERMISOS: Solo super_admin puede crear clientes
    if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
        return jsonify({"error": "No tienes permisos para crear clientes"}), 403
    
    try:
        nombre = request.form['nombre']
        qbo_id = request.form.get('qbo_id') or None
        
        # Evitar duplicados
        if qbo_id and Cliente.query.filter_by(qbo_id=qbo_id).first():
            return jsonify({"error": "Ya existe un cliente con ese QBO ID"}), 400
        
        nuevo_cliente = Cliente(nombre=nombre, qbo_id=qbo_id)
        db.session.add(nuevo_cliente)
        db.session.commit()
        return jsonify({
            "message": "Cliente registrado exitosamente",
            "cliente": nuevo_cliente.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/clientes/<int:cliente_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_cliente(cliente_id):
    # VERIFICAR PERMISOS
    if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
        # Vendedor regular: solo puede editar SUS clientes
        if not current_user.puede_ver_cliente(cliente_id):
            flash('No tienes permisos para editar este cliente', 'error')
            return redirect(url_for('mostrar_clientes'))
    
    cliente = Cliente.query.get_or_404(cliente_id)

    if request.method == 'POST':
        try:
            cliente.nombre = request.form['nombre']
            qbo_id = request.form.get('qbo_id') or None

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
            app.logger.error(f'Error al editar cliente: {e}')
            flash('Error al editar cliente. Intente de nuevo.', 'danger')
            return redirect(url_for('mostrar_clientes'))

    return render_template('cliente_form.html', cliente=cliente)

@app.route('/clientes/<int:cliente_id>', methods=['DELETE'])
@login_required
@requiere_permiso_recurso('clientes', 'eliminar')
def eliminar_cliente(cliente_id):
    # VERIFICAR PERMISOS: Solo super_admin puede eliminar clientes
    if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
        return jsonify({"error": "No tienes permisos para eliminar clientes"}), 403
    
    try:
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404
        db.session.delete(cliente)
        db.session.commit()
        return jsonify({"message": "Cliente eliminado exitosamente"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error interno del servidor"}), 500

# Rutas de CRM eliminadas

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
        app.logger.error(f"Error al generar el reporte: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    logging.warning("No se pudo configurar el locale 'en_US.UTF-8'. Se usará el formato de números por defecto.")

@app.route('/generar_reporte_pesos', methods=['GET'])
@login_required
def generar_reporte_pesos():
    import openpyxl
    from openpyxl.styles import Font, Alignment
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
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/etiquetas_vencimiento', methods=['GET', 'POST'])
@login_required
def etiquetas_vencimiento():
    """Genera etiquetas de vencimiento para productos."""
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
    """
    Genera PDF con etiquetas 4"x2" (dos por página, una arriba y otra abajo).
    Formato para etiquetas de vencimiento (sin cliente ni peso).
    """
    output, c, page_width, page_height = create_letter_page_pdf()
    logo_path = get_logo_path(basedir)
    x_centrado = get_centered_x(page_width)

    etiqueta_num = 0
    while etiqueta_num < cantidad:
        # Primera etiqueta: arriba
        y_pos_1 = page_height - LABEL_HEIGHT
        draw_expiration_label(c, logo_path, datos, x_centrado, y_pos_1)
        etiqueta_num += 1

        # Segunda etiqueta: abajo
        if etiqueta_num < cantidad:
            y_pos_2 = page_height - 2 * LABEL_HEIGHT
            draw_expiration_label(c, logo_path, datos, x_centrado, y_pos_2)
            etiqueta_num += 1

        # Nueva página si hay más etiquetas
        if etiqueta_num < cantidad:
            c.showPage()

    c.save()
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="etiquetas_vencimiento.pdf", mimetype='application/pdf')


try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    logging.warning("No se pudo configurar el locale 'en_US.UTF-8'. Se usará el formato de números por defecto.")



def validar_estructura_csv(csv_input, campos_requeridos):
    """Valida que el CSV tenga los campos requeridos"""
    try:
        primera_fila = next(csv_input)
        campos_csv = set(primera_fila.keys())
        campos_faltantes = set(campos_requeridos) - campos_csv
        
        if campos_faltantes:
            raise ValueError(f"Campos faltantes en CSV: {', '.join(campos_faltantes)}")
        
        # Resetear el iterator (necesario para pandas o re-leer el archivo)
        return True
    except StopIteration:
        raise ValueError("El archivo CSV está vacío")

def limpiar_codigo(codigo):
    """Limpia y normaliza códigos de productos/clientes"""
    if not codigo:
        return None
    return str(codigo).strip().upper()

def validar_precio(precio_str):
    """Valida y convierte precio a float"""
    try:
        precio = float(precio_str)
        if precio < 0:
            raise ValueError("El precio no puede ser negativo")
        return precio
    except (ValueError, TypeError):
        raise ValueError(f"Precio inválido: {precio_str}")

def validar_margen(margen_str, default=1.0):
    """Valida y convierte margen a float"""
    if not margen_str or margen_str.strip() == '':
        return default
    try:
        margen = float(margen_str)
        if margen <= 0:
            raise ValueError("El margen debe ser mayor a 0")
        return margen
    except (ValueError, TypeError):
        raise ValueError(f"Margen inválido: {margen_str}")

# Función mejorada para procesar precios por lista
def procesar_precios_por_lista_mejorado(csv_input, lista_precio_id, resultados):
    """
    Versión mejorada del procesamiento de precios por lista con más validaciones
    """
    if not lista_precio_id:
        raise ValueError("Se requiere seleccionar una lista de precios")
    
    lista = ListaPrecio.query.get(lista_precio_id)
    if not lista:
        raise ValueError("Lista de precios no encontrada")
    
    # Validar estructura del CSV
    campos_requeridos = ['codigo_producto', 'precio_base']
    
    # Contar total de filas para progress tracking
    filas_procesadas = 0
    batch_size = 100  # Procesar en lotes para mejor rendimiento
    
    for fila_num, fila in enumerate(csv_input, start=2):
        try:
            # Limpiar y validar código de producto
            codigo_producto = limpiar_codigo(fila.get('codigo_producto'))
            if not codigo_producto:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Código de producto es obligatorio')
                continue
            
            # Buscar producto
            producto = Producto.query.filter_by(codigo=codigo_producto).first()
            if not producto:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Producto {codigo_producto} no encontrado')
                continue
            
            # Validar y convertir precio base
            try:
                precio_base = validar_precio(fila.get('precio_base', ''))
            except ValueError as e:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: {str(e)}')
                continue
            
            # Obtener y validar márgenes
            try:
                margen_jomar = validar_margen(fila.get('margen_jomar', ''), 1.0)
                margen_retail = validar_margen(fila.get('margen_retail', ''), 1.2)
            except ValueError as e:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: {str(e)}')
                continue
            
            # Verificar límites razonables para márgenes
            if margen_jomar > 10 or margen_retail > 10:
                resultados['warnings'].append(f'Fila {fila_num}: Márgenes muy altos para producto {codigo_producto}')
            
            # Buscar precio existente o crear nuevo
            precio_existente = PrecioProducto.query.filter_by(
                lista_precio_id=lista_precio_id,
                producto_id=producto.id
            ).first()
            
            if precio_existente:
                # Actualizar existente
                precio_existente.precio_base = precio_base
                precio_existente.margen_jomar = margen_jomar
                precio_existente.margen_retail = margen_retail
                precio_existente.calcular_precios()
                precio_existente.fecha_actualizacion = datetime.utcnow()
                accion = 'actualizado'
            else:
                # Crear nuevo
                nuevo_precio = PrecioProducto(
                    lista_precio_id=lista_precio_id,
                    producto_id=producto.id,
                    precio_base=precio_base,
                    margen_jomar=margen_jomar,
                    margen_retail=margen_retail
                )
                nuevo_precio.calcular_precios()
                db.session.add(nuevo_precio)
                accion = 'creado'
            
            resultados['procesados'] += 1
            resultados['detalles'].append(f'Fila {fila_num}: Precio para {codigo_producto} {accion} exitosamente')
            
            filas_procesadas += 1
            
            # Commit en lotes para mejor rendimiento
            if filas_procesadas % batch_size == 0:
                db.session.flush()
                
        except Exception as e:
            resultados['errores'] += 1
            resultados['detalles'].append(f'Fila {fila_num}: Error inesperado - {str(e)}')
    
    return resultados

# Función para generar reporte de carga
@app.route('/precios/generar-reporte-carga', methods=['POST'])
@login_required
def generar_reporte_carga():
    """Genera un reporte detallado de la carga de precios"""
    try:
        datos = request.get_json()
        tipo_reporte = datos.get('tipo', 'lista_precios')
        lista_id = datos.get('lista_id')
        
        if tipo_reporte == 'lista_precios' and lista_id:
            lista = ListaPrecio.query.get(lista_id)
            if not lista:
                return jsonify({'error': 'Lista no encontrada'}), 404
            
            # Obtener precios de la lista
            precios = db.session.query(PrecioProducto, Producto).join(
                Producto, PrecioProducto.producto_id == Producto.id
            ).filter(PrecioProducto.lista_precio_id == lista_id).all()
            
            output = io.StringIO()
            fieldnames = ['codigo_producto', 'nombre_producto', 'precio_base', 
                         'precio_jomar', 'precio_retail', 'margen_jomar', 'margen_retail', 
                         'fecha_actualizacion']
            
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            for precio, producto in precios:
                writer.writerow({
                    'codigo_producto': producto.codigo,
                    'nombre_producto': producto.nombre,
                    'precio_base': precio.precio_base,
                    'precio_jomar': precio.precio_jomar,
                    'precio_retail': precio.precio_retail,
                    'margen_jomar': precio.margen_jomar,
                    'margen_retail': precio.margen_retail,
                    'fecha_actualizacion': precio.fecha_actualizacion.strftime('%Y-%m-%d %H:%M:%S') if precio.fecha_actualizacion else ''
                })
            
            csv_data = output.getvalue()
            output.close()
            
            response = make_response(csv_data)
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename=reporte_precios_{lista.nombre.replace(" ", "_")}.csv'
            
            return response
        
        return jsonify({'error': 'Tipo de reporte no soportado'}), 400
        
    except Exception as e:
        app.logger.error(f'Error generando reporte: {e}')
        return jsonify({'error': 'Error generando reporte'}), 500

# Función para validar CSV antes de procesarlo
@app.route('/precios/validar-csv', methods=['POST'])
@login_required
def validar_csv_precios():
    """Valida un CSV antes de procesarlo completamente"""
    # Tipos MIME válidos para archivos CSV
    ALLOWED_MIME_TYPES = ['text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel']
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB máximo

    try:
        if 'archivo_csv' not in request.files:
            return jsonify({'error': 'No se encontró archivo CSV'}), 400

        archivo = request.files['archivo_csv']
        if archivo.filename == '':
            return jsonify({'error': 'No se seleccionó archivo'}), 400

        # Validar nombre de archivo con secure_filename
        filename = secure_filename(archivo.filename)
        if not filename.lower().endswith('.csv'):
            return jsonify({'error': 'El archivo debe ser CSV'}), 400

        # Validar tipo MIME
        if archivo.content_type and archivo.content_type not in ALLOWED_MIME_TYPES:
            app.logger.warning(f'Intento de validar archivo con MIME type no permitido: {archivo.content_type}')
            return jsonify({'error': 'Tipo de archivo no permitido'}), 400

        tipo_carga = request.form.get('tipo_carga')

        # Leer contenido y validar tamaño
        content = archivo.stream.read()
        if len(content) > MAX_FILE_SIZE:
            return jsonify({'error': 'El archivo excede el tamaño máximo permitido (10MB)'}), 400

        # Validar que el contenido es texto UTF-8 válido
        try:
            decoded_content = content.decode("UTF8")
        except UnicodeDecodeError:
            return jsonify({'error': 'El archivo debe estar codificado en UTF-8'}), 400

        # Leer primeras 10 filas para validación
        stream = io.StringIO(decoded_content, newline=None)
        csv_input = csv.DictReader(stream)
        
        validacion = {
            'valido': True,
            'errores': [],
            'warnings': [],
            'preview': [],
            'total_filas': 0
        }
        
        # Definir campos requeridos según tipo
        campos_requeridos = {
            'lista_precios': ['codigo_producto', 'precio_base'],
            'asignacion_clientes': ['codigo_cliente', 'nombre_lista_precio'],
            'precios_especificos': ['codigo_cliente', 'codigo_producto', 'precio_base']
        }
        
        if tipo_carga not in campos_requeridos:
            validacion['valido'] = False
            validacion['errores'].append('Tipo de carga no válido')
            return jsonify(validacion), 400
        
        # Validar encabezados
        try:
            primera_fila = next(csv_input)
            campos_csv = set(primera_fila.keys())
            campos_faltantes = set(campos_requeridos[tipo_carga]) - campos_csv
            
            if campos_faltantes:
                validacion['valido'] = False
                validacion['errores'].append(f'Campos faltantes: {", ".join(campos_faltantes)}')
            
            # Agregar primera fila al preview
            validacion['preview'].append(primera_fila)
            validacion['total_filas'] = 1
            
        except StopIteration:
            validacion['valido'] = False
            validacion['errores'].append('El archivo CSV está vacío')
            return jsonify(validacion), 400
        
        # Validar siguientes filas (máximo 9 más para preview)
        for i, fila in enumerate(csv_input):
            if i >= 9:  # Solo revisar 10 filas total
                break
                
            validacion['preview'].append(fila)
            validacion['total_filas'] += 1
            
            # Validaciones básicas según tipo
            if tipo_carga == 'lista_precios':
                if not fila.get('codigo_producto', '').strip():
                    validacion['warnings'].append(f'Fila {i+2}: Código producto vacío')
                
                try:
                    precio = float(fila.get('precio_base', 0))
                    if precio <= 0:
                        validacion['warnings'].append(f'Fila {i+2}: Precio base debe ser mayor a 0')
                except ValueError:
                    validacion['warnings'].append(f'Fila {i+2}: Precio base no es un número válido')
        
        # Contar filas totales (reset stream)
        archivo.stream.seek(0)
        stream = io.StringIO(archivo.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        validacion['total_filas'] = sum(1 for _ in csv_input)
        
        return jsonify(validacion), 200
        
    except Exception as e:
        app.logger.error(f'Error validando archivo: {e}')
        return jsonify({'error': 'Error validando archivo'}), 500

# Agregar logging para mejor debugging
@app.route('/precios/log-carga', methods=['POST'])
@login_required  
def log_carga_precios():
    """Registra actividades de carga masiva para auditoría"""
    try:
        datos = request.get_json()
        
        # Aquí podrías agregar a una tabla de auditoría
        logging.info(f"Carga masiva ejecutada por usuario {current_user.username}: "
                    f"Tipo: {datos.get('tipo')}, "
                    f"Registros: {datos.get('procesados', 0)}, "
                    f"Errores: {datos.get('errores', 0)}")
        
        return jsonify({'status': 'logged'}), 200
        
    except Exception as e:
        return jsonify({'error': 'Error interno del servidor'}), 500

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('carga_masiva.log'),
        logging.StreamHandler()
    ]
)

@app.route('/precios/carga-masiva')
@login_required
def carga_masiva_precios():
    """Interfaz para carga masiva de precios mediante CSV"""
    listas = ListaPrecio.query.filter_by(activa=True).all()
    clientes = Cliente.query.all()
    productos = Producto.query.all()
    
    return render_template('precios/carga_masiva.html', 
                         listas=listas,
                         clientes=clientes,
                         productos=productos)

@app.route('/precios/procesar-csv', methods=['POST'])
@login_required
def procesar_csv_precios():
    """Procesar archivo CSV con precios"""
    # Tipos MIME válidos para archivos CSV
    ALLOWED_MIME_TYPES = ['text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel']
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB máximo

    try:
        if 'archivo_csv' not in request.files:
            return jsonify({'error': 'No se encontró archivo CSV'}), 400

        archivo = request.files['archivo_csv']
        if archivo.filename == '':
            return jsonify({'error': 'No se seleccionó archivo'}), 400

        # Validar nombre de archivo con secure_filename
        filename = secure_filename(archivo.filename)
        if not filename.lower().endswith('.csv'):
            return jsonify({'error': 'El archivo debe ser CSV'}), 400

        # Validar tipo MIME
        if archivo.content_type and archivo.content_type not in ALLOWED_MIME_TYPES:
            app.logger.warning(f'Intento de subir archivo con MIME type no permitido: {archivo.content_type}')
            return jsonify({'error': 'Tipo de archivo no permitido'}), 400

        # Leer contenido y validar tamaño
        content = archivo.stream.read()
        if len(content) > MAX_FILE_SIZE:
            return jsonify({'error': 'El archivo excede el tamaño máximo permitido (10MB)'}), 400

        tipo_carga = request.form.get('tipo_carga')
        lista_precio_id = request.form.get('lista_precio_id')

        # Validar que el contenido es texto UTF-8 válido
        try:
            decoded_content = content.decode("UTF8")
        except UnicodeDecodeError:
            return jsonify({'error': 'El archivo debe estar codificado en UTF-8'}), 400

        # Leer archivo CSV
        stream = io.StringIO(decoded_content, newline=None)
        csv_input = csv.DictReader(stream)
        
        resultados = {
            'procesados': 0,
            'errores': 0,
            'warnings': [],
            'detalles': []
        }
        
        if tipo_carga == 'lista_precios':
            resultados = procesar_precios_por_lista(csv_input, lista_precio_id, resultados)
        elif tipo_carga == 'asignacion_clientes':
            resultados = procesar_asignacion_clientes(csv_input, resultados)
        elif tipo_carga == 'precios_especificos':
            resultados = procesar_precios_especificos(csv_input, resultados)
        else:
            return jsonify({'error': 'Tipo de carga no válido'}), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'mensaje': f'Procesamiento completado. {resultados["procesados"]} registros procesados, {resultados["errores"]} errores.',
            'resultados': resultados
        }), 200
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error procesando archivo: {e}')
        return jsonify({'error': 'Error procesando archivo'}), 500

def procesar_precios_por_lista(csv_input, lista_precio_id, resultados):
    """Procesar CSV para actualizar precios en una lista específica"""
    if not lista_precio_id:
        raise ValueError("Se requiere seleccionar una lista de precios")
    
    lista = ListaPrecio.query.get(lista_precio_id)
    if not lista:
        raise ValueError("Lista de precios no encontrada")
    
    for fila_num, fila in enumerate(csv_input, start=2):
        try:
            # Validar campos requeridos
            codigo_producto = fila.get('codigo_producto', '').strip()
            precio_base = fila.get('precio_base', '').strip()
            
            if not codigo_producto or not precio_base:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Código producto y precio base son obligatorios')
                continue
            
            # CORRECCIÓN: Buscar producto por ID (ya que los valores en CSV son IDs)
            try:
                producto_id = int(codigo_producto)
                producto = Producto.query.get(producto_id)
            except ValueError:
                # Si no es un número, intentar buscar por qbo_id o nombre
                producto = Producto.query.filter(
                    (Producto.qbo_id == codigo_producto) | 
                    (Producto.nombre.ilike(f'%{codigo_producto}%'))
                ).first()
            
            if not producto:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Producto {codigo_producto} no encontrado')
                continue
            
            # Validar precio base
            try:
                precio_base = float(precio_base)
                if precio_base < 0:
                    raise ValueError("Precio no puede ser negativo")
            except ValueError:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Precio base inválido')
                continue
            
            # Obtener márgenes (opcionales, usar defaults si no se especifican)
            margen_jomar = float(fila.get('margen_jomar', 1.0) or 1.0)
            margen_retail = float(fila.get('margen_retail', 1.2) or 1.2)
            
            # Buscar precio existente o crear nuevo
            precio_existente = PrecioProducto.query.filter_by(
                lista_precio_id=lista_precio_id,
                producto_id=producto.id
            ).first()
            
            if precio_existente:
                # Actualizar existente
                precio_existente.precio_base = precio_base
                precio_existente.margen_jomar = margen_jomar
                precio_existente.margen_retail = margen_retail
                precio_existente.calcular_precios()
                precio_existente.fecha_actualizacion = datetime.utcnow()
                accion = 'actualizado'
            else:
                # Crear nuevo
                nuevo_precio = PrecioProducto(
                    lista_precio_id=lista_precio_id,
                    producto_id=producto.id,
                    precio_base=precio_base,
                    margen_jomar=margen_jomar,
                    margen_retail=margen_retail
                )
                nuevo_precio.calcular_precios()
                db.session.add(nuevo_precio)
                accion = 'creado'
            
            resultados['procesados'] += 1
            resultados['detalles'].append(f'Fila {fila_num}: Precio para producto {producto.nombre} (ID: {producto.id}) {accion} exitosamente')
            
        except Exception as e:
            resultados['errores'] += 1
            resultados['detalles'].append(f'Fila {fila_num}: Error - {str(e)}')
    
    return resultados

def procesar_asignacion_clientes(csv_input, resultados):
    """Procesar CSV para asignar listas de precios a clientes"""
    for fila_num, fila in enumerate(csv_input, start=2):
        try:
            codigo_cliente = fila.get('codigo_cliente', '').strip()
            nombre_lista = fila.get('nombre_lista_precio', '').strip()
            
            if not codigo_cliente or not nombre_lista:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Código cliente y nombre lista son obligatorios')
                continue
            
            # Buscar cliente
            cliente = Cliente.query.filter_by(codigo=codigo_cliente).first()
            if not cliente:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Cliente {codigo_cliente} no encontrado')
                continue
            
            # Buscar lista de precios
            lista = ListaPrecio.query.filter_by(nombre=nombre_lista, activa=True).first()
            if not lista:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Lista {nombre_lista} no encontrada')
                continue
            
            # Verificar si ya existe asignación activa
            asignacion_existente = ClienteListaPrecio.query.filter_by(
                cliente_id=cliente.id,
                activa=True
            ).first()
            
            if asignacion_existente:
                # Desactivar asignación anterior
                asignacion_existente.activa = False
                resultados['warnings'].append(f'Cliente {codigo_cliente}: Lista anterior desactivada')
            
            # Crear nueva asignación
            nueva_asignacion = ClienteListaPrecio(
                cliente_id=cliente.id,
                lista_precio_id=lista.id
            )
            db.session.add(nueva_asignacion)
            
            resultados['procesados'] += 1
            resultados['detalles'].append(f'Fila {fila_num}: Lista {nombre_lista} asignada a cliente {codigo_cliente}')
            
        except Exception as e:
            resultados['errores'] += 1
            resultados['detalles'].append(f'Fila {fila_num}: Error - {str(e)}')
    
    return resultados

def procesar_precios_especificos(csv_input, resultados):
    """Procesar CSV para precios específicos cliente-producto"""
    for fila_num, fila in enumerate(csv_input, start=2):
        try:
            codigo_cliente = fila.get('codigo_cliente', '').strip()
            codigo_producto = fila.get('codigo_producto', '').strip()
            precio_base = fila.get('precio_base', '').strip()
            
            if not codigo_cliente or not codigo_producto or not precio_base:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Cliente, producto y precio base son obligatorios')
                continue
            
            # Buscar cliente por ID o nombre
            try:
                cliente_id = int(codigo_cliente)
                cliente = Cliente.query.get(cliente_id)
            except ValueError:
                cliente = Cliente.query.filter(Cliente.nombre.ilike(f'%{codigo_cliente}%')).first()
            
            if not cliente:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Cliente {codigo_cliente} no encontrado')
                continue
            
            # CORRECCIÓN: Buscar producto por ID (igual que arriba)
            try:
                producto_id = int(codigo_producto)
                producto = Producto.query.get(producto_id)
            except ValueError:
                producto = Producto.query.filter(
                    (Producto.qbo_id == codigo_producto) | 
                    (Producto.nombre.ilike(f'%{codigo_producto}%'))
                ).first()
            
            if not producto:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Producto {codigo_producto} no encontrado')
                continue
            
            # Validar precio
            try:
                precio_base = float(precio_base)
                if precio_base < 0:
                    raise ValueError("Precio no puede ser negativo")
            except ValueError:
                resultados['errores'] += 1
                resultados['detalles'].append(f'Fila {fila_num}: Precio base inválido')
                continue
            
            # Obtener márgenes
            margen_jomar = float(fila.get('margen_jomar', 1.0) or 1.0)
            margen_retail = float(fila.get('margen_retail', 1.2) or 1.2)
            
            # Buscar precio específico existente o crear nuevo
            precio_existente = PrecioClienteProducto.query.filter_by(
                cliente_id=cliente.id,
                producto_id=producto.id,
                activo=True
            ).first()
            
            if precio_existente:
                # Actualizar existente
                precio_existente.precio_base = precio_base
                precio_existente.margen_jomar = margen_jomar
                precio_existente.margen_retail = margen_retail
                precio_existente.calcular_precios()
                precio_existente.fecha_actualizacion = datetime.utcnow()
                accion = 'actualizado'
            else:
                # Crear nuevo
                nuevo_precio = PrecioClienteProducto(
                    cliente_id=cliente.id,
                    producto_id=producto.id,
                    precio_base=precio_base,
                    margen_jomar=margen_jomar,
                    margen_retail=margen_retail
                )
                nuevo_precio.calcular_precios()
                db.session.add(nuevo_precio)
                accion = 'creado'
            
            resultados['procesados'] += 1
            resultados['detalles'].append(f'Fila {fila_num}: Precio específico {cliente.nombre}-{producto.nombre} {accion}')
            
        except Exception as e:
            resultados['errores'] += 1
            resultados['detalles'].append(f'Fila {fila_num}: Error - {str(e)}')
    
    return resultados

@app.route('/precios/descargar-plantilla/<tipo>')
@login_required
def descargar_plantilla_csv(tipo):
    """Descargar plantillas CSV para diferentes tipos de carga"""
    output = io.StringIO()
    
    if tipo == 'lista_precios':
        fieldnames = ['codigo_producto', 'precio_base', 'margen_jomar', 'margen_retail']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        # Obtener algunos productos reales para el ejemplo
        productos_ejemplo = Producto.query.limit(3).all()
        if productos_ejemplo:
            for producto in productos_ejemplo:
                writer.writerow({
                    'codigo_producto': str(producto.id),  # Usar ID real
                    'precio_base': '25.50',
                    'margen_jomar': '1.0',
                    'margen_retail': '1.2'
                })
        else:
            # Fallback si no hay productos
            writer.writerow({
                'codigo_producto': '1',
                'precio_base': '25.50',
                'margen_jomar': '1.0',
                'margen_retail': '1.2'
            })
        filename = 'plantilla_precios_lista.csv'
        
    elif tipo == 'asignacion_clientes':
        fieldnames = ['codigo_cliente', 'nombre_lista_precio']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        # Obtener ejemplos reales
        cliente_ejemplo = Cliente.query.first()
        lista_ejemplo = ListaPrecio.query.first()
        
        writer.writerow({
            'codigo_cliente': str(cliente_ejemplo.id) if cliente_ejemplo else '1',
            'nombre_lista_precio': lista_ejemplo.nombre if lista_ejemplo else 'Lista Mayorista'
        })
        filename = 'plantilla_asignacion_clientes.csv'
        
    elif tipo == 'precios_especificos':
        fieldnames = ['codigo_cliente', 'codigo_producto', 'precio_base', 'margen_jomar', 'margen_retail']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        cliente_ejemplo = Cliente.query.first()
        producto_ejemplo = Producto.query.first()
        
        writer.writerow({
            'codigo_cliente': str(cliente_ejemplo.id) if cliente_ejemplo else '1',
            'codigo_producto': str(producto_ejemplo.id) if producto_ejemplo else '1',
            'precio_base': '23.75',
            'margen_jomar': '1.0',
            'margen_retail': '1.15'
        })
        filename = 'plantilla_precios_especificos.csv'
    else:
        return jsonify({'error': 'Tipo de plantilla no válido'}), 400
    
    # Crear respuesta con archivo CSV
    csv_data = output.getvalue()
    output.close()
    
    response = make_response(csv_data)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    
    return response

if __name__ == '__main__':
    # Configuración para desarrollo local
    if os.environ.get('FLASK_ENV') == 'development':
        ip_servidor = obtener_ip_servidor()
        app.logger.info(f"La aplicación está disponible en la IP: {ip_servidor}:{5002}")
        app.run(debug=True, host='0.0.0.0', port=5002)
    else:
        # Configuración para producción (Heroku)
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=False)
