# WhatsApp Integration R&D Log

## Hypothesis
Baileys (Node.js bridge) can reliably connect InteroperBot to WhatsApp
with <5s message latency and >99% uptime over 7 days.

## Experiments

### Trial 1: Baileys Bridge — Basic Connection
- **Date**: 2026-03-09
- **Setup**: Node.js v25.8.0, Baileys v6.7.16, macOS, `helpers/wa-bridge/`
- **Hypothesis**: Bridge connects to WhatsApp, generates QR, accepts pairing
- **Method**: Start bridge, observe connection events, test HTTP/WS endpoints
- **Observations**:
  - `npm install` → 92 packages, 0 vulnerabilities, 19s
  - Baileys imports (`makeWASocket`, `useMultiFileAuthState`) load correctly
  - HTTP+WS server binds to `127.0.0.1:3456`, `/status` returns `{"connected":false}`
  - `connection.update` event fires with `qr` key on first attempt
  - QR value was valid on first connection, then `undefined` on subsequent attempts
  - Connection cycle: connect → "not logged in, attempting registration" → 405 "Connection Failure" → reconnect
  - `printQRInTerminal` option deprecated in Baileys v6 — must listen to `connection.update` for QR
  - `requestPairingCode()` method exists as alternative to QR scanning
  - Rate limiting: WhatsApp throttles QR generation after rapid reconnect attempts (~30min cooldown)
  - Reconnect delay of 5s + max 10 retries prevents tight loops
  - pino logger at `warn` level suppresses noisy Baileys JSON output
- **Result**: PARTIAL — infrastructure works, auth blocked by QR rate limit
- **Next**: Wait 30min for rate limit reset, then test QR scan. Also test pairing code flow with `WA_PHONE_NUMBER`.

### Trial 1b: Pairing Code Auth (pending)
- **Date**: [pending]
- **Setup**: Same bridge, `WA_PHONE_NUMBER` env var set
- **Hypothesis**: Pairing code bypasses QR rate limit
- **Method**: `python bot.py --setup-whatsapp +1NNNNNN`, enter code in WhatsApp
- **Observations**: [pending]
- **Result**: [pending]

### Trial 2: Baileys Bridge — Message Round-Trip (pending)
- **Date**: [pending]
- **Hypothesis**: After auth, bridge receives and sends messages within 5s
- **Method**: Send 10 test messages via WhatsApp, verify bridge receives them, send replies
- **Observations**: [pending]
- **Result**: [pending]

### Trial 3: Baileys Bridge — 24h Stability (pending)
- **Date**: [pending]
- **Hypothesis**: Bridge maintains connection for 24h without intervention
- **Method**: Leave running, log reconnects, measure uptime
- **Observations**: [pending]
- **Result**: [pending]

## Technical Notes

### Baileys v6 Breaking Changes (vs v5)
- `printQRInTerminal` deprecated — QR comes via `connection.update` event, render with `qrcode-terminal`
- QR value can be `undefined` even when `qr` key is present (rate limiting)
- `requestPairingCode(phoneNumber)` available for phone-number-based auth
- `Browsers.macOS('Safari')` for browser identity
- pino logger required (Baileys uses structured JSON logging internally)

### Connection Error Codes
- 405: "Connection Failure" — WebSocket decoding error during pairing handshake (common when rate-limited)
- 401 (DisconnectReason.loggedOut): Must re-authenticate, delete `auth/` directory
- Others: Auto-reconnect with delay

### Python-Node Bridge Architecture
- Python (`whatsapp.py`) manages Node subprocess lifecycle
- HTTP `POST /send` for outgoing messages
- WebSocket `/ws` for incoming message stream
- HTTP `GET /status` and `GET /qr` for monitoring
- Same subprocess helper pattern as `helpers/transcribe` (Swift) and `helpers/extract_keyframes.sh` (bash)

## Decision Matrix
| Method | Latency | Uptime | Cost | Setup | Score |
|---|---|---|---|---|---|
| Baileys bridge | <1s (WS) | ? | Free | Medium | ? |
| Green API | ? | ? | $15/mo | Easy | ? |
| Meta Cloud API | ? | ? | Free | Hard | ? |
| whatsapp-web.js | ? | ? | Free | Medium | ? |

## Current Winner: Baileys (pending auth verification)
