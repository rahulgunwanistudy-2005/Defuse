"""A credential broker owns replacement values; Defuse sees metadata receipts only.

The broker MUST install credentials into all consumers before acknowledging an idempotency key.
It is an integration boundary, not a credential store or a secret-returning GitLab endpoint.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr, ValidationError

from defuse.automate.models import CredentialReceipt, CredentialRequest


class CredentialBroker:
    def __init__(
        self,
        url: str,
        token: SecretStr | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        ):
            raise ValueError("credential broker requires HTTPS (HTTP allowed only on loopback)")
        self.url, self.token, self.transport = url.rstrip("/"), token, transport

    async def replace(self, request: CredentialRequest) -> CredentialReceipt:
        headers = {"Idempotency-Key": f"{request.incident_id}:{request.action_id}"}
        if self.token is not None:
            headers["Authorization"] = f"Bearer {self.token.get_secret_value()}"
        async with httpx.AsyncClient(
            transport=self.transport, timeout=60, follow_redirects=False
        ) as client:
            response = await client.post(
                self.url + "/replace", headers=headers, json=request.model_dump(mode="json")
            )
        if response.status_code != 200:
            raise RuntimeError(f"credential broker returned HTTP {response.status_code}")
        try:
            receipt = CredentialReceipt.model_validate_json(response.content)
        except ValidationError as exc:
            raise ValueError("credential broker returned an invalid metadata receipt") from exc
        for field in ("incident_id", "action_id", "target", "namespace"):
            if getattr(receipt, field) != getattr(request, field):
                raise ValueError("credential receipt does not match the requested action")
        if request.retire_old and not receipt.old_revoked:
            raise ValueError("credential authority did not retire the exposed credential")
        if {c.ref for c in request.consumers} != set(receipt.consumer_refs):
            raise ValueError("credential receipt does not cover all consumer environment scopes")
        return receipt
