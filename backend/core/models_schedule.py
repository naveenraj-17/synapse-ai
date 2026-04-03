"""
Pydantic models for the Schedules feature.
"""
from typing import Literal
from pydantic import BaseModel


class Schedule(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    created_at: str
    target_type: Literal["agent", "orchestration"]
    target_id: str
    prompt: str
    schedule_type: Literal["interval", "cron"]
    # Interval fields
    interval_value: int | None = None
    interval_unit: Literal["minutes", "hours", "days"] | None = None
    # Cron fields
    cron_expression: str | None = None
    missed_run_policy: Literal["run_immediately", "skip"] = "skip"
    # Server-computed state -- never trust client-provided values
    last_run_at: str | None = None
    next_run_at: str | None = None


class ScheduleCreate(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    target_type: Literal["agent", "orchestration"]
    target_id: str
    prompt: str
    schedule_type: Literal["interval", "cron"]
    # Interval fields
    interval_value: int | None = None
    interval_unit: Literal["minutes", "hours", "days"] | None = None
    # Cron fields
    cron_expression: str | None = None
    missed_run_policy: Literal["run_immediately", "skip"] = "skip"


class ScheduleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    target_type: Literal["agent", "orchestration"] | None = None
    target_id: str | None = None
    prompt: str | None = None
    schedule_type: Literal["interval", "cron"] | None = None
    interval_value: int | None = None
    interval_unit: Literal["minutes", "hours", "days"] | None = None
    cron_expression: str | None = None
    missed_run_policy: Literal["run_immediately", "skip"] | None = None
