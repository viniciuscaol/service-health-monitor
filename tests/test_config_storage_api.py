import asyncio
from dataclasses import replace
import time

from fastapi.testclient import TestClient
import pytest
import yaml

from monitor.checks import Result
from monitor.config import Service, load_config
from monitor.main import create_app
from monitor.storage import Store


def write_config(tmp_path, data):
    path=tmp_path/"services.yml"; path.write_text(yaml.safe_dump(data))
    return path


@pytest.mark.parametrize("data", [
    None, [], {"services":[]}, {"services":[{"id":"a","type":"ping"}]},
    {"services":[{"id":"a","type":"http","url":"file:///etc/passwd"}]},
    {"services":[{"id":"a","type":"http","url":"http://user:pass@localhost"}]},
    {"services":[{"id":"a","type":"http","url":"http://localhost:bad"}]},
    {"services":[{"id":"a","type":"http","url":"http://localhost","expected_status":[True]}]},
    {"services":[{"id":"a","type":"tcp","host":"localhost","port":0}]},
    {"services":[{"id":"a","type":"tcp","host":"localhost","timeout_seconds":float("nan")}]},
    {"services":[{"id":"a","type":"tcp","host":"localhost","port":True}]},
    {"interval_seconds":True,"services":[{"id":"a","type":"tcp","host":"localhost"}]},
    {"services":[{"id":"a","type":"tcp","host":"localhost","typo":1}]},
    {"services":[{"id":"same","type":"tcp","host":"localhost"}]*2},
    {"services":[{"id":"a","type":"tls","host":"localhost","ca_file":"absent.pem"}]},
])
def test_invalid_config(tmp_path,data):
    with pytest.raises(ValueError): load_config(write_config(tmp_path,data))


def test_yaml_error(tmp_path):
    path=tmp_path/"bad.yml"; path.write_text("services: [")
    with pytest.raises(ValueError, match="YAML inválido"): load_config(path)


def test_store_persistence_and_changed_target(tmp_path):
    path=tmp_path/"monitor.db"; service=Service("tcp","TCP","tcp",host="localhost")
    store=Store(path)
    assert store.snapshot([service])[0]["latest"] is None
    store.save_round([(service,Result("up","conectado",time.time(),2.3))],7)
    reopened=Store(path)
    assert reopened.snapshot([service])[0]["latest"]["latency_ms"] == 2.3
    assert reopened.snapshot([replace(service,port=8443)])[0]["latest"] is None


def test_retention_and_history_limit(tmp_path):
    service=Service("tcp","TCP","tcp",host="localhost")
    store=Store(tmp_path/"db.sqlite")
    store.save_round([(service,Result("up","antigo",time.time()-86400*8))],7)
    assert store.snapshot([service])[0]["history"] == []
    store.save_round([(service,Result("up",str(i),time.time())) for i in range(60)],7)
    history=store.snapshot([service])[0]["history"]
    assert len(history)==50 and history[0]["message"]=="59" and history[-1]["message"]=="10"


def test_api_initial_history_and_health(tmp_path):
    path=write_config(tmp_path,{"services":[{"id":"test","name":"<script>test</script>","type":"tcp","host":"localhost"}]})
    app=create_app(path,tmp_path/"db.sqlite",start_collector=False)
    with TestClient(app) as client:
        assert client.get("/").status_code==200
        assert client.get("/static/app.js").status_code==200
        response=client.get("/api/snapshot")
        assert response.headers["cache-control"]=="no-store"
        assert response.json()["services"][0]["latest"] is None
        # Uma coleta parada nunca recebe um health check saudável.
        assert client.get("/health").status_code==503
        app.state.store.save_round([(app.state.config.services[0],Result("down","porta fechada",time.time()))],7)
        assert client.get("/api/snapshot").json()["services"][0]["latest"]["status"]=="down"


def test_collector_records_real_http(tmp_path):
    # Servidor HTTP real para exercitar o ciclo de vida do coletor.
    import http.server
    import threading
    handler=lambda *args: http.server.SimpleHTTPRequestHandler(*args,directory=str(tmp_path))
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        path=write_config(tmp_path,{"services":[{"id":"local","type":"http","url":f"http://127.0.0.1:{server.server_port}/"}]})
        app=create_app(path,tmp_path/"db.sqlite")
        with TestClient(app) as client:
            for _ in range(100):
                item=client.get("/api/snapshot").json()["services"][0]
                if item["latest"]: break
                time.sleep(.02)
            assert item["latest"]["status"]=="up"
            assert client.get("/health").status_code==200
    finally:
        server.shutdown(); server.server_close(); thread.join()
