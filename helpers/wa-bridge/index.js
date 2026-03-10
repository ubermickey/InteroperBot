/**
 * InteroperBot WhatsApp Bridge — Baileys + HTTP/WebSocket server.
 *
 * Runs on 127.0.0.1:3456 (configurable via WA_BRIDGE_PORT).
 * - GET  /status  → { connected: bool }
 * - POST /send    → { to: "+1...", text: "..." } → sends WhatsApp message
 * - WebSocket /ws → pushes incoming messages as JSON events
 */

const { makeWASocket, useMultiFileAuthState, DisconnectReason } = require('baileys');
const http = require('http');
const { WebSocketServer } = require('ws');

const PORT = parseInt(process.env.WA_BRIDGE_PORT || '3456', 10);
const AUTH_DIR = './auth';

let sock = null;
const wsClients = new Set();

async function startBridge() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: true,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', ({ connection, lastDisconnect }) => {
        if (connection === 'close') {
            const reason = lastDisconnect?.error?.output?.statusCode;
            if (reason !== DisconnectReason.loggedOut) {
                console.log('Reconnecting...');
                startBridge();
            } else {
                console.log('Logged out. Delete auth/ and re-scan QR.');
            }
        }
        if (connection === 'open') {
            console.log('WhatsApp connected');
            broadcast({ type: 'status', connected: true });
        }
    });

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
    const headers = { 'Content-Type': 'application/json' };

    if (req.method === 'GET' && req.url === '/status') {
        res.writeHead(200, headers);
        res.end(JSON.stringify({ connected: sock?.user != null }));
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
    ws.on('close', () => wsClients.delete(ws));
});

// --- Start ---
server.listen(PORT, '127.0.0.1', () => {
    console.log(`WhatsApp bridge listening on 127.0.0.1:${PORT}`);
    startBridge();
});
