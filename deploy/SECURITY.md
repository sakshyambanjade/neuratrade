# Network hardening (apply on VPS)

Restrict non-public services:
```bash
sudo ufw default deny incoming
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow from 127.0.0.1 to any port 8000 proto tcp    # FastAPI
sudo ufw allow from 127.0.0.1 to any port 8742 proto tcp    # Prajnyavan
sudo ufw allow from 127.0.0.1 to any port 11434 proto tcp   # Ollama
sudo ufw allow from 127.0.0.1 to any port 6379 proto tcp    # Redis (optional)
sudo ufw enable
```

Secrets:
- Store API keys and BRAIN_SECRET in `.env` only; never commit.
- Rotate API_KEY for production; keep a different dev key.

Backups:
- Use `python backend/scripts/backup_db.py` daily (cron) to keep 7-day SQLite snapshots.
