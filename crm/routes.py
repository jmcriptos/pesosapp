# crm/routes.py

from flask import Blueprint, jsonify, request
from models.crm_cliente import CRMCliente
from models.contacto import ContactoCliente
from models.horario import HorarioCliente
from models.interaccion import InteraccionCliente
from models.extensions import db


crm_bp = Blueprint('crm', __name__)

@crm_bp.route('/ping', methods=['GET'])
def ping():
    return jsonify({'status': 'CRM activo'}), 200

# Obtener todos los clientes CRM
@crm_bp.route('/clientes', methods=['GET'])
def obtener_clientes_crm():
    clientes = CRMCliente.query.all()
    resultado = [{
        'id': c.id,
        'cliente_original_id': c.cliente_original_id,
        'categoria_cliente': c.categoria_cliente,
        'potencial_mensual': c.potencial_mensual,
        'frecuencia_compra_dias': c.frecuencia_compra_dias,
        'zona_geografica': c.zona_geografica,
        'notas_generales': c.notas_generales
    } for c in clientes]
    return jsonify(resultado), 200

# Crear un nuevo cliente CRM
@crm_bp.route('/clientes', methods=['POST'])
def crear_cliente_crm():
    data = request.json
    cliente = CRMCliente(
        cliente_original_id=data.get('cliente_original_id'),
        categoria_cliente=data.get('categoria_cliente'),
        potencial_mensual=data.get('potencial_mensual'),
        frecuencia_compra_dias=data.get('frecuencia_compra_dias'),
        zona_geografica=data.get('zona_geografica'),
        notas_generales=data.get('notas_generales')
    )
    db.session.add(cliente)
    db.session.commit()
    return jsonify({'mensaje': 'Cliente CRM creado', 'id': cliente.id}), 201

# Actualizar cliente CRM
@crm_bp.route('/clientes/<int:id>', methods=['PUT'])
def actualizar_cliente_crm(id):
    cliente = CRMCliente.query.get_or_404(id)
    data = request.json
    cliente.categoria_cliente = data.get('categoria_cliente', cliente.categoria_cliente)
    cliente.potencial_mensual = data.get('potencial_mensual', cliente.potencial_mensual)
    cliente.frecuencia_compra_dias = data.get('frecuencia_compra_dias', cliente.frecuencia_compra_dias)
    cliente.zona_geografica = data.get('zona_geografica', cliente.zona_geografica)
    cliente.notas_generales = data.get('notas_generales', cliente.notas_generales)
    db.session.commit()
    return jsonify({'mensaje': 'Cliente actualizado'}), 200

# Eliminar cliente CRM
@crm_bp.route('/clientes/<int:id>', methods=['DELETE'])
def eliminar_cliente_crm(id):
    cliente = CRMCliente.query.get_or_404(id)
    db.session.delete(cliente)
    db.session.commit()
    return jsonify({'mensaje': 'Cliente eliminado'}), 200

# Obtener contactos de un cliente CRM
@crm_bp.route('/clientes/<int:id>/contactos', methods=['GET'])
def obtener_contactos(id):
    contactos = ContactoCliente.query.filter_by(crm_cliente_id=id).all()
    resultado = [{
        'id': c.id,
        'nombre_completo': c.nombre_completo,
        'cargo_posicion': c.cargo_posicion,
        'es_contacto_principal': c.es_contacto_principal,
        'nivel_influencia': c.nivel_influencia,
        'mejor_horario_contacto': c.mejor_horario_contacto
    } for c in contactos]
    return jsonify(resultado), 200

# Agregar contacto a cliente CRM
@crm_bp.route('/clientes/<int:id>/contactos', methods=['POST'])
def crear_contacto(id):
    data = request.json
    cliente = CRMCliente.query.get_or_404(id)
    contacto = ContactoCliente(
        crm_cliente=cliente,
        nombre_completo=data.get('nombre_completo'),
        cargo_posicion=data.get('cargo_posicion'),
        es_contacto_principal=data.get('es_contacto_principal', False),
        nivel_influencia=data.get('nivel_influencia'),
        mejor_horario_contacto=data.get('mejor_horario_contacto')
    )
    db.session.add(contacto)
    db.session.commit()
    return jsonify({'mensaje': 'Contacto creado', 'id': contacto.id}), 201

# Obtener interacciones de un cliente CRM
@crm_bp.route('/clientes/<int:id>/interacciones', methods=['GET'])
def obtener_interacciones(id):
    interacciones = InteraccionCliente.query.filter_by(crm_cliente_id=id).all()
    resultado = [{
        'id': i.id,
        'fecha': i.fecha.isoformat() if i.fecha else None,
        'tipo': i.tipo,
        'descripcion': i.descripcion
    } for i in interacciones]
    return jsonify(resultado), 200

# Crear interacción para un cliente CRM
@crm_bp.route('/clientes/<int:id>/interacciones', methods=['POST'])
def crear_interaccion(id):
    data = request.json
    cliente = CRMCliente.query.get_or_404(id)
    interaccion = InteraccionCliente(
        crm_cliente=cliente,
        fecha=data.get('fecha'),
        tipo=data.get('tipo'),
        descripcion=data.get('descripcion')
    )
    db.session.add(interaccion)
    db.session.commit()
    return jsonify({'mensaje': 'Interacción registrada', 'id': interaccion.id}), 201

# Obtener horarios preferidos de un cliente CRM
@crm_bp.route('/clientes/<int:id>/horarios', methods=['GET'])
def obtener_horarios(id):
    horarios = HorarioCliente.query.filter_by(crm_cliente_id=id).all()
    resultado = [{
        'id': h.id,
        'dia_semana': h.dia_semana,
        'hora_inicio': h.hora_inicio,
        'hora_fin': h.hora_fin
    } for h in horarios]
    return jsonify(resultado), 200

# Crear horario para un cliente CRM
@crm_bp.route('/clientes/<int:id>/horarios', methods=['POST'])
def crear_horario(id):
    data = request.json
    cliente = CRMCliente.query.get_or_404(id)
    horario = HorarioCliente(
        crm_cliente=cliente,
        dia_semana=data.get('dia_semana'),
        hora_inicio=data.get('hora_inicio'),
        hora_fin=data.get('hora_fin')
    )
    db.session.add(horario)
    db.session.commit()
    return jsonify({'mensaje': 'Horario agregado', 'id': horario.id}), 201
