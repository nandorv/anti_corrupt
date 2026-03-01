import urllib.request

urls = [
    ("1-JSON-leg57", "https://dadosabertos.camara.leg.br/arquivos/secretarios/json/secretarios-legislatura57.json"),
    ("2-CSV-leg57",  "https://dadosabertos.camara.leg.br/arquivos/secretarios/csv/secretarios-legislatura57.csv"),
    ("3-dir",        "https://dadosabertos.camara.leg.br/arquivos/secretarios/"),
    ("4-API-v2",     "https://dadosabertos.camara.leg.br/api/v2/secretarios"),
    ("5-deputy",     "https://dadosabertos.camara.leg.br/api/v2/deputados/220593/secretarios"),
    ("6-leg56-json", "https://dadosabertos.camara.leg.br/arquivos/secretarios/json/secretarios-legislatura56.json"),
    ("7-no-num-json","https://dadosabertos.camara.leg.br/arquivos/secretarios/secretarios.json"),
    ("8-no-num-csv", "https://dadosabertos.camara.leg.br/arquivos/secretarios/secretarios.csv"),
]

for label, url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            status = r.status
            ct = r.headers.get("Content-Type", "?")
            body = r.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        ct = e.headers.get("Content-Type", "?")
        try:
            body = e.read(200).decode("utf-8", "replace")
        except Exception:
            body = "(unreadable)"
    except Exception as e:
        status = "ERR"
        ct = "?"
        body = str(e)
    print(f"=== {label} ===")
    print(f"  Status: {status}  CT: {ct}")
    print(f"  Body[:250]: {body[:250]!r}")
    print()
