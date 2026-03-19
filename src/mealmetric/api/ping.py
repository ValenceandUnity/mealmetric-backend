from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}
