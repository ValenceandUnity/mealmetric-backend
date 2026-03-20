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


def test_db_session_generator_returns_none_when_engine_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _RequestState:
        request_id = "req-engine"

    class _Request:
        state = _RequestState()

    monkeypatch.setattr(db_session, "get_engine", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    caplog.set_level("ERROR", logger="mealmetric.db")

    gen = db_session.get_db(_Request())  # type: ignore[arg-type]
    assert next(gen) is None

    with pytest.raises(StopIteration):
        next(gen)

    assert any(
        record.message == "database session setup failed"
        and getattr(record, "stage", None) == "get_engine"
        for record in caplog.records
    )


def test_db_session_generator_swallows_close_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _RequestState:
        request_id = "req-close"

    class _Request:
        state = _RequestState()

    class _BrokenSession:
        def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(db_session, "get_engine", lambda: object())
    monkeypatch.setattr(db_session, "sessionmaker", lambda **_kwargs: (lambda: _BrokenSession()))
    caplog.set_level("ERROR", logger="mealmetric.db")

    gen = db_session.get_db(_Request())  # type: ignore[arg-type]
    _ = next(gen)

    with pytest.raises(StopIteration):
        next(gen)

    assert any(
        record.message == "database session close failed"
        and getattr(record, "stage", None) == "session_close"
        for record in caplog.records
    )
