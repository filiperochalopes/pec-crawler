# PEC Crawler API

API que monitora as novas versões do **e-SUS APS PEC**, armazena os dados encontrados e disponibiliza as informações por endpoints HTTP. O crawler também pode gerar um resumo das notas de versão com IA, quando configurado.

## O que ela faz

- Consulta periodicamente a página de atualizações do PEC.
- Salva versões inéditas, links de download e notas de versão no banco de dados.
- Executa automaticamente todos os dias no horário configurado.
- Expõe endpoints para acionar a consulta e consultar o histórico.
- Opcionalmente, resume as notas de versão usando Azure OpenAI.

## Pré-requisitos

- Python 3.10 ou superior
- Chromium para o Playwright
- Um banco PostgreSQL acessível pela aplicação

## Como executar localmente

### 1. Crie o ambiente e instale as dependências

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure as variáveis de ambiente

Crie um arquivo `.env` ou exporte as variáveis no terminal. Os valores abaixo são um ponto de partida:

```bash
export TZ=America/Bahia
export RUN_AT=07:00
export DATABASE_URL="postgresql+asyncpg://pec:changeme@localhost:5432/pec"
# opcional; caminho relativo das releases no Docusaurus
export RELEASES_PATH="docs/Versoes/"
```

Para habilitar o resumo das notas de versão com IA, inclua:

```bash
export AZURE_OPENAI_ENDPOINT="https://seu-recurso.openai.azure.com/"
export AZURE_OPENAI_API_KEY="sua-chave"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o-2024-05-13"
export AZURE_OPENAI_API_VERSION="2024-02-15-preview"
```

Quando essas variáveis estão definidas, o resumo em HTML é salvo no campo `release_notes_summary`.

O crawler segue o controle "Download" publicado na página inicial até a página
de notas (aceita link, `onclick`, nova aba, navegação de SPA e redirecionamentos),
sem montar URLs a partir do número da versão. Na página de notas, resolve o
endereço do controle Linux sem baixar o instalador. A versão completa vem do
caminho do instalador (por exemplo, `5.6.1`) ou do título da página, e precisa
pertencer à família anunciada, quando houver. Versões já registradas não são
inseridas novamente.

Uma falha na coleta agendada é registrada como erro pelo agendador. O endpoint
`/healthz` indica apenas que a API está ativa; não confirma o sucesso da coleta.

### 3. Inicie a API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

A documentação interativa ficará disponível em `http://localhost:8000/docs`.

## Executar com Docker

Com o arquivo `.env` configurado, execute:

```bash
docker compose up --build
```

A API será exposta na porta `8000`.

## Testes

Com o [uv](https://docs.astral.sh/uv/), as dependências de `requirements.txt` são
instaladas em um ambiente temporário, sem criar `.venv`:

```bash
PEC_TEST_BROWSER_CHANNEL=chrome uv run --no-project --python 3.11 \
  --with-requirements requirements.txt python -m unittest discover -s tests
```

`PEC_TEST_BROWSER_CHANNEL=chrome` usa o Google Chrome instalado. Sem essa
variável, os testes de navegador usam o Chromium do Playwright
(`playwright install chromium`). Os testes não acessam a internet nem o banco.

## Endpoints

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/run` | Executa o crawler imediatamente e persiste uma nova versão, se encontrada. |
| `GET` | `/last` | Retorna a última versão persistida. |
| `GET` | `/{version}` | Retorna uma versão persistida, usando o formato `5.4.38`. |
| `GET` | `/runs?limit=20` | Lista as versões mais recentes. Aceita de 1 a 200 itens. |
| `GET` | `/healthz` | Verifica se a API está disponível. |

### Exemplos rápidos

```bash
# Executar uma consulta agora
curl -X POST http://localhost:8000/run

# Consultar a última versão encontrada
curl http://localhost:8000/last

# Consultar uma versão específica
curl http://localhost:8000/5.4.38

# Consultar o status da aplicação
curl http://localhost:8000/healthz
```

## Banco de dados

A aplicação inicializa as tabelas necessárias ao iniciar. Caso precise criar a tabela manualmente, use:

```sql
CREATE TABLE pec_versions (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL,
    download_link TEXT NOT NULL,
    release_notes_page TEXT,
    release_notes_summary TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

---

Este repositório faz parte de uma automação em parceria com:

<p align="center">
  <a href="https://noharm.ai/" target="_blank" rel="noopener noreferrer">
    <img src="assets/noharm-logo.png" alt="Noharm.ai" width="260">
  </a>
</p>
