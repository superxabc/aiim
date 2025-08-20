from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import im as im_model
from app.services import im_service
from app.services import receipts_service
from app.core.ws_auth import get_current_user_id_from_request


router = APIRouter()


@router.post("/conversations", response_model=im_model.ConversationInfo)
def create_conversation(
    req: im_model.ConversationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
            )
        # Ensure creator is first member
        if user_id not in req.member_ids:
            req.member_ids.insert(0, user_id)
        conv = im_service.create_conversation(db, req)
        return conv
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/conversations", response_model=im_model.ConversationListResponse)
def list_conversations(
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id_from_request(request)
    items = im_service.list_conversations_with_meta(db, user_id)
    return {"conversations": items}


@router.post("/messages", response_model=im_model.MessageCreateResponse)
async def create_message(
    req: im_model.MessageCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
            )

        # 对于音频消息，验证media_id是否存在和有效
        if req.type == "audio" and isinstance(req.content, dict):
            media_id = req.content.get("media_id")
            if media_id:
                from app.core.media_storage import media_storage

                # 验证媒体文件是否存在
                metadata = media_storage.get_file_metadata(
                    media_id, req.conversation_id
                )
                if not metadata:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Media file {media_id} not found",
                    )

        # 生成 seq（在事件循环中）
        from app.core.seq import next_seq

        seq_value = await next_seq(req.conversation_id)
        # 幂等：若携带 client_msg_id，先检查是否已存在
        if req.client_msg_id:
            exists = (
                db.query(im_model.IMMessage)
                .filter(
                    im_model.IMMessage.conversation_id == req.conversation_id,
                    im_model.IMMessage.sender_id == user_id,
                    im_model.IMMessage.client_msg_id == req.client_msg_id,
                )
                .first()
            )
            if exists:
                return {"message": exists}
        msg = im_service.create_message(db, req, sender_id=user_id, seq_value=seq_value)
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/messages/stream", response_model=im_model.MessageCreateResponse)
async def create_stream_chunk(
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
            )
        conv_id = body.get("conversation_id")
        chunk = body.get("chunk")
        stream_end = bool(body.get("stream_end", False))
        if not conv_id or chunk is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="invalid payload"
            )
        # 成员校验
        member = (
            db.query(im_model.ConversationMember)
            .filter(
                im_model.ConversationMember.conversation_id == conv_id,
                im_model.ConversationMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        # 生成序列并入库
        from app.core.seq import next_seq

        seq_value = await next_seq(conv_id)
        msg = im_service.create_stream_chunk(
            db,
            conversation_id=conv_id,
            sender_id=user_id,
            content=str(chunk),
            client_msg_id=body.get("client_msg_id"),
            stream_end=stream_end,
            tenant_id=body.get("tenant_id"),
            seq_value=seq_value,
        )
        return {"message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/messages/{conversation_id}", response_model=im_model.MessageListResponse)
def list_messages(
    conversation_id: str,
    request: Request,
    limit: int = 50,
    before_id: str | None = None,
    after_seq: int | None = None,
    db: Session = Depends(get_db),
):
    try:
        user_id = get_current_user_id_from_request(request)
        # Optional: restrict to members only
        if user_id:
            member = (
                db.query(im_model.ConversationMember)
                .filter(
                    im_model.ConversationMember.conversation_id == conversation_id,
                    im_model.ConversationMember.user_id == user_id,
                )
                .first()
            )
            if not member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
                )
        items = im_service.list_messages(
            db, conversation_id, limit=limit, before_id=before_id, after_seq=after_seq
        )
        return {"conversation_id": conversation_id, "messages": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/receipts/delivered", status_code=status.HTTP_204_NO_CONTENT)
def mark_delivered(
    request: Request,
    body: dict,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id_from_request(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )
    conv_id = body.get("conversation_id")
    message_id = body.get("message_id")
    if not conv_id or not message_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid payload"
        )
    # 成员校验（发送 delivered 的必须是会话成员）
    member = (
        db.query(im_model.ConversationMember)
        .filter(
            im_model.ConversationMember.conversation_id == conv_id,
            im_model.ConversationMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    # 更新持久化状态并广播（per-user receipts）
    from app.services.receipts_service import mark_delivered as svc_mark_delivered

    svc_mark_delivered(db, conv_id, message_id, user_id)
    return


@router.post("/receipts/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    req: receipts_service.ReceiptReadRequestBody,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id_from_request(request)
    if not user_id or user_id != req.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )
    receipts_service.mark_read(db, req)
    return


@router.get("/receipts/{conversation_id}/{message_id}")
def get_receipts(
    conversation_id: str,
    message_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id_from_request(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )
    # 仅会话成员可查看
    member = (
        db.query(im_model.ConversationMember)
        .filter(
            im_model.ConversationMember.conversation_id == conversation_id,
            im_model.ConversationMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    items = receipts_service.list_receipts(db, conversation_id, message_id)
    return {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "receipts": [
            {
                "user_id": r.user_id,
                "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
                "read_at": r.read_at.isoformat() if r.read_at else None,
            }
            for r in items
        ],
    }
