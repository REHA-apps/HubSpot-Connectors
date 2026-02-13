# CRM Connectors
Modern HubSpot → Slack / WhatsApp Integration Framework
Built with FastAPI · Supabase · uv · Docker · Nginx · Pre‑commit · Ruff · Pyright

---

## 🚀 Overview

This project provides a modular, scalable integration framework for connecting **HubSpot CRM** with communication channels such as **Slack** and **WhatsApp**.

It is designed to be:

- **Extensible** — add new channels easily (Slack, WhatsApp, Email, SMS, etc.)
- **Maintainable** — clean architecture with connectors, clients, services
- **Production‑ready** — Docker, Nginx, CI/CD, pre‑commit, type checking
- **Fast** — async httpx, uv, FastAPI

---

## 📦 Project Structure

```
crm-connectors/
├── app/
│   ├── api/
│   │   ├── router.py
│   │   ├── hubspot/
│   │   ├── slack/
│   │   └── whatsapp/
│   ├── clients/
│   ├── connectors/
│   ├── services/
│   ├── integrations/
│   ├── db/
│   ├── utils/
│   ├── core/
│   └── main.py
│
├── scripts/
│   └── demo.py
│
├── tests/
│
├── .pre-commit-config.yaml
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── docker-compose.dev.yml
├── nginx.conf
├── .env
├── README.md
└── .gitignore

```
---

## 🧩 Features

### HubSpot
- OAuth installation
- Token refresh with Supabase persistence
- Contact search
- Task creation
- Webhook event handling

### Slack
- Slash commands (`/hs-find`)
- Rich Block Kit UI
- Event notifications


---

## 🛠️ Local Development

### Install dependencies
```bash
uv sync
```

### Run FastAPI locally
```bash
just dev
```

---

## 🐳 Docker

### Development mode (hot reload)
```bash
docker-compose -f docker-compose.dev.yml up --build
```

### Production mode
```bash
docker-compose up --build
```

---

## 🧪 Testing

### Run tests
```bash
pytest -q
```

---

## 🔍 Linting & Formatting

```bash
just lint
just typecheck
```

---

## 🔐 Environment Variables

See `.env.example` for required variables.

---

## 🚢 Deployment

This project includes:

- Dockerfile
- Nginx reverse proxy
- GitHub Actions CI/CD pipeline

---

## 📄 License

MIT License.
