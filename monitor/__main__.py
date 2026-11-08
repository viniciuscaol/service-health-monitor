import argparse
import asyncio
import json
import sqlite3
import sys

from .checks import check_all
from .config import load_config
from .storage import Store


def main():
    parser = argparse.ArgumentParser(description="Verifica serviços e grava uma rodada no histórico.")
    parser.add_argument("--config", default="config/services.yml")
    parser.add_argument("--db", default="data/monitor.db")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        results = asyncio.run(check_all(config.services))
        Store(args.db).save_round(results, config.retention_days)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"Configuração ou armazenamento inválido: {exc}", file=sys.stderr)
        return 2
    print(json.dumps([dict(id=s.id, name=s.name, **r.as_dict()) for s, r in results], ensure_ascii=False, indent=2))
    return 1 if any(r.status == "down" for _, r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
