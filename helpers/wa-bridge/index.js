/**
 * InteroperBot WhatsApp Bridge — Baileys + HTTP/WebSocket server.
 *
 * Runs on 127.0.0.1:3456 (configurable via WA_BRIDGE_PORT).
 * Auth: QR code (default) or pairing code (set WA_PHONE_NUMBER).
 *
 * - GET  /status  → { connected, user, qrPending }
 * - GET  /qr      → { qr: "..." } (current QR data, if awaiting scan)
 * - POST /send    → { to: "+1...", text: "..." } → sends WhatsApp message
 * - WebSocket /ws → pushes incoming messages as JSON events
 */

const { makeWASocket, useMultiFileAuthState, DisconnectReason, Browsers } = require('baileys');
const http = require('http');
const { WebSocketServer } = require('ws');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');
const pino = require('pino');

const PORT = parseInt(process.env.WA_BRIDGE_PORT || '3456', 10);
const AUTH_DIR = './auth';
const PHONE_NUMBER = process.env.WA_PHONE_NUMBER || '';  // e.g. "+12135551234"
const MAX_RECONNECTS = 10;
const RECONNECT_DELAY_MS = 5000;

let sock = null;
let currentQR = null;
let currentQRImage = null;
let reconnectCount = 0;
const wsClients = new Set();

const logger = pino({ level: 'warn' });

async function startBridge() {
    if (reconnectCount >= MAX_RECONNECTS) {
        console.error(`Max reconnects (${MAX_RECONNECTS}) reached. Exiting.`);
        console.error('Delete auth/ directory and restart to re-authenticate.');
        process.exit(1);
    }

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

    sock = makeWASocket({
        auth: state,
        logger,
        browser: Browsers.macOS('Safari'),
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        // --- QR code pairing ---
        if (qr) {
            currentQR = qr;
            console.log('\n┌─────────────────────────────────────┐');
            console.log('│  Scan this QR with WhatsApp:        │');
            console.log('│  Settings → Linked Devices → Link   │');
            console.log('└─────────────────────────────────────┘\n');
            qrcode.generate(qr, { small: true });
            QRCode.toDataURL(qr, { width: 280, margin: 2 })
                .then(url => {
                    currentQRImage = url;
                    broadcast({ type: 'qr', qr, qrImage: url });
                })
                .catch(() => {
                    currentQRImage = null;
                    broadcast({ type: 'qr', qr });
                });
        }

        // --- Pairing code (phone number based, alternative to QR) ---
        if (connection === 'open' && !sock.authState?.creds?.registered && PHONE_NUMBER) {
            try {
                const code = await sock.requestPairingCode(PHONE_NUMBER.replace(/^\+/, ''));
                console.log(`\nPairing code: ${code}`);
                console.log('Enter this code in WhatsApp → Linked Devices → Link with Phone Number\n');
            } catch (err) {
                console.error('Pairing code request failed:', err.message);
            }
        }

        if (connection === 'close') {
            currentQR = null;
            currentQRImage = null;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const reason = lastDisconnect?.error?.message || 'unknown';

            if (statusCode === DisconnectReason.loggedOut) {
                console.log('Logged out. Delete auth/ and restart.');
                process.exit(1);
            }

            reconnectCount++;
            console.log(
                `Connection closed (${reason}). ` +
                `Reconnecting in ${RECONNECT_DELAY_MS / 1000}s... ` +
                `(${reconnectCount}/${MAX_RECONNECTS})`
            );
            setTimeout(startBridge, RECONNECT_DELAY_MS);
        }

        if (connection === 'open') {
            currentQR = null;
            currentQRImage = null;
            reconnectCount = 0;
            console.log('WhatsApp connected as', sock.user?.id || 'unknown');
            broadcast({ type: 'status', connected: true });
        }
    });

    // --- Pairing code: request immediately after socket creation ---
    if (PHONE_NUMBER && !state.creds.registered) {
        // Wait for the socket to connect before requesting pairing code
        setTimeout(async () => {
            try {
                const code = await sock.requestPairingCode(PHONE_NUMBER.replace(/^\+/, ''));
                console.log(`\n╔═══════════════════════════════════╗`);
                console.log(`║  Pairing code: ${code.match(/.{1,4}/g).join('-')}       ║`);
                console.log(`║  Enter in WhatsApp → Link Device  ║`);
                console.log(`╚═══════════════════════════════════╝\n`);
            } catch (err) {
                console.error('Pairing code failed:', err.message);
                console.log('Falling back to QR code method...');
            }
        }, 5000);
    }

    sock.ev.on('messages.upsert', ({ messages }) => {
        for (const msg of messages) {
            if (msg.key.fromMe) continue;

            const text = msg.message?.conversation
                || msg.message?.extendedTextMessage?.text
                || '';
            if (!text) continue;

            const sender = msg.key.remoteJid.replace('@s.whatsapp.net', '');
            const timestamp = new Date((msg.messageTimestamp || 0) * 1000).toISOString();

            console.log(`[${sender}] ${text.substring(0, 80)}`);

            broadcast({
                type: 'message',
                from: sender,
                text,
                timestamp,
                id: msg.key.id,
            });
        }
    });
}

function broadcast(data) {
    const json = JSON.stringify(data);
    for (const ws of wsClients) {
        if (ws.readyState === 1) ws.send(json);
    }
}

// --- HTTP server ---
const server = http.createServer(async (req, res) => {
    const headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
    };

    if (req.method === 'OPTIONS') {
        res.writeHead(204, {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        });
        res.end();
        return;
    }

    if (req.method === 'GET' && req.url === '/status') {
        res.writeHead(200, headers);
        res.end(JSON.stringify({
            connected: sock?.user != null,
            user: sock?.user?.id || null,
            qrPending: currentQR != null,
        }));
        return;
    }

    if (req.method === 'GET' && req.url === '/qr') {
        res.writeHead(200, headers);
        res.end(JSON.stringify({ qr: currentQR, qrImage: currentQRImage }));
        return;
    }

    if (req.method === 'POST' && req.url === '/send') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', async () => {
            try {
                const { to, text } = JSON.parse(body);
                const jid = to.replace(/^\+/, '') + '@s.whatsapp.net';
                await sock.sendMessage(jid, { text });
                res.writeHead(200, headers);
                res.end(JSON.stringify({ sent: true }));
            } catch (err) {
                console.error('Send error:', err.message);
                res.writeHead(500, headers);
                res.end(JSON.stringify({ error: err.message }));
            }
        });
        return;
    }

    res.writeHead(404, headers);
    res.end(JSON.stringify({ error: 'Not Found' }));
});

// --- WebSocket server ---
const wss = new WebSocketServer({ server });

wss.on('connection', ws => {
    wsClients.add(ws);
    ws.send(JSON.stringify({
        type: 'status',
        connected: sock?.user != null,
        qrPending: currentQR != null,
    }));
    ws.on('close', () => wsClients.delete(ws));
});

// --- Start ---
server.listen(PORT, '127.0.0.1', () => {
    console.log(`WhatsApp bridge listening on 127.0.0.1:${PORT}`);
    if (PHONE_NUMBER) {
        console.log(`Pairing mode: will request code for ${PHONE_NUMBER}`);
    } else {
        console.log('QR mode: scan QR code to authenticate');
    }
    startBridge();
});
