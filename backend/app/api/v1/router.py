from fastapi import APIRouter

from app.api.v1 import auth, chat, floorplans, projects, public, requirements

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(requirements.router)
api_router.include_router(floorplans.router)
api_router.include_router(public.router)
api_router.include_router(chat.router)
