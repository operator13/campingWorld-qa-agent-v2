# Feature: Public Dashboard Sharing via ngrok

> Share the QA Command Center dashboard with anyone outside your local network using a secure ngrok tunnel.

**Status:** PLANNED
**Priority:** Low
**Depends on:** QA Command Center Dashboard

---

## The Problem

The dashboard runs on `localhost:8080` and is only accessible to devices on the same WiFi network. To share it with colleagues, stakeholders, or friends outside your network, you need a public URL.

---

## Setup Instructions

### Step 1: Install ngrok

```bash
# macOS (Homebrew)
brew install ngrok

# Or download from https://ngrok.com/download
```

### Step 2: Create a Free ngrok Account

1. Go to https://dashboard.ngrok.com/signup
2. Sign up (free tier includes 1 tunnel, 1 online ngrok process)
3. Copy your auth token from https://dashboard.ngrok.com/get-started/your-authtoken

### Step 3: Authenticate

```bash
ngrok config add-authtoken YOUR_AUTH_TOKEN_HERE
```

### Step 4: Start the Tunnel

```bash
# Make sure the dashboard server is running first
uvicorn qa_agent.dashboard.server:app --host 0.0.0.0 --port 8080

# In a separate terminal, start ngrok
ngrok http 8080
```

ngrok will display:

```
Session Status    online
Forwarding        https://abc123.ngrok-free.app → http://localhost:8080
```

### Step 5: Share the URL

Send the `https://abc123.ngrok-free.app` URL to anyone — they can open it in any browser. Full dashboard functionality including:

- Live health gauge and domain cards
- Agent evaluation scores with tooltips
- Test runner (can trigger tests remotely)
- Run history with clickable HTML reports
- WebSocket real-time updates

---

## Optional: Custom Domain (Paid)

With ngrok's paid plan ($8/month), you can set a stable subdomain:

```bash
ngrok http 8080 --domain=qa-dashboard.ngrok-free.app
```

This gives you the same URL every time instead of a random one.

---

## Optional: Auto-Start Script

Create a script that starts both the dashboard and ngrok:

```bash
#!/bin/bash
# run-public-dashboard.sh

echo "Starting QA Command Center..."
uvicorn qa_agent.dashboard.server:app --host 0.0.0.0 --port 8080 &
SERVER_PID=$!
sleep 2

echo "Starting ngrok tunnel..."
ngrok http 8080 --log=stdout &
NGROK_PID=$!

echo ""
echo "Dashboard running. Check ngrok output for public URL."
echo "Press Ctrl+C to stop."

trap "kill $SERVER_PID $NGROK_PID 2>/dev/null" EXIT
wait
```

```bash
chmod +x run-public-dashboard.sh
./run-public-dashboard.sh
```

---

## Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Anyone with the URL can access** | ngrok URLs are random and hard to guess; share only with trusted people |
| **Test runner can trigger tests** | Tests only run on your machine — no destructive impact on external systems |
| **Health/eval data exposed** | Dashboard is read-only for external viewers (test runner requires local context) |
| **ngrok free tier** | URLs change each restart; sessions expire after 2 hours of inactivity |
| **Want to restrict access?** | ngrok paid plans support basic auth: `ngrok http 8080 --basic-auth="user:password"` |

### Adding Basic Auth (Recommended for Sharing)

```bash
ngrok http 8080 --basic-auth="qa-viewer:yourpassword"
```

Visitors will be prompted for username/password before seeing the dashboard.

---

## WebSocket Support

ngrok supports WebSocket tunneling out of the box. The dashboard's real-time features (test runner streaming, eval updates, health updates) will work through the tunnel with no additional configuration.

---

## Alternatives

| Option | Pros | Cons |
|--------|------|------|
| **ngrok** | Instant setup, free tier, WebSocket support | Random URLs on free tier, 2hr timeout |
| **Cloudflare Tunnel** | Free, stable URLs, no timeout | Requires Cloudflare account + domain |
| **Tailscale** | Peer-to-peer VPN, no exposed ports | Both parties need Tailscale installed |
| **Deploy to cloud** | Permanent URL, always-on | Costs money, Docker deployment needed |
| **Port forwarding** | No third-party dependency | Security risk, router config needed |
