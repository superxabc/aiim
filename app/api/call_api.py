"""
通话API接口
提供通话控制、ICE配置等功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.ws_auth import get_current_user_id_from_request
from app.models import im as im_model
from app.services.call_service import CallManagementService


router = APIRouter()


@router.post("/initiate")
async def initiate_call(
    call_request: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    """发起通话"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        conversation_id = call_request.get("conversation_id")
        if not conversation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="conversation_id is required",
            )

        # 验证用户是会话成员
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
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a conversation member",
            )

        # 创建通话
        try:
            call = CallManagementService.create_call(
                db=db,
                conversation_id=conversation_id,
                initiator_id=user_id,
                call_type=call_request.get("type", "audio"),
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

        # 获取ICE配置
        ice_config = CallManagementService.get_ice_configuration(user_id)

        return {
            "call_id": call.call_id,
            "status": call.status,
            "ice_configuration": ice_config,
            "created_at": call.start_time.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate call: {str(e)}",
        )


@router.post("/{call_id}/accept")
async def accept_call(
    call_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """接受通话"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 验证通话存在
        call = (
            db.query(im_model.CallLog)
            .filter(im_model.CallLog.call_id == call_id)
            .first()
        )
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
            )

        # 验证用户是会话成员
        member = (
            db.query(im_model.ConversationMember)
            .filter(
                im_model.ConversationMember.conversation_id == call.conversation_id,
                im_model.ConversationMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a conversation member",
            )

        # 加入通话
        success = CallManagementService.join_call(db, call_id, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot join call in current state",
            )

        # 获取ICE配置
        ice_config = CallManagementService.get_ice_configuration(user_id)

        # 获取更新后的通话信息
        updated_call = (
            db.query(im_model.CallLog)
            .filter(im_model.CallLog.call_id == call_id)
            .first()
        )

        return {
            "call_id": call_id,
            "status": updated_call.status,
            "ice_configuration": ice_config,
            "participants": CallManagementService.get_call_participants(db, call_id),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to accept call: {str(e)}",
        )


@router.post("/{call_id}/reject")
async def reject_call(
    call_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """拒绝通话"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 更新通话状态
        call = CallManagementService.update_call_status(
            db, call_id, "rejected", user_id
        )
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
            )

        return {
            "call_id": call_id,
            "status": call.status,
            "end_time": call.end_time.isoformat() if call.end_time else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject call: {str(e)}",
        )


@router.post("/{call_id}/hangup")
async def hangup_call(
    call_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """挂断通话"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 用户离开通话
        success = CallManagementService.leave_call(db, call_id, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not in call or call not found",
            )

        # 获取更新后的通话状态
        call = (
            db.query(im_model.CallLog)
            .filter(im_model.CallLog.call_id == call_id)
            .first()
        )

        return {
            "call_id": call_id,
            "status": call.status if call else "completed",
            "end_time": call.end_time.isoformat() if call and call.end_time else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to hangup call: {str(e)}",
        )


@router.get("/{call_id}/status")
async def get_call_status(
    call_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """获取通话状态"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        call = (
            db.query(im_model.CallLog)
            .filter(im_model.CallLog.call_id == call_id)
            .first()
        )
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Call not found"
            )

        # 验证权限
        member = (
            db.query(im_model.ConversationMember)
            .filter(
                im_model.ConversationMember.conversation_id == call.conversation_id,
                im_model.ConversationMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this call",
            )

        participants = CallManagementService.get_call_participants(db, call_id)

        return {
            "call_id": call.call_id,
            "conversation_id": call.conversation_id,
            "status": call.status,
            "initiator_id": call.initiator_id,
            "start_time": call.start_time.isoformat(),
            "answer_time": call.answer_time.isoformat() if call.answer_time else None,
            "end_time": call.end_time.isoformat() if call.end_time else None,
            "duration_sec": call.duration_sec,
            "participants": participants,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get call status: {str(e)}",
        )


@router.get("/conversation/{conversation_id}/history")
async def get_call_history(
    conversation_id: str,
    request: Request,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """获取会话通话历史"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 验证权限
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
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a conversation member",
            )

        calls = CallManagementService.get_call_history(
            db, conversation_id, limit, offset
        )

        call_list = []
        for call in calls:
            call_list.append(
                {
                    "call_id": call.call_id,
                    "status": call.status,
                    "initiator_id": call.initiator_id,
                    "start_time": call.start_time.isoformat(),
                    "answer_time": (
                        call.answer_time.isoformat() if call.answer_time else None
                    ),
                    "end_time": call.end_time.isoformat() if call.end_time else None,
                    "duration_sec": call.duration_sec,
                }
            )

        return {
            "conversation_id": conversation_id,
            "calls": call_list,
            "total": len(call_list),
            "limit": limit,
            "offset": offset,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get call history: {str(e)}",
        )


@router.get("/ice-configuration")
async def get_ice_configuration(
    request: Request,
):
    """获取ICE服务器配置"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        ice_config = CallManagementService.get_ice_configuration(user_id)

        return ice_config

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get ICE configuration: {str(e)}",
        )
