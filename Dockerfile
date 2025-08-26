FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Bahia

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata curl ca-certificates libxml2 libxslt1.1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código
COPY . .

# Usuário não-root + diretório de dados (opcional, não usado p/ PG)
RUN adduser --disabled-password --gecos "" appuser \
 && mkdir -p /data \
 && chown -R appuser:appuser /app /data

USER appuser
EXPOSE 8000

# Vars padrão (podem ser sobrescritas no compose/.env)
ENV RUN_AT=07:00

WORKDIR /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]