"""
TURN服务集成
提供ICE候选生成和TURN凭证管理
"""

from __future__ import annotations

import hmac
import hashlib
import base64
import time
from typing import Dict, List, Any

from .config import settings


class TURNCredentialService:
    """TURN凭证服务"""

    def __init__(self):
        self.turn_secret = settings.TURN_PASSWORD or "default_turn_secret"
        self.credential_ttl = settings.TURN_CREDENTIAL_TTL

    def generate_turn_credentials(self, username: str) -> Dict[str, str]:
        """生成TURN临时凭证"""
        if not settings.TURN_SERVER:
            return {}

        # 生成时间戳用户名
        timestamp = int(time.time()) + self.credential_ttl
        temp_username = f"{timestamp}:{username}"

        # 使用HMAC-SHA1生成密码
        password = base64.b64encode(
            hmac.new(
                self.turn_secret.encode("utf-8"),
                temp_username.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")

        return {
            "username": temp_username,
            "credential": password,
            "ttl": self.credential_ttl,
        }

    def get_ice_servers(self, user_id: str) -> List[Dict[str, Any]]:
        """获取ICE服务器配置"""
        ice_servers = []

        # STUN服务器
        stun_servers = [
            s.strip() for s in settings.STUN_SERVERS.split(",") if s.strip()
        ]
        for stun_server in stun_servers:
            ice_servers.append({"urls": stun_server})

        # TURN服务器
        if settings.TURN_SERVER:
            turn_creds = self.generate_turn_credentials(user_id)
            if turn_creds:
                ice_servers.append(
                    {
                        "urls": f"turn:{settings.TURN_SERVER}",
                        "username": turn_creds["username"],
                        "credential": turn_creds["credential"],
                        "credentialType": "password",
                    }
                )

                # 同时添加TURNS (TLS)
                ice_servers.append(
                    {
                        "urls": f"turns:{settings.TURN_SERVER}",
                        "username": turn_creds["username"],
                        "credential": turn_creds["credential"],
                        "credentialType": "password",
                    }
                )

        return ice_servers


class WebRTCConfigService:
    """WebRTC配置服务"""

    def __init__(self):
        self.turn_service = TURNCredentialService()

    def get_rtc_configuration(self, user_id: str) -> Dict[str, Any]:
        """获取WebRTC配置"""
        ice_servers = self.turn_service.get_ice_servers(user_id)

        return {
            "iceServers": ice_servers,
            "iceTransportPolicy": "all",  # relay, all
            "bundlePolicy": "balanced",  # balanced, max-compat, max-bundle
            "rtcpMuxPolicy": "require",  # negotiate, require
            "iceCandidatePoolSize": 4,
            # 其他WebRTC配置
            "sdpSemantics": "unified-plan",
        }

    def validate_ice_candidate(self, candidate: Dict[str, Any]) -> bool:
        """验证ICE候选的有效性"""
        required_fields = ["candidate", "sdpMLineIndex"]
        return all(field in candidate for field in required_fields)

    def sanitize_sdp(self, sdp: str) -> str:
        """清理和验证SDP内容"""
        # 基本SDP验证和清理
        lines = sdp.strip().split("\n")
        sanitized_lines = []

        for line in lines:
            line = line.strip()
            if line:
                # 基本格式验证
                if "=" in line:
                    sanitized_lines.append(line)

        return "\n".join(sanitized_lines)


# 全局WebRTC配置服务实例
webrtc_config = WebRTCConfigService()
