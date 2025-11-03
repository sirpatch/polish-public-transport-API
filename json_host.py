from flask import Flask, jsonify
import requests, re, json, time, threading

app = Flask(__name__)

BASE = "https://czynaczas.pl"
SOCKET = f"{BASE}/socket.io/?EIO=4&transport=polling"

cities = [
    {"name": "zielonagora", "stops_url": f"{BASE}/api/zielonagora/transport", "socket_ns": "zielonagora"},
    {"name": "wroclaw", "stops_url": f"{BASE}/api/wroclaw/transport", "socket_ns": "wroclaw"},
    {"name": "warsaw", "stops_url": f"{BASE}/api/warsaw/transport", "socket_ns": "warsaw"},
    {"name": "poznan", "stops_url": f"{BASE}/api/poznan/transport", "socket_ns": "poznan"},
    {"name": "kielce", "stops_url": f"{BASE}/api/kielce/transport", "socket_ns": "kielce"},
    {"name": "krakow", "stops_url": f"{BASE}/api/krakow/transport", "socket_ns": "krakow"},
    {"name": "leszno", "stops_url": f"{BASE}/api/leszno/transport", "socket_ns": "leszno"},
    {"name": "lodz", "stops_url": f"{BASE}/api/lodz/transport", "socket_ns": "lodz"},
    {"name": "gzm", "stops_url": f"{BASE}/api/gzm/transport", "socket_ns": "gzm"},
    {"name": "rzeszow", "stops_url": f"{BASE}/api/rzeszow/transport", "socket_ns": "rzeszow"},
    {"name": "slupsk", "stops_url": f"{BASE}/api/slupsk/transport", "socket_ns": "slupsk"},
    {"name": "swinoujscie", "stops_url": f"{BASE}/api/swinoujscie/transport", "socket_ns": "swinoujscie"},
    {"name": "szczecin", "stops_url": f"{BASE}/api/szczecin/transport", "socket_ns": "szczecin"},
    {"name": "trojmiasto", "stops_url": f"{BASE}/api/trojmiasto/transport", "socket_ns": "trojmiasto"},
]

COOKIE = ""
latest_buses = {}
latest_stops = {}
lock = threading.Lock()


# ---------- Fetching ----------
def fetch_buses_once(city):
    headers = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Referer": f"{BASE}/{city['name']}", "Accept": "*/*"}
    if COOKIE: headers["Cookie"] = COOKIE
    try:
        r = requests.get(SOCKET, headers=headers, timeout=6)
        sid_match = re.search(r'"sid":"([^"]+)"', r.text)
        if not sid_match: return {}
        sid = sid_match.group(1)
        url = f"{SOCKET}&sid={sid}"
        requests.post(url, headers=headers, data=f'40/{city["socket_ns"]},{{}}', timeout=6)
        time.sleep(1)
        r = requests.get(url, headers=headers, timeout=6)
        if f"42/{city['socket_ns']}" not in r.text: return {}
        payload = r.text.split(f"42/{city['socket_ns']},")[1]
        data = json.loads(payload)
        return data[1].get("data", {})
    except Exception as e:
        print(f"[{city['name']}] bus fetch error:", e)
        return {}


def fetch_stops(city):
    headers = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Referer": f"{BASE}/{city['name']}", "Accept": "*/*"}
    if COOKIE: headers["Cookie"] = COOKIE
    try:
        r = requests.get(city["stops_url"], headers=headers, timeout=6)
        r.raise_for_status()
        data = r.json()
        stops = data.get("stops", [])
        result = []
        for s in stops:
            if len(s) >= 4:
                result.append({
                    "id": s[0],
                    "name": s[1],
                    "lat": s[2],
                    "lon": s[3],
                    "stop_name": f"{s[1]} - {s[0]}",
                    "trip_headsign": s[4] if len(s) > 4 else ""
                })
        return result
    except Exception as e:
        print(f"[{city['name']}] stop fetch error:", e)
        return []


# ---------- Background thread ----------
def updater():
    while True:
        for city in cities:
            buses = fetch_buses_once(city)
            stops = fetch_stops(city)
            with lock:
                if buses: latest_buses[city["name"]] = buses
                if stops: latest_stops[city["name"]] = stops
        time.sleep(10)


# ---------- JSON endpoints ----------
@app.route("/busproject/<city>_bus_data.json")
def get_city_buses(city):
    if city not in [c["name"] for c in cities]:
        return jsonify({"error": "unknown city"}), 404
    with lock:
        return jsonify({city: latest_buses.get(city, {})})


@app.route("/busproject/<city>_stop.json")
def get_city_stops(city):
    if city not in [c["name"] for c in cities]:
        return jsonify({"error": "unknown city"}), 404
    with lock:
        return jsonify({city: latest_stops.get(city, [])})


# ---------- Start ----------
if __name__ == "__main__":
    threading.Thread(target=updater, daemon=True).start()
    print("🌍 JSON server running on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
