# WhatsApp Integration R&D Log

## Hypothesis
Baileys (Node.js bridge) can reliably connect InteroperBot to WhatsApp
with <5s message latency and >99% uptime over 7 days.

## Experiments

### Trial 1: Baileys Bridge — Basic Connection
- **Date**: [date]
- **Setup**: Node.js bridge, personal WhatsApp, single contact
- **Hypothesis**: Bridge connects, receives messages, replies within 5s
- **Method**: Send 10 test messages over 1 hour, measure latency
- **Observations**: [latency, errors, disconnects]
- **Result**: PASS / FAIL / PARTIAL
- **Next**: [what to try based on result]

### Trial 2: Baileys Bridge — 24h Stability
- **Date**: [date]
- **Hypothesis**: Bridge maintains connection for 24h without intervention
- **Method**: Leave running, log reconnects, measure uptime
- **Observations**: [reconnect count, total downtime]
- **Result**: PASS / FAIL / PARTIAL

### Trial 3: [Fallback — if Baileys fails]
- **Date**: [date]
- **Alternative tested**: Green API / Meta Cloud API / whatsapp-web.js
- **Hypothesis**: [alternative] achieves same latency/uptime targets
- **Method**: Same test protocol as Trial 1
- **Observations**: [results]
- **Result**: PASS / FAIL / PARTIAL

## Decision Matrix
| Method | Latency | Uptime | Cost | Setup | Score |
|---|---|---|---|---|---|
| Baileys bridge | ? | ? | Free | Medium | ? |
| Green API | ? | ? | $15/mo | Easy | ? |
| Meta Cloud API | ? | ? | Free | Hard | ? |
| whatsapp-web.js | ? | ? | Free | Medium | ? |

## Current Winner: [TBD after trials]
