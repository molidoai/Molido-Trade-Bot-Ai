"""Add PROP account type and prop-firm fields

Revision ID: 002
Revises: 001
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend account_type enum with PROP (PostgreSQL)
    op.execute("ALTER TYPE account_type ADD VALUE IF NOT EXISTS 'PROP'")

    prop_phase = sa.Enum(
        "CHALLENGE", "VERIFICATION", "FUNDED", "SCALED",
        name="prop_phase",
    )
    prop_phase.create(op.get_bind(), checkfirst=True)

    op.add_column("broker_accounts", sa.Column("prop_firm_name", sa.String(length=100), nullable=True))
    op.add_column("broker_accounts", sa.Column("prop_phase", prop_phase, nullable=True))
    op.add_column("broker_accounts", sa.Column("prop_account_size", sa.Float(), nullable=True))
    op.add_column("broker_accounts", sa.Column("prop_max_daily_loss_pct", sa.Float(), nullable=True))
    op.add_column("broker_accounts", sa.Column("prop_max_total_drawdown_pct", sa.Float(), nullable=True))
    op.add_column("broker_accounts", sa.Column("prop_profit_target_pct", sa.Float(), nullable=True))
    op.add_column("broker_accounts", sa.Column("prop_min_trading_days", sa.Integer(), nullable=True))
    op.add_column("broker_accounts", sa.Column("prop_consistency_rule_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_accounts", "prop_consistency_rule_pct")
    op.drop_column("broker_accounts", "prop_min_trading_days")
    op.drop_column("broker_accounts", "prop_profit_target_pct")
    op.drop_column("broker_accounts", "prop_max_total_drawdown_pct")
    op.drop_column("broker_accounts", "prop_max_daily_loss_pct")
    op.drop_column("broker_accounts", "prop_account_size")
    op.drop_column("broker_accounts", "prop_phase")
    op.drop_column("broker_accounts", "prop_firm_name")
    sa.Enum(name="prop_phase").drop(op.get_bind(), checkfirst=True)
