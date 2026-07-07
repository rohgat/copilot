const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const qrcode = require('qrcode-terminal');

const app = express();
app.use(express.json());

const PORT = parseInt(process.env.WHATSAPP_BRIDGE_PORT || '3001');

let clientReady = false;
let qrCode = null;

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: './data/whatsapp_session' }),
  puppeteer: {
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  },
});

client.on('qr', (qr) => {
  qrCode = qr;
  clientReady = false;
  console.log('[WhatsApp] Scan QR code to link your number:');
  qrcode.generate(qr, { small: true });
  console.log('[WhatsApp] Or visit http://localhost:' + PORT + '/qr-web to scan in browser');
});

client.on('ready', () => {
  clientReady = true;
  qrCode = null;
  console.log('[WhatsApp] Connected and ready');
});

client.on('disconnected', (reason) => {
  clientReady = false;
  console.log('[WhatsApp] Disconnected:', reason);
});

client.on('auth_failure', (msg) => {
  clientReady = false;
  console.error('[WhatsApp] Auth failure:', msg);
});

client.initialize();

// POST /send — send a WhatsApp message
app.post('/send', async (req, res) => {
  const { to, message } = req.body;
  if (!to || !message) {
    return res.status(400).json({ error: 'Missing to or message' });
  }
  if (!clientReady) {
    return res.status(503).json({ error: 'WhatsApp not connected', status: 'disconnected' });
  }
  try {
    // Format phone number: remove + for WhatsApp ID
    const chatId = to.replace(/^\+/, '') + '@c.us';
    await client.sendMessage(chatId, message);
    res.json({ ok: true });
  } catch (err) {
    console.error('[WhatsApp] Send error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// GET /status
app.get('/status', (req, res) => {
  res.json({
    status: clientReady ? 'connected' : 'disconnected',
    hasQr: !!qrCode,
  });
});

// GET /qr — returns QR data for dashboard display
app.get('/qr', (req, res) => {
  if (!qrCode) {
    return res.status(404).json({ error: 'No QR code available', ready: clientReady });
  }
  res.json({ qr: qrCode });
});

// GET /qr-web — render QR in browser
app.get('/qr-web', (req, res) => {
  if (clientReady) {
    return res.send('<html><body style="font-family:sans-serif;text-align:center;padding:40px"><h2>✅ WhatsApp Connected</h2></body></html>');
  }
  if (!qrCode) {
    return res.send('<html><body style="font-family:sans-serif;text-align:center;padding:40px"><h2>Waiting for QR code...</h2><script>setTimeout(()=>location.reload(),3000)</script></body></html>');
  }
  res.send(`
    <html><head><title>Copilot — WhatsApp Setup</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    </head>
    <body style="font-family:sans-serif;text-align:center;padding:40px;background:#f8f9fa">
      <h2>Scan with WhatsApp</h2>
      <p style="color:#666">Open WhatsApp → Linked Devices → Link a Device</p>
      <div id="qr" style="display:inline-block;margin:20px;padding:20px;background:white;border-radius:8px"></div>
      <p style="color:#999;font-size:12px">Page refreshes automatically</p>
      <script>
        new QRCode(document.getElementById('qr'), { text: ${JSON.stringify(qrCode)}, width: 256, height: 256 });
        setTimeout(() => location.reload(), 30000);
      </script>
    </body></html>
  `);
});

app.listen(PORT, () => {
  console.log('[WhatsApp Bridge] Listening on port ' + PORT);
});
