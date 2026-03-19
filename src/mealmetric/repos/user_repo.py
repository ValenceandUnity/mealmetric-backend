import uuid

from sqlalchemy import Select, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from mealmetric.models.role import Role as NormalizedRole
from mealmetric.models.user import Role, User
from mealmetric.models.user_role import UserRole


def _query_by_email(email: str) -> Select[tuple[User]]:
    return select(User).where(User.email == email)


def _query_by_id(user_id: uuid.UUID) -> Select[tuple[User]]:
    return select(User).where(User.id == user_id)


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(_query_by_email(email))


def get_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.scalar(_query_by_id(user_id))


def create_user(session: Session, email: str, password_hash: str, role: Role) -> User:
    user = User(email=email, password_hash=password_hash, role=role)
    session.add(user)
    session.flush()
    session.refresh(user)
    return user


def bump_token_version(session: Session, user: User) -> User:
    user.token_version += 1
    session.add(user)
    session.flush()
    return user


def _is_missing_normalized_schema_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "no such table" in message or "does not exist" in message or "undefinedtable" in message


def get_role_by_name(session: Session, role_name: Role) -> NormalizedRole | None:
    stmt: Select[tuple[NormalizedRole]] = select(NormalizedRole).where(
        NormalizedRole.name == role_name.value
    )
    return session.scalar(stmt)


def get_or_create_role(session: Session, role_name: Role) -> NormalizedRole:
    role = get_role_by_name(session, role_name)
    if role is not None:
        return role

    role = NormalizedRole(name=role_name.value)
    session.add(role)
    session.flush()
    session.refresh(role)
    return role


def assign_role_to_user(session: Session, user_id: uuid.UUID, role_name: Role) -> UserRole | None:
    try:
        role = get_or_create_role(session, role_name)
        stmt: Select[tuple[UserRole]] = select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
        )
        existing = session.scalar(stmt)
        if existing is not None:
            return existing

        user_role = UserRole(user_id=user_id, role_id=role.id)
        session.add(user_role)
        session.flush()
        return user_role
    except AttributeError:
        return None
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_normalized_schema_error(exc):
            return None
        raise


def get_roles_for_user(session: Session, user_id: uuid.UUID) -> frozenset[Role]:
    try:
        stmt = (
            select(NormalizedRole.name)
            .join(UserRole, UserRole.role_id == NormalizedRole.id)
            .where(UserRole.user_id == user_id)
        )
        role_names = session.scalars(stmt).all()
        normalized_roles: set[Role] = set()
        for role_name in role_names:
            try:
                normalized_roles.add(Role(role_name))
            except ValueError:
                continue
        return frozenset(normalized_roles)
    except AttributeError:
        return frozenset()
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_normalized_schema_error(exc):
            return frozenset()
        raise


def user_has_role(session: Session, user_id: uuid.UUID, role_name: Role) -> bool:
    return role_name in get_roles_for_user(session, user_id)


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        return get_by_email(self.session, email)

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return get_by_id(self.session, user_id)

    def create_user(self, email: str, password_hash: str, role: Role) -> User:
        return create_user(self.session, email=email, password_hash=password_hash, role=role)

    def assign_role_to_user(self, user_id: uuid.UUID, role_name: Role) -> UserRole | None:
        return assign_role_to_user(self.session, user_id=user_id, role_name=role_name)

    def get_roles_for_user(self, user_id: uuid.UUID) -> frozenset[Role]:
        return get_roles_for_user(self.session, user_id)
