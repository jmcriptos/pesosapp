"""Add multi-vendor system

Revision ID: 660d129cdef9
Revises: 9b5b69d7a839
Create Date: 2025-05-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '660d129cdef9'  # NO CAMBIAR ESTA LÍNEA
down_revision = '9b5b69d7a839'
branch_labels = None
depends_on = None

def upgrade():
    # Crear tabla de roles
    op.create_table('rol',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=50), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('nivel_jerarquia', sa.Integer(), default=0),
        sa.Column('activo', sa.Boolean(), default=True),
        sa.Column('fecha_creacion', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre')
    )
    
    # Crear tabla de permisos
    op.create_table('permiso',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('categoria', sa.String(length=50), nullable=True),
        sa.Column('recurso', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre')
    )
    
    # Crear tabla de rol_permiso (relación muchos a muchos)
    op.create_table('rol_permiso',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rol_id', sa.Integer(), nullable=False),
        sa.Column('permiso_id', sa.Integer(), nullable=False),
        sa.Column('puede_leer', sa.Boolean(), default=True),
        sa.Column('puede_crear', sa.Boolean(), default=False),
        sa.Column('puede_editar', sa.Boolean(), default=False),
        sa.Column('puede_eliminar', sa.Boolean(), default=False),
        sa.ForeignKeyConstraint(['permiso_id'], ['permiso.id'], ),
        sa.ForeignKeyConstraint(['rol_id'], ['rol.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rol_id', 'permiso_id', name='unique_rol_permiso')
    )
    
    # Crear tabla de territorios
    op.create_table('territorio',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('tipo', sa.String(length=50), nullable=True),
        sa.Column('coordenadas', sa.JSON(), nullable=True),
        sa.Column('activo', sa.Boolean(), default=True),
        sa.Column('fecha_creacion', sa.DateTime(), default=datetime.utcnow),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Crear tabla de vendedores
    op.create_table('vendedor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('nombre_completo', sa.String(length=200), nullable=False),
        sa.Column('telefono', sa.String(length=20), nullable=True),
        sa.Column('fecha_ingreso', sa.Date(), default=datetime.utcnow),
        sa.Column('rol_id', sa.Integer(), nullable=False),
        sa.Column('territorio_id', sa.Integer(), nullable=True),
        sa.Column('supervisor_id', sa.Integer(), nullable=True),
        sa.Column('activo', sa.Boolean(), default=True),
        sa.Column('ultimo_login', sa.DateTime(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), default=datetime.utcnow),
        sa.ForeignKeyConstraint(['rol_id'], ['rol.id'], ),
        sa.ForeignKeyConstraint(['supervisor_id'], ['vendedor.id'], ),
        sa.ForeignKeyConstraint(['territorio_id'], ['territorio.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )
    
    # Crear tabla de asignación cliente-vendedor
    op.create_table('cliente_vendedor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('vendedor_id', sa.Integer(), nullable=False),
        sa.Column('tipo_asignacion', sa.String(length=50), default='principal'),
        sa.Column('fecha_inicio', sa.Date(), default=datetime.utcnow),
        sa.Column('fecha_fin', sa.Date(), nullable=True),
        sa.Column('activo', sa.Boolean(), default=True),
        sa.Column('porcentaje_comision', sa.Float(), default=100.0),
        sa.ForeignKeyConstraint(['cliente_id'], ['cliente.id'], ),
        sa.ForeignKeyConstraint(['vendedor_id'], ['vendedor.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Agregar campos de auditoría a tablas existentes
    op.add_column('pedido', sa.Column('vendedor_id', sa.Integer(), nullable=True))
    op.add_column('pedido', sa.Column('creado_por', sa.Integer(), nullable=True))
    op.add_column('pedido', sa.Column('modificado_por', sa.Integer(), nullable=True))
    op.add_column('pedido', sa.Column('fecha_modificacion', sa.DateTime(), nullable=True))
    
    op.add_column('facturacion', sa.Column('vendedor_id', sa.Integer(), nullable=True))
    op.add_column('facturacion', sa.Column('creado_por', sa.Integer(), nullable=True))
    
    op.add_column('recepcion', sa.Column('creado_por', sa.Integer(), nullable=True))
    
    # Crear foreign keys para los campos agregados
    op.create_foreign_key('fk_pedido_vendedor', 'pedido', 'vendedor', ['vendedor_id'], ['id'])
    op.create_foreign_key('fk_pedido_creado_por', 'pedido', 'vendedor', ['creado_por'], ['id'])
    op.create_foreign_key('fk_pedido_modificado_por', 'pedido', 'vendedor', ['modificado_por'], ['id'])
    
    op.create_foreign_key('fk_facturacion_vendedor', 'facturacion', 'vendedor', ['vendedor_id'], ['id'])
    op.create_foreign_key('fk_facturacion_creado_por', 'facturacion', 'vendedor', ['creado_por'], ['id'])
    
    op.create_foreign_key('fk_recepcion_creado_por', 'recepcion', 'vendedor', ['creado_por'], ['id'])

def downgrade():
    # Eliminar foreign keys agregadas
    op.drop_constraint('fk_recepcion_creado_por', 'recepcion', type_='foreignkey')
    op.drop_constraint('fk_facturacion_creado_por', 'facturacion', type_='foreignkey')
    op.drop_constraint('fk_facturacion_vendedor', 'facturacion', type_='foreignkey')
    op.drop_constraint('fk_pedido_modificado_por', 'pedido', type_='foreignkey')
    op.drop_constraint('fk_pedido_creado_por', 'pedido', type_='foreignkey')
    op.drop_constraint('fk_pedido_vendedor', 'pedido', type_='foreignkey')
    
    # Eliminar columnas agregadas
    op.drop_column('recepcion', 'creado_por')
    op.drop_column('facturacion', 'creado_por')
    op.drop_column('facturacion', 'vendedor_id')
    op.drop_column('pedido', 'fecha_modificacion')
    op.drop_column('pedido', 'modificado_por')
    op.drop_column('pedido', 'creado_por')
    op.drop_column('pedido', 'vendedor_id')
    
    # Eliminar tablas en orden inverso
    op.drop_table('cliente_vendedor')
    op.drop_table('vendedor')
    op.drop_table('territorio')
    op.drop_table('rol_permiso')
    op.drop_table('permiso')
    op.drop_table('rol')