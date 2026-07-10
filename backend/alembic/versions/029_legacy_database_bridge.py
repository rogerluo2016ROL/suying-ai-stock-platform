"""Compatibility bridge for databases stamped at historical revision 029.

The original 029 migration was not retained in this repository.  Its schema
effects are audited separately; this revision restores a linear Alembic graph
so fresh databases and existing stamped databases can converge safely.
"""

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
