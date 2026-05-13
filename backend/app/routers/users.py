"""User profile endpoints — thin layer around `app.services.users`.

The frontend's Settings panel uses these to load/save per-user
preferences, switch the active user, and create / delete profiles."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import users as users_svc

log = logging.getLogger("astroagent.users")
router = APIRouter(prefix="/api/users", tags=["users"])


class CreateRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)


class SetActiveRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)


class UpdateRequest(BaseModel):
    """Loose schema — the client sends whatever subsections it edited
    (appearance, session, llm, voice) and the service merges them in.
    Extra keys are accepted to make schema evolution painless."""
    appearance: dict | None = None
    session: dict | None = None
    llm: dict | None = None
    voice: dict | None = None

    model_config = {"extra": "allow"}


@router.get("")
async def list_users():
    """Return every user profile the backend knows about + the active
    one.  Used by the user switcher on mount."""
    users = await users_svc.list_users()
    active = await users_svc.get_active_user()
    return {"users": users, "active": active}


@router.get("/current")
async def get_current_user():
    """Return the active user's full profile.  This is what the frontend
    calls on app load to apply the saved settings."""
    name = await users_svc.get_active_user()
    profile = await users_svc.get_user(name)
    if profile is None:
        raise HTTPException(404, f"Active user '{name}' has no profile on disk.")
    return profile


@router.get("/{username}")
async def get_user(username: str):
    profile = await users_svc.get_user(username)
    if profile is None:
        raise HTTPException(404, f"User '{username}' not found.")
    return profile


@router.post("")
async def create_user(req: CreateRequest):
    try:
        profile = await users_svc.create_user(req.username)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log.info("Created user profile: %s", req.username)
    return profile


@router.put("/{username}")
async def update_user(username: str, req: UpdateRequest):
    payload = req.model_dump(exclude_none=True)
    try:
        profile = await users_svc.update_user(username, payload)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return profile


@router.delete("/{username}")
async def delete_user(username: str):
    await users_svc.delete_user(username)
    return {"ok": True}


@router.post("/active")
async def set_active(req: SetActiveRequest):
    """Persist which user is "currently logged in".  Affects the value
    `./start.sh` will pick up on next launch via the `.active` sentinel
    file."""
    try:
        await users_svc.set_active_user(req.username)
    except ValueError as e:
        raise HTTPException(404, str(e))
    log.info("Active user → %s", req.username)
    return {"active": req.username}
