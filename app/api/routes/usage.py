from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.api.deps import get_usage_report_service, get_usage_service, require_user
from app.repositories.users import User
from app.services.usage import UsageService
from app.services.usage_report import UsageReportService, render_usage_report_browser_shell

router = APIRouter()


@router.get("/usage")
def get_usage(
    user: Annotated[User, Depends(require_user)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
) -> dict[str, Any]:
    return usage_service.get_usage_summary(user.id)


@router.get("/usage/events")
def get_usage_events(
    user: Annotated[User, Depends(require_user)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
) -> dict[str, Any]:
    return usage_service.list_usage_events(user.id)


@router.get("/usage/report", response_class=HTMLResponse)
def get_usage_report(
    user: Annotated[User, Depends(require_user)],
    usage_report_service: Annotated[UsageReportService, Depends(get_usage_report_service)],
) -> HTMLResponse:
    return HTMLResponse(usage_report_service.render_user_usage_report(user.id))


@router.get("/usage/report/browser", response_class=HTMLResponse)
def get_usage_report_browser() -> HTMLResponse:
    return HTMLResponse(render_usage_report_browser_shell())
