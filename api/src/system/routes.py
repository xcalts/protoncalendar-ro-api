import fastapi

router = fastapi.APIRouter(prefix="", tags=["System"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
