"""
通话管理服务
处理通话生命周期管理、状态跟踪和事件广播
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session

from ..models import im as im_model
from ..core.events import publish_event_async
from ..core.turn_service import webrtc_config


class CallManagementService:
    """通话管理服务"""

    @staticmethod
    def create_call(
        db: Session, conversation_id: str, initiator_id: str, call_type: str = "audio"
    ) -> im_model.CallLog:
        """创建新通话"""

        # 检查是否已有活跃通话
        active_call = (
            db.query(im_model.CallLog)
            .filter(
                im_model.CallLog.conversation_id == conversation_id,
                im_model.CallLog.status.in_(["initiated", "ringing", "answered"]),
            )
            .first()
        )

        if active_call:
            raise ValueError("A call is already active in this conversation")

        # 创建通话记录
        call = im_model.CallLog(
            conversation_id=conversation_id,
            initiator_id=initiator_id,
            status="initiated",
        )
        db.add(call)
        db.flush()

        # 添加发起者为参与者
        initiator_participant = im_model.CallParticipant(
            call_id=call.call_id, user_id=initiator_id, join_time=datetime.utcnow()
        )
        db.add(initiator_participant)

        db.commit()
        db.refresh(call)

        return call

    @staticmethod
    def get_call_participants(db: Session, call_id: str) -> List[str]:
        """获取通话参与者列表"""
        participants = (
            db.query(im_model.CallParticipant.user_id)
            .filter(
                im_model.CallParticipant.call_id == call_id,
                im_model.CallParticipant.leave_time.is_(None),
            )
            .all()
        )
        return [p.user_id for p in participants]

    @staticmethod
    def update_call_status(
        db: Session, call_id: str, new_status: str, user_id: Optional[str] = None
    ) -> Optional[im_model.CallLog]:
        """更新通话状态"""
        call = (
            db.query(im_model.CallLog)
            .filter(im_model.CallLog.call_id == call_id)
            .first()
        )

        if not call:
            return None

        old_status = call.status
        call.status = new_status

        # 根据状态变化更新相关时间戳
        now = datetime.utcnow()
        if new_status == "answered" and old_status in ["initiated", "ringing"]:
            call.answer_time = now
        elif new_status in ["completed", "missed", "rejected"]:
            call.end_time = now
            if call.answer_time:
                call.duration_sec = int((now - call.answer_time).total_seconds())

        db.commit()
        db.refresh(call)

        # 广播状态变化事件
        try:
            CallManagementService._broadcast_call_event(
                call, "call.status_changed", user_id
            )
        except Exception:
            pass

        return call

    @staticmethod
    def join_call(db: Session, call_id: str, user_id: str) -> bool:
        """用户加入通话"""
        call = (
            db.query(im_model.CallLog)
            .filter(im_model.CallLog.call_id == call_id)
            .first()
        )

        if not call or call.status not in ["initiated", "ringing", "answered"]:
            return False

        # 检查是否已在通话中
        existing = (
            db.query(im_model.CallParticipant)
            .filter(
                im_model.CallParticipant.call_id == call_id,
                im_model.CallParticipant.user_id == user_id,
                im_model.CallParticipant.leave_time.is_(None),
            )
            .first()
        )

        if existing:
            return True  # 已在通话中

        # 添加参与者
        participant = im_model.CallParticipant(
            call_id=call_id, user_id=user_id, join_time=datetime.utcnow()
        )
        db.add(participant)

        # 如果是第一次有人接听，更新状态为answered
        if call.status in ["initiated", "ringing"]:
            call.status = "answered"
            call.answer_time = datetime.utcnow()

        db.commit()

        # 广播加入事件
        try:
            CallManagementService._broadcast_call_event(
                call, "call.participant_joined", user_id
            )
        except Exception:
            pass

        return True

    @staticmethod
    def leave_call(db: Session, call_id: str, user_id: str) -> bool:
        """用户离开通话"""
        participant = (
            db.query(im_model.CallParticipant)
            .filter(
                im_model.CallParticipant.call_id == call_id,
                im_model.CallParticipant.user_id == user_id,
                im_model.CallParticipant.leave_time.is_(None),
            )
            .first()
        )

        if not participant:
            return False

        # 标记离开时间
        participant.leave_time = datetime.utcnow()

        # 检查是否还有其他活跃参与者
        remaining_participants = (
            db.query(im_model.CallParticipant)
            .filter(
                im_model.CallParticipant.call_id == call_id,
                im_model.CallParticipant.leave_time.is_(None),
                im_model.CallParticipant.user_id != user_id,
            )
            .count()
        )

        # 如果没有其他参与者，结束通话
        if remaining_participants == 0:
            call = (
                db.query(im_model.CallLog)
                .filter(im_model.CallLog.call_id == call_id)
                .first()
            )
            if call and call.status not in ["completed", "missed", "rejected"]:
                call.status = "completed"
                call.end_time = datetime.utcnow()
                if call.answer_time:
                    call.duration_sec = int(
                        (call.end_time - call.answer_time).total_seconds()
                    )

        db.commit()

        # 广播离开事件
        try:
            call = (
                db.query(im_model.CallLog)
                .filter(im_model.CallLog.call_id == call_id)
                .first()
            )
            if call:
                CallManagementService._broadcast_call_event(
                    call, "call.participant_left", user_id
                )
        except Exception:
            pass

        return True

    @staticmethod
    def get_ice_configuration(user_id: str) -> Dict[str, Any]:
        """获取ICE服务器配置"""
        return webrtc_config.get_rtc_configuration(user_id)

    @staticmethod
    def _broadcast_call_event(
        call: im_model.CallLog, event_type: str, user_id: Optional[str] = None
    ):
        """广播通话事件"""
        payload = {
            "event": event_type,
            "call_id": call.call_id,
            "conversation_id": call.conversation_id,
            "status": call.status,
            "initiator_id": call.initiator_id,
            "start_time": call.start_time.isoformat() if call.start_time else None,
            "answer_time": call.answer_time.isoformat() if call.answer_time else None,
            "end_time": call.end_time.isoformat() if call.end_time else None,
            "duration_sec": call.duration_sec,
            "user_id": user_id,
        }

        # 向会话频道广播
        publish_event_async(f"im:conv:{call.conversation_id}", payload)

    @staticmethod
    def get_call_history(
        db: Session, conversation_id: str, limit: int = 20, offset: int = 0
    ) -> List[im_model.CallLog]:
        """获取通话历史"""
        calls = (
            db.query(im_model.CallLog)
            .filter(im_model.CallLog.conversation_id == conversation_id)
            .order_by(im_model.CallLog.start_time.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return calls

    @staticmethod
    def get_active_call(
        db: Session, conversation_id: str
    ) -> Optional[im_model.CallLog]:
        """获取会话中的活跃通话"""
        return (
            db.query(im_model.CallLog)
            .filter(
                im_model.CallLog.conversation_id == conversation_id,
                im_model.CallLog.status.in_(["initiated", "ringing", "answered"]),
            )
            .first()
        )


class WebRTCSignalingService:
    """WebRTC信令服务"""

    @staticmethod
    def validate_sdp_offer(sdp: str) -> bool:
        """验证SDP offer格式"""
        if not sdp or not isinstance(sdp, str):
            return False

        # 基本SDP格式检查
        lines = sdp.strip().split("\n")
        has_version = any(line.startswith("v=") for line in lines)
        has_origin = any(line.startswith("o=") for line in lines)
        has_session = any(line.startswith("s=") for line in lines)

        return has_version and has_origin and has_session

    @staticmethod
    def validate_sdp_answer(sdp: str) -> bool:
        """验证SDP answer格式"""
        return WebRTCSignalingService.validate_sdp_offer(sdp)

    @staticmethod
    def validate_ice_candidate(candidate: Dict[str, Any]) -> bool:
        """验证ICE候选"""
        required_fields = ["candidate", "sdpMLineIndex"]
        if not all(field in candidate for field in required_fields):
            return False

        # 验证candidate字符串格式
        candidate_str = candidate.get("candidate", "")
        if not candidate_str or not isinstance(candidate_str, str):
            return False

        # 基本的candidate格式检查
        return candidate_str.startswith("candidate:")

    @staticmethod
    def sanitize_webrtc_signal(signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """清理WebRTC信令数据"""
        sanitized = {}

        signal_type = signal_data.get("type")
        if signal_type in ["offer", "answer"]:
            sdp = signal_data.get("sdp")
            if sdp:
                sanitized["type"] = signal_type
                sanitized["sdp"] = webrtc_config.sanitize_sdp(sdp)
        elif signal_type == "candidate":
            candidate = signal_data.get("candidate")
            if candidate and WebRTCSignalingService.validate_ice_candidate(candidate):
                sanitized["type"] = "candidate"
                sanitized["candidate"] = candidate

        return sanitized
