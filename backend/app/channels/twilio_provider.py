"""Twilio WhatsApp (sandbox or production sender) over plain HTTPS; no SDK. Credentials come from the environment only:
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM (e.g. whatsapp:+14155238886 for the sandbox)."""
import base64
import hashlib
import hmac

import httpx

from .base import InboundMessage, MediaDownloadError, MediaRef, ProviderError, parse_inbound_params

API = "https://api.twilio.com/2010-04-01"
MAX_MEDIA_BYTES = 15 * 1024 * 1024
MAX_BODY = 1500  # WhatsApp bodies are limited to 1600 characters


def compute_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Twilio's request signature: base64(HMAC-SHA1(auth_token, url + each POST field name and value, sorted by name))."""
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()).decode()


class TwilioProvider:
    name = "twilio"

    def __init__(self, account_sid: str, auth_token: str, from_number: str, transport: httpx.BaseTransport | None = None,
                 timeout: float = 10):
        self.sid, self.token = account_sid, auth_token
        self.from_number = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
        self.http = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True)

    def verify_signature(self, url: str, params: dict[str, str], signature: str | None) -> bool:
        if not signature:
            return False
        return hmac.compare_digest(compute_signature(self.token, url, params), signature)

    def parse_inbound(self, params: dict[str, str]) -> InboundMessage:
        return parse_inbound_params(params)

    def download_media(self, media: MediaRef) -> tuple[bytes, str]:
        try:
            r = self.http.get(media.url, auth=(self.sid, self.token))
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise MediaDownloadError(f"could not download media: {type(e).__name__}") from e
        if len(r.content) > MAX_MEDIA_BYTES:
            raise MediaDownloadError("media too large")
        return r.content, (r.headers.get("content-type", "").split(";")[0] or media.content_type)

    def send(self, phone: str, text: str, media_urls: list[str] | None = None) -> str:
        data: dict = {"From": self.from_number, "To": f"whatsapp:{phone}", "Body": text[:MAX_BODY]}
        if media_urls:
            data["MediaUrl"] = media_urls
        try:
            r = self.http.post(f"{API}/Accounts/{self.sid}/Messages.json", data=data, auth=(self.sid, self.token))
        except httpx.HTTPError as e:
            raise ProviderError(f"Twilio request failed: {type(e).__name__}") from e
        if r.status_code in (200, 201):
            return r.json().get("sid", "")
        detail = r.text[:160].replace("\n", " ")
        raise ProviderError(f"Twilio HTTP {r.status_code}: {detail}", retryable=r.status_code == 429 or r.status_code >= 500)
