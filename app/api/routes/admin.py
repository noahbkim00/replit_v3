from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.api.deps import (
    get_limit_service,
    get_usage_report_service,
    get_usage_service,
    require_admin,
)
from app.repositories.users import User
from app.services.limits import LimitService
from app.services.usage import UsageService
from app.services.usage_report import UsageReportService

router = APIRouter()


class UserLimitsUpdate(BaseModel):
    requests_per_minute: int | None = None
    daily_tokens: int | None = None
    total_tokens: int | None = None


@router.put("/admin/users/{user_id}/limits")
def update_user_limits(
    user_id: str,
    limits_update: UserLimitsUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    limit_service: Annotated[LimitService, Depends(get_limit_service)],
) -> dict[str, int | None | str]:
    return limit_service.update_user_limits(
        user_id=user_id,
        requests_per_minute=limits_update.requests_per_minute,
        daily_tokens=limits_update.daily_tokens,
        total_tokens=limits_update.total_tokens,
    )


@router.get("/admin/users/{user_id}/limits")
def get_user_limits(
    user_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    limit_service: Annotated[LimitService, Depends(get_limit_service)],
) -> dict[str, int | None | str]:
    return limit_service.get_user_limits(user_id)


@router.get("/admin/users/{user_id}/usage")
def get_user_usage(
    user_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
) -> dict[str, Any]:
    return usage_service.get_usage_summary(user_id)


@router.get("/admin/users/{user_id}/usage/report", response_class=HTMLResponse)
def get_user_usage_report(
    user_id: str,
    admin: Annotated[User, Depends(require_admin)],
    usage_report_service: Annotated[UsageReportService, Depends(get_usage_report_service)],
) -> HTMLResponse:
    return HTMLResponse(
        usage_report_service.render_admin_user_usage_report(
            admin_user_id=admin.id,
            target_user_id=user_id,
        )
    )


@router.get("/admin/usage/report", response_class=HTMLResponse)
def get_admin_usage_report(
    admin: Annotated[User, Depends(require_admin)],
    usage_report_service: Annotated[UsageReportService, Depends(get_usage_report_service)],
) -> HTMLResponse:
    return HTMLResponse(usage_report_service.render_admin_usage_report(admin.id))
