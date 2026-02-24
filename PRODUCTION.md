# Production Deployment Guide: HubSpot-Slack Connector

For a FastAPI project using Docker and Supabase, **Render** (render.com) is the recommended hosting platform. It offers the best balance of simplicity, features (Auto-SSL, Docker support), and price.

---

## 🏗️ Option 1: Managed Hosting (Recommended: Render)

Render handles SSL, load balancing, and zero-downtime deployments automatically.

### Step 1: Prepare Repository
Ensure your code is pushed to a private GitHub/GitLab repository.

### Step 2: Create a Web Service
1. Link your repo to Render.
2. Choose **Web Service**.
3. Set **Environment** to `Docker`.
4. Render will automatically detect your `Dockerfile`.

### Step 3: Configure Environment Variables
In the "Environment" tab, add all variables from your `.env`:
- `SUPABASE_URL` & `SUPABASE_KEY`
- `HUBSPOT_CLIENT_ID` & `HUBSPOT_CLIENT_SECRET`
- `SLACK_CLIENT_ID` & `SLACK_CLIENT_SECRET`
- `API_BASE_URL`: This will be your `https://your-app-name.onrender.com`.

### Step 4: Health Check
Set the health check path to `/api/health` (or your root `/`) to ensure Render knows when your app is ready.

---

## 🛠️ Option 2: Virtual Private Server (VPS)
If you prefer full control (DigitalOcean, AWS EC2, Hetzner) using the provided **Docker + Nginx** setup.

### Step 1: Server Setup
Install Docker and Docker Compose on your Linux server.

### Step 2: Clone & Configure
```bash
git clone <your-repo>
cd crm-connectors
cp .env.example .env # Update with production values
```

### Step 3: Launch
```bash
docker-compose up -d --build
```
This will launch:
1. **The App**: Accessible on internal port 8000.
2. **Nginx**: Acting as a reverse proxy, listening on port 80 (and 443 if you add Certbot).

---

## 🔐 Security Best Practices

1. **SSL/HTTPS**:
   - **Render**: Handled automatically.
   - **VPS**: Use **Certbot (Let's Encrypt)** to secure your Nginx setup.
2. **Database Access**: Restrict your Supabase project to only allow connections from your production IP (if not using the API).
3. **Secrets**: NEVER commit your `.env` file to version control. Always use the hosting platform's secret manager.
4. **Logs**: Use a logging service (like BetterStack or Axiom) to monitor production errors in real-time.

---

## 🚀 Scaling
- **Horizontal Scaling**: On Render, you can simply slide a bar to increase instances. The `IntegrationService` request-scoped cache works across instances as long as session affinity isn't required (FastAPI is stateless).
- **Database**: Supabase handles scaling the PG instance independently of your app servers.
