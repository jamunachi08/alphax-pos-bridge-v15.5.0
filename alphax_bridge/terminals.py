"""
Card terminal adapters.

Card terminals are different from the byte-pushable hardware the bridge
already drives. They're cloud-mediated: the cashier SPA says "charge $46
for invoice SINV-2026-0001," and the provider's SDK orchestrates with the
bank network and the physical PIN-pad terminal, then returns
approve/decline/timeout.

Each provider gets one adapter class implementing this interface. The SPA
sees one uniform `/charge`, `/refund`, `/cancel` HTTP endpoint regardless
of which provider is configured — the only difference is `provider` in
the device profile.

Built-in adapters (skeletons):

  generic-rest      Generic REST adapter — for any provider that exposes a
                    JSON HTTP API. Configurable endpoint URLs and field
                    mappings, no SDK required.
  geidea            Geidea (KSA / GCC). Provider SDK / cloud API.
  hyperpay          HyperPay (KSA / GCC).
  network-intl      Network International (UAE).
  payfort           Amazon Payment Services (formerly Payfort).
  mock              Returns approval after 1.5s. For dev / demo / training.

Adding a new provider = one new class subclassing `TerminalAdapter`. The
SPA doesn't need to change.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional

log = logging.getLogger("alphax-bridge.terminal")


class ChargeResult:
    """Standardized result returned to the SPA. Whatever the provider
    actually returns gets normalized into this shape."""

    APPROVED = "approved"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    TIMEOUT  = "timeout"
    ERROR    = "error"

    def __init__(
        self, status: str, *,
        amount: float = 0.0,
        currency: str = "",
        provider_txn_id: str = "",
        auth_code: str = "",
        masked_pan: str = "",
        card_brand: str = "",
        card_type: str = "",          # credit / debit / mada
        retrieval_ref: str = "",
        terminal_id: str = "",
        merchant_id: str = "",
        receipt_text: str = "",       # provider-supplied receipt body
        decline_reason: str = "",
        raw: Optional[dict] = None,
    ):
        self.status = status
        self.amount = amount
        self.currency = currency
        self.provider_txn_id = provider_txn_id
        self.auth_code = auth_code
        self.masked_pan = masked_pan
        self.card_brand = card_brand
        self.card_type = card_type
        self.retrieval_ref = retrieval_ref
        self.terminal_id = terminal_id
        self.merchant_id = merchant_id
        self.receipt_text = receipt_text
        self.decline_reason = decline_reason
        self.raw = raw or {}

    @property
    def ok(self) -> bool:
        return self.status == self.APPROVED

    def to_dict(self) -> dict:
        return {
            "status":          self.status,
            "ok":              self.ok,
            "amount":          self.amount,
            "currency":        self.currency,
            "provider_txn_id": self.provider_txn_id,
            "auth_code":       self.auth_code,
            "masked_pan":      self.masked_pan,
            "card_brand":      self.card_brand,
            "card_type":       self.card_type,
            "retrieval_ref":   self.retrieval_ref,
            "terminal_id":     self.terminal_id,
            "merchant_id":     self.merchant_id,
            "receipt_text":    self.receipt_text,
            "decline_reason":  self.decline_reason,
        }


class TerminalAdapter(ABC):
    """Base class for every card-terminal provider adapter.

    Adapters are instantiated by the registry from a profile. They keep
    their own connection state (e.g. session tokens, terminal handles) and
    are reused across multiple charges.
    """

    name = "base"

    def __init__(self, **opts):
        self.opts = opts
        self.terminal_id = opts.get("terminal_id", "")
        self.merchant_id = opts.get("merchant_id", "")

    # ---- lifecycle -------------------------------------------------------

    def open(self) -> None:
        """Establish whatever the provider needs (session, login)."""
        pass

    def close(self) -> None:
        pass

    # ---- core operations -------------------------------------------------

    @abstractmethod
    def charge(self, amount: float, currency: str, *,
               invoice_ref: str = "",
               idempotency_key: str = "",
               metadata: Optional[dict] = None,
               timeout: float = 90.0) -> ChargeResult:
        """Charge `amount` in `currency`. Block until the customer taps /
        inserts / swipes (or the provider returns)."""

    def refund(self, amount: float, original_txn_id: str, *,
               idempotency_key: str = "",
               metadata: Optional[dict] = None) -> ChargeResult:
        raise NotImplementedError(f"{self.name} does not support refunds")

    def cancel(self, current_txn_id: str = "") -> ChargeResult:
        """Cancel a charge that's currently waiting for the customer."""
        return ChargeResult(ChargeResult.CANCELLED, provider_txn_id=current_txn_id)

    # ---- diagnostics -----------------------------------------------------

    def status(self) -> dict:
        return {
            "name": self.name,
            "terminal_id": self.terminal_id,
            "merchant_id": self.merchant_id,
            "ok": True,
        }


# ===========================================================================
# Mock adapter (for dev + training)
# ===========================================================================


class MockTerminalAdapter(TerminalAdapter):
    """Always approves after a configurable delay. Use this for training
    cashiers or running demos without real terminal hardware.

    Profile options:
      delay_seconds    1.5 default — how long to "wait for the customer"
      decline_amount   if set, any charge equal to this exact amount declines
                       (handy for showing the decline path in training)
    """
    name = "mock"

    def charge(self, amount, currency, *,
               invoice_ref="", idempotency_key="", metadata=None, timeout=90.0):
        delay = float(self.opts.get("delay_seconds", 1.5))
        time.sleep(min(delay, timeout))

        decline_amt = self.opts.get("decline_amount")
        if decline_amt is not None and abs(amount - float(decline_amt)) < 0.001:
            return ChargeResult(
                ChargeResult.DECLINED, amount=amount, currency=currency,
                decline_reason="mock decline",
                provider_txn_id=f"MOCK-{uuid.uuid4().hex[:8]}",
                merchant_id=self.merchant_id, terminal_id=self.terminal_id,
            )

        return ChargeResult(
            ChargeResult.APPROVED, amount=amount, currency=currency,
            provider_txn_id=f"MOCK-{uuid.uuid4().hex[:12].upper()}",
            auth_code=str(uuid.uuid4().int)[:6],
            masked_pan="**** **** **** 4242",
            card_brand="VISA", card_type="credit",
            retrieval_ref=str(uuid.uuid4().int)[:12],
            merchant_id=self.merchant_id, terminal_id=self.terminal_id,
            receipt_text="MOCK TERMINAL\nAPPROVED\nMode: Test",
        )

    def refund(self, amount, original_txn_id, *, idempotency_key="", metadata=None):
        time.sleep(0.5)
        return ChargeResult(
            ChargeResult.APPROVED, amount=amount,
            provider_txn_id=f"MOCK-RF-{uuid.uuid4().hex[:8]}",
            merchant_id=self.merchant_id, terminal_id=self.terminal_id,
        )


# ===========================================================================
# Generic REST adapter — works for any provider with a JSON HTTP API
# ===========================================================================


class GenericRESTTerminalAdapter(TerminalAdapter):
    """Configurable REST adapter for providers that expose a JSON HTTP API.

    No SDK / library required — works through stdlib urllib. Field
    mappings are configurable in the profile so you don't have to edit
    code for slight payload differences.

    Profile options:
      base_url            "https://api.example.com/pos/v1"
      auth_header         e.g. "Authorization"
      auth_value          e.g. "Bearer YOUR_KEY"   (use a secret, of course)
      charge_path         "/charge"                (POST)
      refund_path         "/refund"                (POST)
      cancel_path         "/cancel"                (POST)
      status_path         "/status"                (GET)

      payload_amount      "amount"        — JSON field for the amount
      payload_currency    "currency"      — JSON field for the currency
      payload_invoice     "reference"     — invoice ref field
      payload_idem        "idempotency_key" — idempotency key field

      response_status     "status"        — JSON path for the status field
      response_approved   "APPROVED"      — value that means success
      response_declined   "DECLINED"
      response_txn_id     "transaction_id"
      response_auth       "auth_code"
      response_pan        "masked_pan"
      response_brand      "card_brand"
      response_decline_reason "decline_reason"
    """
    name = "generic-rest"

    def __init__(self, **opts):
        super().__init__(**opts)
        self.base_url = opts.get("base_url", "").rstrip("/")
        self.auth_header = opts.get("auth_header", "Authorization")
        self.auth_value  = opts.get("auth_value", "")
        self.charge_path = opts.get("charge_path", "/charge")
        self.refund_path = opts.get("refund_path", "/refund")
        self.cancel_path = opts.get("cancel_path", "/cancel")
        self.status_path = opts.get("status_path", "/status")
        # field maps with sensible defaults
        self.f_amount   = opts.get("payload_amount", "amount")
        self.f_currency = opts.get("payload_currency", "currency")
        self.f_invoice  = opts.get("payload_invoice", "reference")
        self.f_idem     = opts.get("payload_idem", "idempotency_key")
        self.r_status   = opts.get("response_status", "status")
        self.r_approved = opts.get("response_approved", "APPROVED")
        self.r_declined = opts.get("response_declined", "DECLINED")
        self.r_txn      = opts.get("response_txn_id", "transaction_id")
        self.r_auth     = opts.get("response_auth", "auth_code")
        self.r_pan      = opts.get("response_pan", "masked_pan")
        self.r_brand    = opts.get("response_brand", "card_brand")
        self.r_reason   = opts.get("response_decline_reason", "decline_reason")

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        from urllib import request, error
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.auth_value:
            headers[self.auth_header] = self.auth_value
        req = request.Request(url, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except error.HTTPError as e:
            try: payload = json.loads(e.read().decode("utf-8"))
            except Exception: payload = {}
            payload["_http_status"] = e.code
            return payload
        except Exception as e:
            return {"_error": str(e)}

    def _interpret(self, resp: dict, amount: float, currency: str) -> ChargeResult:
        if "_error" in resp:
            return ChargeResult(ChargeResult.ERROR, amount=amount, currency=currency,
                                decline_reason=resp["_error"], raw=resp)
        status = str(resp.get(self.r_status, "")).upper()
        if status == str(self.r_approved).upper():
            return ChargeResult(
                ChargeResult.APPROVED, amount=amount, currency=currency,
                provider_txn_id=resp.get(self.r_txn, ""),
                auth_code=resp.get(self.r_auth, ""),
                masked_pan=resp.get(self.r_pan, ""),
                card_brand=resp.get(self.r_brand, ""),
                merchant_id=self.merchant_id, terminal_id=self.terminal_id,
                raw=resp,
            )
        if status == str(self.r_declined).upper():
            return ChargeResult(
                ChargeResult.DECLINED, amount=amount, currency=currency,
                decline_reason=resp.get(self.r_reason, ""),
                provider_txn_id=resp.get(self.r_txn, ""),
                raw=resp,
            )
        return ChargeResult(ChargeResult.ERROR, amount=amount, currency=currency,
                            decline_reason=f"unexpected status: {status}", raw=resp)

    def charge(self, amount, currency, *,
               invoice_ref="", idempotency_key="", metadata=None, timeout=90.0):
        body = {
            self.f_amount: amount,
            self.f_currency: currency,
            self.f_invoice: invoice_ref,
            self.f_idem: idempotency_key or str(uuid.uuid4()),
            "terminal_id": self.terminal_id,
            "merchant_id": self.merchant_id,
        }
        if metadata: body["metadata"] = metadata
        resp = self._post(self.charge_path, body, timeout)
        return self._interpret(resp, amount, currency)

    def refund(self, amount, original_txn_id, *, idempotency_key="", metadata=None):
        body = {
            self.f_amount: amount,
            "original_txn_id": original_txn_id,
            self.f_idem: idempotency_key or str(uuid.uuid4()),
        }
        resp = self._post(self.refund_path, body, 30.0)
        return self._interpret(resp, amount, "")

    def cancel(self, current_txn_id=""):
        resp = self._post(self.cancel_path, {"transaction_id": current_txn_id}, 10.0)
        return self._interpret(resp, 0, "") if resp else ChargeResult(ChargeResult.CANCELLED)


# ===========================================================================
# Provider stubs — Geidea, HyperPay, Network International, Payfort
# ===========================================================================
#
# These extend GenericRESTTerminalAdapter with provider-specific defaults
# (URLs, field-name mappings) so a typical config only needs to set
# `merchant_id`, `terminal_id`, and the `auth_value` (API key / secret).
#
# NOTE: these are skeletons. Each provider has its own production URL,
# sandbox URL, signing scheme (HMAC over the request body, mTLS, etc.) and
# webhook callback model. Connecting to the live network requires a
# merchant account, sandbox credentials, and certification testing — none
# of which the bridge can do for you. The adapters are wired so that once
# you have credentials, you set them in the profile and trade requests.
# In the meantime they hit a configurable endpoint or fall back to mock.


class GeideaAdapter(GenericRESTTerminalAdapter):
    name = "geidea"

    def __init__(self, **opts):
        defaults = dict(
            base_url="https://api.merchant.geidea.net/pgw/api/v6/direct",
            charge_path="/pay",
            refund_path="/refund",
            cancel_path="/void",
            status_path="/status",
            payload_amount="amount",
            payload_currency="currency",
            payload_invoice="merchantReferenceId",
            payload_idem="callbackUrl",
            response_status="responseCode",
            response_approved="000",
            response_declined="105",
            response_txn_id="orderId",
            response_auth="authorizationCode",
            response_pan="cardNumber",
            response_brand="cardBrand",
            response_decline_reason="responseMessage",
        )
        defaults.update(opts)
        super().__init__(**defaults)


class HyperPayAdapter(GenericRESTTerminalAdapter):
    name = "hyperpay"

    def __init__(self, **opts):
        defaults = dict(
            base_url="https://eu-test.oppwa.com/v1",
            charge_path="/payments",
            payload_amount="amount",
            payload_currency="currency",
            payload_invoice="merchantTransactionId",
            response_status="result.code",
            response_approved="000.000.000",
            response_txn_id="id",
            response_decline_reason="result.description",
        )
        defaults.update(opts)
        super().__init__(**defaults)


class NetworkIntlAdapter(GenericRESTTerminalAdapter):
    name = "network-intl"

    def __init__(self, **opts):
        defaults = dict(
            base_url="https://api-gateway.ngenius-payments.com",
            charge_path="/transactions/outlets/<<OUTLET>>/orders",
            payload_amount="amount.value",
            payload_currency="amount.currencyCode",
            response_status="state",
            response_approved="CAPTURED",
            response_txn_id="orderReference",
        )
        defaults.update(opts)
        super().__init__(**defaults)


class PayfortAdapter(GenericRESTTerminalAdapter):
    """Amazon Payment Services (formerly Payfort).

    Payfort requires every request and response to be signed with
    SHA-256 using a shared secret called the "SHA Request Phrase"
    (or "SHA Response Phrase" for inbound responses).

    Algorithm (per APS docs):
        1. Take all request fields (key/value pairs), excluding the
           `signature` field itself.
        2. Sort the keys lexicographically.
        3. Concatenate: shaRequestPhrase + key1=value1 + key2=value2 + ...
                        + shaRequestPhrase
        4. SHA-256 hex digest of that UTF-8 string is the `signature`.

    Required provider_options:
        merchant_identifier:    your merchant identifier from APS portal
        access_code:            your access code (used as auth_value)
        sha_request_phrase:     shared secret for outbound signing
        sha_response_phrase:    shared secret for verifying inbound responses
                                (optional but recommended)
        language:               'en' or 'ar' (defaults to 'en')

    Sandbox base_url: https://sbpaymentservices.payfort.com/FortAPI
    Production base_url: https://paymentservices.payfort.com/FortAPI

    See docs/card-terminals.md for setup walkthrough.
    """
    name = "payfort"

    def __init__(self, **opts):
        # Pull Payfort-specific options out before calling super()
        self.sha_request_phrase  = opts.pop("sha_request_phrase", "")
        self.sha_response_phrase = opts.pop("sha_response_phrase", "")
        self.merchant_identifier = opts.pop("merchant_identifier",
                                            opts.get("merchant_id", ""))
        self.access_code         = opts.pop("access_code",
                                            opts.get("auth_value", ""))
        self.language            = opts.pop("language", "en")

        defaults = dict(
            base_url="https://paymentservices.payfort.com/FortAPI",
            charge_path="/paymentApi",
            payload_amount="amount",
            payload_currency="currency",
            payload_invoice="merchant_reference",
            response_status="response_code",
            response_approved="14000",       # APS "AUTHORIZATION_SUCCESS"
            response_txn_id="fort_id",
            response_decline_reason="response_message",
            response_pan="card_number",
            response_brand="card_brand",
            # Payfort uses no Authorization header — signing is in-body.
            auth_header="X-Payfort-Auth-Unused",
            auth_value="",
        )
        defaults.update(opts)
        super().__init__(**defaults)

    @staticmethod
    def compute_signature(fields: dict, phrase: str) -> str:
        """Compute the Payfort SHA-256 signature for a set of fields.

        Per APS spec: sort keys ascending, concatenate as `key=value`,
        wrap with the shared secret on both sides, SHA-256 hex digest.

        - Skips the `signature` field if present (you don't sign over
          a signature you're computing).
        - Skips fields with None values; APS treats absence as different
          from empty string.
        - Empty-string values are included (they're meaningful).
        - Coerces values to str via str(), matching APS reference impls.

        Returns the lowercase hex digest (64 chars).
        """
        import hashlib
        # Filter, sort, format
        parts = []
        for key in sorted(fields.keys()):
            if key == "signature":
                continue
            val = fields[key]
            if val is None:
                continue
            parts.append(f"{key}={val}")
        canonical = phrase + "".join(parts) + phrase
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _build_payfort_request(self, command: str, body: dict) -> dict:
        """Add Payfort-required envelope fields and sign."""
        envelope = {
            "command":              command,
            "access_code":          self.access_code,
            "merchant_identifier":  self.merchant_identifier,
            "language":             self.language,
        }
        envelope.update(body)
        # Strip None values so they don't end up in the signed payload.
        envelope = {k: v for k, v in envelope.items() if v is not None}
        envelope["signature"] = self.compute_signature(
            envelope, self.sha_request_phrase
        )
        return envelope

    def verify_response_signature(self, response: dict) -> bool:
        """Verify a Payfort response signature using sha_response_phrase.

        Returns True if no response phrase is configured (i.e., caller
        opted out of verification — the network connection is still TLS
        so this isn't insecure, just less defense-in-depth).

        Returns False if a phrase is configured AND the response
        signature doesn't match. Caller should treat that as a hard
        failure even if response_code says "approved" — it could indicate
        a man-in-the-middle or a misconfiguration.
        """
        if not self.sha_response_phrase:
            return True
        sent_sig = response.get("signature")
        if not sent_sig:
            return False
        expected = self.compute_signature(response, self.sha_response_phrase)
        # Constant-time comparison (defense against timing oracles).
        import hmac
        return hmac.compare_digest(sent_sig.lower(), expected.lower())

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        # Determine the Payfort `command` based on the path or default
        # to PURCHASE for the standard charge endpoint.
        command = body.pop("_command", "PURCHASE")
        signed_body = self._build_payfort_request(command, body)
        # Don't pass auth_value via header — it's already in the signed body.
        from urllib import request, error
        url = self.base_url + path
        data = json.dumps(signed_body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = request.Request(url, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8") or "{}")
        except error.HTTPError as e:
            try: payload = json.loads(e.read().decode("utf-8"))
            except Exception: payload = {}
            payload["_http_status"] = e.code
            return payload
        except Exception as e:
            return {"_error": str(e)}

        # Verify response signature if configured.
        if not self.verify_response_signature(payload):
            payload["_error"] = (
                "Payfort response signature verification failed. "
                "This could indicate a misconfigured sha_response_phrase or "
                "a man-in-the-middle. The response will not be trusted as "
                "approved even if response_code says it was."
            )
        return payload

    def charge(self, amount, currency, *, invoice_ref="",
               idempotency_key="", metadata=None, timeout=90.0):
        # Payfort wants amount in minor units (e.g. cents/halalas).
        # Override the parent build by stuffing the minor-unit amount
        # into a sub-dict and tagging the command.
        from .terminals_helpers import currency_minor_units
        minor_amount = int(round(amount * (10 ** currency_minor_units(currency))))
        body = {
            self.payload_amount:    minor_amount,
            self.payload_currency:  currency,
            self.payload_invoice:   invoice_ref or idempotency_key or "no-ref",
            "_command":             "PURCHASE",
        }
        if metadata:
            body.update({k: v for k, v in metadata.items() if v is not None})
        resp = self._post(self.charge_path, body, timeout)
        return self._interpret(resp, amount, currency)


# ---- factory ---------------------------------------------------------------


TERMINALS = {
    "mock":         MockTerminalAdapter,
    "generic-rest": GenericRESTTerminalAdapter,
    "geidea":       GeideaAdapter,
    "hyperpay":     HyperPayAdapter,
    "network-intl": NetworkIntlAdapter,
    "payfort":      PayfortAdapter,
}


def make_terminal(provider: str, **opts) -> TerminalAdapter:
    cls = TERMINALS.get(provider)
    if not cls:
        raise ValueError(f"Unknown terminal provider: {provider}")
    return cls(**opts)
