from flask import Flask, render_template_string, jsonify
import requests, re, json, time, threading

app = Flask(__name__)

BASE = "https://czynaczas.pl"
SOCKET = f"{BASE}/socket.io/?EIO=4&transport=polling"
STOPS_URL = f"{BASE}/api/zielonagora/transport"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Origin": BASE,
    "Referer": BASE + "/zielonagora",
    "Accept": "*/*",
}

COOKIE = ""  # ← paste full cookie string from browser
if COOKIE:
    HEADERS["Cookie"] = COOKIE

latest_buses = {}
latest_stops = {}
last_update = 0


def fetch_buses_once():
    """Perform Socket.IO handshake and fetch current buses"""
    try:
        r = requests.get(SOCKET, headers=HEADERS, timeout=6)
        sid_match = re.search(r'"sid":"([^"]+)"', r.text)
        if not sid_match:
            return {}
        sid = sid_match.group(1)
        url = f"{SOCKET}&sid={sid}"
        # join Zielona Góra namespace
        requests.post(url, headers=HEADERS, data='40/zielonagora,{}', timeout=6)
        time.sleep(1)
        r = requests.get(url, headers=HEADERS, timeout=6)
        if "42/zielonagora" not in r.text:
            return {}
        payload = r.text.split("42/zielonagora,")[1]
        data = json.loads(payload)
        return data[1].get("data", {})
    except Exception as e:
        print("bus fetch error:", e)
        return {}


def fetch_stops():
    """Fetch all stop coordinates from REST API"""
    try:
        r = requests.get(STOPS_URL, headers=HEADERS, timeout=6)
        r.raise_for_status()
        data = r.json()
        stops = data.get("stops", [])
        result = []
        for s in stops:
            # format: [id, name, lat, lon]
            if len(s) >= 4:
                result.append({"id": s[0], "name": s[1], "lat": s[2], "lon": s[3]})
        return result
    except Exception as e:
        print("stop fetch error:", e)
        return []


def updater():
    global latest_buses, latest_stops, last_update
    while True:
        buses = fetch_buses_once()
        stops = fetch_stops()
        if buses:
            latest_buses = buses
            last_update = time.time()
            print(f"✅ {len(buses)} buses")
        if stops:
            latest_stops = stops
        time.sleep(10)  # refresh every 10 s


@app.route("/")
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>Zielona Góra — Real-Time Bus Tracker</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <link rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <style>
        html,body,#map{height:100%;margin:0;}
        .bus-label {
          background: rgba(255,255,255,0.8);
          border-radius: 4px;
          padding: 2px 4px;
          font-size: 12px;
          font-weight: bold;
          color: #000;
          border: 1px solid #333;
        }
      </style>
    </head>
    <body>
      <div id="map"></div>
      <script>
        const map = L.map('map').setView([51.94,15.50],13);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          attribution: '&copy; OpenStreetMap'
        }).addTo(map);

        let busMarkers = {}, stopMarkers = [];

        async function update() {
          const [busRes, stopRes] = await Promise.all([
            fetch('/api/buses'), fetch('/api/stops')
          ]);
          const buses = await busRes.json();
          const stops = await stopRes.json();

          // draw stops once
          if (stopMarkers.length === 0 && stops.length) {
            for (const s of stops) {
              const m = L.circleMarker([s.lat, s.lon], {
                radius: 4, color: '#0078ff', fillColor:'#00aaff', fillOpacity:0.7
              }).bindPopup("Stop: " + s.name);
              m.addTo(map);
              stopMarkers.push(m);
            }
          }

          // draw / update buses
          for (const [id, b] of Object.entries(buses)) {
            if (!b.lat || !b.lon) continue;
            const label = b.route_id || '?';
            const icon = L.divIcon({
              className: 'bus-label',
              html: label,
              iconSize: [30,20]
            });
            if (!busMarkers[id]) {
              busMarkers[id] = L.marker([b.lat,b.lon], {icon})
                .addTo(map)
                .bindPopup("Bus " + b.vehicleNo + "<br>Route " + label);
            } else {
              busMarkers[id].setLatLng([b.lat,b.lon]);
            }
          }
        }

        update();
        setInterval(update, 10000);
      </script>
    </body>
    </html>
    """
    return render_template_string(html)


@app.route("/api/buses")
def api_buses():
    return jsonify(latest_buses)


@app.route("/api/stops")
def api_stops():
    return jsonify(latest_stops)


if __name__ == "__main__":
    threading.Thread(target=updater, daemon=True).start()
    print("🌐 Running on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000)
