"""Add kafka to servicetype enum.

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-17

Adds 'kafka' as a new managed service type. Strimzi Kafka Operator
handles the CRD lifecycle (Kafka clusters in tenant namespaces).
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE servicetype ADD VALUE IF NOT EXISTS 'kafka'")


def downgrade() -> None:
    pass
