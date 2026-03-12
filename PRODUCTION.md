# Production Deployment Guide: rehaapp.com

This guide provides step-by-step instructions for hosting the **REHA Connect** platform and its **Homepage** in production using Render, Supabase, Stripe, and Cloudflare.

## 🏗️ Architecture Overview

- **Domain Management**: Cloudflare (`rehaapp.com`)
- **Frontend**: Render Static Site (`rehaapp.com`, `www.rehaapp.com`)
- **Backend API**: Render Web Service (Docker) (`api.rehaapp.com`)
- **Database**: Supabase (PostgreSQL + Auth)
- **Payments**: Stripe

---

## 🌐 Step 1: Domain & DNS (Cloudflare)

1.  **Register/Transfer Domain**: Ensure `rehaapp.com` is managed in Cloudflare.
2.  **DNS Records**:
    - You will add CNAME records later once Render provides the hostnames.
    - Ensure "Proxy status" is set to **Proxied** (orange cloud) for best performance/security.
3.  **SSL/TLS**: Set mode to **Full (strict)** in Cloudflare's SSL/TLS settings.

---

## ⚡ Step 2: Database & Auth (Supabase)

1.  **Create Project**: Create a new project in the [Supabase Dashboard](https://database.new).
2.  **Get Credentials**:
    - Go to **Project Settings** > **API**.
    - Copy the `Project URL` (used as `SUPABASE_URL`).
    - Copy the `service_role` key (used as `SUPABASE_KEY`).
3.  **Database Schema**:
    - Run your migration scripts or initialize tables for `workspaces`, `usage`, etc. (refer to `app/db/` if applicable).

---

## 💳 Step 3: Payments (Stripe)

1.  **Activate Account**: Complete your business profile in the [Stripe Dashboard](https://dashboard.stripe.com).
2.  **Create Product**:
    - Create a "Pro Plan" product.
    - Set up a Recurring Price (e.g., $19/month).
    - Copy the **Price ID** (e.g., `price_1P...`). This is your `STRIPE_PRO_PRICE_ID`.
3.  **Get API Keys**:
    - Go to **Developers** > **API Keys**.
    - Copy the `Secret key` (starting with `sk_live_` for prod). This is your `STRIPE_SECRET_KEY`.
4.  **Webhooks**:
    - After hosting the API, go to **Webhooks** > **Add endpoint**.
    - URL: `https://api.rehaapp.com/api/stripe/webhook` (update this after Step 4).
    - Select events: `checkout.session.completed`, `customer.subscription.updated/deleted`.
    - Copy the `Signing secret` (`whsec_...`). This is your `STRIPE_WEBHOOK_SECRET`.

---

## 🚀 Step 4: Hosting the Backend (Render Web Service)

1.  **New Web Service**: Connect your `crm-connectors` repository.
2.  **Settings**:
    - **Name**: `reha-api`
    - **Runtime**: `Docker`
    - **Plan**: `Starter` (Free tier sleeps after 15m; Starter is recommended for production).
3.  **Environment Variables**:
    - `ENV`: `prod`
    - `PORT`: `10000`
    - `API_BASE_URL`: `https://api.rehaapp.com`
    - `SUPABASE_URL`: (From Step 2)
    - `SUPABASE_KEY`: (From Step 2)
    - `HUBSPOT_CLIENT_ID` / `SECRET`: (From HubSpot Developer Portal)
    - `SLACK_CLIENT_ID` / `SECRET` / `SIGNING_SECRET`: (From Slack App Settings)
    - `STRIPE_SECRET_KEY` / `WEBHOOK_SECRET`: (From Step 3)
    - `OPENAI_API_KEY`: (From OpenAI Dashboard)
4.  **Custom Domain**:
    - In Render, go to **Settings** > **Custom Domains**.
    - Add `api.rehaapp.com`.
    - Update DNS in Cloudflare with the provided CNAME.

---

## 🏠 Step 5: Hosting the Homepage (Render Static Site)

1.  **New Static Site**: Connect your `REHA-Homepage` repository.
2.  **Settings**:
    - **Build Command**: (Leave empty if it's pure HTML)
    - **Publish Directory**: `.` (or the folder containing `index.html`)
3.  **Custom Domain**:
    - Add `rehaapp.com` and `www.rehaapp.com`.
    - Update DNS in Cloudflare with the provided settings.

---

## 🔄 Step 6: Update App Redirects

Now that the site is live at `api.rehaapp.com`, you **must** update the OAuth callback URLs in the developer portals:

### 🟠 HubSpot Developer Portal
1.  Go to your App Settings > **Auth**.
2.  Update **Redirect URL** to:
    - `https://api.rehaapp.com/api/hubspot/oauth/callback`

### 🔵 Slack App Settings
1.  Go to **OAuth & Permissions**.
2.  Update **Redirect URLs** to:
    - `https://api.rehaapp.com/api/slack/oauth/callback`
3.  Go to **Event Subscriptions** & **Interactivity**:
    - Update Request URLs to `https://api.rehaapp.com/api/slack/events` and `https://api.rehaapp.com/api/slack/interactivity`.

---

## ✅ Final Verification

1.  Visit `https://rehaapp.com` to ensure the homepage loads.
2.  Visit `https://api.rehaapp.com/api/health` to verify the API is up.
3.  Perform a test installation from the homepage to verify the OAuth flow to the new production URLs.
