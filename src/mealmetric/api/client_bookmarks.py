from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from mealmetric.api.deps.auth import get_current_user, require_roles, require_trusted_caller
from mealmetric.api.schemas.bookmark import (
    BookmarkFolderCreateRequest,
    BookmarkFolderListResponse,
    BookmarkFolderRead,
    BookmarkItemCreateRequest,
    BookmarkItemRead,
)
from mealmetric.api.schemas.vendor import MealPlanSummaryRead
from mealmetric.db.session import get_db
from mealmetric.models.user import Role, User
from mealmetric.services.bookmark_service import (
    BookmarkConflictError,
    BookmarkFolderView,
    BookmarkItemView,
    BookmarkNotFoundError,
    BookmarkService,
)
from mealmetric.services.vendor_service import MealPlanSummaryView

router = APIRouter(
    prefix="/client/bookmarks",
    dependencies=[Depends(require_trusted_caller), Depends(require_roles(Role.CLIENT))],
    tags=["client-bookmarks"],
)
DBSessionDep = Annotated[Session | None, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="db_unavailable"
        )
    return db


def _meal_plan_to_read(plan: MealPlanSummaryView) -> MealPlanSummaryRead:
    return MealPlanSummaryRead(
        id=plan.id,
        vendor_id=plan.vendor_id,
        vendor_name=plan.vendor_name,
        vendor_zip_code=plan.vendor_zip_code,
        slug=plan.slug,
        name=plan.name,
        description=plan.description,
        status=plan.status,
        total_price_cents=plan.total_price_cents,
        total_calories=plan.total_calories,
        item_count=plan.item_count,
        availability_count=plan.availability_count,
    )


def _item_to_read(view: BookmarkItemView) -> BookmarkItemRead:
    return BookmarkItemRead(
        id=view.id,
        meal_plan_id=view.meal_plan_id,
        note=view.note,
        created_at=view.created_at,
        meal_plan=_meal_plan_to_read(view.meal_plan),
    )


def _folder_to_read(view: BookmarkFolderView) -> BookmarkFolderRead:
    return BookmarkFolderRead(
        id=view.id,
        client_user_id=view.client_user_id,
        name=view.name,
        description=view.description,
        created_at=view.created_at,
        updated_at=view.updated_at,
        items=[_item_to_read(item) for item in view.items],
    )


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BookmarkNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, BookmarkConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error")


@router.get("", response_model=BookmarkFolderListResponse)
def list_bookmarks(db: DBSessionDep, current_user: CurrentUserDep) -> BookmarkFolderListResponse:
    session = _require_db(db)
    service = BookmarkService(session)
    items = [_folder_to_read(item) for item in service.list_folders(client_user_id=current_user.id)]
    return BookmarkFolderListResponse(items=items, count=len(items))


@router.post("", response_model=BookmarkFolderRead, status_code=status.HTTP_201_CREATED)
def create_bookmark_folder(
    payload: BookmarkFolderCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> BookmarkFolderRead:
    session = _require_db(db)
    service = BookmarkService(session)
    try:
        result = service.create_folder(
            client_user_id=current_user.id,
            name=payload.name,
            description=payload.description,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        raise _translate_error(exc) from exc
    return _folder_to_read(result)


@router.post(
    "/{folder_id}/items", response_model=BookmarkItemRead, status_code=status.HTTP_201_CREATED
)
def create_bookmark_item(
    folder_id: UUID,
    payload: BookmarkItemCreateRequest,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> BookmarkItemRead:
    session = _require_db(db)
    service = BookmarkService(session)
    try:
        result = service.add_item(
            client_user_id=current_user.id,
            folder_id=folder_id,
            meal_plan_id=payload.meal_plan_id,
            note=payload.note,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        raise _translate_error(exc) from exc
    return _item_to_read(result)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bookmark_folder(
    folder_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> Response:
    session = _require_db(db)
    service = BookmarkService(session)
    try:
        service.delete_folder(client_user_id=current_user.id, folder_id=folder_id)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{folder_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bookmark_item(
    folder_id: UUID,
    item_id: UUID,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> Response:
    session = _require_db(db)
    service = BookmarkService(session)
    try:
        service.delete_item(
            client_user_id=current_user.id,
            folder_id=folder_id,
            item_id=item_id,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
