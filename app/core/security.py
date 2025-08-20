"""安全相关工具和中间件"""

import hashlib
import hmac
import secrets
import time
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings


class SecurityHeaders(BaseHTTPMiddleware):
    """添加安全头中间件"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # 安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HTTPS相关 (生产环境)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # CORS (如果需要)
        if "origin" in request.headers:
            # 在生产环境中应该配置具体的允许域名
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type"
            )

        return response


class APIKeyAuth:
    """API密钥认证 (用于服务间调用)"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "API_KEY", None)

    def verify_api_key(self, provided_key: str) -> bool:
        """验证API密钥"""
        if not self.api_key:
            return False

        # 使用恒定时间比较防止时序攻击
        return hmac.compare_digest(self.api_key, provided_key)

    def __call__(self, request: Request) -> bool:
        """从请求中验证API密钥"""
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required"
            )

        if not self.verify_api_key(api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
            )

        return True


class RequestSignature:
    """请求签名验证 (用于Webhook等)"""

    def __init__(self, secret: str):
        self.secret = secret.encode()

    def generate_signature(self, payload: bytes, timestamp: str) -> str:
        """生成请求签名"""
        message = f"{timestamp}.{payload.decode()}".encode()
        signature = hmac.new(self.secret, message, hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={signature}"

    def verify_signature(
        self, payload: bytes, signature: str, tolerance: int = 300
    ) -> bool:
        """验证请求签名"""
        try:
            # 解析签名
            pairs = dict(pair.split("=") for pair in signature.split(","))
            timestamp = pairs.get("t")
            expected_sig = pairs.get("v1")

            if not timestamp or not expected_sig:
                return False

            # 检查时间戳是否在容忍范围内
            current_time = int(time.time())
            if abs(current_time - int(timestamp)) > tolerance:
                return False

            # 验证签名
            message = f"{timestamp}.{payload.decode()}".encode()
            computed_sig = hmac.new(self.secret, message, hashlib.sha256).hexdigest()

            return hmac.compare_digest(expected_sig, computed_sig)

        except (ValueError, KeyError):
            return False


class ContentValidation:
    """内容验证工具"""

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理文件名，防止路径遍历攻击"""
        import os
        import re

        # 移除路径分隔符
        filename = os.path.basename(filename)

        # 移除危险字符
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", filename)

        # 限制长度
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[: 255 - len(ext)] + ext

        # 防止保留名称
        reserved_names = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }

        name_without_ext = os.path.splitext(filename)[0].upper()
        if name_without_ext in reserved_names:
            filename = f"file_{filename}"

        return filename or "unnamed_file"

    @staticmethod
    def validate_media_content(content: bytes, content_type: str) -> Dict[str, Any]:
        """验证媒体文件内容"""
        import magic

        # 检测真实文件类型
        detected_type = magic.from_buffer(content, mime=True)

        # 基础验证
        result = {
            "valid": True,
            "detected_type": detected_type,
            "declared_type": content_type,
            "size": len(content),
            "issues": [],
        }

        # 类型一致性检查
        if not detected_type.startswith(content_type.split("/")[0]):
            result["issues"].append(
                f"Type mismatch: declared {content_type}, detected {detected_type}"
            )

        # 大小检查
        max_size = getattr(settings, "MEDIA_MAX_FILE_SIZE", 50 * 1024 * 1024)
        if len(content) > max_size:
            result["valid"] = False
            result["issues"].append(f"File too large: {len(content)} > {max_size}")

        # 音频/视频特定检查
        if detected_type.startswith("audio/"):
            result.update(ContentValidation._validate_audio(content))
        elif detected_type.startswith("video/"):
            result.update(ContentValidation._validate_video(content))

        return result

    @staticmethod
    def _validate_audio(content: bytes) -> Dict[str, Any]:
        """音频文件特定验证"""
        try:
            from mutagen import File as MutagenFile
            from io import BytesIO

            # 使用mutagen解析音频元数据
            audio_file = MutagenFile(BytesIO(content))
            if audio_file is None:
                return {"issues": ["Invalid audio file format"]}

            duration = getattr(audio_file.info, "length", 0)
            bitrate = getattr(audio_file.info, "bitrate", 0)

            return {
                "duration": duration,
                "bitrate": bitrate,
                "channels": getattr(audio_file.info, "channels", None),
            }

        except Exception as e:
            return {"issues": [f"Audio validation error: {str(e)}"]}

    @staticmethod
    def _validate_video(content: bytes) -> Dict[str, Any]:
        """视频文件特定验证"""
        # 简单的视频验证（生产环境可能需要更复杂的验证）
        return {"video_validation": "basic"}


def generate_secure_token(length: int = 32) -> str:
    """生成安全的随机令牌"""
    return secrets.token_urlsafe(length)


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """安全的密码哈希"""
    if salt is None:
        salt = secrets.token_hex(32)

    # 使用PBKDF2
    import hashlib

    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000  # 迭代次数
    )

    return password_hash.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """验证密码"""
    computed_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(password_hash, computed_hash)
