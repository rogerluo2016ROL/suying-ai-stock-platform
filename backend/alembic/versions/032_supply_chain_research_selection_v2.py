"""Add auditable supply-chain research and selection V2 storage.

Revision ID: 032
Revises: 031
Create Date: 2026-07-11

The migration is additive.  V1 three-high and expectation-gap rows remain
unchanged, while every V2 score is versioned and nullable so that missing
evidence is never silently converted into a zero score.
"""

from alembic import op


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


SCORE_COLUMNS = {
    "supply_chain_node_scores": (
        "demand_certainty",
        "value_pool_score",
        "bottleneck_score",
        "supply_demand_score",
        "technology_maturity_score",
        "commercialization_score",
        "transmission_score",
        "evidence_quality_score",
        "total_score",
    ),
    "business_tag_authenticity_scores": (
        "product_evidence_score",
        "customer_evidence_score",
        "order_revenue_evidence_score",
        "source_reliability_score",
        "freshness_score",
        "authenticity_score",
    ),
    "business_tag_operating_quality_scores": (
        "growth_score",
        "profit_score",
        "moat_score",
        "total_score",
    ),
    "business_tag_benefit_scores": (
        "node_attractiveness",
        "operating_quality_score",
        "revenue_exposure_score",
        "order_certainty_score",
        "profit_elasticity_score",
        "delivery_capability_score",
        "benefit_raw",
        "authenticity_score",
        "benefit_score",
    ),
    "business_tag_selection_scores": (
        "benefit_score",
        "expectation_gap_score",
        "catalyst_score",
        "risk_score",
        "confidence_score",
        "opportunity_score",
    ),
}

COVERAGE_COLUMNS = {
    "business_tag_operating_quality_scores": (
        "growth_coverage",
        "profit_coverage",
        "moat_coverage",
        "total_coverage",
    ),
    "business_tag_benefit_scores": ("coverage_ratio",),
}


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS supply_chain_node_dimensions (
            dimension_record_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            chain_id TEXT,
            template_id TEXT,
            dimension_id TEXT NOT NULL CHECK (dimension_id IN (
                'function_value','technology_route','physical_bom','value_pool',
                'competition_moat','supply_demand_cycle','evidence_validation','market_expectation'
            )),
            as_of_date DATE NOT NULL,
            status TEXT NOT NULL DEFAULT 'unknown' CHECK (
                status IN ('known','estimated','proxy','unknown','contradicted')
            ),
            score DOUBLE PRECISION CHECK (score IS NULL OR score BETWEEN 0 AND 100),
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0
                CHECK (coverage_ratio BETWEEN 0 AND 1),
            confidence_score DOUBLE PRECISION
                CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100),
            payload JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (node_id, dimension_id, as_of_date)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS supply_chain_transmission_edges (
            edge_id TEXT PRIMARY KEY,
            chain_id TEXT NOT NULL,
            from_node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            to_node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            flow_type TEXT NOT NULL CHECK (
                flow_type IN ('product_flow','value_flow','technology_flow','data_flow')
            ),
            transmission_logic TEXT NOT NULL,
            transmission_strength DOUBLE PRECISION
                CHECK (transmission_strength IS NULL OR transmission_strength BETWEEN 0 AND 100),
            transmission_lag_days INTEGER
                CHECK (transmission_lag_days IS NULL OR transmission_lag_days >= 0),
            failure_conditions JSONB NOT NULL DEFAULT '[]',
            leading_metric_ids JSONB NOT NULL DEFAULT '[]',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0
                CHECK (coverage_ratio BETWEEN 0 AND 1),
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (chain_id, from_node_id, to_node_id, flow_type)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS supply_chain_technology_routes (
            route_id TEXT PRIMARY KEY,
            chain_id TEXT NOT NULL,
            node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            route_name TEXT NOT NULL,
            maturity_stage TEXT NOT NULL CHECK (maturity_stage IN (
                'concept','prototype','engineering_sample','customer_validation',
                'small_batch','mass_production','mature','declining'
            )),
            performance_metrics JSONB NOT NULL DEFAULT '{}',
            manufacturing_difficulty JSONB NOT NULL DEFAULT '{}',
            cost_trend JSONB NOT NULL DEFAULT '{}',
            substitute_route_ids JSONB NOT NULL DEFAULT '[]',
            failure_conditions JSONB NOT NULL DEFAULT '[]',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            last_strong_evidence_date DATE,
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS supply_chain_node_scores (
            score_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            demand_certainty DOUBLE PRECISION,
            value_pool_score DOUBLE PRECISION,
            bottleneck_score DOUBLE PRECISION,
            supply_demand_score DOUBLE PRECISION,
            technology_maturity_score DOUBLE PRECISION,
            commercialization_score DOUBLE PRECISION,
            transmission_score DOUBLE PRECISION,
            evidence_quality_score DOUBLE PRECISION,
            total_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0
                CHECK (coverage_ratio BETWEEN 0 AND 1),
            score_status TEXT NOT NULL DEFAULT 'insufficient_evidence',
            score_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (node_id, trade_date, model_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS business_tag_authenticity_scores (
            score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            evidence_level TEXT NOT NULL
                CHECK (evidence_level IN ('E0','E1','E2','E3','E4','E5','E6')),
            product_evidence_score DOUBLE PRECISION,
            customer_evidence_score DOUBLE PRECISION,
            order_revenue_evidence_score DOUBLE PRECISION,
            source_reliability_score DOUBLE PRECISION,
            freshness_score DOUBLE PRECISION,
            authenticity_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0
                CHECK (coverage_ratio BETWEEN 0 AND 1),
            max_pool_code TEXT CHECK (max_pool_code IS NULL OR max_pool_code IN ('A','B','C','D')),
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            score_detail JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date, model_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS business_tag_operating_quality_scores (
            score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            growth_score DOUBLE PRECISION,
            profit_score DOUBLE PRECISION,
            moat_score DOUBLE PRECISION,
            total_score DOUBLE PRECISION,
            growth_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
            profit_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
            moat_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
            data_status JSONB NOT NULL DEFAULT '{}',
            cap_hits JSONB NOT NULL DEFAULT '[]',
            score_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date, model_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS business_tag_benefit_scores (
            score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            node_attractiveness DOUBLE PRECISION,
            operating_quality_score DOUBLE PRECISION,
            revenue_exposure_score DOUBLE PRECISION,
            order_certainty_score DOUBLE PRECISION,
            profit_elasticity_score DOUBLE PRECISION,
            delivery_capability_score DOUBLE PRECISION,
            benefit_raw DOUBLE PRECISION,
            authenticity_score DOUBLE PRECISION,
            benefit_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
            score_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date, model_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS business_tag_selection_scores (
            selection_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            benefit_score DOUBLE PRECISION,
            expectation_gap_score DOUBLE PRECISION,
            catalyst_score DOUBLE PRECISION,
            risk_score DOUBLE PRECISION,
            confidence_score DOUBLE PRECISION,
            opportunity_score DOUBLE PRECISION,
            pool_code TEXT CHECK (pool_code IS NULL OR pool_code IN ('A','B','C','D')),
            eligibility_status TEXT NOT NULL,
            veto_reasons JSONB NOT NULL DEFAULT '[]',
            factor_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date, model_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS business_tag_pool_state (
            mapping_id TEXT PRIMARY KEY REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            pool_code TEXT NOT NULL CHECK (pool_code IN ('A','B','C','D')),
            state_status TEXT NOT NULL DEFAULT 'active',
            effective_from DATE NOT NULL,
            next_validation_event TEXT,
            next_validation_date DATE,
            source_selection_id TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS business_tag_pool_transition_log (
            transition_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            from_pool_code TEXT
                CHECK (from_pool_code IS NULL OR from_pool_code IN ('A','B','C','D')),
            to_pool_code TEXT
                CHECK (to_pool_code IS NULL OR to_pool_code IN ('A','B','C','D')),
            transition_date DATE NOT NULL,
            transition_reason TEXT NOT NULL,
            trigger_evidence_ids JSONB NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            reviewer TEXT,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # These two cross-model registry tables already exist in the live database,
    # but old bootstrap SQL did not make them reproducible through Alembic.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS screening_models (
            id SERIAL PRIMARY KEY,
            model_key VARCHAR NOT NULL UNIQUE,
            display_name VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            factor_keys VARCHAR[] NOT NULL DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_versions (
            id SERIAL PRIMARY KEY,
            model_name VARCHAR NOT NULL,
            version_tag VARCHAR NOT NULL,
            snapshot_count INTEGER NOT NULL DEFAULT 0,
            win_rate DOUBLE PRECISION,
            mean_return DOUBLE PRECISION,
            is_current BOOLEAN NOT NULL DEFAULT FALSE,
            deployed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (model_name, version_tag)
        )
        """
    )

    for table_name, columns in SCORE_COLUMNS.items():
        for index, column_name in enumerate(columns):
            op.execute(
                f"ALTER TABLE {table_name} "
                f"ADD CONSTRAINT ck_{table_name[:18]}_{index}_0_100 "
                f"CHECK ({column_name} IS NULL OR {column_name} BETWEEN 0 AND 100)"
            )
    for table_name, columns in COVERAGE_COLUMNS.items():
        for index, column_name in enumerate(columns):
            op.execute(
                f"ALTER TABLE {table_name} "
                f"ADD CONSTRAINT ck_{table_name[:18]}_cov_{index} "
                f"CHECK ({column_name} BETWEEN 0 AND 1)"
            )

    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_node_dimensions_lookup "
        "ON supply_chain_node_dimensions(node_id, as_of_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_transmission_edges_chain "
        "ON supply_chain_transmission_edges(chain_id, flow_type)",
        "CREATE INDEX IF NOT EXISTS idx_node_scores_date "
        "ON supply_chain_node_scores(trade_date, total_score DESC NULLS LAST)",
        "CREATE INDEX IF NOT EXISTS idx_selection_scores_pool "
        "ON business_tag_selection_scores"
        "(trade_date, model_version, pool_code, opportunity_score DESC NULLS LAST)",
        "CREATE INDEX IF NOT EXISTS idx_pool_transition_mapping "
        "ON business_tag_pool_transition_log(mapping_id, transition_date DESC)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_screening_snapshots_supply_chain_v2 "
        "ON screening_snapshots"
        "(model_key, trade_date, stock_code, COALESCE(time_slot, '')) "
        "WHERE model_key = 'supply_chain_research_selection_v2'",
    ):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_screening_snapshots_supply_chain_v2")
    for table_name in (
        "business_tag_pool_transition_log",
        "business_tag_pool_state",
        "business_tag_selection_scores",
        "business_tag_benefit_scores",
        "business_tag_operating_quality_scores",
        "business_tag_authenticity_scores",
        "supply_chain_node_scores",
        "supply_chain_technology_routes",
        "supply_chain_transmission_edges",
        "supply_chain_node_dimensions",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table_name}")
