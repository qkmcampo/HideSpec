# HideSpec Web Dashboard

Browser-only dashboard for the HideSpec leather inspection system.

## Run locally

```bash
npm install
npm run dev
```

Create `.env.local` to override the Raspberry Pi address:

```ini
VITE_PI_IP_ADDRESS=192.168.100.114
# VITE_API_BASE_URL=http://192.168.100.114:5000
# VITE_STREAM_URL=http://192.168.100.114:5001
```
