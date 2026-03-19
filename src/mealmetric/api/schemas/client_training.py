import uuid
from datetime import date, datetime

from pydantic import BaseModel

from mealmetric.models.training import (
    AssignmentStatus,
    TrainingPackageStatus,
    WorkoutCompletionStatus,
)


class ClientTrainingPackageSummary(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: TrainingPackageStatus
    duration_days: int | None
    is_template: bool


class ClientAssignmentChecklistItemRead(BaseModel):
    id: uuid.UUID
    label: str
    details: str | None
    position: int
    is_required: bool


class ClientAssignmentRoutineRead(BaseModel):
    routine_id: uuid.UUID
    position: int
    day_label: str | None
    title: str
    description: str | None
    difficulty: str | None
    estimated_minutes: int | None


class ClientAssignmentRead(BaseModel):
    id: uuid.UUID
    training_package_id: uuid.UUID
    pt_user_id: uuid.UUID
    client_user_id: uuid.UUID
    status: AssignmentStatus
    assigned_at: datetime
    start_date: date | None
    end_date: date | None
    created_at: datetime
    updated_at: datetime
    package: ClientTrainingPackageSummary


class ClientAssignmentListResponse(BaseModel):
    items: list[ClientAssignmentRead]
    count: int


class ClientAssignmentDetailResponse(ClientAssignmentRead):
    routines: list[ClientAssignmentRoutineRead]
    checklist_items: list[ClientAssignmentChecklistItemRead]


class ClientAssignmentChecklistResponse(BaseModel):
    items: list[ClientAssignmentChecklistItemRead]
    count: int


class ClientWorkoutLogRead(BaseModel):
    id: uuid.UUID
    client_user_id: uuid.UUID
    pt_user_id: uuid.UUID
    assignment_id: uuid.UUID | None
    routine_id: uuid.UUID | None
    performed_at: datetime
    duration_minutes: int | None
    completion_status: WorkoutCompletionStatus
    client_notes: str | None
    pt_notes: str | None
    created_at: datetime
    updated_at: datetime


class ClientWorkoutLogListResponse(BaseModel):
    items: list[ClientWorkoutLogRead]
    count: int


class ClientWorkoutLogCreateRequest(BaseModel):
    assignment_id: uuid.UUID | None = None
    routine_id: uuid.UUID | None = None
    performed_at: datetime | None = None
    duration_minutes: int | None = None
    completion_status: WorkoutCompletionStatus = WorkoutCompletionStatus.COMPLETED
    client_notes: str | None = None
