"""0001 — initial full schema (Phase 02, mirrors Section 5 of the phase brief).

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("role_name", sa.String(16), primary_key=True),
        sa.Column("allowed_actions", pg.ARRAY(sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "employees",
        sa.Column("emp_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(16), sa.ForeignKey("roles.role_name"), nullable=False),
        sa.Column("branch", sa.String(40), nullable=False),
        sa.Column("join_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
    )
    op.create_table(
        "customers",
        sa.Column("cust_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("occupation", sa.String(60), nullable=False),
        sa.Column("declared_income", sa.Numeric(14, 2), nullable=False),
        sa.Column("kyc_risk", sa.String(8), nullable=False),
        sa.Column("phone", sa.String(16), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
    )
    op.create_index("ix_customers_phone", "customers", ["phone"])
    op.create_table(
        "accounts",
        sa.Column("acc_id", sa.Integer(), primary_key=True),
        sa.Column("cust_id", sa.Integer(), sa.ForeignKey("customers.cust_id"), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("branch", sa.String(40), nullable=False),
        sa.Column("open_date", sa.Date(), nullable=False),
        sa.Column("last_active_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
    )
    op.create_index("ix_accounts_cust_id", "accounts", ["cust_id"])
    op.create_index("ix_accounts_branch", "accounts", ["branch"])
    op.create_table(
        "transactions",
        sa.Column("txn_id", sa.Integer(), primary_key=True),
        sa.Column("from_acc", sa.Integer(), sa.ForeignKey("accounts.acc_id"), nullable=False),
        sa.Column("to_acc", sa.Integer(), sa.ForeignKey("accounts.acc_id"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(8), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("employees.emp_id"), nullable=True),
    )
    op.create_index("ix_tx_from_ts", "transactions", ["from_acc", "ts"])
    op.create_index("ix_tx_to_ts", "transactions", ["to_acc", "ts"])
    op.create_index("ix_tx_ts", "transactions", ["ts"])
    op.create_table(
        "activity_log",
        sa.Column("log_id", sa.Integer(), primary_key=True),
        sa.Column("emp_id", sa.Integer(), sa.ForeignKey("employees.emp_id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("target_acc", sa.Integer(), sa.ForeignKey("accounts.acc_id"), nullable=True),
        sa.Column("details", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ip", sa.String(20), nullable=False),
        sa.Column("device", sa.String(24), nullable=False),
        sa.Column("off_hours", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("role_violation", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_log_emp_ts", "activity_log", ["emp_id", "ts"])
    op.create_index("ix_log_action", "activity_log", ["action"])
    op.create_index("ix_log_target_acc", "activity_log", ["target_acc"])
    op.create_table(
        "ground_truth",
        sa.Column("gt_id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.String(4), nullable=False),
        sa.Column("entity_type", sa.String(12), nullable=False),
        sa.Column("entity_ids", pg.ARRAY(sa.Integer()), nullable=False),
        sa.Column("is_suspicious", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "runs",
        sa.Column("run_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("txn_count", sa.Integer(), nullable=True),
        sa.Column("alert_count", sa.Integer(), nullable=True),
        sa.Column("config", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(12), nullable=False),
    )
    op.create_table(
        "cases",
        sa.Column("case_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("assignee", sa.String(80), nullable=True),
        sa.Column("status", sa.String(14), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','ESCALATED','CLOSED_TRUE','CLOSED_FALSE')",
            name="cases_status_allowed",
        ),
    )
    op.create_table(
        "case_notes",
        sa.Column("note_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.case_id"), nullable=False),
        sa.Column("author", sa.String(80), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_case_notes_case_id", "case_notes", ["case_id"])
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("rule_set", pg.ARRAY(sa.String(4)), nullable=False),
        sa.Column("entity_type", sa.String(12), nullable=False),
        sa.Column("entity_ids", pg.ARRAY(sa.Integer()), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("band", sa.String(8), nullable=False),
        sa.Column("reasons", pg.JSONB(), nullable=False),
        sa.Column("evidence", pg.JSONB(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="OPEN"),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.case_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("jsonb_array_length(reasons) > 0", name="alerts_reasons_nonempty"),
        sa.CheckConstraint("evidence <> CAST('{}' AS JSONB)", name="alerts_evidence_nonempty"),
    )


def downgrade() -> None:
    for table in [
        "alerts",
        "case_notes",
        "cases",
        "runs",
        "ground_truth",
        "activity_log",
        "transactions",
        "accounts",
        "customers",
        "employees",
        "roles",
    ]:
        op.drop_table(table)
