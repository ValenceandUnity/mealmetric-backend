import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from mealmetric.db import session as db_session
from mealmetric.models.user import Role, User
from mealmetric.repos.user_repo import UserRepository
from mealmetric.services.user_service import UserService


class _FakeSession:
    def __init__(self, result: User | None) -> None:
        self._result = result

    def scalar(self, _stmt):  # type: ignore[no-untyped-def]
        return self._result


def test_user_model_defaults() -> None:
    user = User(email="user@example.com", password_hash="hash")

    assert user.email == "user@example.com"
    assert user.role is None


def test_user_role_enum_binds_lowercase_values_for_postgres() -> None:
    bind_processor = User.__table__.c.role.type.bind_processor(postgresql.dialect())
    assert bind_processor is not None

    assert bind_processor(Role.CLIENT) == "client"
    assert bind_processor(Role.PT) == "pt"


def test_repo_and_service_lookup() -> None:
    user = User(email="x@example.com", password_hash="pw")
    session = _FakeSession(user)
    repo = UserRepository(session)  # type: ignore[arg-type]
    service = UserService(repo)

    assert repo.get_by_email("x@example.com") is user
    assert service.get_user_by_email("x@example.com") is user


def test_db_session_generator_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class _DummySession:
        def close(self) -> None:
            events.append("closed")

    def _session_factory() -> Session:
        events.append("opened")
        return _DummySession()  # type: ignore[return-value]

    def _sessionmaker(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return _session_factory

    monkeypatch.setattr(db_session, "get_engine", lambda: object())
    monkeypatch.setattr(db_session, "sessionmaker", _sessionmaker)
    gen = db_session.get_db_session()

    _ = next(gen)
    assert events == ["opened"]

    with pytest.raises(StopIteration):
        next(gen)
    assert events == ["opened", "closed"]
