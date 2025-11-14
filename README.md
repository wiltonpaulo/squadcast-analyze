# Squadcast Analyze

A lightweight, modular Python CLI tool to **fetch and analyze incident data from the Squadcast API**.

Built for DevOps and SRE teams who want to extract insights — top incidents, environment trends, service health, MTTR — directly from Squadcast exports.

## 🚀 Features

- **Modular Python package** with clean CLI (using [Typer](https://typer.tiangolo.com/))
- **Authentication** via refresh token (`X-Refresh-Token` → access token)
- **Fetch incidents** with date, team and assignee filters
- **Analyze** top counts by service, priority, environment, etc.
- **List fields** dynamically (auto-detects JSON schema)
- **Safe output** to local `data/raw` and `data/processed`
- Optional support for:
  - `list-teams` — to inspect your available team IDs
  - `config set` — to edit `.env` values directly via CLI

## 🧩 Folder structure

```
squadcast-analyze/
├── src/
│   └── squadcast_analyze/
│       ├── __init__.py
│       ├── cli.py               # CLI entrypoint
│       ├── auth.py              # Token retrieval logic
│       ├── client.py            # Squadcast API client
│       ├── config.py            # Environment loader (.env)
│       ├── analyzer.py          # DataFrame conversions & grouping
│       └── io_utils.py          # Helpers for JSON I/O, timestamps, dirs
├── data/
│   ├── raw/                     # Fetched raw JSON or CSV data
│   └── processed/               # CSV outputs from analysis
├── .env                         # Config file with API URLs & tokens
├── pyproject.toml               # Build metadata
└── README.md
```

## ⚙️ Installation

```bash
# clone your private repo
git clone git@github.com:wiltonpaulo/squadcast-analyze.git
cd squadcast-analyze

# create a venv
python3 -m venv .venv
source .venv/bin/activate

# install in editable mode
pip install -e .
```

## 🔐 Configuration

Create a `.env` file at the project root:

```ini
SQUADCAST_REFRESH_TOKEN=your_refresh_token_here
SQUADCAST_AUTH_URL=https://auth.squadcast.com/oauth/access-token
SQUADCAST_BASE_API=https://api.squadcast.com/v3
SQUADCAST_TEAM_ID=<id>
SQUADCAST_ASSIGNEE_ID=<user_id>
DEFAULT_START=2025-11-10T00:00:00.000Z
DEFAULT_END=2025-11-12T23:59:59.999Z
STATUS=acknowledged
```

> 💡 You can generate a new `REFRESH_TOKEN` in Squadcast under your **API Integrations** page.

## 🧠 Usage

### 1️⃣ Get a token
```bash
squadcast-analyze auth
```
> Prints an access token retrieved from your refresh token.

### 2️⃣ Fetch incidents
```bash
squadcast-analyze fetch \
    --start 2025-11-10T00:00:00.000Z \
    --end 2025-11-12T23:59:59.999Z \
    --team 62b4349bdfe4d7b4809d7b5f \
    --assignee 67d1243a70e596040c5a4041 \
    --type json
```

Optional flags:
- `--team none` → ignore TEAM_ID (fetch all).
- `--assignee <user_id>` → fetch using assignee's user id.
- `--tags 'alert_type=mem(k8)'` → filter for a specific tag.
- `--status acknowledged` → filter for status of the alert.
- `--debug` → show full URL and response preview.

Results are saved under `data/raw/`, e.g.:
```
data/raw/incidents_20251112T140906Z.json
```

### 3️⃣ Explore available fields
```bash
squadcast-analyze list-fields --input data/raw/incidents_20251112T140906Z.json
```
Example output:
```
Available fields:
- title
- priority
- service
- tags.env_alias.value
- tags.source.value
- tta (ms)
- ttr (ms)
...
Total fields: 39
```

### 4️⃣ Analyze top values
```bash
# Top 10 by service
squadcast-analyze analyze \
    --input data/raw/incidents_20251112T140906Z.json \
    --group-by service \
    --top 10

# Top 10 by environment alias
squadcast-analyze analyze \
    --input data/raw/incidents_20251112T140906Z.json \
    --group-by env_alias \
    --top 10

# Top 10 by priority
squadcast-analyze analyze \
    --input data/raw/incidents_20251112T140906Z.json \
    --group-by priority \
    --top 10 \
    --csv-out data/processed/top_priority.csv
```

## 🧰 Optional convenience commands

If added to the CLI, you can use shorter aliases:

```bash
squadcast-analyze title --input ... --top 10
squadcast-analyze service --input ... --top 10
squadcast-analyze priority --input ... --top 10
squadcast-analyze env --input ... --top 10
```

## 🧪 Examples

| Command | Description | Output |
|----------|--------------|--------|
| `squadcast-analyze fetch --team none --type json` | Fetch all incidents in UTC range | `data/raw/*.json` |
| `squadcast-analyze analyze --input data/raw/incidents.json --group-by service --top 10` | Top 10 by service | Table in terminal |
| `squadcast-analyze analyze --input data/raw/incidents.json --group-by priority --top 10 --csv-out data/processed/top_priority.csv` | Save results to CSV | `data/processed/*.csv` |

