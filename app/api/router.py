from fastapi import APIRouter

from app.api.routes import admin, chat, health, models, usage

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(models.router)
api_router.include_router(chat.router)
api_router.include_router(usage.router)
api_router.include_router(admin.router)
