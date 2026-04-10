#!/usr/bin/env python3
"""
build_routes.py
---------------
Downloads Israel Ministry of Transport GTFS zip,
extracts routes + stops + stop_times,
and outputs routes.json for the BusNav app.

Output format:
{
  "updated": "2026-04-10",
  "routes": {
    "דן": {
      "79": {
        "name": "עיריית ת\"א / אבן גבירול ← אבן גבירול / בלוך",
        "stops": [
          {"n": "עיריית תל אביב / אבן גבירול", "la": 32.0673, "lo": 34.7813},
          ...
        ]
      }
    },
    "אגד": { ... }
  }
}
"""

import urllib.request
import zipfile
import io
import csv
import json
import datetime
import os
import sys

GTFS_URL = "ftp://gtfs.mot.gov.il/israel-public-transportation.zip"
# HTTP mirror (more reliable from GitHub Actions)
GTFS_HTTP = "https://gtfs.mot.gov.il/israel-public-transportation.zip"

# Operator code → Hebrew name mapping
AGENCY_MAP = {
    "3":  "אגד",
    "5":  "דן",
    "7":  "מטרופולין",
    "8":  "קווים",
    "16": "נת״ע",
    "18": "אפיקים",
    "25": "נתיב אקספרס",
    "31": "סופרבוס",
    "32": "אלקטרה אפיקים",
}

def download_gtfs():
    print("Downloading GTFS...", flush=True)
    try:
        req = urllib.request.Request(GTFS_HTTP, headers={"User-Agent": "BusNav/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        print(f"Downloaded {len(data)//1024//1024} MB", flush=True)
        return data
    except Exception as e:
        print(f"HTTP failed: {e}, trying FTP...", flush=True)
        with urllib.request.urlopen(GTFS_URL, timeout=120) as r:
            data = r.read()
        print(f"Downloaded {len(data)//1024//1024} MB via FTP", flush=True)
        return data

def read_csv_from_zip(zf, filename):
    """Read a CSV file from the zip, return list of dicts."""
    try:
        with zf.open(filename) as f:
            content = f.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))
            return list(reader)
    except KeyError:
        print(f"  Warning: {filename} not found in zip", flush=True)
        return []

def build_routes(gtfs_data):
    print("Parsing GTFS...", flush=True)
    zf = zipfile.ZipFile(io.BytesIO(gtfs_data))

    # 1. Read agencies
    agencies = {}
    for row in read_csv_from_zip(zf, "agency.txt"):
        aid = row.get("agency_id","").strip()
        name = row.get("agency_name","").strip()
        agencies[aid] = AGENCY_MAP.get(aid, name)
    print(f"  Agencies: {len(agencies)}", flush=True)

    # 2. Read stops
    stops_map = {}
    for row in read_csv_from_zip(zf, "stops.txt"):
        sid = row.get("stop_id","").strip()
        stops_map[sid] = {
            "n": row.get("stop_name","").strip(),
            "la": float(row.get("stop_lat",0)),
            "lo": float(row.get("stop_lon",0)),
        }
    print(f"  Stops: {len(stops_map)}", flush=True)

    # 3. Read routes
    routes_info = {}
    for row in read_csv_from_zip(zf, "routes.txt"):
        rid = row.get("route_id","").strip()
        routes_info[rid] = {
            "ref": row.get("route_short_name","").strip(),
            "name": row.get("route_long_name","").strip(),
            "agency": row.get("agency_id","").strip(),
        }
    print(f"  Routes: {len(routes_info)}", flush=True)

    # 4. Read trips — one representative trip per route
    trip_to_route = {}
    route_to_trip = {}  # route_id → first trip_id
    for row in read_csv_from_zip(zf, "trips.txt"):
        rid = row.get("route_id","").strip()
        tid = row.get("trip_id","").strip()
        trip_to_route[tid] = rid
        if rid not in route_to_trip:
            route_to_trip[rid] = tid
    print(f"  Trips: {len(trip_to_route)}", flush=True)

    # 5. Read stop_times — only for representative trips
    print("  Reading stop_times (this takes a while)...", flush=True)
    wanted_trips = set(route_to_trip.values())
    trip_stops = {}  # trip_id → ordered list of stop_ids

    for row in read_csv_from_zip(zf, "stop_times.txt"):
        tid = row.get("trip_id","").strip()
        if tid not in wanted_trips:
            continue
        sid = row.get("stop_id","").strip()
        seq = int(row.get("stop_sequence","0") or 0)
        if tid not in trip_stops:
            trip_stops[tid] = []
        trip_stops[tid].append((seq, sid))

    print(f"  Loaded stop_times for {len(trip_stops)} trips", flush=True)

    # 6. Build output structure
    output = {}  # agency_name → route_ref → {name, stops}

    for rid, rinfo in routes_info.items():
        ref = rinfo["ref"]
        if not ref:
            continue
        agency_id = rinfo["agency"]
        agency_name = agencies.get(agency_id, agency_id)
        tid = route_to_trip.get(rid)
        if not tid or tid not in trip_stops:
            continue

        # Sort stops by sequence
        sorted_stops = [s for _, s in sorted(trip_stops[tid])]
        # Remove consecutive duplicates
        deduped = []
        for s in sorted_stops:
            if not deduped or deduped[-1] != s:
                deduped.append(s)

        # Build stop objects
        stop_objs = []
        for sid in deduped:
            if sid in stops_map:
                stop_objs.append(stops_map[sid])

        if len(stop_objs) < 2:
            continue

        # Add to output
        if agency_name not in output:
            output[agency_name] = {}

        # If ref already exists, keep the one with more stops
        if ref in output[agency_name]:
            if len(stop_objs) > len(output[agency_name][ref]["stops"]):
                output[agency_name][ref] = {
                    "name": rinfo["name"],
                    "stops": stop_objs,
                }
        else:
            output[agency_name][ref] = {
                "name": rinfo["name"],
                "stops": stop_objs,
            }

    total = sum(len(v) for v in output.values())
    print(f"  Built {total} routes across {len(output)} operators", flush=True)
    return output

def main():
    gtfs_data = download_gtfs()
    routes = build_routes(gtfs_data)

    today = datetime.date.today().isoformat()
    result = {"updated": today, "routes": routes}

    out_path = os.path.join(os.path.dirname(__file__), "routes.json")
    print(f"Writing {out_path}...", flush=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"Done! routes.json = {size_mb:.1f} MB", flush=True)

if __name__ == "__main__":
    main()
