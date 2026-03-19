import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy.orm import Session

from mealmetric.core.middleware.request_id import get_request_id
from mealmetric.models.audit_log import AuditEventAction, AuditEventCategory, AuditLog
from mealmetric.models.user import Role

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_MAX_DEPTH = 4
_MAX_ITEMS = 50
_MAX_STRING_LENGTH = 1000


def append_event(
    session: Session,
    *,
    category: AuditEventCategory,
    action: AuditEventAction,
    target_entity_type: str,
    target_entity_id: object,
    actor_user_id: uuid.UUID | None = None,
    actor_role: Role | str | None = None,
    related_entity_type: str | None = None,
    related_entity_id: object | None = None,
    request_id: str | None = None,
    metadata: Mapping[str, object] | None = None,
    message: str | None = None,
) -> AuditLog:
    audit_row = AuditLog(
        category=category,
        action=action,
        actor_user_id=actor_user_id,
        actor_role=_normalize_actor_role(actor_role),
        target_entity_type=target_entity_type,
        target_entity_id=_stringify_identifier(target_entity_id),
        related_entity_type=related_entity_type,
        related_entity_id=(
            _stringify_identifier(related_entity_id) if related_entity_id is not None else None
        ),
        request_id=_normalize_request_id(request_id),
        metadata_json=_sanitize_mapping(metadata or {}),
        message=message,
    )
    session.add(audit_row)
    session.flush()
    return audit_row


def _normalize_actor_role(actor_role: Role | str | None) -> str | None:
    if actor_role is None:
        return None
    if isinstance(actor_role, Enum):
        return str(actor_role.value)
    return _truncate_string(str(actor_role))


def _normalize_request_id(request_id: str | None) -> str | None:
    normalized = request_id if request_id is not None else get_request_id()
    if normalized == "-":
        return None
    return _truncate_string(normalized)


def _stringify_identifier(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return _truncate_string(str(value))


def _sanitize_mapping(value: Mapping[str, object]) -> dict[str, JsonValue]:
    return {
        _truncate_string(str(key)): _sanitize_value(item, depth=0)
        for key, item in list(value.items())[:_MAX_ITEMS]
    }


def _sanitize_value(value: object, *, depth: int) -> JsonValue:
    if depth >= _MAX_DEPTH:
        return _truncate_string(str(value))

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate_string(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _truncate_string(str(value.value))
    if isinstance(value, Mapping):
        return {
            _truncate_string(str(key)): _sanitize_value(item, depth=depth + 1)
            for key, item in list(value.items())[:_MAX_ITEMS]
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_value(item, depth=depth + 1) for item in list(value)[:_MAX_ITEMS]]
    return _truncate_string(str(value))


def _truncate_string(value: str) -> str:
    if len(value) <= _MAX_STRING_LENGTH:
        return value
    return value[: _MAX_STRING_LENGTH - 3] + "..."
