from fastapi import APIRouter

router = APIRouter()

@router.get("/callback")
def slack_callback(code: str):
    return {"status": "slack connected"}
