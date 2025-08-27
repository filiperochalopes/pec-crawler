FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Bahia

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libpangocairo-1.0-0 libpango-1.0-0 libx11-xcb1 libxshmfence1 \
    libxext6 libxfixes3 libxkbcommon0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install chromium

# Copia o código
COPY . .

# Usuário não-root + diretório de dados
RUN adduser --disabled-password --gecos "" appuser \
 && mkdir -p /data \
 && chown -R appuser:appuser /app /data

USER appuser
EXPOSE 8000

# Vars padrão (podem ser sobrescritas no compose/.env)
ENV RUN_AT=07:00

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]