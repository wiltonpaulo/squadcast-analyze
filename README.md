# squadcast-analyze

Private toolkit to collect, process, and analyze Squadcast API data — providing insights by profile, environment, and incident patterns.

## Quickstart

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env   # edit with your tokens
```

## Commands

Auth
```bash
squadcast-analyze auth
```
Fetch
```bash
squadcast-analyze fetch --start 2025-08-26T23:00:00.000Z --end 2025-08-26T23:59:59.999Z --team <TEAM ID> --type json
```

Analyze
```bash
squadcast-analyze analyze --input data/raw/incidents_YYYYMMDDTHHMMSSZ.json --group-by environment --top 10 --csv-out data/processed/top10_environment.csv
```
