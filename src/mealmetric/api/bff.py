from fastapi import APIRouter, Depends

from mealmetric.api.deps.auth import require_trusted_caller

router = APIRouter(prefix="/bff", dependencies=[Depends(require_trusted_caller)])


@router.get("/ping")
def bff_ping() -> dict[str, bool]:
    return {"ok": True}
