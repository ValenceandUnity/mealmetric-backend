import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

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
    exercise_entries: list["ClientWorkoutLogExerciseEntryRead"]
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
    exercise_entries: list["ClientWorkoutLogExerciseEntryCreateRequest"] = Field(
        default_factory=list
    )


class ClientWorkoutLogExerciseEntryRead(BaseModel):
    id: uuid.UUID
    exercise_name: str | None
    sets: int | None
    reps: int | None
    weight: Decimal | None
    duration_seconds: int | None
    notes: str | None
    position: int
    created_at: datetime
    updated_at: datetime


class ClientWorkoutLogExerciseEntryCreateRequest(BaseModel):
    exercise_name: str | None = None
    sets: int | None = None
    reps: int | None = None
    weight: Decimal | None = None
    duration_seconds: int | None = None
    notes: str | None = None
    position: int

    @model_validator(mode="after")
    def validate_meaningful_row(self) -> "ClientWorkoutLogExerciseEntryCreateRequest":
        meaningful_text = bool(self.exercise_name and self.exercise_name.strip())
        meaningful_notes = bool(self.notes and self.notes.strip())
        if (
            any(
                value is not None
                for value in (self.sets, self.reps, self.weight, self.duration_seconds)
            )
            or meaningful_text
            or meaningful_notes
        ):
            return self
        raise ValueError("exercise_entry_meaningful_field_required")
