"""Persist evidence and scoring snapshots for the AI Token output power chain."""

from typing import Sequence, Union

from alembic import op


revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_output_power_evidence (
            evidence_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            layer_id TEXT NOT NULL,
            power_source_type TEXT NOT NULL CHECK (power_source_type IN ('curtailed_renewable','valley_power','park_self_generation_or_ppa','nominal_capacity')),
            available_mw DOUBLE PRECISION,
            available_hours DOUBLE PRECISION,
            tariff_or_cost DOUBLE PRECISION,
            grid_connection_status TEXT NOT NULL DEFAULT 'unknown',
            storage_support TEXT NOT NULL DEFAULT 'unknown',
            curtailment_or_valley_evidence TEXT,
            hardware_type TEXT,
            model_profile TEXT,
            precision TEXT,
            batch_mode TEXT,
            tokens_per_mw_hour DOUBLE PRECISION,
            cluster_availability DOUBLE PRECISION,
            evidence_grade TEXT NOT NULL DEFAULT 'E0' CHECK (evidence_grade IN ('E0','E1','E2','E3','E4','E5')),
            review_status TEXT NOT NULL DEFAULT 'pending_review' CHECK (review_status IN ('candidate','pending_review','approved','rejected')),
            source_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_url TEXT,
            quote TEXT,
            as_of_date DATE NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_output_capacity_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            model_profile TEXT NOT NULL,
            hardware_type TEXT NOT NULL,
            precision TEXT NOT NULL,
            batch_mode TEXT NOT NULL,
            available_mw DOUBLE PRECISION,
            operating_hours DOUBLE PRECISION,
            utilization DOUBLE PRECISION,
            tokens_per_mw_hour DOUBLE PRECISION,
            cluster_availability DOUBLE PRECISION,
            billable_tokens DOUBLE PRECISION,
            electricity_cost DOUBLE PRECISION,
            compute_depreciation DOUBLE PRECISION,
            facility_and_cooling_cost DOUBLE PRECISION,
            network_cost DOUBLE PRECISION,
            operation_cost DOUBLE PRECISION,
            financing_cost DOUBLE PRECISION,
            cost_per_million_tokens DOUBLE PRECISION,
            calculation_status TEXT NOT NULL DEFAULT 'unknown',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            as_of_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_dimension_scores (
            dimension_score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            dimension_id TEXT NOT NULL CHECK (dimension_id IN ('function_value','technology_route','physical_bom','value_pool','competition_moat','supply_demand_cycle','evidence_validation')),
            score DOUBLE PRECISION,
            explanation TEXT,
            coverage_ratio DOUBLE PRECISION,
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            as_of_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, dimension_id, as_of_date)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_market_snapshots (
            market_snapshot_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            valuation JSONB NOT NULL DEFAULT '{}',
            price_change JSONB NOT NULL DEFAULT '{}',
            turnover JSONB NOT NULL DEFAULT '{}',
            fund_flow JSONB NOT NULL DEFAULT '{}',
            crowding JSONB NOT NULL DEFAULT '{}',
            strategy_signal JSONB NOT NULL DEFAULT '{}',
            market_signal_score DOUBLE PRECISION,
            separate_from_industry_evidence BOOLEAN NOT NULL DEFAULT TRUE,
            source_status TEXT NOT NULL DEFAULT 'unknown',
            coverage_ratio DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_pool_states (
            pool_state_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            evidence_grade TEXT NOT NULL CHECK (evidence_grade IN ('E0','E1','E2','E3','E4','E5')),
            pool_code TEXT NOT NULL CHECK (pool_code IN ('A','B','C','D')),
            authenticity_score DOUBLE PRECISION,
            commercialization_score DOUBLE PRECISION,
            industrial_attractiveness_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION,
            reason_codes JSONB NOT NULL DEFAULT '[]',
            next_validation_node TEXT,
            next_validation_date DATE,
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            as_of_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, as_of_date)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_pool_transitions (
            transition_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            old_pool_code TEXT CHECK (old_pool_code IN ('A','B','C','D')),
            new_pool_code TEXT NOT NULL CHECK (new_pool_code IN ('A','B','C','D')),
            trigger_evidence_ids JSONB NOT NULL DEFAULT '[]',
            transition_date DATE NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            next_validation_node TEXT,
            next_validation_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_token_power_evidence_mapping_date ON business_tag_token_output_power_evidence(mapping_id, as_of_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_power_capacity_mapping_date ON business_tag_token_output_capacity_snapshots(mapping_id, as_of_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_power_dimension_mapping_date ON business_tag_token_dimension_scores(mapping_id, as_of_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_power_market_mapping_date ON business_tag_token_market_snapshots(mapping_id, trade_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_power_pool_mapping_date ON business_tag_token_pool_states(mapping_id, as_of_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_power_transition_mapping_date ON business_tag_token_pool_transitions(mapping_id, transition_date DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_power_transition_mapping_date")
    op.execute("DROP INDEX IF EXISTS idx_token_power_pool_mapping_date")
    op.execute("DROP INDEX IF EXISTS idx_token_power_market_mapping_date")
    op.execute("DROP INDEX IF EXISTS idx_token_power_dimension_mapping_date")
    op.execute("DROP INDEX IF EXISTS idx_token_power_capacity_mapping_date")
    op.execute("DROP INDEX IF EXISTS idx_token_power_evidence_mapping_date")
    op.execute("DROP TABLE IF EXISTS business_tag_token_pool_transitions")
    op.execute("DROP TABLE IF EXISTS business_tag_token_pool_states")
    op.execute("DROP TABLE IF EXISTS business_tag_token_market_snapshots")
    op.execute("DROP TABLE IF EXISTS business_tag_token_dimension_scores")
    op.execute("DROP TABLE IF EXISTS business_tag_token_output_capacity_snapshots")
    op.execute("DROP TABLE IF EXISTS business_tag_token_output_power_evidence")
