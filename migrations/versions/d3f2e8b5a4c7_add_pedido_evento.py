"""Add pedido_evento table for order activity history

Revision ID: d3f2e8b5a4c7
Revises: c9e1f7a2b3c4
Create Date: 2026-04-18 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3f2e8b5a4c7'
down_revision = 'c9e1f7a2b3c4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pedido_evento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pedido_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=50), nullable=False),
        sa.Column('descripcion', sa.String(length=255), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pedido_id'], ['pedido.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['usuario_id'], ['vendedor.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pedido_evento_pedido_id', 'pedido_evento', ['pedido_id'])
    op.create_index('ix_pedido_evento_created_at', 'pedido_evento', ['created_at'])


def downgrade():
    op.drop_index('ix_pedido_evento_created_at', table_name='pedido_evento')
    op.drop_index('ix_pedido_evento_pedido_id', table_name='pedido_evento')
    op.drop_table('pedido_evento')
