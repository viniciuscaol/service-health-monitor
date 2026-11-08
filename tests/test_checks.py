import asyncio
from datetime import datetime, timedelta, timezone
import ssl

import pytest
import trustme

from monitor.checks import certificate_result, check
from monitor.config import Service


async def http_case(code=200, delay=0):
    async def reply(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            await asyncio.sleep(delay)
            writer.write(f"HTTP/1.1 {code} Test\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    server = await asyncio.start_server(reply, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        return await check(Service("web", "Web", "http", url=f"http://127.0.0.1:{port}/", timeout=.15 if delay else 2))


@pytest.mark.parametrize("code,status", [(200,"up"),(500,"down"),(302,"down")])
def test_http_status(code, status):
    result = asyncio.run(http_case(code))
    assert result.status == status
    assert result.http_status == code
    assert result.latency_ms >= 0 and result.checked_at > 0


def test_timeout():
    result = asyncio.run(http_case(delay=.4))
    assert result.status == "down" and result.message == "Tempo limite excedido."


def test_tcp_open_and_closed():
    async def run():
        async def reply(reader, writer):
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_server(reply,"127.0.0.1",0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            good = await check(Service("tcp","TCP","tcp",host="127.0.0.1",port=port))
        bad = await check(Service("tcp","TCP","tcp",host="127.0.0.1",port=port))
        return good, bad
    good,bad=asyncio.run(run())
    assert good.status == "up" and bad.status == "down"


@pytest.mark.parametrize("identity,trusted,days,status", [
    ("localhost",True,90,"up"), ("localhost",True,5,"warning"),
    ("wrong.example",True,90,"down"), ("localhost",False,90,"down"),
    ("localhost",True,-1,"down"),
])
def test_real_tls(tmp_path, identity, trusted, days, status):
    ca=trustme.CA()
    now=datetime.now(timezone.utc)
    cert=ca.issue_cert(identity, not_before=now-timedelta(days=10), not_after=now+timedelta(days=days))
    ca_file=tmp_path/"ca.pem"; ca.cert_pem.write_to_path(ca_file)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); cert.configure_cert(context)
    async def run():
        async def reply(reader, writer):
            writer.close()
            await writer.wait_closed()
        server=await asyncio.start_server(reply,"127.0.0.1",0,ssl=context)
        async with server:
            return await check(Service("tls","TLS","tls",host="localhost",
                port=server.sockets[0].getsockname()[1],ca_file=str(ca_file) if trusted else None))
    result=asyncio.run(run())
    assert result.status == status
    if status != "down":
        assert result.expires_at and result.days_remaining is not None


def test_certificate_boundary():
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    assert certificate_result({"notAfter":"Jan 31 00:00:00 2026 GMT"},30,now).status == "warning"
    assert certificate_result({"notAfter":"Jan  1 00:00:00 2026 GMT"},30,now).status == "down"
