"""
媒体文件存储服务
支持MinIO/S3对象存储，提供安全的文件上传下载功能
"""
from __future__ import annotations

import hashlib
import mimetypes
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin

from minio import Minio
from minio.error import S3Error
from minio.commonconfig import ENABLED
from minio.versioningconfig import VersioningConfig

from .config import settings

import magic


class MediaStorageError(Exception):
    """媒体存储相关异常"""
    pass


class MediaStorageService:
    """媒体文件存储服务"""
    
    def __init__(self):
        self.client = None
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self.enabled = False
        try:
            self.client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )
            self._ensure_bucket_exists()
            self.enabled = True
        except Exception as e:
            print(f"Warning: MinIO connection failed: {e}")
            print("Media storage will be disabled.")
    
    def _ensure_bucket_exists(self):
        """确保存储桶存在"""
        if not self.client:
            return
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                # 启用版本控制
                self.client.set_bucket_versioning(
                    self.bucket_name, 
                    VersioningConfig(ENABLED)
                )
        except S3Error as e:
            raise MediaStorageError(f"Failed to ensure bucket exists: {e}")
    
    def validate_file_type(self, content_type: str, filename: str) -> bool:
        """验证文件类型"""
        allowed_types = [t.strip() for t in settings.MEDIA_ALLOWED_TYPES.split(",")]
        
        # 检查MIME类型
        if content_type not in allowed_types:
            return False
            
        # 基于文件扩展名的额外验证
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type and mime_type not in allowed_types:
            return False
            
        return True
    
    def validate_file_content(self, file_data: bytes, expected_content_type: str) -> Tuple[bool, str]:
        """验证文件内容实际类型"""
        try:
            # 使用python-magic检测真实文件类型
            actual_mime = magic.from_buffer(file_data, mime=True)
            
            # 检查是否匹配声明的类型
            if not actual_mime.startswith("audio/"):
                return False, f"File content is not audio, detected: {actual_mime}"
                
            # 允许的音频格式映射
            audio_formats = {
                "audio/mpeg": ["audio/mpeg"],
                "audio/wav": ["audio/wav", "audio/x-wav"],
                "audio/ogg": ["audio/ogg"],
                "audio/mp4": ["audio/mp4", "audio/x-m4a"],
                "audio/webm": ["audio/webm"],
                "audio/aac": ["audio/aac", "audio/x-aac"]
            }
            
            # 检查实际类型是否在允许范围内
            for declared_type, allowed_actuals in audio_formats.items():
                if expected_content_type == declared_type and actual_mime in allowed_actuals:
                    return True, actual_mime
                    
            return False, f"File type mismatch. Expected: {expected_content_type}, Actual: {actual_mime}"
            
        except Exception as e:
            return False, f"Failed to validate file content: {e}"
    
    def generate_media_id(self) -> str:
        """生成媒体文件ID"""
        return f"media_{uuid.uuid4().hex}"
    
    def generate_upload_token(
        self, 
        conversation_id: str, 
        filename: str, 
        content_type: str,
        file_size: int,
        user_id: str
    ) -> Dict[str, Any]:
        """生成文件上传令牌和预签名URL"""
        
        if not self.enabled or not self.client:
            raise MediaStorageError("Media storage is not available")
        
        # 验证文件类型
        if not self.validate_file_type(content_type, filename):
            raise MediaStorageError(f"File type {content_type} not allowed")
        
        # 验证文件大小
        if file_size > settings.MEDIA_MAX_FILE_SIZE:
            raise MediaStorageError(f"File size {file_size} exceeds limit {settings.MEDIA_MAX_FILE_SIZE}")
        
        # 生成媒体ID和对象键
        media_id = self.generate_media_id()
        object_key = f"conversations/{conversation_id}/media/{media_id}"
        
        # 生成预签名上传URL
        try:
            upload_url = self.client.presigned_put_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
                expires=timedelta(seconds=settings.MEDIA_URL_EXPIRE_SECONDS)
            )
        except S3Error as e:
            raise MediaStorageError(f"Failed to generate upload URL: {e}")
        
        # 生成文件元数据
        metadata = {
            "media_id": media_id,
            "conversation_id": conversation_id,
            "original_filename": filename,
            "content_type": content_type,
            "file_size": file_size,
            "user_id": user_id,
            "upload_time": datetime.utcnow().isoformat(),
            "object_key": object_key
        }
        
        return {
            "media_id": media_id,
            "upload_url": upload_url,
            "object_key": object_key,
            "metadata": metadata,
            "expires_at": (datetime.utcnow() + timedelta(seconds=settings.MEDIA_URL_EXPIRE_SECONDS)).isoformat()
        }
    
    def generate_download_url(self, media_id: str, conversation_id: str) -> str:
        """生成文件下载URL"""
        object_key = f"conversations/{conversation_id}/media/{media_id}"
        
        try:
            download_url = self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
                expires=timedelta(seconds=settings.MEDIA_URL_EXPIRE_SECONDS)
            )
            return download_url
        except S3Error as e:
            raise MediaStorageError(f"Failed to generate download URL: {e}")
    
    def get_file_metadata(self, media_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        """获取文件元数据"""
        object_key = f"conversations/{conversation_id}/media/{media_id}"
        
        try:
            stat = self.client.stat_object(self.bucket_name, object_key)
            return {
                "media_id": media_id,
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified.isoformat() if stat.last_modified else None,
                "etag": stat.etag,
                "metadata": stat.metadata
            }
        except S3Error:
            return None
    
    def delete_file(self, media_id: str, conversation_id: str) -> bool:
        """删除文件"""
        object_key = f"conversations/{conversation_id}/media/{media_id}"
        
        try:
            self.client.remove_object(self.bucket_name, object_key)
            return True
        except S3Error:
            return False
    
    def verify_upload_integrity(
        self, 
        media_id: str, 
        conversation_id: str, 
        expected_hash: str,
        expected_size: int
    ) -> Tuple[bool, Optional[str]]:
        """验证上传文件的完整性"""
        object_key = f"conversations/{conversation_id}/media/{media_id}"
        
        try:
            # 获取文件信息
            stat = self.client.stat_object(self.bucket_name, object_key)
            
            # 验证文件大小
            if stat.size != expected_size:
                return False, f"Size mismatch: expected {expected_size}, got {stat.size}"
            
            # 获取文件内容计算哈希
            response = self.client.get_object(self.bucket_name, object_key)
            file_data = response.read()
            response.close()
            
            # 计算SHA256哈希
            actual_hash = hashlib.sha256(file_data).hexdigest()
            if actual_hash != expected_hash:
                return False, f"Hash mismatch: expected {expected_hash}, got {actual_hash}"
            
            return True, None
            
        except S3Error as e:
            return False, f"Failed to verify upload: {e}"


# 全局媒体存储服务实例
media_storage = MediaStorageService()
