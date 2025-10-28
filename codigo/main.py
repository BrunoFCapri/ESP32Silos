import network
import socket
import machine
import time
import ujson
import ubinascii
import urequests
from time import sleep, ticks_ms, ticks_diff
from secrets import SUPABASE_URL, SUPABASE_KEY, SUPABASE_TABLE

# ===== CONFIG =====
LED_PIN = 2
MOISTURE_PIN = 34  # Pin ADC (ej. GPIO34)
READING_FREQUENCY_MS = 5 * 1000  # 5 segundos
WIFI_FILE = "wifi.txt"

# Supabase (importado desde secrets.py)
# Supabase (rellena con tus valores)
SUPABASE_URL = "xxxx"  # sin slash final
SUPABASE_KEY = "xxx"
SUPABASE_INSERT_URL = SUPABASE_URL + "/rest/v1/" + SUPABASE_TABLE


# Calibración del sensor de humedad (ADC 0..4095)
RAW_AIR = 4095   # valor medido en aire/seco
RAW_WATER = 0    # valor medido en agua/totalmente húmedo
# ==================

led = machine.Pin(LED_PIN, machine.Pin.OUT)

# Configurar ADC
adc = machine.ADC(machine.Pin(MOISTURE_PIN))
adc.atten(machine.ADC.ATTN_11DB)  # rango 0-3.3V
adc.width(machine.ADC.WIDTH_12BIT)  # 0-4095

last_reading_time = 0
last_moisture = None
last_raw = None

def read_saved_wifi():
    try:
        with open(WIFI_FILE, "r") as f:
            lines = f.read().splitlines()
            if len(lines) >= 2:
                ssid = lines[0].strip()
                pwd = lines[1].strip()
                return ssid, pwd
    except Exception:
        pass
    return None, None

def save_wifi(ssid, pwd):
    try:
        with open(WIFI_FILE, "w") as f:
            f.write(ssid + "\n")
            f.write(pwd + "\n")
        return True
    except Exception as e:
        print("Error guardando wifi:", e)
        return False

def connect_sta(ssid, pwd, timeout_s=15):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print("Ya conectado:", wlan.ifconfig())
        return True
    print("Conectando a WiFi:", ssid)
    wlan.connect(ssid, pwd)
    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout_s:
            print("Timeout al conectar WiFi")
            return False
        time.sleep(0.5)
    print("Conectado. IP:", wlan.ifconfig()[0])
    return True

def url_decode(s):
    # decodifica %20 y + para espacios y hex %XX
    res = ""
    i = 0
    while i < len(s):
        c = s[i]
        if c == "+":
            res += " "
        elif c == "%":
            try:
                hexv = s[i+1:i+3]
                res += chr(int(hexv, 16))
                i += 2
            except:
                res += "%"
        else:
            res += c
        i += 1
    return res

def parse_query(qs):
    params = {}
    if not qs:
        return params
    parts = qs.split("&")
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k] = url_decode(v)
        else:
            params[p] = ""
    return params

def do_ap_mode():
    """Configura el ESP32 como AP y sirve el portal de configuración."""
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid='ESP32-CONFIG', password='micropython')
    print('Punto de acceso activado. Conectate a "ESP32-CONFIG"')
    print('Dirección IP del AP:', ap.ifconfig()[0])

    web_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    web_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    web_server.bind(('', 80))
    web_server.listen(5)
    html = """\
HTTP/1.1 200 OK
Content-Type: text/html

<!doctype html>
<html>
    <head><meta charset="utf-8"><title>Configuración WiFi</title>
    <style>
      body { font-family: sans-serif; background:#f0f2f5; }
      .card { max-width:400px;margin:40px auto;padding:20px;background:white;border-radius:8px;box-shadow:0 4px 8px rgba(0,0,0,.1); }
      input { width:100%; padding:10px;margin:8px 0;border:1px solid #ccc;border-radius:6px; }
      button { width:100%; padding:10px;background:#007bff;color:white;border:none;border-radius:6px; }
    </style>
    </head>
    <body><div class="card">
    <h3>Configurar WiFi</h3>
    <form action="/config" method="get">
      <input name="ssid" placeholder="SSID"><br>
      <input name="password" placeholder="Password" type="password"><br>
      <button type="submit">Guardar y reiniciar</button>
    </form>
    </div></body></html>
"""

    while True:
        try:
            conn, addr = web_server.accept()
            request = conn.recv(2048)
            if not request:
                conn.close()
                continue
            req_str = request.decode('utf-8', 'ignore')
            # obtener la ruta (entre 'GET ' y ' HTTP/')
            first_line = req_str.split("\n")[0]
            parts = first_line.split(" ")
            path = ""
            if len(parts) >= 2:
                path = parts[1]
            print("Req from", addr, "->", path)
            if path.startswith("/config"):
                # puede venir como /config?ssid=...&password=...
                q = ""
                if "?" in path:
                    q = path.split("?", 1)[1]
                params = parse_query(q)
                ssid = params.get("ssid", "").strip()
                pwd = params.get("password", "").strip()
                if ssid:
                    save_wifi(ssid, pwd)
                    resp = "HTTP/1.1 200 OK\nContent-Type: text/html\n\n<h2>Credenciales guardadas. Reiniciando...</h2>"
                    conn.send(resp.encode())
                    conn.close()
                    time.sleep(2)
                    machine.reset()
                else:
                    conn.send(html.encode())
                    conn.close()
            else:
                conn.send(html.encode())
                conn.close()
        except Exception as e:
            # errores de socket o decodificación
            print("Error en portal AP:", e)
            try:
                conn.close()
            except:
                pass

def map_constrained(val, in_max, in_min, out_min=0, out_max=100):
    # Mapea val entre in_min..in_max a out_min..out_max con límite
    if in_max == in_min:
        return 0
    # Si la calibración está invertida (RAW_AIR > RAW_WATER) funcionará
    mapped = (val - in_min) * (out_max - out_min) // (in_max - in_min) + out_min
    if mapped < out_min:
        mapped = out_min
    if mapped > out_max:
        mapped = out_max
    return int(mapped)

def read_moisture():
    raw = adc.read()  # 0..4095 en ESP32
    # Invertimos el mapeo para que 0% = seco (aire) y 100% = mojado (agua)
    percent = map_constrained(raw, RAW_WATER, RAW_AIR, 0, 100)
    return percent, raw

def send_to_supabase(moisture_pct, raw):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json",
        # Usar "minimal" evita requerir permiso SELECT en RLS y ahorra ancho de banda
        "Prefer": "return=minimal"
    }
    # Solo enviamos el porcentaje de humedad
    payload = {"moisture": moisture_pct}
    body = ujson.dumps(payload)
    try:
        print("POST ->", SUPABASE_INSERT_URL)
        r = urequests.post(SUPABASE_INSERT_URL, headers=headers, data=body, timeout=10)
        print("HTTP", r.status_code)
        try:
            print("Resp:", r.text)
        except:
            pass
        r.close()
        return r.status_code
    except Exception as e:
        print("Error enviando a Supabase:", e)
        return None

def start_api_server():
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    s.setblocking(False)
    return s

def handle_api_requests(server_socket):
    global last_moisture, last_raw
    try:
        conn, addr = server_socket.accept()
        req = conn.recv(1024)
        if not req:
            conn.close()
            return
        req_str = req.decode('utf-8', 'ignore')
        first_line = req_str.split("\n")[0]
        parts = first_line.split(" ")
        path = ""
        if len(parts) >= 2:
            path = parts[1]
        if path.startswith("/data"):
            resp_obj = {"moisture": last_moisture, "raw": last_raw}
            resp_json = ujson.dumps(resp_obj)
            conn.send(b'HTTP/1.1 200 OK\nContent-Type: application/json\n\n')
            conn.send(resp_json.encode())
        else:
            conn.send(b'HTTP/1.1 404 Not Found\nContent-Type: text/plain\n\nNot Found')
        conn.close()
    except OSError:
        # no hay conexión pendiente
        pass
    except Exception as e:
        print("Error manejando petición API:", e)

# ---------- MAIN ----------
if __name__ == "__main__":
    ssid, pwd = read_saved_wifi()
    if ssid:
        ok = connect_sta(ssid, pwd, timeout_s=12)
        if not ok:
            print("No se pudo conectar con credenciales guardadas, arrancando AP para configuración.")
            do_ap_mode()
    else:
        print("No hay credenciales guardadas, arrancando AP para configuración.")
        do_ap_mode()

    # Si llegamos aquí, estamos conectados en modo STA
    api_server = start_api_server()
    print("API lista. /data mostrará la última lectura.")

    while True:
        try:
            now = ticks_ms()
            if ticks_diff(now, last_reading_time) >= READING_FREQUENCY_MS:
                moisture, raw = read_moisture()
                last_moisture = moisture
                last_raw = raw
                # Log simplificado para reflejar que solo enviamos humedad
                print("Lectura -> Moisture:", moisture, "%")
                led.value(1)
                status = send_to_supabase(moisture, raw)
                led.value(0)
                if status is None:
                    # opcional: aquí podrías almacenar localmente en un archivo para reenviar luego
                    print("Fallo al enviar. Considera almacenar localmente para reintento.")
                last_reading_time = now

            # atender peticiones API no bloqueante
            handle_api_requests(api_server)
            sleep(0.1)
        except Exception as e:
            print("Error en loop principal:", e)
            sleep(1)

