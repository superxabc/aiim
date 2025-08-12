from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from ..models import im as im_model
from ..core.pubsub import pubsub


class ReceiptReadRequestBody(BaseModel):
    conversation_id: str
    user_id: str
    last_read_message_id: str


def mark_read(db: Session, req: ReceiptReadRequestBody) -> None:
    member = (
        db.query(im_model.ConversationMember)
        .filter(
            im_model.ConversationMember.conversation_id == req.conversation_id,
            im_model.ConversationMember.user_id == req.user_id,
        )
        .first()
    )
    if not member:
        # 不存在则创建最小成员记录（兼容外部调用），实际生产应严格鉴权
        member = im_model.ConversationMember(
            conversation_id=req.conversation_id,
            user_id=req.user_id,
            role="member",
            joined_at=datetime.utcnow(),
        )
        db.add(member)

    member.last_read_message_id = req.last_read_message_id
    db.commit()

    # 发布已读事件
    try:
        payload = {
            "event": "receipt.read",
            "conversation_id": req.conversation_id,
            "user_id": req.user_id,
            "last_read_message_id": req.last_read_message_id,
        }
        import asyncio
        asyncio.create_task(pubsub.publish(f"im:conv:{req.conversation_id}", payload))
    except Exception:
        pass


def mark_delivered(db: Session, conversation_id: str, message_id: str) -> None:
    msg = (
        db.query(im_model.IMMessage)
        .filter(
            im_model.IMMessage.conversation_id == conversation_id,
            im_model.IMMessage.message_id == message_id,
        )
        .first()
    )
    if not msg:
        return
    if msg.status != "delivered":
        msg.status = "delivered"
        db.commit()
    # 发布送达事件
    try:
        payload = {
            "event": "receipt.delivered",
            "conversation_id": conversation_id,
            "message_id": message_id,
        }
        import asyncio
        asyncio.create_task(pubsub.publish(f"im:conv:{conversation_id}", payload))
    except Exception:
        pass


