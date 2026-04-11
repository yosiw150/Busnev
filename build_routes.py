#!/usr/bin/env python3
"""
build_routes.py - Downloads Israel GTFS and builds routes.json
"""
import ftplib
import urllib.request
import zipfile
import io
import csv
import json
import datetime
import os

FTP_HOST = "gtfs.mot.gov.il"
FTP_FILE = "israel-public-transportation.zip"

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
    print("Trying FTP download...", flush=True)
    try:
        buf = io.BytesIO()
        with ftplib.FTP(FTP_HOST, timeout=120) as ftp:
            ftp.login()
            size = ftp.size(FTP_FILE)
            print(f"File size: {size//1024//1024} MB", flush=True)
            ftp.retrbinary(f"RETR {FTP_FILE}", buf.write)
        data = buf.getvalue()
        print(f"Downloaded {len(data)//1024//1024} MB via FTP", flush=True)
        return data
    except Exception as e:
        print(f"FTP failed: {e}", flush=True)

    print("Trying HTTP download...", flush=True)
    for url in [
        f"https://{FTP_HOST}/{FTP_FILE}",
        f"http://{FTP_HOST}/{FTP_FILE}",
        f"http://199.203.58.18/{FTP_FILE}",
    ]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BusNav/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            print(f"Downloaded {len(data)//1024//1024} MB from {url}", flush=True)
            return data
        except Exception as e:
            print(f"  {url}: {e}", flush=True)

    raise Exception("All download methods failed")

def read_csv(zf, name):
    try:
        with zf.open(name) as f:
            return list(csv.DictReader(io.StringIO(f.read().decode("utf-8-sig"))))
    except Exception as e:
        print(f"  Warning: {name}: {e}", flush=True)
        return []

def build_routes(data):
    print("Parsing GTFS...", flush=True)
    zf = zipfile.ZipFile(io.BytesIO(data))

    agencies = {r["agency_id"].strip(): AGENCY_MAP.get(r["agency_id"].strip(), r["agency_name"].strip())
                for r in read_csv(zf, "agency.txt")}
    print(f"  Agencies: {len(agencies)}", flush=True)

    stops_map = {r["stop_id"].strip(): {
        "n": r["stop_name"].strip(),
        "la": float(r["stop_lat"]),
        "lo": float(r["stop_lon"])
    } for r in read_csv(zf, "stops.txt")}
    print(f"  Stops: {len(stops_map)}", flush=True)

    routes_info = {r["route_id"].strip(): {
        "ref": r["route_short_name"].strip(),
        "name": r["route_long_name"].strip(),
        "agency": r["agency_id"].strip()
    } for r in read_csv(zf, "routes.txt")}
    print(f"  Routes: {len(routes_info)}", flush=True)

    route_to_trip = {}
    for r in read_csv(zf, "trips.txt"):
        rid = r["route_id"].strip()
        if rid not in route_to_trip:
            route_to_trip[rid] = r["trip_id"].strip()

    wanted = set(route_to_trip.values())
    print(f"  Reading stop_times for {len(wanted)} trips...", flush=True)
    trip_stops = {}
    for r in read_csv(zf, "stop_times.txt"):
        tid = r["trip_id"].strip()
        if tid not in wanted:
            continue
        if tid not in trip_stops:
            trip_stops[tid] = []
        trip_stops[tid].append((int(r.get("stop_sequence", 0) or 0), r["stop_id"].strip()))

    output = {}
    for rid, rinfo in routes_info.items():
        ref = rinfo["ref"]
        if not ref:
            continue
        aid = rinfo["agency"]
        aname = agencies.get(aid, aid)
        tid = route_to_trip.get(rid)
        if not tid or tid not in trip_stops:
            continue
        deduped = []
        for _, sid in sorted(trip_stops[tid]):
            if not deduped or deduped[-1] != sid:
                deduped.append(sid)
        stop_objs = [stops_map[s] for s in deduped if s in stops_map]
        if len(stop_objs) < 2:
            continue
        if aname not in output:
            output[aname] = {}
        if ref not in output[aname] or len(stop_objs) > len(output[aname][ref]["stops"]):
            output[aname][ref] = {"name": rinfo["name"], "stops": stop_objs}

    total = sum(len(v) for v in output.values())
    print(f"  Built {total} routes across {len(output)} operators", flush=True)
    return output

def main():
    data = download_gtfs()
    routes = build_routes(data)
    result = {"updated": datetime.date.today().isoformat(), "routes": routes}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routes.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Done! routes.json = {os.path.getsize(path)//1024//1024} MB", flush=True)

if __name__ == "__main__":
    main()
