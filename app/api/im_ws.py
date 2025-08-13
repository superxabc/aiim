from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.pubsub import pubsub
from app.core.ws_auth import get_user_id_from_websocket
from app.services import im_service
from app.models import im as im_model
from app.core.config import settings


router = APIRouter()


@router.websocket("/ws")
async def im_gateway(websocket: WebSocket):
    # 最小鉴权：token -> user_id
    user_id = get_user_id_from_websocket(websocket)
    if not user_id:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    # 在线路由登记（Redis可用时）
    try:
        info = {"instance_id": settings.INSTANCE_ID, "platform": "ws", "last_ping_ts": 0}
        if hasattr(pubsub, "set_connection"):
            await pubsub.set_connection(user_id, json.dumps(info), ttl_sec=60)  # type: ignore
    except Exception:
        pass
    subscriptions: dict[str, asyncio.Queue] = {}
    last_pong = asyncio.get_event_loop().time()
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=20)
                data = json.loads(msg)
            except asyncio.TimeoutError:
                now = asyncio.get_event_loop().time()
                if now - last_pong > 20:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            except Exception:
                continue

            t = data.get("type")
            if t == "subscribe":
                conv_id = data.get("conversation_id")
                if not conv_id:
                    continue
                chan = f"im:conv:{conv_id}"
                # 成员校验（最小实现，非持久连接上下文中创建 session）
                try:
                    from app.core.database import SessionLocal
                    db = SessionLocal()
                    member = (
                        db.query(im_model.ConversationMember)
                        .filter(
                            im_model.ConversationMember.conversation_id == conv_id,
                            im_model.ConversationMember.user_id == user_id,
                        )
                        .first()
                    )
                    if not member:
                        await websocket.send_text(json.dumps({"type": "error", "message": "forbidden"}))
                        continue
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass
                if chan in subscriptions:
                    continue
                q = await pubsub.subscribe(chan)

                async def forwarder(channel: str, queue: asyncio.Queue):
                    while True:
                        payload = await queue.get()
                        if payload is None:
                            break
                        await websocket.send_text(json.dumps({"type": "event", "channel": channel, "data": payload}))

                subscriptions[chan] = q
                asyncio.create_task(forwarder(chan, q))
                await websocket.send_text(json.dumps({"type": "subscribed", "conversation_id": conv_id}))

            elif t == "unsubscribe":
                conv_id = data.get("conversation_id")
                if not conv_id:
                    continue
                chan = f"im:conv:{conv_id}"
                q = subscriptions.pop(chan, None)
                if q:
                    await pubsub.unsubscribe(chan, q)
                await websocket.send_text(json.dumps({"type": "unsubscribed", "conversation_id": conv_id}))

            elif t == "pong":
                last_pong = asyncio.get_event_loop().time()
                # 续期路由信息
                try:
                    info = {"instance_id": settings.INSTANCE_ID, "platform": "ws", "last_ping_ts": int(last_pong)}
                    if hasattr(pubsub, "set_connection"):
                        await pubsub.set_connection(user_id, json.dumps(info), ttl_sec=60)  # type: ignore
                except Exception:
                    pass

            else:
                # 支持 send_msg（直接通过 WS 发送并入库）
                if t == "send_msg":
                    conv_id = data.get("conversation_id")
                    content = data.get("content")
                    msg_type = data.get("msg_type", "text")
                    if not conv_id or not content:
                        await websocket.send_text(json.dumps({"type": "error", "message": "invalid payload"}))
                        continue
                    try:
                        from app.core.database import SessionLocal
                        from app.core.seq import next_seq
                        db = SessionLocal()
                        # 先生成 seq（在事件循环中）
                        seq_value = await next_seq(conv_id)
                        # 幂等：如带 client_msg_id 则先查
                        existing = None
                        if data.get("client_msg_id"):
                            existing = (
                                db.query(im_model.IMMessage)
                                .filter(
                                    im_model.IMMessage.conversation_id == conv_id,
                                    im_model.IMMessage.sender_id == user_id,
                                    im_model.IMMessage.client_msg_id == data.get("client_msg_id"),
                                )
                                .first()
                            )
                        if existing:
                            await websocket.send_text(
                                json.dumps({"type": "ack", "event": "message.sent", "message_id": existing.message_id, "seq": existing.seq})
                            )
                            continue
                        req = im_model.MessageCreateRequest(
                            conversation_id=conv_id,
                            type=msg_type,
                            content=content,
                            reply_to=data.get("reply_to"),
                            client_msg_id=data.get("client_msg_id"),
                            tenant_id=data.get("tenant_id"),
                        )
                        msg = im_service.create_message(db, req, sender_id=user_id, seq_value=seq_value)
                        await websocket.send_text(
                            json.dumps({"type": "ack", "event": "message.sent", "message_id": msg.message_id, "seq": msg.seq})
                        )
                    except Exception as e:
                        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
                    finally:
                        try:
                            db.close()
                        except Exception:
                            pass
                elif t == "stream_chunk":
                    conv_id = data.get("conversation_id")
                    chunk = data.get("chunk")
                    stream_end = bool(data.get("stream_end", False))
                    if not conv_id or chunk is None:
                        await websocket.send_text(json.dumps({"type": "error", "message": "invalid payload"}))
                        continue
                    try:
                        from app.core.database import SessionLocal
                        from app.core.seq import next_seq
                        db = SessionLocal()
                        seq_value = await next_seq(conv_id)
                        msg = im_service.create_stream_chunk(
                            db,
                            conversation_id=conv_id,
                            sender_id=user_id,
                            content=str(chunk),
                            client_msg_id=data.get("client_msg_id"),
                            stream_end=stream_end,
                            tenant_id=data.get("tenant_id"),
                            seq_value=seq_value,
                        )
                        await websocket.send_text(
                            json.dumps({"type": "ack", "event": "stream.sent", "message_id": msg.message_id, "seq": msg.seq, "stream_end": stream_end})
                        )
                    except Exception as e:
                        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
                    finally:
                        try:
                            db.close()
                        except Exception:
                            pass
                elif t == "delivered":
                    conv_id = data.get("conversation_id")
                    message_id = data.get("message_id")
                    if conv_id and message_id:
                        from app.core.database import SessionLocal
                        from app.services.receipts_service import mark_delivered
                        db = SessionLocal()
                        try:
                            # per-user delivered（校验成员在 service 内/或下层 API 负责）
                            mark_delivered(db, conv_id, message_id, user_id)
                        finally:
                            try:
                                db.close()
                            except Exception:
                                pass
                else:
                    conv_id = data.get("conversation_id")
                    if conv_id:
                        await pubsub.publish(f"im:conv:{conv_id}", data)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            for chan, q in list(subscriptions.items()):
                await pubsub.unsubscribe(chan, q)
        except Exception:
            pass


