"""Daily-summary response schemas — Phase 6.

One Pydantic model with clear counts + item lists. Items are light
summaries (id + the fields a morning check needs), not full records —
the full endpoints already exist for those.
"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.tasks import IssueCategory, IssuePriority, IssueStatus, TaskStatus
from app.models.inventory import DeliveryStatus


class SummaryTaskItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    site_id: int | None
    title: str
    status: TaskStatus
    due_date: date | None
    is_overdue: bool


class SummaryMaterialItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    name: str
    unit: str
    quantity_on_hand: Decimal
    reorder_level: Decimal
    is_low_stock: bool


class SummaryIssueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    title: str
    category: IssueCategory
    priority: IssuePriority
    status: IssueStatus


class SummaryDeliveryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    quantity: Decimal
    status: DeliveryStatus
    expected_date: date | None


class SummaryUpdateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    status: str
    summary: str | None
    created_at: datetime


class ProjectSummaryOut(BaseModel):
    """Generated on read from live data — never stored."""

    project_id: int
    project_name: str
    date: date
    overdue_count: int
    overdue_tasks: list[SummaryTaskItem]
    due_today_count: int
    due_today_tasks: list[SummaryTaskItem]
    upcoming_count: int
    upcoming_tasks: list[SummaryTaskItem]
    upcoming_days: int
    low_stock_count: int
    low_stock_materials: list[SummaryMaterialItem]
    open_issues_count: int
    open_issues: list[SummaryIssueItem]
    critical_high_issues_count: int
    critical_high_issues: list[SummaryIssueItem]
    pending_deliveries_count: int
    pending_deliveries: list[SummaryDeliveryItem]
    recent_updates_count: int
    recent_updates: list[SummaryUpdateItem]
