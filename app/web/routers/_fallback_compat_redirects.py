from fastapi import APIRouter
from starlette.responses import RedirectResponse

router = APIRouter()

@router.get("/batch")
async def batch_redirect():
    return RedirectResponse(url="/admin", status_code=307)

@router.get("/history")
async def history_redirect():
    return RedirectResponse(url="/admin", status_code=307)
