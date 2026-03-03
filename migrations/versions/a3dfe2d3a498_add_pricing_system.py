"""Add pricing system

Revision ID: a3dfe2d3a498
Revises: 9b5b69d7a839
Create Date: 2025-05-25 12:22:38.129843

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'a3dfe2d3a498'
down_revision = '9b5b69d7a839'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Crear tabla de listas de precios
    if 'lista_precio' not in existing_tables:
        op.create_table('lista_precio',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nombre', sa.String(length=100), nullable=False),
            sa.Column('descripcion', sa.String(length=200), nullable=True),
            sa.Column('es_default', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('activa', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Crear tabla de precios por producto en cada lista
    if 'precio_producto' not in existing_tables:
        op.create_table('precio_producto',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('lista_precio_id', sa.Integer(), nullable=False),
            sa.Column('producto_id', sa.Integer(), nullable=False),
            sa.Column('precio_base', sa.Float(), nullable=False),
            sa.Column('precio_jomar', sa.Float(), nullable=True),
            sa.Column('precio_retail', sa.Float(), nullable=True),
            sa.Column('margen_jomar', sa.Float(), server_default='1.0', nullable=True),
            sa.Column('margen_retail', sa.Float(), server_default='1.2', nullable=True),
            sa.Column('activo', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('fecha_actualizacion', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['lista_precio_id'], ['lista_precio.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['producto_id'], ['producto.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('lista_precio_id', 'producto_id', name='uk_lista_producto')
        )
    
    # Crear tabla de listas de precios por cliente
    if 'cliente_lista_precio' not in existing_tables:
        op.create_table('cliente_lista_precio',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('cliente_id', sa.Integer(), nullable=False),
            sa.Column('lista_precio_id', sa.Integer(), nullable=False),
            sa.Column('fecha_asignacion', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('activa', sa.Boolean(), server_default='true', nullable=False),
            sa.ForeignKeyConstraint(['cliente_id'], ['cliente.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['lista_precio_id'], ['lista_precio.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('cliente_id', 'lista_precio_id', name='uk_cliente_lista')
        )
    
    # Crear tabla de precios específicos por cliente-producto
    if 'precio_cliente_producto' not in existing_tables:
        op.create_table('precio_cliente_producto',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('cliente_id', sa.Integer(), nullable=False),
            sa.Column('producto_id', sa.Integer(), nullable=False),
            sa.Column('precio_base', sa.Float(), nullable=False),
            sa.Column('precio_jomar', sa.Float(), nullable=True),
            sa.Column('precio_retail', sa.Float(), nullable=True),
            sa.Column('margen_jomar', sa.Float(), server_default='1.0', nullable=True),
            sa.Column('margen_retail', sa.Float(), server_default='1.2', nullable=True),
            sa.Column('activo', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('fecha_actualizacion', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['cliente_id'], ['cliente.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['producto_id'], ['producto.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('cliente_id', 'producto_id', name='uk_cliente_producto_precio')
        )

    # Insertar lista de precios por defecto (compatible con SQLite/PostgreSQL)
    exists = bind.execute(
        sa.text("SELECT 1 FROM lista_precio WHERE nombre = :nombre LIMIT 1"),
        {"nombre": "Lista de Precios General"}
    ).first()
    if not exists:
        bind.execute(
            sa.text(
                "INSERT INTO lista_precio (nombre, descripcion, es_default, activa, fecha_creacion) "
                "VALUES (:nombre, :descripcion, :es_default, :activa, :fecha_creacion)"
            ),
            {
                "nombre": "Lista de Precios General",
                "descripcion": "Lista de precios por defecto del sistema",
                "es_default": True,
                "activa": True,
                "fecha_creacion": datetime.utcnow()
            }
        )

def downgrade():
    op.drop_table('precio_cliente_producto')
    op.drop_table('cliente_lista_precio')
    op.drop_table('precio_producto')
    op.drop_table('lista_precio')
