# docs/archive/n8n — Material legacy de v1.0

Esta carpeta contiene documentación **legacy** de la arquitectura v1.0 de
BuscadorDeEmpleo, cuando la orquestación (disparo diario, llamadas a las APIs
de empleo, entrega del digest) la hacía **n8n** por fuera, consumiendo un
servicio FastAPI headless.

En **v2.0** la app es standalone: hace su propio fetch (JSearch vía RapidAPI) y
entrega el digest directamente vía APScheduler. **n8n ya no es necesario** y esta
integración no forma parte de la configuración activa.

## Contenido de este archivo

- [`N8N-WORKFLOW.md`](N8N-WORKFLOW.md) — Guía paso a paso del workflow n8n v1.0:
  nodos, parámetros, snippets y el contrato JSON de los endpoints FastAPI.
  Conservada como referencia histórica.

## Documentación activa

La documentación de la app v2.0 (instalación, `.env`, `docker compose up`,
uso de las páginas Streamlit, entrega del digest) está en el
[`README.md`](../../../README.md) en la raíz del repositorio.
