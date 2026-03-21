import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from mealmetric.models.bookmark import BookmarkFolder, BookmarkItem


def list_folders_for_client(session: Session, *, client_user_id: uuid.UUID) -> list[BookmarkFolder]:
    stmt: Select[tuple[BookmarkFolder]] = (
        select(BookmarkFolder)
        .where(BookmarkFolder.client_user_id == client_user_id)
        .options(selectinload(BookmarkFolder.items))
        .order_by(BookmarkFolder.name.asc(), BookmarkFolder.id.asc())
    )
    return list(session.scalars(stmt))


def get_folder_for_client(
    session: Session,
    *,
    folder_id: uuid.UUID,
    client_user_id: uuid.UUID,
) -> BookmarkFolder | None:
    stmt: Select[tuple[BookmarkFolder]] = (
        select(BookmarkFolder)
        .where(
            BookmarkFolder.id == folder_id,
            BookmarkFolder.client_user_id == client_user_id,
        )
        .options(selectinload(BookmarkFolder.items))
    )
    return session.scalar(stmt)


def create_folder(
    session: Session,
    *,
    client_user_id: uuid.UUID,
    name: str,
    description: str | None,
) -> BookmarkFolder:
    folder = BookmarkFolder(
        client_user_id=client_user_id,
        name=name,
        description=description,
    )
    session.add(folder)
    session.flush()
    return folder


def delete_folder(session: Session, folder: BookmarkFolder) -> None:
    session.delete(folder)
    session.flush()


def get_item_for_folder(
    session: Session,
    *,
    item_id: uuid.UUID,
    folder_id: uuid.UUID,
) -> BookmarkItem | None:
    stmt: Select[tuple[BookmarkItem]] = select(BookmarkItem).where(
        BookmarkItem.id == item_id,
        BookmarkItem.folder_id == folder_id,
    )
    return session.scalar(stmt)


def create_item(
    session: Session,
    *,
    folder_id: uuid.UUID,
    meal_plan_id: uuid.UUID,
    note: str | None,
) -> BookmarkItem:
    item = BookmarkItem(folder_id=folder_id, meal_plan_id=meal_plan_id, note=note)
    session.add(item)
    session.flush()
    return item


def delete_item(session: Session, item: BookmarkItem) -> None:
    session.delete(item)
    session.flush()
