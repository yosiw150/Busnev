#!/usr/bin/env python3
“””
build_routes.py - Builds routes.json from OpenStreetMap Overpass API
Fetches all bus routes in Israel at once — no FTP/HTTPS blocking issues.
“””
import urllib.request
import urllib.parse
import json
import datetime
import os
import time

OVERPASS_URL = “https://overpass-api.de/api/interpreter”

# Operator name mapping

OPERATOR_MAP = {
“dan”: “דן”, “דן”: “דן”, “dan bus”: “דן”,
“egged”: “אגד”, “אגד”: “אגד”,
“metropoline”: “מטרופולין”, “מטרופולין”: “מטרופולין”,
“kavim”: “קווים”, “קווים”: “קווים”,
“nta”: “נת״ע”, “נת"ע”: “נת״ע”, “נתיב אקספרס”: “נתיב אקספרס”,
“afikim”: “אפיקים”, “אפיקים”: “אפיקים”,
“superbus”: “סופרבוס”, “סופרבוס”: “סופרבוס”,
“electra afikim”: “אפיקים”,
}

def normalize_operator(op):
if not op:
return “אחר”
op_lower = op.lower().strip()
for key, val in OPERATOR_MAP.items():
if key.lower() in op_lower:
return val
return op.strip()

def fetch_overpass(query):
data = urllib.parse.urlencode({“data”: query}).encode()
req = urllib.request.Request(OVERPASS_URL, data=data, method=“POST”)
req.add_header(“Content-Type”, “application/x-www-form-urlencoded”)
req.add_header(“User-Agent”, “BusNav/1.0”)
with urllib.request.urlopen(req, timeout=180) as r:
return json.loads(r.read().decode(“utf-8”))

def build_routes():
print(“Fetching all Israel bus routes from OSM…”, flush=True)

```
# Fetch all bus route relations in Israel bounding box
query = """
```

[out:json][timeout:120];
(
relation[“type”=“route”][“route”=“bus”](29.4,34.2,33.4,35.9);
);
out body;

> ;
> out skel qt;
> “””

```
print("  Querying Overpass API...", flush=True)
data = fetch_overpass(query)
print(f"  Got {len(data['elements'])} elements", flush=True)

# Build node map
node_map = {}
for el in data["elements"]:
    if el["type"] == "node":
        node_map[el["id"]] = el

# Process relations
relations = [el for el in data["elements"] if el["type"] == "relation"]
print(f"  Relations: {len(relations)}", flush=True)

output = {}
processed = 0

for rel in relations:
    tags = rel.get("tags", {})
    ref = tags.get("ref", "").strip()
    if not ref:
        continue
    
    # Get operator
    op_raw = tags.get("operator", tags.get("network", tags.get("operator:en", "")))
    operator = normalize_operator(op_raw)
    
    # Extract stops
    stops = []
    seen = set()
    for member in rel.get("members", []):
        if member["type"] != "node":
            continue
        role = member.get("role", "")
        if role not in ["stop", "stop_entry_only", "stop_exit_only", "platform", ""]:
            continue
        node = node_map.get(member["ref"])
        if not node:
            continue
        ntags = node.get("tags", {})
        name = ntags.get("name:he") or ntags.get("name") or f"תחנה {len(stops)+1}"
        lat = node.get("lat")
        lon = node.get("lon")
        if lat is None or lon is None:
            continue
        # Skip duplicates
        key = f"{lat:.4f},{lon:.4f}"
        if key in seen:
            continue
        seen.add(key)
        stops.append({"n": name, "la": lat, "lo": lon})
    
    if len(stops) < 2:
        continue
    
    # Store — keep version with most stops
    if operator not in output:
        output[operator] = {}
    
    route_name = tags.get("name", f"קו {ref}")
    if ref not in output[operator] or len(stops) > len(output[operator][ref]["stops"]):
        output[operator][ref] = {"name": route_name, "stops": stops}
    
    processed += 1

total = sum(len(v) for v in output.values())
print(f"  Processed {processed} relations → {total} unique routes across {len(output)} operators", flush=True)
return output
```

def main():
routes = build_routes()
result = {“updated”: datetime.date.today().isoformat(), “routes”: routes}
path = os.path.join(os.path.dirname(os.path.abspath(**file**)), “routes.json”)
with open(path, “w”, encoding=“utf-8”) as f:
json.dump(result, f, ensure_ascii=False, separators=(”,”, “:”))
size = os.path.getsize(path) / 1024 / 1024
print(f”Done! routes.json = {size:.1f} MB”, flush=True)

if **name** == “**main**”:
main()
