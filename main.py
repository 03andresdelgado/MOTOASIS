import asyncio
import json
import logging
import os
import re
import secrets
from datetime import datetime
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

app = FastAPI()
security = HTTPBasic()
logger = logging.getLogger(__name__)


def enviar_notificacion_whatsapp(viaje):
    configuracion = {
        "WHATSAPP_ACCESS_TOKEN": os.getenv("WHATSAPP_ACCESS_TOKEN"),
        "WHATSAPP_PHONE_NUMBER_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
        "WHATSAPP_RECIPIENT": os.getenv("WHATSAPP_RECIPIENT"),
        "WHATSAPP_TEMPLATE_NAME": os.getenv("WHATSAPP_TEMPLATE_NAME"),
    }
    faltantes = [nombre for nombre, valor in configuracion.items() if not valor]
    if faltantes:
        logger.warning(
            "No se envió el aviso de WhatsApp; faltan variables: %s",
            ", ".join(faltantes),
        )
        return False

    destinatario = re.sub(r"\D", "", configuracion["WHATSAPP_RECIPIENT"])
    if not destinatario:
        logger.error("WHATSAPP_RECIPIENT no contiene un número válido.")
        return False

    api_version = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v22.0").strip("/")
    idioma = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "es")
    parametros = [
        str(viaje["id_viaje"]),
        viaje.get("nombre") or "No indicado",
        viaje.get("telefono") or "No indicado",
        viaje.get("origen") or "No indicado",
        viaje.get("destino") or "No indicado",
    ]
    coordenadas_origen = viaje.get("coordenadas_origen")
    if coordenadas_origen:
        enlace_ubicacion = (
            "https://maps.google.com/?q="
            f"{coordenadas_origen[1]},{coordenadas_origen[0]}"
        )
        parametros[3] = f"{parametros[3]} | Ubicación: {enlace_ubicacion}"
    payload = {
        "messaging_product": "whatsapp",
        "to": destinatario,
        "type": "template",
        "template": {
            "name": configuracion["WHATSAPP_TEMPLATE_NAME"],
            "language": {"code": idioma},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": parametro}
                        for parametro in parametros
                    ],
                }
            ],
        },
    }
    solicitud = Request(
        "https://graph.facebook.com/"
        f"{api_version}/{configuracion['WHATSAPP_PHONE_NUMBER_ID']}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {configuracion['WHATSAPP_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(solicitud, timeout=10) as respuesta:
            if respuesta.status not in (200, 201):
                logger.error("WhatsApp API respondió con HTTP %s.", respuesta.status)
                return False
    except HTTPError as error:
        detalle = error.read().decode("utf-8", "replace")
        logger.error("WhatsApp API respondió con HTTP %s: %s", error.code, detalle)
        return False
    except (URLError, TimeoutError) as error:
        logger.error("No se pudo contactar a WhatsApp API: %s", error)
        return False

    return True


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
    origen_lat: Optional[float] = None
    origen_lng: Optional[float] = None


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
          #ubicacion { background: #1769aa; margin-top: .5rem; }
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
          <button id="ubicacion" type="button">Usar mi ubicación actual</button>
          <p id="estado-ubicacion" role="status"></p>
          <label>¿A dónde vas?
            <textarea name="destino" maxlength="500" required></textarea>
          </label>
          <button id="enviar" type="submit">Solicitar servicio</button>
        </form>
        <p id="resultado" role="status"></p>
        <script>
          const form = document.getElementById("solicitud");
          const button = document.getElementById("enviar");
          const botonUbicacion = document.getElementById("ubicacion");
          const estadoUbicacion = document.getElementById("estado-ubicacion");
          let ubicacionSeleccionada = null;
          const resultado = document.getElementById("resultado");
          botonUbicacion.addEventListener("click", () => {
            if (!navigator.geolocation) {
              estadoUbicacion.textContent = "Este navegador no permite obtener la ubicación.";
              return;
            }
            botonUbicacion.disabled = true;
            estadoUbicacion.textContent = "Obteniendo ubicación...";
            navigator.geolocation.getCurrentPosition(
              (posicion) => {
                const { latitude, longitude } = posicion.coords;
                ubicacionSeleccionada = { origen_lat: latitude, origen_lng: longitude };
                form.elements.origen.value = "Ubicación GPS compartida";
                estadoUbicacion.textContent = "Ubicación agregada. Puedes editar la dirección si lo necesitas.";
                botonUbicacion.disabled = false;
              },
              (error) => {
                const mensajes = {
                  1: "Permite el acceso a la ubicación en tu navegador para continuar.",
                  2: "No se pudo determinar tu ubicación. Inténtalo otra vez.",
                  3: "La solicitud de ubicación tardó demasiado. Inténtalo otra vez."
                };
                estadoUbicacion.textContent = mensajes[error.code] || "No se pudo obtener la ubicación.";
                botonUbicacion.disabled = false;
              },
              { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
            );
          });
          form.elements.origen.addEventListener("input", () => {
            if (ubicacionSeleccionada) {
              ubicacionSeleccionada = null;
              estadoUbicacion.textContent = "Se usará la dirección escrita, sin ubicación GPS.";
            }
          });
          form.addEventListener("submit", async (event) => {
            event.preventDefault();
            button.disabled = true;
            resultado.className = "";
            resultado.textContent = "Enviando solicitud...";
            try {
              const datos = Object.fromEntries(new FormData(form));
              if (ubicacionSeleccionada) Object.assign(datos, ubicacionSeleccionada);
              const respuesta = await fetch("/api/v1/viajes/solicitar-web", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(datos)
              });
              const contenido = await respuesta.json();
              if (!respuesta.ok) throw new Error(contenido.detail || "No se pudo enviar la solicitud.");
              resultado.className = "ok";
              resultado.textContent = contenido.data.notificacion_whatsapp === "enviada"
                ? "¡Solicitud recibida! El aviso fue enviado por WhatsApp. Tu número de viaje es #" + contenido.data.id_viaje + "."
                : "¡Solicitud recibida! Tu número de viaje es #" + contenido.data.id_viaje + ". El aviso por WhatsApp no se pudo enviar; contacta directamente al operador.";
              form.reset();
              ubicacionSeleccionada = null;
              estadoUbicacion.textContent = "";
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
                <th>Estado</th><th>Origen</th><th>Destino</th><th>Aviso WhatsApp</th><th>Fecha de creación</th>
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
                  viaje.origen || (
                    viaje.coordenadas_origen
                      ? viaje.coordenadas_origen.join(", ")
                      : "—"
                  ),
                  viaje.destino || viaje.coordenadas_destino.join(", "),
                  viaje.notificacion_whatsapp || "Pendiente",
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
        "coordenadas_origen": (
            [solicitud.origen_lng, solicitud.origen_lat]
            if solicitud.origen_lat is not None
            and solicitud.origen_lng is not None
            else None
        ),
        "coordenadas_destino": None,
        "notificacion_whatsapp": "pendiente",
        "fecha_creacion": datetime.now(),
    }

    viajes_db.append(nuevo_viaje)
    notificacion_enviada = await asyncio.to_thread(
        enviar_notificacion_whatsapp, nuevo_viaje
    )
    nuevo_viaje["notificacion_whatsapp"] = (
        "enviada" if notificacion_enviada else "pendiente"
    )
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
