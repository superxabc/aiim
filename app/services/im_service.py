from __future__ import annotations

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from ..models import im as im_model
from ..core.events import publish_event_async
from ..core.seq import next_seq


def create_conversation(
    db: Session, req: im_model.ConversationCreateRequest
) -> im_model.Conversation:
    conversation = im_model.Conversation(
        type=req.type,
        name=req.name,
        tenant_id=req.tenant_id,
    )
    db.add(conversation)
    db.flush()

    for i, uid in enumerate(dict.fromkeys(req.member_ids)):
        member = im_model.ConversationMember(
            conversation_id=conversation.conversation_id,
            user_id=uid,
            role="owner" if i == 0 else "member",
            tenant_id=req.tenant_id,
        )
        db.add(member)

    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(db: Session, user_id: str | None) -> List[im_model.Conversation]:
    q = db.query(im_model.Conversation)
    if user_id:
        q = q.join(
            im_model.ConversationMember,
            im_model.Conversation.conversation_id
            == im_model.ConversationMember.conversation_id,
        ).filter(im_model.ConversationMember.user_id == user_id)
    return q.order_by(im_model.Conversation.updated_at.desc()).all()


def list_conversations_with_meta(
    db: Session, user_id: Optional[str]
) -> List[im_model.Conversation]:
    items = list_conversations(db, user_id)
    # 组装 last_message 与 unread_count（基于 seq 的简化计算）
    for conv in items:
        last = (
            db.query(im_model.IMMessage)
            .filter(im_model.IMMessage.conversation_id == conv.conversation_id)
            .order_by(im_model.IMMessage.created_at.desc())
            .first()
        )
        setattr(conv, "last_message", last)
        if user_id:
            member = (
                db.query(im_model.ConversationMember)
                .filter(
                    im_model.ConversationMember.conversation_id == conv.conversation_id,
                    im_model.ConversationMember.user_id == user_id,
                )
                .first()
            )
            if member:
                last_seq = conv.last_seq or 0
                unread = max(0, int(last_seq) - int(member.last_read_seq or 0))
                setattr(conv, "unread_count", unread)
            else:
                setattr(conv, "unread_count", None)
        else:
            setattr(conv, "unread_count", None)
    return items


def create_message(
    db: Session,
    req: im_model.MessageCreateRequest,
    sender_id: str | None = None,
    seq_value: int | None = None,
) -> im_model.IMMessage:
    # 成员校验：只有会话成员可发消息
    if sender_id:
        member = (
            db.query(im_model.ConversationMember)
            .filter(
                im_model.ConversationMember.conversation_id == req.conversation_id,
                im_model.ConversationMember.user_id == sender_id,
            )
            .first()
        )
        if not member:
            raise ValueError("forbidden: not a conversation member")

    # 分配 seq（会话内递增，Redis 优先）
    if seq_value is None:
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 运行中事件循环，避免阻塞；跳过，由上层传入 seq
                seq_value = None
            else:
                seq_value = loop.run_until_complete(next_seq(req.conversation_id))
        except Exception:
            seq_value = None

    # 统一存储内容为 JSON
    payload_content = req.content
    msg = im_model.IMMessage(
        conversation_id=req.conversation_id,
        sender_id=sender_id or "unknown",
        type=req.type,
        content=payload_content,
        reply_to=req.reply_to,
        client_msg_id=req.client_msg_id,
        tenant_id=req.tenant_id,
        created_at=datetime.utcnow(),
        seq=seq_value,
        status="sent",
    )
    db.add(msg)

    conv = (
        db.query(im_model.Conversation)
        .filter(im_model.Conversation.conversation_id == req.conversation_id)
        .first()
    )
    if conv:
        conv.updated_at = datetime.utcnow()
        if msg.seq is not None and (conv.last_seq or 0) < msg.seq:
            conv.last_seq = msg.seq

    db.commit()
    db.refresh(msg)

    try:
        payload = {
            "event": "message.created",
            "conversation_id": msg.conversation_id,
            "message": {
                "message_id": msg.message_id,
                "sender_id": msg.sender_id,
                "type": msg.type,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "reply_to": msg.reply_to,
                "seq": msg.seq,
            },
        }
        publish_event_async(f"im:conv:{msg.conversation_id}", payload)
    except Exception:
        pass

    return msg


def create_stream_chunk(
    db: Session,
    conversation_id: str,
    sender_id: str,
    content: str,
    client_msg_id: str | None = None,
    stream_end: bool = False,
    tenant_id: str | None = None,
    seq_value: int | None = None,
) -> im_model.IMMessage:
    if seq_value is None:
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                seq_value = None
            else:
                seq_value = loop.run_until_complete(next_seq(conversation_id))
        except Exception:
            seq_value = None

    # 流式消息扩展字段
    msg = im_model.IMMessage(
        conversation_id=conversation_id,
        sender_id=sender_id,
        type="stream_chunk",
        content={"chunk": content},
        client_msg_id=client_msg_id,
        tenant_id=tenant_id,
        created_at=datetime.utcnow(),
        seq=seq_value,
        status="sent",
        stream_id=client_msg_id,
        chunk_index=(0 if not client_msg_id else None),
        is_end=bool(stream_end),
    )
    db.add(msg)

    conv = (
        db.query(im_model.Conversation)
        .filter(im_model.Conversation.conversation_id == conversation_id)
        .first()
    )
    if conv:
        conv.updated_at = datetime.utcnow()
        if msg.seq is not None and (conv.last_seq or 0) < msg.seq:
            conv.last_seq = msg.seq

    db.commit()
    db.refresh(msg)

    try:
        payload = {
            "event": "message.stream_chunk",
            "conversation_id": msg.conversation_id,
            "message": {
                "message_id": msg.message_id,
                "sender_id": msg.sender_id,
                "type": msg.type,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "seq": msg.seq,
                "stream_end": bool(stream_end),
            },
        }
        publish_event_async(f"im:conv:{msg.conversation_id}", payload)
    except Exception:
        pass

    return msg


def list_messages(
    db: Session,
    conversation_id: str,
    limit: int = 50,
    before_id: Optional[str] = None,
    after_seq: Optional[int] = None,
) -> List[im_model.IMMessage]:
    q = db.query(im_model.IMMessage).filter(
        im_model.IMMessage.conversation_id == conversation_id
    )
    if before_id:
        anchor = (
            db.query(im_model.IMMessage)
            .filter(im_model.IMMessage.message_id == before_id)
            .first()
        )
        if anchor:
            q = q.filter(im_model.IMMessage.created_at < anchor.created_at)
    if after_seq is not None:
        q = q.filter(im_model.IMMessage.seq != None).filter(
            im_model.IMMessage.seq > after_seq
        )  # noqa: E711
    # 优先按 seq 排序，其次按 created_at
    if hasattr(im_model.IMMessage, "seq"):
        q = q.order_by(
            im_model.IMMessage.seq.asc().nulls_last(),
            im_model.IMMessage.created_at.asc(),
        )
    else:
        q = q.order_by(im_model.IMMessage.created_at.asc())
    q = q.limit(limit)
    return q.all()
