import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealmetric.models.bookmark import BookmarkFolder, BookmarkItem
from mealmetric.repos import bookmark_repo
from mealmetric.services.vendor_service import MealPlanSummaryView, VendorService


class BookmarkServiceError(Exception):
    """Base bookmark-domain service error."""


class BookmarkConflictError(BookmarkServiceError):
    """Raised when a uniqueness constraint is hit."""


class BookmarkNotFoundError(BookmarkServiceError):
    """Raised when a folder or item is missing."""


@dataclass(frozen=True, slots=True)
class BookmarkItemView:
    id: uuid.UUID
    meal_plan_id: uuid.UUID
    note: str | None
    created_at: datetime
    meal_plan: MealPlanSummaryView


@dataclass(frozen=True, slots=True)
class BookmarkFolderView:
    id: uuid.UUID
    client_user_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    items: tuple[BookmarkItemView, ...]


class BookmarkService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._vendor_service = VendorService(session)

    def list_folders(self, *, client_user_id: uuid.UUID) -> tuple[BookmarkFolderView, ...]:
        folders = bookmark_repo.list_folders_for_client(
            self._session,
            client_user_id=client_user_id,
        )
        return tuple(self._folder_to_view(folder) for folder in folders)

    def create_folder(
        self,
        *,
        client_user_id: uuid.UUID,
        name: str,
        description: str | None,
    ) -> BookmarkFolderView:
        try:
            folder = bookmark_repo.create_folder(
                self._session,
                client_user_id=client_user_id,
                name=name,
                description=description,
            )
        except IntegrityError as exc:
            raise BookmarkConflictError("bookmark_folder_already_exists") from exc
        return self._folder_to_view(folder)

    def add_item(
        self,
        *,
        client_user_id: uuid.UUID,
        folder_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
        note: str | None,
    ) -> BookmarkItemView:
        folder = self._require_folder(folder_id=folder_id, client_user_id=client_user_id)
        try:
            item = bookmark_repo.create_item(
                self._session,
                folder_id=folder.id,
                meal_plan_id=meal_plan_id,
                note=note,
            )
        except IntegrityError as exc:
            raise BookmarkConflictError("bookmark_item_already_exists") from exc
        return self._item_to_view(item)

    def delete_folder(self, *, client_user_id: uuid.UUID, folder_id: uuid.UUID) -> None:
        folder = self._require_folder(folder_id=folder_id, client_user_id=client_user_id)
        bookmark_repo.delete_folder(self._session, folder)

    def delete_item(
        self,
        *,
        client_user_id: uuid.UUID,
        folder_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> None:
        self._require_folder(folder_id=folder_id, client_user_id=client_user_id)
        item = bookmark_repo.get_item_for_folder(
            self._session,
            item_id=item_id,
            folder_id=folder_id,
        )
        if item is None:
            raise BookmarkNotFoundError("bookmark_item_not_found")
        bookmark_repo.delete_item(self._session, item)

    def _require_folder(
        self,
        *,
        folder_id: uuid.UUID,
        client_user_id: uuid.UUID,
    ) -> BookmarkFolder:
        folder = bookmark_repo.get_folder_for_client(
            self._session,
            folder_id=folder_id,
            client_user_id=client_user_id,
        )
        if folder is None:
            raise BookmarkNotFoundError("bookmark_folder_not_found")
        return folder

    def _folder_to_view(self, folder: BookmarkFolder) -> BookmarkFolderView:
        return BookmarkFolderView(
            id=folder.id,
            client_user_id=folder.client_user_id,
            name=folder.name,
            description=folder.description,
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            items=tuple(
                self._item_to_view(item)
                for item in sorted(folder.items, key=lambda entry: (entry.created_at, entry.id))
            ),
        )

    def _item_to_view(self, item: BookmarkItem) -> BookmarkItemView:
        meal_plan = self._vendor_service.get_meal_plan_detail(
            meal_plan_id=item.meal_plan_id,
            discoverable_only=False,
        )
        if meal_plan is None:
            raise BookmarkNotFoundError("meal_plan_not_found")
        return BookmarkItemView(
            id=item.id,
            meal_plan_id=item.meal_plan_id,
            note=item.note,
            created_at=item.created_at,
            meal_plan=MealPlanSummaryView(
                id=meal_plan.id,
                vendor_id=meal_plan.vendor_id,
                vendor_name=meal_plan.vendor_name,
                vendor_zip_code=meal_plan.vendor_zip_code,
                slug=meal_plan.slug,
                name=meal_plan.name,
                description=meal_plan.description,
                status=meal_plan.status,
                total_price_cents=meal_plan.total_price_cents,
                total_calories=meal_plan.total_calories,
                item_count=meal_plan.item_count,
                availability_count=meal_plan.availability_count,
            ),
        )
