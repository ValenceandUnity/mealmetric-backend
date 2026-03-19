import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from mealmetric.models.training import (
    AssignmentStatus,
    PtClientLinkStatus,
    TrainingPackageStatus,
)


class PTProfileRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str | None
    bio: str | None
    certifications_text: str | None
    specialties_text: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PTProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    certifications_text: str | None = None
    specialties_text: str | None = None
    is_active: bool = True


class PTClientLinkRead(BaseModel):
    id: uuid.UUID
    pt_user_id: uuid.UUID
    client_user_id: uuid.UUID
    status: PtClientLinkStatus
    started_at: datetime | None
    ended_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PTClientLinkListResponse(BaseModel):
    items: list[PTClientLinkRead]
    count: int


class PTClientLinkCreateRequest(BaseModel):
    client_user_id: uuid.UUID
    status: PtClientLinkStatus = PtClientLinkStatus.PENDING
    notes: str | None = None


class PTClientLinkStatusUpdateRequest(BaseModel):
    status: PtClientLinkStatus


class PTFolderRead(BaseModel):
    id: uuid.UUID
    pt_user_id: uuid.UUID
    name: str
    description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class PTFolderListResponse(BaseModel):
    items: list[PTFolderRead]
    count: int


class PTFolderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    sort_order: int = 0


class PTFolderUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    sort_order: int


class RoutineRead(BaseModel):
    id: uuid.UUID
    pt_user_id: uuid.UUID
    folder_id: uuid.UUID | None
    title: str
    description: str | None
    difficulty: str | None
    estimated_minutes: int | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class RoutineListResponse(BaseModel):
    items: list[RoutineRead]
    count: int


class RoutineCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    folder_id: uuid.UUID | None = None
    description: str | None = None
    difficulty: str | None = None
    estimated_minutes: int | None = None


class RoutineUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    folder_id: uuid.UUID | None = None
    description: str | None = None
    difficulty: str | None = None
    estimated_minutes: int | None = None


class TrainingPackageRead(BaseModel):
    id: uuid.UUID
    pt_user_id: uuid.UUID
    folder_id: uuid.UUID | None
    title: str
    description: str | None
    status: TrainingPackageStatus
    duration_days: int | None
    is_template: bool
    created_at: datetime
    updated_at: datetime


class TrainingPackageListResponse(BaseModel):
    items: list[TrainingPackageRead]
    count: int


class TrainingPackageCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    folder_id: uuid.UUID | None = None
    description: str | None = None
    status: TrainingPackageStatus = TrainingPackageStatus.DRAFT
    duration_days: int | None = None
    is_template: bool = True


class TrainingPackageUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    folder_id: uuid.UUID | None = None
    description: str | None = None
    status: TrainingPackageStatus
    duration_days: int | None = None
    is_template: bool


class PackageRoutineRead(BaseModel):
    id: uuid.UUID
    training_package_id: uuid.UUID
    routine_id: uuid.UUID
    position: int
    day_label: str | None
    created_at: datetime


class PackageRoutineListResponse(BaseModel):
    items: list[PackageRoutineRead]
    count: int


class PackageRoutineReplaceItem(BaseModel):
    routine_id: uuid.UUID
    position: int
    day_label: str | None = None


class PackageRoutineReplaceRequest(BaseModel):
    items: list[PackageRoutineReplaceItem]


class ChecklistItemRead(BaseModel):
    id: uuid.UUID
    training_package_id: uuid.UUID | None
    routine_id: uuid.UUID | None
    label: str
    details: str | None
    position: int
    is_required: bool
    created_at: datetime
    updated_at: datetime


class ChecklistItemListResponse(BaseModel):
    items: list[ChecklistItemRead]
    count: int


class ChecklistItemReplaceItem(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    details: str | None = None
    position: int = 0
    is_required: bool = True


class ChecklistReplaceRequest(BaseModel):
    items: list[ChecklistItemReplaceItem]


class ClientAssignmentRead(BaseModel):
    id: uuid.UUID
    training_package_id: uuid.UUID
    pt_user_id: uuid.UUID
    client_user_id: uuid.UUID
    pt_client_link_id: uuid.UUID
    status: AssignmentStatus
    assigned_at: datetime
    start_date: date | None
    end_date: date | None
    created_at: datetime
    updated_at: datetime


class ClientAssignmentListResponse(BaseModel):
    items: list[ClientAssignmentRead]
    count: int


class ClientAssignmentCreateRequest(BaseModel):
    training_package_id: uuid.UUID
    status: AssignmentStatus = AssignmentStatus.ASSIGNED
    start_date: date | None = None
    end_date: date | None = None


class ClientAssignmentStatusUpdateRequest(BaseModel):
    status: AssignmentStatus
