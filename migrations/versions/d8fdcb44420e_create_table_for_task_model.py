"""create table for Task model

Revision ID: d8fdcb44420e
Revises: 0823eca8a7e1
Create Date: 2021-01-12 22:58:06.807829

"""
from alembic import op
import sqlalchemy as sa
from webapp.type_decorators import UUID


# revision identifiers, used by Alembic.
revision = 'd8fdcb44420e'
down_revision = '0823eca8a7e1'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('task',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', UUID(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('processing', 'done', 'error', name='status', default='processing'), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('result_location', sa.String(length=256), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], 'fk_user_id'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uuid')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('task')
    # ### end Alembic commands ###
