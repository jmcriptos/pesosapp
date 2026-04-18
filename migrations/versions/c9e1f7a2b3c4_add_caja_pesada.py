"""Add caja_pesada table for per-box weighing

Revision ID: c9e1f7a2b3c4
Revises: b7c8d9e0f1a3
Create Date: 2026-04-18 13:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9e1f7a2b3c4'
down_revision = 'b7c8d9e0f1a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'caja_pesada',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('detalle_pedido_id', sa.Integer(), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('peso', sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column('lote', sa.String(length=50), nullable=False),
        sa.Column('fecha_elaboracion', sa.Date(), nullable=False),
        sa.Column('fecha_vencimiento', sa.Date(), nullable=False),
        sa.Column('pesado_por', sa.Integer(), nullable=True),
        sa.Column('pesado_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['detalle_pedido_id'], ['detalle_pedido.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pesado_por'], ['vendedor.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('detalle_pedido_id', 'numero', name='uq_caja_detalle_numero'),
    )
    op.create_index('ix_caja_pesada_detalle_pedido_id', 'caja_pesada', ['detalle_pedido_id'])
    op.create_index('ix_caja_pesada_lote', 'caja_pesada', ['lote'])


def downgrade():
    op.drop_index('ix_caja_pesada_lote', table_name='caja_pesada')
    op.drop_index('ix_caja_pesada_detalle_pedido_id', table_name='caja_pesada')
    op.drop_table('caja_pesada')
