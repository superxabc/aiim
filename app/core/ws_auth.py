from __future__ import annotations

from typing import Optional
from fastapi import WebSocket, Request
from jose import jwt
from .config import settings


def extract_token_from_subprotocol(websocket: WebSocket) -> Optional[str]:
    subprotocol = websocket.headers.get("sec-websocket-protocol")
    if not subprotocol:
        return None
    parts = [p.strip() for p in subprotocol.split(",")]
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    if len(parts) == 1 and parts[0] and parts[0].lower() != "bearer":
        return parts[0]
    return None


def get_user_id_from_websocket(websocket: WebSocket) -> Optional[str]:
    token = extract_token_from_subprotocol(websocket)
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None



def get_current_user_id_from_request(request: Request) -> Optional[str]:
    """Decode JWT from Authorization header and return user id (sub).

    Supports headers in the form: Authorization: Bearer <token>
    Falls back to `token` query parameter for convenience in dev.
    """
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    token: Optional[str] = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.query_params.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None

