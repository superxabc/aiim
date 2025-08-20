"""
媒体文件API接口
提供文件上传、下载、管理等功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.media_storage import media_storage, MediaStorageError
from app.core.ws_auth import get_current_user_id_from_request
from app.models import im as im_model


router = APIRouter()


@router.post("/upload_token", response_model=im_model.UploadTokenResponse)
async def get_upload_token(
    req: im_model.UploadTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """获取文件上传令牌和预签名URL"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 验证用户是否为会话成员
        member = (
            db.query(im_model.ConversationMember)
            .filter(
                im_model.ConversationMember.conversation_id == req.conversation_id,
                im_model.ConversationMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a conversation member",
            )

        # 生成上传令牌
        try:
            token_data = media_storage.generate_upload_token(
                conversation_id=req.conversation_id,
                filename=req.filename,
                content_type=req.content_type,
                file_size=req.file_size,
                user_id=user_id,
            )
        except MediaStorageError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        return im_model.UploadTokenResponse(
            media_id=token_data["media_id"],
            upload_url=token_data["upload_url"],
            expires_at=token_data["expires_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate upload token: {str(e)}",
        )


@router.post("/upload_complete")
async def upload_complete(
    req: im_model.MediaUploadCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """通知文件上传完成，验证文件完整性"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 验证用户权限
        member = (
            db.query(im_model.ConversationMember)
            .filter(
                im_model.ConversationMember.conversation_id == req.conversation_id,
                im_model.ConversationMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a conversation member",
            )

        # 验证文件完整性
        is_valid, error_msg = media_storage.verify_upload_integrity(
            media_id=req.media_id,
            conversation_id=req.conversation_id,
            expected_hash=req.file_hash,
            expected_size=req.file_size,
        )

        if not is_valid:
            # 删除无效文件
            media_storage.delete_file(req.media_id, req.conversation_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File validation failed: {error_msg}",
            )

        return {"status": "success", "media_id": req.media_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload verification failed: {str(e)}",
        )


@router.get("/{media_id}/download", response_model=im_model.MediaDownloadResponse)
async def download_media(
    media_id: str,
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """获取媒体文件下载URL"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 验证用户权限
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

        # 获取文件元数据
        metadata = media_storage.get_file_metadata(media_id, conversation_id)
        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
            )

        # 生成下载URL
        try:
            download_url = media_storage.generate_download_url(
                media_id, conversation_id
            )
        except MediaStorageError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate download URL: {str(e)}",
            )

        from datetime import datetime, timedelta
        from app.core.config import settings

        expires_at = (
            datetime.utcnow() + timedelta(seconds=settings.MEDIA_URL_EXPIRE_SECONDS)
        ).isoformat()

        return im_model.MediaDownloadResponse(
            download_url=download_url,
            content_type=metadata.get("content_type", "application/octet-stream"),
            filename=metadata.get("metadata", {}).get(
                "original_filename", f"{media_id}"
            ),
            file_size=metadata.get("size", 0),
            expires_at=expires_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get download URL: {str(e)}",
        )


@router.get("/{media_id}/metadata")
async def get_media_metadata(
    media_id: str,
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """获取媒体文件元数据"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 验证用户权限
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

        # 获取文件元数据
        metadata = media_storage.get_file_metadata(media_id, conversation_id)
        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found"
            )

        return metadata

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metadata: {str(e)}",
        )


@router.delete("/{media_id}")
async def delete_media(
    media_id: str,
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """删除媒体文件"""
    try:
        user_id = get_current_user_id_from_request(request)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        # 验证用户权限 - 只有文件上传者或会话管理员可以删除
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

        # 检查是否有权限删除（可以扩展为检查文件上传者）
        # TODO: 添加文件所有权验证

        # 删除文件
        success = media_storage.delete_file(media_id, conversation_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media file not found or already deleted",
            )

        return {"status": "deleted", "media_id": media_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete media: {str(e)}",
        )
