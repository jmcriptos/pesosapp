"""Vistas del módulo de maquila. Solo traducen request → servicio → template."""
from flask import Blueprint, render_template

from app import requiere_rol
from flask_login import login_required

bp = Blueprint('maquila', __name__, url_prefix='/maquila')


@bp.route('')
@login_required
@requiere_rol(['super_admin'])
def index():
    return render_template('maquila/index.html', clientes=[])
