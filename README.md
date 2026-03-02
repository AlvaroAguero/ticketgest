# TicketGest

Sistema de ticketera en Flask para crear, aprobar, responder y cerrar tickets con clases dinámicas.

## Funcionalidades

- Definición de **tipos de solicitud** con lista de correos para notificaciones.
- Definición de **clases de ticket** con campos dinámicos (string, numeric, text, date).
- Soporte de controles: textfield, textbox, combo, radio, lista múltiple.
- Creación de instancias con:
  - ID numérico.
  - Path de acceso directo (`/tickets/<access_path>`).
  - Adjunto a nivel instancia.
  - Descarga de adjuntos de clase al crear o ver un ticket.
- Bitácora por ticket con historial de cambios y adjuntos por entrada.
- Notificación (log local) al cambiar estado del ticket, incluyendo creador + lista de correos del tipo.
- Pantalla principal con filtros por estado, tipo, clase y creador.
- Panel de administración para configuración de tipos y clases.

## Ejecución

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Luego abrir `http://localhost:5000`.

## Inicializar DB manualmente

```bash
flask --app app.py init-db
```

## Notificaciones

Las notificaciones se registran en `notification.log`.
