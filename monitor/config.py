from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    kind: str
    url: str = ""
    host: str = ""
    port: int = 443
    timeout: float = 5
    expected_status: tuple[int, ...] = (200,)
    warn_days: int = 30
    ca_file: str | None = None

    @property
    def target(self):
        return self.url if self.kind == "http" else f"{self.host}:{self.port}"

    @property
    def key(self):
        # Uma mudança de alvo ou critério não reutiliza os resultados anteriores.
        spec = [self.id, self.kind, self.target, self.expected_status,
                self.warn_days, self.ca_file, self.timeout]
        return sha256(json.dumps(spec).encode()).hexdigest()


@dataclass(frozen=True)
class Config:
    interval_seconds: int
    retention_days: int
    services: tuple[Service, ...]


def number(value, low, high, field, integer=False):
    valid = type(value) is int if integer else type(value) in (int, float)
    if not valid or not low <= value <= high:
        raise ValueError(f"{field}: informe um número entre {low} e {high}.")
    return value


def load_config(path):
    path = Path(path)
    if path.stat().st_size > 128 * 1024:
        raise ValueError("Configuração excede 128 KiB.")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError("YAML inválido.") from exc
    if not isinstance(data, dict) or set(data) - {"interval_seconds", "retention_days", "services"}:
        raise ValueError("Use interval_seconds, retention_days e services na configuração.")
    interval = number(data.get("interval_seconds", 60), 10, 3600, "interval_seconds", True)
    retention = number(data.get("retention_days", 7), 1, 30, "retention_days", True)
    entries = data.get("services")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 50:
        raise ValueError("services deve conter de 1 a 50 serviços.")
    services, ids = [], set()
    common = {"id", "name", "type", "timeout_seconds"}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Cada serviço deve ser um objeto YAML.")
        kind = entry.get("type")
        if kind not in ("http", "tcp", "tls"):
            raise ValueError("type deve ser http, tcp ou tls.")
        allowed = common | ({"url", "expected_status"} if kind == "http" else {"host", "port"})
        if kind == "tls":
            allowed |= {"warn_days", "ca_file"}
        if set(entry) - allowed:
            raise ValueError("Campo desconhecido ou incompatível com o tipo de serviço.")
        sid = entry.get("id", "")
        if not isinstance(sid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", sid) or sid in ids:
            raise ValueError("id deve ser único, com até 48 letras minúsculas, números, _ ou -.")
        name = entry.get("name", sid)
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("name deve ter de 1 a 100 caracteres.")
        args = dict(id=sid, name=name.strip(), kind=kind,
                    timeout=number(entry.get("timeout_seconds", 5), .1, 30, "timeout_seconds"))
        if kind == "http":
            url = entry.get("url", "")
            try:
                parsed = urlsplit(url) if isinstance(url, str) else None
                if (not parsed or parsed.scheme not in ("http", "https") or not parsed.hostname
                        or parsed.username is not None or parsed.password is not None
                        or parsed.fragment or len(url) > 2048):
                    raise ValueError()
                _ = parsed.port
            except ValueError as exc:
                raise ValueError("url deve ser HTTP(S), sem credenciais ou fragmento.") from exc
            codes = entry.get("expected_status", [200])
            if not isinstance(codes, list) or not codes or len(codes) > 500:
                raise ValueError("expected_status deve ser uma lista de códigos HTTP.")
            for code in codes:
                number(code, 100, 599, "expected_status", True)
            args.update(url=url, expected_status=tuple(codes))
        else:
            host = entry.get("host", "")
            if not isinstance(host, str) or not host or len(host) > 253 or any(c.isspace() for c in host) or "/" in host:
                raise ValueError("host deve ser um hostname ou IP, sem protocolo ou caminho.")
            args.update(host=host, port=number(entry.get("port", 443), 1, 65535, "port", True))
            if kind == "tls":
                args["warn_days"] = number(entry.get("warn_days", 30), 0, 365, "warn_days", True)
                if entry.get("ca_file") is not None:
                    if not isinstance(entry["ca_file"], str) or not entry["ca_file"]:
                        raise ValueError("ca_file deve ser um caminho de arquivo.")
                    ca = (path.parent / entry["ca_file"]).resolve()
                    if not ca.is_file():
                        raise ValueError("Arquivo ca_file não encontrado.")
                    args["ca_file"] = str(ca)
        services.append(Service(**args)); ids.add(sid)
    return Config(interval, retention, tuple(services))
