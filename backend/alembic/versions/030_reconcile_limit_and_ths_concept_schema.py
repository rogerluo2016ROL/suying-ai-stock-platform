"""Reconcile legacy limit list and THS concept schemas without data loss."""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE SEQUENCE IF NOT EXISTS limit_list_d_id_seq")
    op.execute("UPDATE limit_list_d SET id = nextval('limit_list_d_id_seq') WHERE id IS NULL")
    op.execute("ALTER TABLE limit_list_d ALTER COLUMN id SET DEFAULT nextval('limit_list_d_id_seq')")
    op.execute("ALTER TABLE limit_list_d ALTER COLUMN id SET NOT NULL")
    op.execute("ALTER SEQUENCE limit_list_d_id_seq OWNED BY limit_list_d.id")
    op.execute("ALTER TABLE limit_list_d DROP CONSTRAINT IF EXISTS limit_list_d_uniq")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'limit_list_d'::regclass AND contype = 'p'
            ) THEN
                ALTER TABLE limit_list_d
                    ADD CONSTRAINT limit_list_d_pkey PRIMARY KEY (id);
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE IF EXISTS ths_concept_map RENAME TO ths_concept_catalog_legacy")
    op.create_table("ths_concept_map", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts_code", sa.Text(), nullable=False), sa.Column("concept_name", sa.Text(), nullable=False),
        sa.Column("concept_code", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.UniqueConstraint("ts_code", "concept_name", name="ths_concept_map_unique"))
    op.create_index("idx_ths_concept_map_code", "ths_concept_map", ["ts_code"])
    op.create_index("idx_ths_concept_map_concept", "ths_concept_map", ["concept_name"])

def downgrade():
    op.drop_index("idx_ths_concept_map_concept", table_name="ths_concept_map")
    op.drop_index("idx_ths_concept_map_code", table_name="ths_concept_map")
    op.drop_table("ths_concept_map")
    op.execute("ALTER TABLE IF EXISTS ths_concept_catalog_legacy RENAME TO ths_concept_map")
