import base64
import hashlib
import hmac

import httpx


def valid_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected.encode(), signature.encode())


class LineError(Exception):
    pass


class LineClient:
    def __init__(self, token: str, http: httpx.Client | None = None):
        if not token:
            raise LineError("LINE access token is not configured")
        self.token = token
        self.http = http or httpx.Client(base_url="https://api.line.me", timeout=15)

    def request(self, method, path, **kwargs):
        headers = {"Authorization": "Bearer " + self.token, **kwargs.pop("headers", {})}
        try:
            response = self.http.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise LineError("LINE request timed out or failed") from exc
        if response.status_code == 409 and response.headers.get("x-line-accepted-request-id"):
            return response
        if response.status_code >= 400:
            raise LineError(f"LINE HTTP {response.status_code}")
        return response

    def reply(self, reply_token: str, message: str):
        self.request(
            "POST",
            "/v2/bot/message/reply",
            json={
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": message[:4500]}],
            },
        )

    def push(self, group_id: str, message: str, retry_key: str):
        self.request(
            "POST",
            "/v2/bot/message/push",
            headers={"X-Line-Retry-Key": retry_key},
            json={"to": group_id, "messages": [{"type": "text", "text": message[:4500]}]},
        )

    def quota_available(self, group_id: str) -> bool:
        quota = self.request("GET", "/v2/bot/message/quota").json()
        if quota.get("type") == "none":
            return True
        used = self.request("GET", "/v2/bot/message/quota/consumption").json()["totalUsage"]
        members = self.request("GET", f"/v2/bot/group/{group_id}/members/count").json()["count"]
        return used + members <= quota["value"]

    def close(self):
        self.http.close()
