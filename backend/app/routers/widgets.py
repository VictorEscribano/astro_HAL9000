"""REST API for custom widgets (HAL creative playground)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.tools.widget_forge import delete_widget, get_widget, list_widgets, save_widget

router = APIRouter(prefix="/api/widgets", tags=["widgets"])


class WidgetIn(BaseModel):
    name: str
    description: str
    html_content: str


@router.get("")
async def get_widgets():
    return list_widgets()


@router.get("/{widget_id}")
async def get_widget_by_id(widget_id: str):
    w = get_widget(widget_id)
    if not w:
        raise HTTPException(404, "Widget not found")
    return w


@router.post("", status_code=201)
async def create_widget(body: WidgetIn):
    return save_widget(body.name, body.description, body.html_content)


@router.delete("/{widget_id}", status_code=204)
async def remove_widget(widget_id: str):
    if not delete_widget(widget_id):
        raise HTTPException(404, "Widget not found")
