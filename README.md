# dentro de pec_app/
python -m venv .venv && source .venv/bin/activate
pip install "fastapi>=0.112" "uvicorn[standard]>=0.30" "apscheduler>=3.10" \
            "httpx>=0.27" "beautifulsoup4>=4.12" "lxml>=5.2" \
            "sqlalchemy>=2.0" "aiosqlite>=0.20"

# (opcional) configs
export TZ=America/Bahia
export RUN_AT=07:00
export DATABASE_URL="sqlite+aiosqlite:///./pec.sqlite3"

# subir a API

uvicorn main:app --host 0.0.0.0 --port 8000

# testar com curl

curl -X POST http://localhost:8000/run
curl http://localhost:8000/last

# Banco de dados inicial

```sql
CREATE TABLE pec_versions (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL,
    download_link TEXT NOT NULL,
    release_notes_page TEXT,
    release_notes_summary TEXT,
    created_at TIMESTAMP NOT NULL
);
```

# Reference (endpoints)

- POST /run — executa agora e persiste nova versão.
- GET /last — última versão persistida.
- GET /runs?limit=20 — histórico recente de versões.
- GET /healthz — health check.