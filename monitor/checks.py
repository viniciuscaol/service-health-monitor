import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
import ssl
import time

import httpx

from .config import Service


@dataclass
class Result:
    status: str
    message: str
    checked_at: float = 0
    latency_ms: float = 0
    http_status: int | None = None
    expires_at: str | None = None
    days_remaining: int | None = None

    def as_dict(self):
        return asdict(self)


def certificate_result(cert, warn_days, now=None):
    now = now or datetime.now(timezone.utc)
    expiry = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), timezone.utc)
    seconds = (expiry - now).total_seconds()
    days = math.floor(seconds / 86400)
    if seconds <= 0:
        status, message = "down", "Certificado expirado."
    elif seconds <= warn_days * 86400:
        status, message = "warning", "Certificado próximo do vencimento."
    else:
        status, message = "up", "Certificado válido e hostname verificado."
    return Result(status, message, expires_at=expiry.isoformat(), days_remaining=days)


async def probe(service: Service):
    if service.kind == "http":
        async with httpx.AsyncClient(timeout=service.timeout, follow_redirects=False, trust_env=False) as client:
            # Não baixa o corpo, que pode ser grande ou conter dados internos.
            async with client.stream("GET", service.url, headers={"User-Agent": "ServiceHealthMonitor/0.1"}) as response:
                okay = response.status_code in service.expected_status
                return Result("up" if okay else "down",
                              "Status HTTP esperado." if okay else "Status HTTP diferente do esperado.",
                              http_status=response.status_code)
    kwargs = {}
    if service.kind == "tls":
        kwargs = dict(ssl=ssl.create_default_context(cafile=service.ca_file),
                      server_hostname=service.host,
                      ssl_handshake_timeout=service.timeout, ssl_shutdown_timeout=.2)
    _, writer = await asyncio.open_connection(service.host, service.port, **kwargs)
    try:
        if service.kind == "tls":
            cert = writer.get_extra_info("ssl_object").getpeercert()
            return certificate_result(cert, service.warn_days)
        return Result("up", "Conexão TCP estabelecida.")
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), .3)
        except (OSError, asyncio.TimeoutError):
            pass


async def check(service):
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(probe(service), service.timeout)
    except (asyncio.TimeoutError, httpx.TimeoutException):
        result = Result("down", "Tempo limite excedido.")
    except (ssl.SSLError, httpx.RequestError, OSError):
        # Não registra a URL completa ou conteúdo de exceções com dados sensíveis.
        result = Result("down", "Falha de conexão ou validação TLS.")
    result.checked_at = time.time()
    result.latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return result


async def check_all(services):
    semaphore = asyncio.Semaphore(5)

    async def bounded(service):
        async with semaphore:
            return service, await check(service)

    return await asyncio.gather(*(bounded(service) for service in services))
