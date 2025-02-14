from flask import Flask, render_template, request, redirect, send_file, jsonify, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import io
import pandas as pd
from io import BytesIO
from sqlalchemy.orm import registry, Session
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta  # Asegúrate de instalar python-dateutil
import openpyxl
from openpyxl.styles import Font, Alignment
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from flask_migrate import Migrate
import os
import xlsxwriter
import socket
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import locale
import traceback


app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'productos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'supersecretkey'


db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Definición de los modelos
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(200))
    temperatura = db.Column(db.String(50))
    
    facturaciones = db.relationship('Facturacion', back_populates='producto', cascade="all, delete-orphan")
    recepciones = db.relationship('Recepcion', back_populates='producto', lazy=True, cascade="all, delete-orphan")
    importaciones = db.relationship('Importacion', back_populates='producto', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'temperatura': self.temperatura
        }


class Cliente(db.Model):
    __tablename__ = 'cliente'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    
    facturaciones = db.relationship('Facturacion', back_populates='cliente', cascade="all, delete-orphan")

    def to_dict(self):
        return {'id': self.id, 'nombre': self.nombre}


class Facturacion(db.Model):
    __tablename__ = 'facturacion'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    peso = db.Column(db.Float, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    lote = db.Column(db.String(50), nullable=False)
    fecha_fabricacion = db.Column(db.String(10), nullable=False)  # Formato 'YYYY-MM-DD'
    fecha_expiracion = db.Column(db.String(10), nullable=False)   # Formato 'YYYY-MM-DD'
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
    flete_local = db.Column(db.Float, nullable=True)  # Campo que almacena el Flete Local
    costo_total_almacen = db.Column(db.Float, nullable=True)  # Campo que almacena el Costo en Almacén
    
    producto = db.relationship('Producto', back_populates='importaciones')

def obtener_ip_servidor():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No se envía ningún dato. La conexión es ficticia para obtener la IP local.
        s.connect(('8.8.8.8', 80))
        ip_servidor = s.getsockname()[0]
    except Exception:
        ip_servidor = '127.0.0.1'
    finally:
        s.close()
    return ip_servidor

# Ruta principal
@app.route('/')
def index():
    ip_servidor = obtener_ip_servidor()
    port = 5002
    return render_template('index.html', server_ip=f"{ip_servidor}:{port}")


# Rutas para Productos
@app.route('/productos', methods=['POST'])
def crear_producto():
    nombre = request.form['nombre']
    descripcion = request.form['descripcion']
    temperatura = request.form['temperatura']
    
    nuevo_producto = Producto(nombre=nombre, descripcion=descripcion, temperatura=temperatura)
    db.session.add(nuevo_producto)
    db.session.commit()

    # Preparar los datos del producto para enviarlos en la respuesta
    producto_data = nuevo_producto.to_dict()

    return jsonify({'message': 'Producto creado exitosamente.', 'producto': producto_data}), 200


@app.route('/productos')
def mostrar_productos():
    productos = Producto.query.all()
    return render_template('productos.html', productos=productos)


@app.route('/productos/<int:producto_id>/eliminar', methods=['POST'])
def eliminar_producto(producto_id):
    try:
        producto = Producto.query.get(producto_id)
        if producto:
            db.session.delete(producto)
            db.session.commit()
            return jsonify({'message': 'Producto eliminado correctamente.'}), 200
        else:
            return jsonify({'error': 'Producto no encontrado.'}), 404
    except Exception as e:
        print(f"Error al eliminar el producto: {e}")
        return jsonify({'error': 'Error al eliminar el producto.'}), 500


@app.route('/api/productos', methods=['GET'])
def obtener_productos_api():
    productos = Producto.query.all()
    productos_data = [{"id": p.id, "nombre": p.nombre} for p in productos]
    return jsonify(productos_data)


# Manejador para sobreescribir métodos HTTP
@app.before_request
def override_method():
    if request.method == 'POST' and '_method' in request.form:
        method = request.form['_method'].upper()
        if method in ['PUT', 'DELETE']:
            request.environ['REQUEST_METHOD'] = method


# Rutas para Recepciones
@app.route('/recepciones')
def mostrar_recepciones():
    productos = Producto.query.all()
    recepciones = Recepcion.query.all()

    # Obtener la última recepción registrada
    ultima_recepcion = Recepcion.query.order_by(Recepcion.id.desc()).first()

    return render_template('recepciones.html', productos=productos, recepciones=recepciones, ultima_recepcion=ultima_recepcion)


@app.route('/api/recepciones', methods=['GET'])
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

        # Preparar los datos de la recepción para enviarlos en la respuesta
        recepcion_data = nueva_recepcion.to_dict()

        return jsonify({
            "message": "Recepción registrada exitosamente",
            "recepcion": recepcion_data
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al registrar la recepción: {str(e)}"}), 500


@app.route('/recepciones/<int:id>', methods=['DELETE'])
def eliminar_recepcion(id):
    recepcion = Recepcion.query.get_or_404(id)
    try:
        db.session.delete(recepcion)
        db.session.commit()
        return jsonify({"message": "Recepción eliminada con éxito"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar la recepción: {str(e)}"}), 500


@app.route('/facturacion', methods=['GET', 'POST'])
def facturacion():
    if request.method == 'GET':
        productos = Producto.query.all()
        clientes = Cliente.query.all()

        # Obtener la fecha de hoy
        today = datetime.utcnow().date()

        # Cargar los datos del último cliente y producto seleccionados desde la sesión
        previous_data = {
            'producto_id': session.get('producto_id', ''),
            'cliente_id': session.get('cliente_id', ''),
            'lote': session.get('lote', ''),
            'fecha_fabricacion': session.get('fecha_fabricacion', '')
        }

        # Si hay un cliente seleccionado, obtener sus facturaciones del día de hoy
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





@app.route('/ultimos_facturaciones', methods=['GET'])
def ultimos_facturaciones():
    cliente_id = request.args.get('cliente_id', type=int)  # Obtener el cliente actual si está disponible
    hoy = datetime.utcnow().date()

    # Usar join para obtener el nombre del producto y del cliente
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
        'producto': facturacion.producto_nombre,  # Devolver el nombre del producto
        'cliente': facturacion.cliente_nombre,    # Devolver el nombre del cliente
        'peso': facturacion.peso,
        'lote': facturacion.lote,
        'fecha_fabricacion': facturacion.fecha_fabricacion,
        'fecha_expiracion': facturacion.fecha_expiracion,
        'fecha_registro': facturacion.fecha_registro
    } for facturacion in facturaciones])







@app.route('/facturacion/registrar', methods=['POST'])
def registrar_facturacion():
    try:
        producto_id = request.form['producto_id']
        cliente_id = request.form['cliente_id']
        peso = request.form['peso']
        lote = request.form['lote']
        fecha_fabricacion = request.form['fecha_fabricacion']
        fecha_fabricacion_date = datetime.strptime(fecha_fabricacion, '%Y-%m-%d')

        # Calcula la fecha de expiración
        fecha_expiracion = fecha_fabricacion_date + timedelta(days=365)

        # Guarda los datos en la sesión (sin el peso)
        session['producto_id'] = producto_id
        session['cliente_id'] = cliente_id
        session['lote'] = lote
        session['fecha_fabricacion'] = fecha_fabricacion

        # Registra la nueva facturación
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


def gestionar_facturacion():
    try:
        producto_id = request.form['producto_id']
        cliente_id = request.form['cliente_id']
        peso = request.form['peso']
        lote = request.form['lote']
        fecha_fabricacion = request.form['fecha_fabricacion']
        fecha_fabricacion_date = datetime.strptime(fecha_fabricacion, '%Y-%m-%d')

        fecha_expiracion = fecha_fabricacion_date + timedelta(days=365)

        fecha_registro = request.form.get('fecha_registro')
        if not fecha_registro:
            fecha_registro = datetime.utcnow()
        else:
            fecha_registro = datetime.strptime(fecha_registro, "%Y-%m-%d")

        nueva_facturacion = Facturacion(
            producto_id=producto_id,
            cliente_id=cliente_id,
            peso=peso,
            lote=lote,
            fecha_fabricacion=fecha_fabricacion,
            fecha_expiracion=fecha_expiracion.strftime('%Y-%m-%d'),
            fecha_registro=fecha_registro
        )

        db.session.add(nueva_facturacion)
        db.session.commit()

        return jsonify({'message': 'Peso registrado exitosamente'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/facturaciones_cliente', methods=['GET'])
def facturaciones_cliente():
    cliente_id = request.args.get('cliente_id')
    fecha_actual = request.args.get('fecha')  # Fecha en formato YYYY-MM-DD

    if not cliente_id or not fecha_actual:
        return jsonify({'error': 'Cliente y fecha son requeridos'}), 400

    try:
        fecha_actual_inicio = datetime.strptime(fecha_actual, '%Y-%m-%d').date()
        fecha_actual_fin = fecha_actual_inicio + timedelta(days=1)  # Hasta el final del día

        facturaciones = Facturacion.query.filter(
            Facturacion.cliente_id == cliente_id,
            Facturacion.fecha_registro >= fecha_actual_inicio,
            Facturacion.fecha_registro < fecha_actual_fin
        ).order_by(Facturacion.fecha_registro.desc()).limit(20).all()

        if not facturaciones:
            return jsonify([])  # Si no hay facturaciones, devolver una lista vacía

        return jsonify([facturacion.to_dict() for facturacion in facturaciones])

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/facturaciones_cliente/<int:cliente_id>', methods=['GET'])
def obtener_facturaciones_cliente(cliente_id):
    hoy = datetime.utcnow().date()
    # Obtener las facturaciones para el cliente actual del día de hoy
    facturaciones = Facturacion.query.filter_by(cliente_id=cliente_id).filter(
        Facturacion.fecha_registro >= hoy).all()

    return jsonify([facturacion.to_dict() for facturacion in facturaciones])


@app.route('/facturacion/eliminar/<int:id>', methods=['DELETE'])
def eliminar_facturacion(id):
    facturacion = Facturacion.query.get_or_404(id)
    try:
        db.session.delete(facturacion)
        db.session.commit()
        return jsonify({"message": "Peso eliminado con éxito"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# Rutas para Importaciones y Reportes
@app.route('/formulario_importacion')
def formulario_importacion():
    productos = Producto.query.all()

    # Obtener una lista de números de factura únicos y agregar información relevante
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
def registrar_importacion():
    try:
        # Datos generales de la importación
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

        # Convertir la fecha de importación a objeto datetime
        if fecha_importacion_str:
            fecha_importacion = datetime.strptime(fecha_importacion_str, '%Y-%m-%d')
        else:
            fecha_importacion = datetime.utcnow()  # Usar la fecha actual si no se proporciona

        productos = []

        print("Datos recibidos del formulario:")
        print(request.form)

        # Inicializar variables para cálculos globales
        total_fob_general = 0
        total_cif_ang_general = 0

        # Primero, calcular el total FOB general y el total CIF ANG general
        num_productos = len([key for key in request.form.keys() if 'productos' in key and '[producto]' in key])

        for i in range(num_productos):
            qty_total = float(request.form.get(f'productos[{i}][qty_total]', 0))
            price_fob = float(request.form.get(f'productos[{i}][price_fob]', 0))
            total_fob = qty_total * price_fob
            total_fob_general += total_fob

        # Calcular total CIF ANG general después de tener total FOB general
        for i in range(num_productos):
            qty_total = float(request.form.get(f'productos[{i}][qty_total]', 0))
            price_fob = float(request.form.get(f'productos[{i}][price_fob]', 0))
            total_fob = qty_total * price_fob
            flete_proporcional = (total_fob / total_fob_general) * flete_total if total_fob_general > 0 else 0
            total_cif = total_fob + flete_proporcional
            cif_ang = total_cif * tipo_cambio_ang
            total_cif_ang_general += cif_ang

        # Ahora, procesar cada producto y guardar los datos
        for i in range(num_productos):
            producto_id = int(request.form.get(f'productos[{i}][producto]', 0))
            und_caja = int(request.form.get(f'productos[{i}][und_caja]', 1))
            qty_total = float(request.form.get(f'productos[{i}][qty_total]', 0))
            price_fob = float(request.form.get(f'productos[{i}][price_fob]', 0))
            total_fob = qty_total * price_fob

            # Cálculos individuales
            flete_proporcional = (total_fob / total_fob_general) * flete_total if total_fob_general > 0 else 0
            total_cif = total_fob + flete_proporcional
            cif_ang = total_cif * tipo_cambio_ang
            arancel_ang = cif_ang * arancel_porcentaje
            ob_ang = cif_ang * ob_porcentaje
            ob_45 = ob_ang * 0.045

            # Distribuir Flete Local proporcionalmente según el CIF ANG
            flete_local_proporcional = (cif_ang / total_cif_ang_general) * flete_local_total if total_cif_ang_general > 0 else 0

            # Distribuir Gastos de Agente Aduanal proporcionalmente según el CIF ANG
            gastos_aduanal_proporcional = (cif_ang / total_cif_ang_general) * gastos_agente_aduanal if total_cif_ang_general > 0 else 0

            # Calcular el Costo Total en Almacén
            costo_total_almacen_producto = cif_ang + arancel_ang + ob_ang + gastos_aduanal_proporcional + flete_local_proporcional - ob_45

            # Calcular el Costo por Unidad ANG
            total_unidades = qty_total * und_caja
            costo_por_unidad_ang = costo_total_almacen_producto / total_unidades if total_unidades > 0 else 0

            # Precio Jomar es el costo por unidad (puedes ajustarlo si es diferente)
            precio_jomar = costo_por_unidad_ang

            # Precio Retail (puedes ajustar el margen según corresponda)
            precio_retail = precio_jomar * 1.2  # Por ejemplo, un margen del 20%

            # Crear instancia de Importacion
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
                fecha_importacion=fecha_importacion,  # Usar la fecha proporcionada
                cif_ang=cif_ang,
                ob_ang=ob_ang,
                flete_local=flete_local_proporcional,
                costo_total_almacen=costo_total_almacen_producto
            )

            db.session.add(nueva_importacion)
            productos.append(nueva_importacion)

            # Imprimir valores para depuración
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


# Rutas para Reportes de Facturas
@app.route('/reporte_factura/<numero_factura>', methods=['GET'])
def reporte_factura(numero_factura):
    # Consultar las importaciones y los productos asociados para la factura dada
    importaciones = db.session.query(Importacion, Producto).join(Producto).filter(Importacion.numero_factura == numero_factura).all()

    if not importaciones:
        # Manejar el caso donde no hay importaciones para el número de factura dado
        return "No se encontraron importaciones para el número de factura proporcionado.", 404

    # Obtener la fecha de importación (asumiendo que es la misma para todas las importaciones con el mismo número de factura)
    fecha_importacion = importaciones[0][0].fecha_importacion.strftime('%d/%m/%Y')

    # Preparar el buffer y el documento PDF
    buffer = BytesIO()
    page_width, page_height = landscape(A4)

    # Ajustar los márgenes para ganar más espacio
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.25 * inch,
        rightMargin=0.25 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch
    )

    elements = []

    # Cargar estilos y definir estilos personalizados
    styles = getSampleStyleSheet()
    styleTitle = styles['Title']
    styleTitle.alignment = TA_LEFT  # Alineación a la izquierda dentro de la celda

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

    # Añadir el logo y el título con desplazamiento a la derecha
    logo_path = os.path.join(basedir, 'static', 'logo_etiquetas.png')
    if os.path.exists(logo_path):
        # Establecer las dimensiones del logo
        logo_width = 50  # en puntos
        logo_height = 50  # en puntos
        logo = Image(logo_path, width=logo_width, height=logo_height)

        titulo_text = f"Reporte de Importación - Factura {numero_factura}"
        titulo = Paragraph(titulo_text, styleTitle)

        # Definir el desplazamiento deseado a la derecha
        desired_indent = 1.0 * inch  # Ajustar este valor según sea necesario

        # Crear la tabla con tres columnas: espacio en blanco, logo y título
        data_title = [['', logo, titulo]]
        table_title = Table(
            data_title,
            colWidths=[desired_indent, logo_width, None]  # None permite que la columna del título se ajuste automáticamente
        )

        # Estilos de la tabla
        table_title_style = TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ])
        table_title.setStyle(table_title_style)

        # Alinear la tabla a la izquierda
        table_title.hAlign = 'LEFT'

        elements.append(table_title)
    else:
        # Si no hay logo, solo el título con desplazamiento
        desired_indent = 1.0 * inch  # Ajustar este valor según sea necesario
        titulo = Paragraph(f"Reporte de Importación - Factura {numero_factura}", styleTitle)
        data_title = [['', titulo]]
        table_title = Table(
            data_title,
            colWidths=[desired_indent, None]
        )
        table_title.hAlign = 'LEFT'
        elements.append(table_title)

    # Mostrar la fecha de importación debajo de la tabla
    style_fecha = ParagraphStyle(
        name='FechaStyle',
        fontSize=9,
        alignment=TA_LEFT,
        leading=12,
        leftIndent=1.0 * inch
    )

    fecha_paragraph = Paragraph(f"Fecha de Importación: {fecha_importacion}", style_fecha)
    elements.append(fecha_paragraph)

    elements.append(Spacer(1, 12))  # Añadir espacio después del título

    # Definir los encabezados abreviados de la tabla
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
        Paragraph("GAA", style_header),  # Gastos Agente Aduanal
        Paragraph("Costo Alm.", style_header),
        Paragraph("Costo/U ANG", style_header)
    ]]

    # Variables para los totales
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
    # No calculamos total_costo_unidad_ang

    # Preparar los datos de la tabla
    for imp, prod in importaciones:
        # Cálculos de totales y acumulaciones
        total_qty += imp.cantidad_total
        total_fob_producto = imp.cantidad_total * imp.precio_fob_unidad
        total_fob += total_fob_producto
        total_flete += imp.flete
        total_cif_producto = total_fob_producto + imp.flete
        total_cif += total_cif_producto
        total_cif_ang += imp.cif_ang or 0
        total_arancel += imp.arancel
        total_ob_ang += imp.ob_ang or 0
        # Calcular OB Dev 4.5% como la mitad de OB ANG
        ob_dev_45 = (imp.ob_ang or 0) * 0.5
        total_ob_45 += ob_dev_45
        total_gastos_agente_aduanal += imp.costo_aduana or 0

        # Calcular el Costo Total en Almacén
        costo_total_almacen_producto = (
            (imp.cif_ang or 0) +
            (imp.arancel or 0) +
            (imp.ob_ang or 0) +
            (imp.costo_aduana or 0) +
            (imp.flete_local or 0) -
            ob_dev_45
        )
        total_costo_total_almacen += costo_total_almacen_producto

        # Calcular el Costo por Unidad ANG
        unidades_por_caja = imp.cantidad_cajas or 1  # Usar 'imp.cantidad_cajas'
        cantidad_total_unidades = imp.cantidad_total * unidades_por_caja
        if cantidad_total_unidades > 0:
            costo_por_unidad_ang = costo_total_almacen_producto / cantidad_total_unidades
        else:
            costo_por_unidad_ang = 0  # O manejar de otra manera si es necesario

        # Precio Jomar es el costo por unidad (puedes ajustarlo si es diferente)
        precio_jomar = costo_por_unidad_ang

        # Precio Retail (puedes ajustar el margen según corresponda)
        precio_retail = precio_jomar * 1.2  # Por ejemplo, un margen del 20%

        # Añadir la fila de datos
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

    # Añadir la fila de totales
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
        Paragraph("", style_header)  # No mostramos total en Costo/U ANG
    ])

    # Definir los anchos de las columnas
    column_widths = [
        2.0 * inch,  # Producto (Aumentado para mostrar el nombre en una sola línea)
        0.5 * inch,  # Qty
        0.5 * inch,  # P FOB
        0.6 * inch,  # T FOB
        0.5 * inch,  # Flete
        0.6 * inch,  # T CIF
        0.6 * inch,  # CIF ANG
        0.6 * inch,  # Arancel
        0.6 * inch,  # OB ANG
        0.6 * inch,  # OB Dev 4.5%
        0.6 * inch,  # GAA
        0.6 * inch,  # Costo Alm.
        0.8 * inch   # Costo/U ANG
    ]

    # Verificar y ajustar si el ancho total excede el ancho utilizable
    total_column_width = sum(column_widths)
    usable_width = page_width - doc.leftMargin - doc.rightMargin
    if total_column_width > usable_width:
        scale_factor = usable_width / total_column_width
        column_widths = [width * scale_factor for width in column_widths]

    # Crear la tabla
    table = Table(data, colWidths=column_widths, repeatRows=1)

    # Estilos de la tabla
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
        # Resaltar la fila de totales
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ])

    # Aplicar un fondo gris claro a cada fila de datos alterna
    for row_num in range(1, len(data) - 1):  # Excluir la fila de encabezado y la fila de totales
        if (row_num % 2) == 1:
            # Aplicar color de fondo a esta fila
            bg_color = colors.HexColor('#f2f2f2')  # Un gris claro
            table_style.add('BACKGROUND', (0, row_num), (-1, row_num), bg_color)

    table.setStyle(table_style)

    elements.append(table)

    elements.append(Spacer(1, 12))  # Añadir espacio después de la tabla

    # Construir el documento PDF
    doc.build(elements)

    # Enviar el PDF generado al navegador
    buffer.seek(0)
    nombre_archivo = f"reporte_factura_{numero_factura}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype='application/pdf'
    )


# Rutas para Clientes
@app.route('/clientes', methods=['GET'])
def mostrar_clientes():
    clientes = Cliente.query.all()
    return render_template('clientes.html', clientes=clientes)


@app.route('/clientes/nuevo', methods=['POST'])
def nuevo_cliente():
    try:
        nombre = request.form['nombre']
        nuevo_cliente = Cliente(nombre=nombre)
        db.session.add(nuevo_cliente)
        db.session.commit()
        return jsonify({
            "message": "Cliente registrado exitosamente",
            "cliente": {
                "id": nuevo_cliente.id,
                "nombre": nuevo_cliente.nombre
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/clientes/<int:cliente_id>', methods=['DELETE'])
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


# Rutas para Reportes
@app.route('/generar_reporte', methods=['GET'])
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

# Intentar configurar el locale
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    print("No se pudo configurar el locale 'en_US.UTF-8'. Se usará el formato de números por defecto.")

@app.route('/generar_reporte_pesos', methods=['GET'])
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

    # Reemplazar espacios y caracteres especiales en el nombre del cliente para usar en el nombre del archivo
    nombre_archivo_cliente = cliente_nombre.replace(" ", "_").replace("/", "_")
    nombre_archivo = f"reporte_pesos_{nombre_archivo_cliente}_{fecha_inicio}_a_{fecha_fin}.xlsx"

    return send_file(output, as_attachment=True, download_name=nombre_archivo, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route('/generar_etiqueta', methods=['POST'])
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
def etiquetas_vencimiento():
    if request.method == 'POST':
        # Obtener los datos del formulario
        producto_id = request.form['producto_id']
        fecha_fabricacion = request.form['fecha_fabricacion']
        lote = request.form['lote']
        cantidad_etiquetas = int(request.form['cantidad_etiquetas'])
        
        # Convertir fecha de fabricación a objeto datetime
        fecha_fabricacion_date = datetime.strptime(fecha_fabricacion, '%Y-%m-%d')
        
        # Calcular la fecha de vencimiento (1 año después)
        fecha_expiracion = fecha_fabricacion_date + timedelta(days=365)
        
        # Obtener el producto de la base de datos
        producto = Producto.query.get(producto_id)
        
        # Datos del producto para la etiqueta
        datos_producto = {
            "nombre_producto": producto.nombre,
            "lote": lote,
            "fecha_fabricacion": fecha_fabricacion_date.strftime('%d/%m/%Y'),
            "fecha_expiracion": fecha_expiracion.strftime('%d/%m/%Y'),
            "temperatura": producto.temperatura
        }
        
        # Generar el PDF con las etiquetas
        return generar_pdf_etiquetas(datos_producto, cantidad_etiquetas)
    
    # Si es un GET, mostrar el formulario
    productos = Producto.query.all()
    return render_template('form_generar_etiquetas.html', productos=productos)

def generar_pdf_etiquetas(datos, cantidad):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    
    # Definición del tamaño de cada etiqueta en pulgadas
    etiqueta_ancho = 1.8 * inch
    etiqueta_alto = 0.8 * inch
    
    # Margen entre las etiquetas
    margen_horizontal = 0.2 * inch
    margen_vertical = 0.1 * inch

    # Margen entre los dos grupos de etiquetas
    separacion_grupos = 0.3 * inch

    # Radio de las esquinas redondeadas
    radio_esquinas = 0.1 * inch

    # Posición inicial para el primer grupo de 4 etiquetas
    x_offset_start = (A4[0] - 2 * etiqueta_ancho - margen_horizontal) / 2  # Centrado en la página horizontalmente
    y_offset_start = A4[1] - inch  # Espaciado desde el borde superior
    
    etiquetas_por_grupo = 4  # 4 etiquetas en cada grupo de 2x4 pulgadas
    etiquetas_por_pagina = 8  # 8 etiquetas en total por página (2 grupos de 4 etiquetas)

    etiqueta_contador = 0

    while cantidad > 0:
        for fila in range(2):  # Dos grupos de 2x4 pulgadas por página
            y_offset = y_offset_start - fila * (2 * etiqueta_alto + margen_vertical + separacion_grupos if fila == 1 else 0)
            for sub_fila in range(2):  # Dos filas de etiquetas por bloque
                for sub_columna in range(2):  # Dos columnas de etiquetas por bloque
                    if cantidad <= 0:
                        break

                    # Calcular la posición para la etiqueta actual
                    etiqueta_x = x_offset_start + sub_columna * (etiqueta_ancho + margen_horizontal)
                    etiqueta_y = y_offset - sub_fila * (etiqueta_alto + margen_vertical)
                    
                    # Dibujar la etiqueta con borde redondeado
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
    # Título centrado
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x_offset + etiqueta_ancho / 2, y_offset + etiqueta_alto - 0.15 * inch, datos["nombre_producto"])
    
    # Alineación a la derecha para los valores
    c.setFont("Helvetica", 7)  # Fuente ligeramente más pequeña
    label_x = x_offset + 0.1 * inch  # Posición de las etiquetas
    value_x = x_offset + etiqueta_ancho - 0.1 * inch  # Alineación a la derecha de los valores

    # Espaciado reducido entre líneas
    line_height = 0.14 * inch

    # Dibujar los textos de las etiquetas y los valores asociados
    c.drawString(label_x, y_offset + etiqueta_alto - 0.3 * inch, "Lot:")
    c.drawRightString(value_x, y_offset + etiqueta_alto - 0.3 * inch, datos['lote'])

    c.drawString(label_x, y_offset + etiqueta_alto - (0.3 * inch + line_height), "Manufactured:")
    c.drawRightString(value_x, y_offset + etiqueta_alto - (0.3 * inch + line_height), datos['fecha_fabricacion'])

    c.drawString(label_x, y_offset + etiqueta_alto - (0.3 * inch + 2 * line_height), "Expiration:")
    c.drawRightString(value_x, y_offset + etiqueta_alto - (0.3 * inch + 2 * line_height), datos['fecha_expiracion'])

    c.drawString(label_x, y_offset + etiqueta_alto - (0.3 * inch + 3 * line_height), "When Kept at:")
    c.drawRightString(value_x, y_offset + etiqueta_alto - (0.3 * inch + 3 * line_height), datos['temperatura'])



if __name__ == '__main__':  
    ip_servidor = obtener_ip_servidor()
    print(f"La aplicación está disponible en la IP: {ip_servidor}:{5002}")
    app.run(debug=False, host='0.0.0.0', port=5002)