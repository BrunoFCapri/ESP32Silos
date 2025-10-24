# ESP32Silos

Proyecto: lecturas de humedad con ESP32 y envío a Supabase. Incluye portal de configuración WiFi por AP y una API HTTP local para obtener la última lectura.

Contenido
- `codigo/` - código MicroPython que corre en el ESP32 (boot.py, main.py, wifi.txt)
- `web/` - página web estática de ejemplo que consulta Supabase para mostrar las lecturas
- `conexiones.txt` / `videoflashear.txt` - notas y procedimientos del hardware

Resumen
Este proyecto lee un sensor de humedad analógico conectado a un pin ADC del ESP32, mapea la lectura a porcentaje y envía el valor a Supabase (tabla `readings`). El ESP también expone una API local `/data` que devuelve la última lectura (útil para consultar directamente desde la red local).

Características principales
- Portal AP para configurar WiFi (al faltar credenciales en `wifi.txt`).
- Lecturas periódicas (configurable) y envío a Supabase vía REST.
- API HTTP simple en el ESP (`/data`).
- Ejemplo de página web que consulta Supabase y muestra las últimas lecturas.

Requisitos
- ESP32 con MicroPython instalado.
- Sensor de humedad analógico (conectado a un pin ADC, por ejemplo GPIO34).
- Cuenta de Supabase y una tabla llamada `readings` (esquema abajo).

Esquema recomendado en Supabase (SQL)
```sql
-- Extensión para generar UUID (opcional)
create extension if not exists "pgcrypto";

create table public.readings (
  id uuid default gen_random_uuid() primary key,
  moisture integer,
  inserted_at timestamptz default now()
);

-- Opcional: permitir inserciones anónimas si usas la anon key en la web
-- Ajusta políticas RLS según tu caso.
```

Configuración de `main.py` (MicroPython)
- `SUPABASE_URL` - URL de tu proyecto Supabase (sin slash final). Ejemplo: `https://abcd1234.supabase.co`
- `SUPABASE_KEY` - clave REST (service_role o anon dependiendo de permisos). Para el dispositivo usa la `service_role` o una clave con permisos de inserción; ten en cuenta la seguridad.
- `SUPABASE_TABLE` - nombre de la tabla (por defecto `readings`).
- `RAW_AIR` y `RAW_WATER` - calibración ADC (valores medidos en aire y en agua) para mapear 0..4095 a 0..100%.

En caso de no tener Micropython en tu ESP32
en el archivo videofashear.txt se en cuentra el link de un video en el cual te enseñan como hacerlo, luego de eso vas a tener que descargar algún editor a gusto, recomendamos Thony por su sencilles pero se puede usar desde el mismo vs code

Calibración
1. Con el sensor en aire (seco) anota el valor ADC (ej. 4095) y ponlo en `RAW_AIR`.
2. Con el sensor en agua (totalmente húmedo) anota el valor ADC (ej. 0) y ponlo en `RAW_WATER`.
3. Ajusta hasta que el porcentaje calculado sea coherente.

Cómo usar
1. Copia `codigo/main.py` y `codigo/boot.py` en el ESP32 (por ejemplo con ampy, rshell o la extensión de VSCode para MicroPython).
2. Edita `codigo/main.py` y completa `SUPABASE_URL` y `SUPABASE_KEY`.
3. Conecta el sensor al pin configurado (`MOISTURE_PIN`) y alimenta el ESP32.
4. Si no hay `wifi.txt` con credenciales, el ESP arrancará en modo AP llamado `ESP32-CONFIG` donde podrás escribir SSID y contraseña. Tras guardar, el dispositivo se reiniciará y se conectará en modo STA.
5. Verifica que las lecturas se envían a Supabase y/o consulta la API local `http://<IP_DEL_ESP>/data` para ver la última lectura.

Página web de la implementacion
En `web/index.html` hay un ejemplo de página estática que consulta la tabla `readings` en Supabase mediante su REST API. Edita las variables `SUPABASE_URL` y `ANON_KEY` dentro de ese archivo para que apunten a tu proyecto.


