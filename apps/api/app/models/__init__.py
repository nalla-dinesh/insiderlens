"""One module per table (SQLAlchemy 2.0 typed Mapped style).
Import all models here so Alembic's target_metadata sees the full schema.
"""

from app.models.account import Account
from app.models.activity_log import ActivityLog
from app.models.alert import Alert
from app.models.case import Case, CaseNote
from app.models.customer import Customer
from app.models.employee import Employee, Role
from app.models.ground_truth import GroundTruth
from app.models.run import Run
from app.models.transaction import Transaction

__all__ = [
    "Account",
    "ActivityLog",
    "Alert",
    "Case",
    "CaseNote",
    "Customer",
    "Employee",
    "GroundTruth",
    "Role",
    "Run",
    "Transaction",
]
