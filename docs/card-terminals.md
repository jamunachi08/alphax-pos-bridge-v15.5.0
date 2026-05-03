# Card Terminals

The bridge handles card terminals through the same configuration-driven
pattern as printers, drawers, and scales. **One Python adapter per
provider, one HTTP endpoint for the SPA, one uniform result shape.**

The big difference: card terminals are *cloud-mediated.* The bridge
doesn't push bytes over USB or serial. Instead, it calls the provider's
HTTP API (or, in some cases, a thin local SDK), which then orchestrates
with the bank network and the physical PIN-pad terminal.

## What the bridge ships out of the box

Five adapters, one per common provider, plus a generic-REST fallback for
anything else:

| Provider                     | profile_id              | Status         |
|------------------------------|-------------------------|----------------|
| Mock (training / demo)       | `mock-terminal`         | ✅ Production-ready |
| Geidea (KSA / GCC)           | `geidea-terminal`       | 🟡 Skeleton — needs your sandbox creds + certification |
| HyperPay (KSA / GCC)         | `hyperpay-terminal`     | 🟡 Skeleton — needs your sandbox creds + certification |
| Network International (UAE)  | `network-intl-terminal` | 🟡 Skeleton — needs your sandbox creds + certification |
| Amazon Payment Services      | `payfort-terminal`      | 🟢 Signing implemented + tested — needs your sandbox creds + certification |
| Anything with a JSON HTTP API| `generic-rest-terminal` | ✅ Configurable, works today |

"Skeleton" means: the adapter speaks the right URL shape and field names,
but you'll need a merchant account, sandbox credentials, and certification
testing before going live. None of those are things the bridge can do for
you — they require you to sign contracts with the providers.

## How a charge flows

```
┌─────────────────────────────────────────────────┐
│ Cashier SPA: customer hits "Card" button         │
│ store.tender('Card', 46.00) is NOT called yet    │
└──────────────────┬──────────────────────────────┘
                   │  POST /charge
                   │  { device: 'card-1', amount: 46.00, currency: 'SAR' }
                   ▼
┌─────────────────────────────────────────────────┐
│ Bridge: registry.get_terminal('card-1')          │
│  → calls adapter.charge(46.00, 'SAR', ...)       │
└──────────────────┬──────────────────────────────┘
                   │  Provider API call
                   ▼
┌─────────────────────────────────────────────────┐
│ Geidea / HyperPay / NI / Payfort cloud           │
│  → physical PIN-pad asks customer to tap card    │
│  → customer taps                                 │
│  → cloud returns {status:"APPROVED", auth:...}   │
└──────────────────┬──────────────────────────────┘
                   │  ChargeResult dict
                   ▼
┌─────────────────────────────────────────────────┐
│ Bridge → SPA: { ok: true, status: "approved",    │
│   auth_code: "AB123", masked_pan: "**** 4242" }  │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
   SPA: store.tender('Card', 46.00, { auth_code: ... })
        → receipt prints with auth code
        → drawer does NOT kick (card sale)
        → cart clears
```

The SPA-side dialog handles the "waiting on terminal" overlay
automatically: when the cashier picks a card-style payment mode and a
terminal is configured, the dialog routes to the terminal instead of
just adding tender locally.

## Result shape

Every adapter, no matter which provider, returns this exact shape:

```json
{
  "device":          "card-1",
  "status":          "approved",          // approved | declined | cancelled | timeout | error
  "ok":              true,                // == (status == "approved")
  "amount":          46.00,
  "currency":        "SAR",
  "provider_txn_id": "GEI-1234567890",
  "auth_code":       "AB123",
  "masked_pan":      "**** **** **** 4242",
  "card_brand":      "VISA",
  "card_type":       "credit",
  "retrieval_ref":   "0123456789",
  "terminal_id":     "T-HTTP",
  "merchant_id":     "M-HTTP",
  "receipt_text":    "",                   // provider-supplied receipt body
  "decline_reason":  ""
}
```

When status is anything but `approved`, the SPA shows a clear error to the
cashier (declined, cancelled, or a generic terminal error). The cashier can
retry, switch to cash, or split the payment across modes.

## Configuring a real provider

Three things every provider needs:

1. **A merchant account.** Sign a contract with the provider, get a MID
   (merchant ID), TID (terminal ID), and API credentials.
2. **Sandbox credentials.** Every provider has a sandbox environment with
   test cards. Use it to validate every code path: approval, decline,
   timeout, cancellation, refund.
3. **Certification testing.** Before production, the provider runs you
   through a checklist — usually 20-50 specific test cases (declined cards,
   timeouts, partial approvals, partial refunds, network drops mid-charge,
   etc.). Pass that, get a production credential.

### Geidea

```yaml
devices:
  - name: card-1
    kind: terminal
    profile: geidea-terminal
    provider_options:
      merchant_id: "your-mid-from-portal"
      terminal_id: "your-tid-from-portal"
      auth_value: "Bearer your-api-key"
      base_url: "https://api.merchant.geidea.net/pgw/api/v6/direct"  # or sandbox
```

Geidea's PGW (Payment Gateway) speaks JSON. The skeleton adapter maps
`amount`, `currency`, `merchantReferenceId`, and parses Geidea's
`responseCode` ("000" = approved). For sandbox, switch `base_url` to
their test environment URL (provided in your merchant onboarding).

Geidea offers two integration paths: hosted pages and direct PGW API.
This adapter uses the direct API path. For the hosted-page flow,
override `charge_path` to point at their `/sessions` endpoint.

### HyperPay

```yaml
devices:
  - name: card-1
    kind: terminal
    profile: hyperpay-terminal
    provider_options:
      merchant_id: "your-entity-id"
      auth_value: "Bearer your-access-token"
      base_url: "https://eu-test.oppwa.com/v1"  # sandbox
      # Production: https://oppwa.com/v1
```

HyperPay's "Copy & Pay" / OPP API also speaks JSON. The skeleton maps
HyperPay's `result.code` field — approved is `"000.000.000"`. Production
deployments typically use the COPYandPAY hosted widget for PCI-DSS scope
reduction; this adapter uses the server-to-server API instead.

### Network International (N-Genius)

```yaml
devices:
  - name: card-1
    kind: terminal
    profile: network-intl-terminal
    provider_options:
      merchant_id: "your-outlet-id"
      auth_value: "Bearer your-access-token"
      base_url: "https://api-gateway.sandbox.ngenius-payments.com"
      # Production: https://api-gateway.ngenius-payments.com
      charge_path: "/transactions/outlets/your-outlet-id/orders"
```

N-Genius is dominant in UAE. The outlet ID has to be embedded in the
URL path, so override `charge_path` to include it.

### Payfort / Amazon Payment Services

```yaml
devices:
  - name: card-1
    kind: terminal
    profile: payfort-terminal
    provider_options:
      merchant_identifier:    "your-merchant-identifier"
      access_code:            "your-access-code"
      sha_request_phrase:     "your-request-phrase"
      sha_response_phrase:    "your-response-phrase"
      language:               "en"
      base_url:               "https://sbpaymentservices.payfort.com/FortAPI"
```

The adapter signs every request with HMAC-SHA-256 over the canonical
form `request_phrase + sorted(key=value) + request_phrase`, exactly per
APS Integration Guide. The signature lives in the `signature` field of
the request body.

If you also configure `sha_response_phrase`, the adapter verifies every
response signature before treating any response as approved. With this
on, a tampered or man-in-the-middle response gets rejected even if its
`response_code` says `14000` (success). Strongly recommended for
production. The verification uses constant-time comparison to defend
against timing oracles.

Sandbox: `https://sbpaymentservices.payfort.com/FortAPI`
Production: `https://paymentservices.payfort.com/FortAPI`

The signer is unit-tested against the published APS spec example;
re-deriving the canonical string from first principles produces the
same hex digest as our implementation.

### Generic REST (anything else)

```yaml
devices:
  - name: card-1
    kind: terminal
    profile: generic-rest-terminal
    provider_options:
      base_url: "https://api.your-provider.example/v1"
      auth_header: "Authorization"
      auth_value: "Bearer your-key"
      charge_path: "/charge"
      payload_amount: "amount_cents"     # if your provider wants cents
      response_status: "result"
      response_approved: "OK"
      response_txn_id: "trans_id"
```

Every field shown in `terminals.py` GenericRESTTerminalAdapter is
overridable. If your provider's response uses dot-paths (e.g.
`result.code`), the adapter will resolve them via simple key lookup.
For deeper paths or custom interpretation, subclass and override
`_interpret(resp, amount, currency)`.

## Adding a new provider

Inherit from `TerminalAdapter` (for ground-up logic) or
`GenericRESTTerminalAdapter` (for REST providers — usually 20-30 lines).

```python
# alphax_bridge/terminals.py
class MyProviderAdapter(GenericRESTTerminalAdapter):
    name = "myprovider"

    def __init__(self, **opts):
        defaults = dict(
            base_url="https://api.myprovider.com/v2",
            charge_path="/transactions",
            response_status="state",
            response_approved="CAPTURED",
            response_txn_id="id",
        )
        defaults.update(opts)
        super().__init__(**defaults)

    # Optional: provider-specific signing
    def _post(self, path, body, timeout):
        body = {**body, "signature": self._sign(body)}
        return super()._post(path, body, timeout)
```

Then register in `TERMINALS`:

```python
TERMINALS["myprovider"] = MyProviderAdapter
```

And ship a profile JSON in `profiles/myprovider-terminal.json`.

## Testing without real hardware

Use the `mock-terminal` profile for development, demos, and training:

```yaml
devices:
  - name: card-1
    kind: terminal
    profile: mock-terminal
    provider_options:
      delay_seconds: 1.5
      decline_amount: 99.99   # any charge of exactly 99.99 will decline
```

Run a charge:

```bash
curl -X POST http://localhost:8420/charge \
     -H "Authorization: Bearer your-token" \
     -H "Content-Type: application/json" \
     -d '{"device":"card-1","amount":46.00,"currency":"SAR",
          "invoice_ref":"SINV-001","idempotency_key":"abc"}'
```

You'll get back the same JSON shape as a real provider would return.
Train your cashiers on the decline path by setting `decline_amount` to
a memorable value.

## Things this bridge intentionally does NOT do

- **It does not store card data.** The provider holds the PAN; the
  bridge only sees a masked PAN in the response.
- **It does not handle 3DS challenges directly.** Most providers handle
  3DS server-side; for those that require a redirect, you'll need to
  add a webhook listener — out of scope for this bridge.
- **It does not implement HMAC signing for every provider.** Payfort and
  some others require it. The skeletons leave a hook for you to add it.
- **It does not handle PCI-DSS scope.** Using a hosted widget or the
  provider's terminal-pad device keeps your bridge out of scope. Server-
  to-server API integrations may bring you in scope; consult your QSA.

## Production checklist

Before flipping a terminal from sandbox to production:

- [ ] Replace sandbox `base_url` with production URL
- [ ] Replace sandbox `auth_value` with production credential
- [ ] Run the provider's certification test plan in sandbox
- [ ] Verify retry behavior: network drop mid-charge, server timeout
- [ ] Verify refund flow works for partial and full amounts
- [ ] Verify cancel flow works while a charge is pending
- [ ] Confirm the receipt prints the correct masked PAN, auth code, brand
- [ ] Confirm declined-card path shows a clear error to the cashier
- [ ] Set up monitoring / alerts for elevated decline rates
- [ ] Document your support escalation path with the provider

The bridge gets you the architecture and the wiring. The contracts,
certification, and operational discipline are on you.
