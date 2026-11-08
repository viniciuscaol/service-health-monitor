"""Teste HTTP de ponta a ponta da demonstração Docker; só usa a biblioteca padrão."""
import json
import time
import urllib.request

base="http://127.0.0.1:8000"
for attempt in range(60):
    try:
        with urllib.request.urlopen(base+"/api/snapshot",timeout=3) as response:
            snapshot=json.load(response)
        rows={s["id"]:s for s in snapshot["services"]}
        expected={"demo-http":"up","demo-tcp":"up","demo-down":"down"}
        if snapshot["collector_running"] and all(rows[k]["latest"] and rows[k]["latest"]["status"]==v for k,v in expected.items()):
            break
    except (OSError,ValueError):
        pass
    time.sleep(.5)
else:
    raise SystemExit("A demonstração não retornou os estados esperados.")
with urllib.request.urlopen(base+"/",timeout=3) as response:
    assert b"Service Health Monitor" in response.read()
with urllib.request.urlopen(base+"/health",timeout=3) as response:
    assert json.load(response)["status"]=="ok"
print("Demonstração aprovada: HTTP e TCP disponíveis; porta fechada identificada; histórico registrado.")
