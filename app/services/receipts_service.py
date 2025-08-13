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


def _upsert_receipt_read(db: Session, conversation_id: str, message_id: str, user_id: str) -> None:
    rec = (
        db.query(im_model.MessageReceipt)
        .filter(
            im_model.MessageReceipt.message_id == message_id,
            im_model.MessageReceipt.user_id == user_id,
        )
        .first()
    )
    now = datetime.utcnow()
    if rec is None:
        rec = im_model.MessageReceipt(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            delivered_at=now,  # 读必然已达
            read_at=now,
        )
        db.add(rec)
    else:
        if rec.delivered_at is None:
            rec.delivered_at = now
        rec.read_at = now
    db.commit()


def _upsert_receipt_delivered(db: Session, conversation_id: str, message_id: str, user_id: str) -> None:
    rec = (
        db.query(im_model.MessageReceipt)
        .filter(
            im_model.MessageReceipt.message_id == message_id,
            im_model.MessageReceipt.user_id == user_id,
        )
        .first()
    )
    now = datetime.utcnow()
    if rec is None:
        rec = im_model.MessageReceipt(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            delivered_at=now,
        )
        db.add(rec)
    else:
        if rec.delivered_at is None:
            rec.delivered_at = now
    db.commit()


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
    # 同步 last_read_seq 基于消息表
    anchor = (
        db.query(im_model.IMMessage)
        .filter(
            im_model.IMMessage.conversation_id == req.conversation_id,
            im_model.IMMessage.message_id == req.last_read_message_id,
        )
        .first()
    )
    if anchor and anchor.seq is not None:
        member.last_read_seq = int(anchor.seq)
    db.commit()
    # 写入 per-user receipts（只为锚点消息 upsert）
    try:
        _upsert_receipt_read(db, req.conversation_id, req.last_read_message_id, req.user_id)
    except Exception:
        pass

    # 发布已读事件
    try:
        payload = {
            "event": "receipt.read",
            "conversation_id": req.conversation_id,
            "user_id": req.user_id,
            "last_read_message_id": req.last_read_message_id,
            "last_read_seq": member.last_read_seq if anchor and anchor.seq is not None else None,
        }
        import asyncio
        asyncio.create_task(pubsub.publish(f"im:conv:{req.conversation_id}", payload))
    except Exception:
        pass


def mark_delivered(db: Session, conversation_id: str, message_id: str, user_id: str) -> None:
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
    # 发送者不可为自身消息上报 delivered
    if msg.sender_id == user_id:
        return
    # 校验是会话成员
    member = (
        db.query(im_model.ConversationMember)
        .filter(
            im_model.ConversationMember.conversation_id == conversation_id,
            im_model.ConversationMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        return
    # 写入/更新 per-user receipts（delivered）
    try:
        _upsert_receipt_delivered(db, conversation_id, message_id, user_id)
    except Exception:
        pass
    # 发布送达事件
    try:
        payload = {
            "event": "receipt.delivered",
            "conversation_id": conversation_id,
            "message_id": message_id,
            "seq": msg.seq,
            "user_id": user_id,
        }
        import asyncio
        asyncio.create_task(pubsub.publish(f"im:conv:{conversation_id}", payload))
    except Exception:
        pass


def list_receipts(db: Session, conversation_id: str, message_id: str):
    items = (
        db.query(im_model.MessageReceipt)
        .filter(
            im_model.MessageReceipt.conversation_id == conversation_id,
            im_model.MessageReceipt.message_id == message_id,
        )
        .all()
    )
    return items


