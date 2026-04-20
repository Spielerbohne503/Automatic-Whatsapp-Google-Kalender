/**
 * WhatsApp Bridge – lokaler HTTP-Server für den Kalender-Bot
 * Verbindet sich via whatsapp-web.js mit WhatsApp.
 * Erste Start: QR-Code im Fenster scannen mit der Bot-Nummer.
 * Danach: Verbindung wird automatisch wiederhergestellt (LocalAuth).
 *
 * Endpunkte:
 *   POST /send   { "phone": "+49...", "message": "..." }
 *   GET  /receive  → nächste eingegangene Nachricht (oder null)
 *   GET  /status   → Verbindungsstatus
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const qrcode  = require('qrcode-terminal');

const PORT = 3000;
const app  = express();
app.use(express.json());

// Eingehende Nachrichten-Warteschlange
const queue = [];

let clientReady = false;
let connectedNumber = null;

// ─── WhatsApp Client ────────────────────────────────────────────────────────
const client = new Client({
    authStrategy: new LocalAuth({ dataPath: './session' }),
    puppeteer: {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
        ],
    },
});

client.on('qr', (qr) => {
    console.log('\n=======================================================');
    console.log('  QR-Code erscheint gleich – mit WhatsApp scannen!');
    console.log('  (WhatsApp → Geräte verknüpfen → Gerät hinzufügen)');
    console.log('=======================================================\n');
    qrcode.generate(qr, { small: true });
});

client.on('authenticated', () => {
    console.log('[WhatsApp] Authentifizierung erfolgreich.');
});

client.on('ready', () => {
    connectedNumber = client.info.wid.user;
    clientReady = true;
    console.log(`[WhatsApp] Verbunden als: +${connectedNumber}`);
    console.log('[Bridge] Bereit auf Port', PORT);
});

client.on('disconnected', (reason) => {
    console.warn('[WhatsApp] Verbindung getrennt:', reason);
    clientReady = false;
});

// Eingehende Nachrichten in die Warteschlange legen
client.on('message', (msg) => {
    // Nur Textnachrichten (kein Status, keine Gruppen)
    if (msg.isStatus || msg.from.endsWith('@g.us')) return;
    if (msg.type !== 'chat') return;

    queue.push({
        from:    msg.from,   // z.B. "4915226310258@c.us"
        text:    msg.body,
        time:    Date.now(),
    });
    console.log(`[Eingehend] ${msg.from}: ${msg.body.substring(0, 60)}`);
});

client.initialize();

// ─── HTTP Endpunkte ──────────────────────────────────────────────────────────

// Nachricht senden
app.post('/send', async (req, res) => {
    const { phone, message } = req.body;
    if (!clientReady) {
        return res.status(503).json({ error: 'WhatsApp nicht verbunden' });
    }
    try {
        const chatId = phone.replace('+', '').replace(/\s/g, '') + '@c.us';
        await client.sendMessage(chatId, message);
        res.json({ ok: true });
    } catch (e) {
        console.error('[Senden Fehler]', e.message);
        res.status(500).json({ error: e.message });
    }
});

// Nächste eingegangene Nachricht holen (Polling)
app.get('/receive', (req, res) => {
    const msg = queue.shift() || null;
    res.json(msg);
});

// Status
app.get('/status', (req, res) => {
    res.json({ connected: clientReady, number: connectedNumber });
});

app.listen(PORT, '127.0.0.1', () => {
    console.log(`[Bridge] HTTP-Server gestartet auf localhost:${PORT}`);
});
