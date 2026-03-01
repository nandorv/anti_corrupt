"""Debug: test SPARQL queries to find the right QIDs for Brazilian politicians."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

SPARQL = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "AntiCorrupt/1.0 Python/httpx debug",
}

def run(label, sparql):
    r = httpx.get(SPARQL, params={"query": sparql, "format": "json"}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    bindings = r.json().get("results", {}).get("bindings", [])
    print(f"\n{'='*60}")
    print(f"  {label}: {len(bindings)} results")
    for b in bindings[:3]:
        label_val = b.get("personLabel") or b.get("itemLabel") or b.get("pLabel") or {}
        name = label_val.get("value", "?") if isinstance(label_val, dict) else "?"
        extra = b.get("posLabel", {}).get("value", "") or b.get("desc", {}).get("value", "")
        print(f"    {name}  {extra}")
    return bindings

# --- Test 1: occupational politician in Brazil
run("Occupation=politician in Brazil", """
SELECT DISTINCT ?person ?personLabel WHERE {
  ?person wdt:P27 wd:Q155 ;
          wdt:P106 wd:Q82955 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en" }
}
LIMIT 5
""")

# --- Test 2: P39 = Deputado Federal QID Q21609546
run("P39 = Q21609546 (Deputado Federal)", """
SELECT DISTINCT ?person ?personLabel WHERE {
  ?person p:P39 ?s .
  ?s ps:P39 wd:Q21609546 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en" }
}
LIMIT 5
""")

# --- Test 3: Check what Q21609546 even is
run("What is Q21609546?", """
SELECT ?itemLabel ?desc WHERE {
  BIND(wd:Q21609546 AS ?item)
  OPTIONAL { ?item schema:description ?desc FILTER(LANG(?desc)="pt") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en" }
}
LIMIT 3
""")

# --- Test 4: Search for the correct QID for "Deputado Federal"
run("Search position: Deputado Federal do Brasil", """
SELECT DISTINCT ?p ?pLabel ?desc WHERE {
  ?p wdt:P31 wd:Q4164871 .   # instance of: position
  ?p wdt:P17 wd:Q155 .        # country: Brazil
  OPTIONAL { ?p schema:description ?desc FILTER(LANG(?desc)="en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en" }
  FILTER(CONTAINS(LCASE(?pLabel), "deputado"))
}
LIMIT 10
""")

# --- Test 5: Senator QID Q18611017
run("What is Q18611017?", """
SELECT ?itemLabel ?desc WHERE {
  BIND(wd:Q18611017 AS ?item)
  OPTIONAL { ?item schema:description ?desc FILTER(LANG(?desc)="pt") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en" }
}
LIMIT 3
""")

# --- Test 6: Find people with P39 = Q23903549 (Senador Federal do Brasil - another possible QID)
run("P39 = Q23903549 (another senator QID?)", """
SELECT DISTINCT ?person ?personLabel WHERE {
  ?person p:P39 ?s .
  ?s ps:P39 wd:Q23903549 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en" }
}
LIMIT 5
""")
