import os
import secrets
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

app = FastAPI()
security = HTTPBasic()


def verificar_admin(credenciales: HTTPBasicCredentials = Depends(security)):
    usuario_configurado = os.getenv("ADMIN_USERNAME")
    clave_configurada = os.getenv("ADMIN_PASSWORD")
    if not usuario_configurado or not clave_configurada:
        raise HTTPException(
            status_code=503,
            detail="Configura ADMIN_USERNAME y ADMIN_PASSWORD para habilitar la administración.",
        )

    usuario_valido = secrets.compare_digest(
        credenciales.username.encode("utf-8"), usuario_configurado.encode("utf-8")
    )
    clave_valida = secrets.compare_digest(
        credenciales.password.encode("utf-8"), clave_configurada.encode("utf-8")
    )
    if not (usuario_valido & clave_valida):
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas.",
            headers={"WWW-Authenticate": "Basic"},
        )


# Modelo de validación para la petición del pasajero
class SolicitudViaje(BaseModel):
    id_pasajero: int
    origen_lat: float
    origen_lng: float
    destino_lat: float
    destino_lng: float


class SolicitudViajeWeb(BaseModel):
    nombre: str
    telefono: str
    origen: str
    destino: str


# Simulación de colección/tabla de viajes en la base de datos
viajes_db = []


@app.get("/", response_class=HTMLResponse)
@app.get("/solicitar", response_class=HTMLResponse)
async def pagina_solicitar():
    return """
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Solicitar mototaxi</title>
        <style>
          body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 600px; padding: 0 1rem; color: #17212b; }
          h1 { margin-bottom: .4rem; }
          p { color: #5b6570; }
          label { display: block; font-weight: 600; margin-top: 1rem; }
          input, textarea, button { box-sizing: border-box; font: inherit; padding: .8rem; width: 100%; }
          input, textarea { border: 1px solid #aeb8c2; border-radius: 6px; margin-top: .35rem; }
          textarea { min-height: 85px; resize: vertical; }
          button { background: #16794b; border: 0; border-radius: 6px; color: white; cursor: pointer; font-weight: 700; margin-top: 1.25rem; }
          button:disabled { cursor: wait; opacity: .65; }
          #resultado { margin-top: 1rem; }
          .error { color: #b42318; }
          .ok { color: #16794b; }
        </style>
      </head>
      <body>
        <h1>Solicita tu mototaxi</h1>
        <p>Déjanos tus datos y los puntos de recogida y destino. Escribe direcciones o referencias claras.</p>
        <form id="solicitud">
          <label>Nombre
            <input name="nombre" autocomplete="name" maxlength="100" required>
          </label>
          <label>Teléfono / WhatsApp
            <input name="telefono" type="tel" autocomplete="tel" maxlength="30" required>
          </label>
          <label>¿Dónde te recogemos?
            <textarea name="origen" maxlength="500" required></textarea>
          </label>
          <label>¿A dónde vas?
            <textarea name="destino" maxlength="500" required></textarea>
          </label>
          <button id="enviar" type="submit">Solicitar servicio</button>
        </form>
        <p id="resultado" role="status"></p>
        <script>
          const form = document.getElementById("solicitud");
          const button = document.getElementById("enviar");
          const resultado = document.getElementById("resultado");
          form.addEventListener("submit", async (event) => {
            event.preventDefault();
            button.disabled = true;
            resultado.className = "";
            resultado.textContent = "Enviando solicitud...";
            try {
              const datos = Object.fromEntries(new FormData(form));
              const respuesta = await fetch("/api/v1/viajes/solicitar-web", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(datos)
              });
              const contenido = await respuesta.json();
              if (!respuesta.ok) throw new Error(contenido.detail || "No se pudo enviar la solicitud.");
              resultado.className = "ok";
              resultado.textContent = "¡Solicitud recibida! Tu número de viaje es #" + contenido.data.id_viaje + ".";
              form.reset();
            } catch (error) {
              resultado.className = "error";
              resultado.textContent = "Error: " + error.message;
            } finally {
              button.disabled = false;
            }
          });
        </script>
        <p><a href="/docs">Documentación de la API</a></p>
      </body>
    </html>
    """


@app.get("/api/v1/viajes", dependencies=[Depends(verificar_admin)])
async def listar_viajes():
    return {"status": "success", "data": viajes_db}


@app.get(
    "/viajes",
    response_class=HTMLResponse,
    dependencies=[Depends(verificar_admin)],
)
async def pagina_viajes():
    return """
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Viajes solicitados</title>
        <style>
          body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 1100px; padding: 0 1rem; color: #17212b; }
          h1 { margin-bottom: .25rem; }
          .muted { color: #5b6570; }
          .table-wrap { overflow-x: auto; margin-top: 1.5rem; }
          table { border-collapse: collapse; width: 100%; }
          th, td { border-bottom: 1px solid #dce2e8; padding: .8rem; text-align: left; white-space: nowrap; }
          th { background: #f3f6f8; }
          #error { color: #b42318; }
        </style>
      </head>
      <body>
        <h1>Viajes solicitados</h1>
        <p class="muted">La lista se actualiza automáticamente cada 5 segundos.</p>
        <p id="status" class="muted">Cargando viajes...</p>
        <p id="error" role="alert"></p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID viaje</th><th>Pasajero</th><th>Teléfono</th><th>ID conductor</th>
                <th>Estado</th><th>Origen</th><th>Destino</th><th>Fecha de creación</th>
              </tr>
            </thead>
            <tbody id="viajes"></tbody>
          </table>
        </div>
        <p><a href="/docs">Abrir documentación de la API</a></p>
        <script>
          const tbody = document.getElementById("viajes");
          const status = document.getElementById("status");
          const error = document.getElementById("error");

          async function cargarViajes() {
            try {
              const respuesta = await fetch("/api/v1/viajes");
              if (!respuesta.ok) throw new Error("Error HTTP " + respuesta.status);
              const resultado = await respuesta.json();
              tbody.replaceChildren();
              for (const viaje of resultado.data) {
                const fila = document.createElement("tr");
                const valores = [
                  viaje.id_viaje,
                  viaje.nombre || viaje.id_pasajero,
                  viaje.telefono || "—",
                  viaje.id_conductor ?? "Sin asignar",
                  viaje.estado,
                  viaje.origen || viaje.coordenadas_origen.join(", "),
                  viaje.destino || viaje.coordenadas_destino.join(", "),
                  new Date(viaje.fecha_creacion).toLocaleString()
                ];
                for (const valor of valores) {
                  const celda = document.createElement("td");
                  celda.textContent = valor;
                  fila.appendChild(celda);
                }
                tbody.appendChild(fila);
              }
              status.textContent = resultado.data.length
                ? "Viajes encontrados: " + resultado.data.length
                : "Todavía no hay viajes. Las nuevas solicitudes aparecerán aquí.";
              error.textContent = "";
            } catch (e) {
              error.textContent = "No se pudieron cargar los viajes: " + e.message;
              status.textContent = "";
            }
          }

          cargarViajes();
          setInterval(cargarViajes, 5000);
        </script>
      </body>
    </html>
    """


@app.post("/api/v1/viajes/solicitar-web")
async def solicitar_mototaxi_desde_web(solicitud: SolicitudViajeWeb):
    nuevo_viaje = {
        "id_viaje": len(viajes_db) + 1,
        "id_pasajero": None,
        "nombre": solicitud.nombre,
        "telefono": solicitud.telefono,
        "id_conductor": None,
        "estado": "buscando_conductor",
        "origen": solicitud.origen,
        "destino": solicitud.destino,
        "coordenadas_origen": None,
        "coordenadas_destino": None,
        "fecha_creacion": datetime.now(),
    }

    viajes_db.append(nuevo_viaje)
    return {"status": "success", "data": nuevo_viaje}


@app.post("/api/v1/viajes/solicitar")
async def solicitar_mototaxi(solicitud: SolicitudViaje):
    # Genera el registro del viaje con estado inicial
    nuevo_viaje = {
        "id_viaje": len(viajes_db) + 1,
        "id_pasajero": solicitud.id_pasajero,
        "id_conductor": None,  # Se actualizará cuando un mototaxi acepte
        "estado": "buscando_conductor",
        # Formato GeoJSON (Longitud, Latitud)
        "coordenadas_origen": [solicitud.origen_lng, solicitud.origen_lat],
        "coordenadas_destino": [solicitud.destino_lng, solicitud.destino_lat],
        "fecha_creacion": datetime.now(),
    }

    # Inserción en base de datos (simulado)
    viajes_db.append(nuevo_viaje)

    # Retorna el viaje para que la app del cliente inicie la espera
    return {"status": "success", "data": nuevo_viaje}
