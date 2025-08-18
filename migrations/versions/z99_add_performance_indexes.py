"""Add performance indexes

Revision ID: z99_add_performance_indexes
Revises: fde620f42cae
Create Date: 2025-01-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'z99_add_performance_indexes'
down_revision = 'fde620f42cae'
branch_labels = None
depends_on = None


def upgrade():
    # Índices para optimizar consultas frecuentes en dashboard
    try:
        # Índice en fecha_pedido para consultas de rangos de fechas
        op.create_index('idx_pedido_fecha_pedido', 'pedido', ['fecha_pedido'])
    except:
        pass  # El índice ya existe
    
    try:
        # Índice en estado para filtros por estado
        op.create_index('idx_pedido_estado', 'pedido', ['estado'])
    except:
        pass
    
    try:
        # Índice compuesto para consultas de vendedor por fecha
        op.create_index('idx_pedido_cliente_fecha', 'pedido', ['cliente_id', 'fecha_pedido'])
    except:
        pass
    
    try:
        # Índice en DetallePedido.pedido_id para joins
        op.create_index('idx_detalle_pedido_pedido_id', 'detalle_pedido', ['pedido_id'])
    except:
        pass
    
    try:
        # Índice en subtotal para agregaciones
        op.create_index('idx_detalle_pedido_subtotal', 'detalle_pedido', ['subtotal'])
    except:
        pass
    
    try:
        # Índice en Vendedor.activo para filtros de vendedores activos
        op.create_index('idx_vendedor_activo', 'vendedor', ['activo'])
    except:
        pass
    
    try:
        # Índice en ClienteVendedor para joins frecuentes
        op.create_index('idx_cliente_vendedor_vendedor_id', 'cliente_vendedor', ['vendedor_id'])
    except:
        pass
    
    try:
        op.create_index('idx_cliente_vendedor_cliente_id', 'cliente_vendedor', ['cliente_id'])
    except:
        pass


def downgrade():
    # Eliminar índices en orden inverso
    try:
        op.drop_index('idx_cliente_vendedor_cliente_id', table_name='cliente_vendedor')
    except:
        pass
    
    try:
        op.drop_index('idx_cliente_vendedor_vendedor_id', table_name='cliente_vendedor')
    except:
        pass
    
    try:
        op.drop_index('idx_vendedor_activo', table_name='vendedor')
    except:
        pass
    
    try:
        op.drop_index('idx_detalle_pedido_subtotal', table_name='detalle_pedido')
    except:
        pass
    
    try:
        op.drop_index('idx_detalle_pedido_pedido_id', table_name='detalle_pedido')
    except:
        pass
    
    try:
        op.drop_index('idx_pedido_cliente_fecha', table_name='pedido')
    except:
        pass
    
    try:
        op.drop_index('idx_pedido_estado', table_name='pedido')
    except:
        pass
    
    try:
        op.drop_index('idx_pedido_fecha_pedido', table_name='pedido')
    except:
        pass