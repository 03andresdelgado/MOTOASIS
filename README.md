# MOTOASIS

## Avisos de solicitudes por WhatsApp

El formulario puede enviar un aviso de cada solicitud al WhatsApp del operador
mediante Meta WhatsApp Cloud API. Para activarlo:

1. Configura WhatsApp Cloud API en Meta, agrega un número de WhatsApp Business y
   obtén el `Phone Number ID` y un token de acceso.
2. Crea y espera la aprobación de una plantilla en español llamada
   `nueva_solicitud_viaje`. Debe tener cinco variables de texto en el cuerpo,
   en este orden: número de viaje, nombre, teléfono del pasajero, recogida y
   destino. Por ejemplo:
   `Nuevo viaje #{{1}}. Pasajero: {{2}}. Teléfono: {{3}}. Recogida: {{4}}. Destino: {{5}}.`
3. En Render, abre el servicio `motoasis` → **Environment** y configura:
   - `WHATSAPP_ACCESS_TOKEN`: token de acceso de Meta.
   - `WHATSAPP_PHONE_NUMBER_ID`: ID del número remitente de WhatsApp Business.
   - `WHATSAPP_RECIPIENT`: número receptor en formato internacional, por ejemplo
     `+573001234567`.
   - `WHATSAPP_TEMPLATE_NAME`: `nueva_solicitud_viaje` (o el nombre que aprobó Meta).
   - `WHATSAPP_TEMPLATE_LANGUAGE`: idioma aprobado de la plantilla, por ejemplo `es`.
   - `WHATSAPP_GRAPH_API_VERSION`: versión vigente de Graph API, por ejemplo `v22.0`.
4. Guarda los cambios y espera a que Render termine el despliegue.

No publiques el token ni lo guardes en el repositorio. El número receptor debe
haber aceptado recibir estos avisos. Las solicitudes se reciben aunque la
notificación de WhatsApp no pueda enviarse; el resultado se muestra en `/viajes`
y el detalle del error queda en los logs de Render.