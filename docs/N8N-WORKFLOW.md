# Workflow n8n — Guía paso a paso

Esta guía explica cómo montar en n8n el workflow diario que trae ofertas de
Arbeitnow y JSearch (vía RapidAPI), las envía a `/jobs/process` para que el
servicio las normalice, deduplique y puntúe, filtra las relevantes y entrega
un digest por Telegram (o email). Está pensada para ir nodo a nodo, con los
parámetros exactos y snippets copy-paste listos para usar.

## Diagrama del flujo

```
Schedule Trigger (08:00)
  ├─ HTTP Request → Arbeitnow API          → array offers (arbeitnow)
  └─ HTTP Request → JSearch (RapidAPI)     → array offers (jsearch)
          ↓
  Code (construir ProcessRequest)
          ↓
  HTTP Request → POST /jobs/process        → ProcessResponse (results + errors)
          ↓
  Split Out (separar results)
          ↓
  Filter (score_total >= 70 AND ya_visto = false)
          ↓
  Code (formatear digest Markdown)
          ↓
  Telegram → Send Message (digest)
```

---

## Prerrequisitos

Antes de activar el workflow en n8n, asegúrate de que se cumplen estos puntos:

1. **Servicio corriendo y alcanzable.** El servicio FastAPI debe estar arrancado
   y accesible desde n8n. Consulta la sección de despliegue para instrucciones
   de Docker: [README.md — Despliegue (Docker)](../README.md#despliegue-docker).

2. **CV subido al menos una vez.** `/jobs/process` requiere un `CVProfile`
   cacheado para poder puntuar las ofertas. Sin él devuelve HTTP 404. Súbelo
   con:
   ```bash
   curl -X POST http://localhost:8000/cv/parse \
     -F "file=@/ruta/a/mi_cv.pdf"
   ```
   Más detalles en [README.md — Subir el CV](../README.md#subir-el-cv).

3. **n8n instalado.** Puede ser vía Docker Compose o en la nube (n8n.cloud).
   La guía presupone que n8n puede hacer peticiones HTTP salientes y que tiene
   acceso de red al servicio (ver sección de URL más abajo).

4. **Credenciales preparadas:**
   - **RapidAPI key** — para las llamadas a JSearch. Se configura como
     credencial en n8n (tipo "Header Auth"); **nunca** como texto plano en el
     nodo. Ver [Sección de Seguridad](#seguridad).
   - **API_KEY del servicio** (si está activada) — la cabecera `X-API-Key`
     que el servicio verifica. También como credencial n8n.

---

## Paso a paso nodo a nodo

### Nodo 1: Schedule Trigger

| Parámetro | Valor |
|-----------|-------|
| Tipo | Schedule Trigger |
| Interval | Custom (Cron) |
| Cron Expression | `0 8 * * *` |

La expresión `0 8 * * *` lanza el flujo a las 08:00 hora local del servidor
n8n (ajústala a tu zona horaria si n8n no corre en UTC+2). Una ejecución
diaria matutina encaja bien con el free tier de JSearch, que tiene límite
mensual de peticiones.

---

### Nodo 2a: HTTP Request — Arbeitnow

| Parámetro | Valor |
|-----------|-------|
| Nombre del nodo | `Arbeitnow` |
| Método | GET |
| URL | `https://www.arbeitnow.com/api/job-board-api` |
| Autenticación | Ninguna (API pública y gratuita) |

La respuesta de Arbeitnow tiene esta forma:

```json
{
  "data": [ ...ofertas... ],
  "links": { "first": "...", "last": "..." },
  "meta": { "current_page": 1, ... }
}
```

Las ofertas están en el campo `data`. El Code node del paso 3 accede a
`$('Arbeitnow').first().json.data`.

**Filtrado opcional:** Arbeitnow admite query params para filtrar por etiquetas,
por ejemplo `?tags=AI` para limitar los resultados a ofertas relacionadas con IA.
Añádelos en "Query Parameters" del nodo si quieres reducir el volumen.

Renombra el nodo a `Arbeitnow` exactamente como aparece en el snippet del
nodo 3; si lo cambias, actualiza el Code node en consecuencia.

---

### Nodo 2b: HTTP Request — JSearch (RapidAPI)

| Parámetro | Valor |
|-----------|-------|
| Nombre del nodo | `JSearch` |
| Método | GET |
| URL | `https://jsearch.p.rapidapi.com/search` |
| Autenticación | Header Auth con credencial RapidAPI (ver Seguridad) |

Query parameters a configurar:

| Parámetro | Ejemplo | Descripción |
|-----------|---------|-------------|
| `query` | `AI Engineer Barcelona` | Búsqueda principal; ajusta según tus puestos objetivo |
| `page` | `1` | Página de resultados |
| `num_pages` | `1` | Nº de páginas a traer (1 = ~10 resultados) |
| `date_posted` | `today` | Solo ofertas del día; evita procesar las mismas del día anterior |

**Cabeceras obligatorias** (configurar como credencial "Header Auth" en n8n,
**no como texto plano**):

```
X-RapidAPI-Key: <tu-rapidapi-key>   ← guardar como credencial n8n
X-RapidAPI-Host: jsearch.p.rapidapi.com
```

> **ADVERTENCIA DE SEGURIDAD — ver [Sección de Seguridad](#seguridad).**
> La RapidAPI key NO va en este repositorio ni en la imagen Docker. Solo en n8n.

La respuesta de JSearch tiene esta forma:

```json
{
  "status": "OK",
  "request_id": "...",
  "data": [ ...ofertas... ]
}
```

Las ofertas están en el campo `data`. El Code node del paso 3 accede a
`$('JSearch').first().json.data`.

**Para añadir más fuentes** (FlyByAPIs u otras): añadir otro nodo HTTP Request
con el nombre correspondiente y añadir una entrada más en el array `sources`
del Code node con el valor `"source"` apropiado (`"generic"` para cualquier
fuente sin mapper dedicado).

---

### Nodo 3: Code — construir el body ProcessRequest

| Parámetro | Valor |
|-----------|-------|
| Tipo | Code (JavaScript) |
| Mode | Run Once for All Items |

Este nodo recoge las respuestas de los dos HTTP Requests anteriores y las
envuelve en el formato `ProcessRequest` que espera el servicio.

**Por qué un Code node y no un Merge:** las dos fuentes llegan con esquemas
distintos (Arbeitnow vs JSearch) y hay que envolverlas en el envelope
`{ sources: [...] }` con el valor `source` correcto para que el servicio
enrute cada oferta al mapper adecuado. El valor del campo `source` **debe**
coincidir exactamente con los valores reconocidos por el servicio
(`"arbeitnow"`, `"jsearch"`, o cualquier otro string para el mapper genérico).

**Snippet copy-paste:**

```javascript
const arbeitnow = $('Arbeitnow').first().json.data || [];
const jsearch   = $('JSearch').first().json.data   || [];

return [{
  json: {
    sources: [
      { source: 'arbeitnow', offers: arbeitnow },
      { source: 'jsearch',   offers: jsearch   },
    ],
  },
}];
```

Si los nodos 2a/2b tienen nombres distintos a `Arbeitnow` y `JSearch`,
actualiza las referencias `$('Arbeitnow')` y `$('JSearch')` en consecuencia.

---

### Nodo 4: HTTP Request — POST /jobs/process

| Parámetro | Valor |
|-----------|-------|
| Método | POST |
| Body Content Type | JSON |
| Body | `={{ $json }}` |
| Timeout | `300000` ms (5 minutos) — ver nota abajo |

**URL según entorno:**

| Entorno | URL |
|---------|-----|
| Dev — n8n en Docker (Mac/Windows) | `http://host.docker.internal:8000/jobs/process` |
| Dev — n8n en Docker (Linux) | IP del host (`ip addr show docker0 \| grep inet`) o red Docker compartida |
| Dev — n8n en local (sin Docker) | `http://localhost:8000/jobs/process` |
| Producción | `https://<tu-dominio>/jobs/process` |

Más información sobre redes en [README.md — Cómo n8n alcanza el servicio](../README.md#cómo-n8n-alcanza-el-servicio).

**Cabeceras obligatorias:**

| Cabecera | Valor | Cuándo |
|----------|-------|--------|
| `Content-Type` | `application/json` | Siempre (n8n suele añadirla automáticamente con JSON body) |
| `X-API-Key` | `{{ $env.API_KEY }}` | Solo si `API_KEY` está configurada en el `.env` del servicio |

La `X-API-Key` se configura como credencial "Header Auth" en n8n, no como
texto plano. Sin `API_KEY` en el entorno del servicio, la autenticación está
desactivada y no hace falta enviar esta cabecera.

**Nota sobre el timeout:** El primer arranque del servicio descarga el modelo
BGE-M3 (~2.3 GB) para los embeddings de deduplicación. Además, el scoring
llama a OpenAI por cada oferta única. Poner el timeout a **300 000 ms** (5
minutos) como mínimo en Options → Timeout; los runs posteriores son
sensiblemente más rápidos porque el modelo ya está cacheado.

La respuesta es un `ProcessResponse`:

```json
{
  "results": [
    {
      "job": {
        "id": "a1b2c3...",
        "title": "AI Engineer",
        "company": "TechCorp",
        "location": "Barcelona",
        "remote": "hybrid",
        "description": "...",
        "salary": null,
        "url": "https://...",
        "source": "arbeitnow",
        "posted_at": "2026-05-24T08:00:00Z",
        "raw": {},
        "urls_alternativas": []
      },
      "score": {
        "score_total": 82,
        "recommendation": "good_fit",
        "desglose": {
          "encaje_puesto": 90,
          "encaje_skills": 85,
          "encaje_ubicacion": 40,
          "encaje_seniority": 75
        },
        "puesto_detectado": "AI Engineer",
        "rango_puesto": 1,
        "reasons_for": ["Rol exactamente en el ranking"],
        "reasons_against": ["Requiere inglés C2"],
        "matched_skills": ["Python", "LangChain"],
        "missing_requirements": [],
        "deal_breaker_hit": false,
        "deal_breaker_cual": null
      },
      "ya_visto": false
    }
  ],
  "errors": []
}
```

`results` viene ordenado por `score_total` DESC. El contrato completo está en
[README.md — Contrato POST /jobs/process](../README.md#contrato-post-jobsprocess).

---

### Nodo 5: Split Out — una oferta por item

| Parámetro | Valor |
|-----------|-------|
| Tipo | Split Out |
| Field To Split Out | `results` |

Tras este nodo, cada item del flujo de n8n representa una oferta individual con
los campos `.job`, `.score` y `.ya_visto`. Los nodos siguientes (Filter, Code,
Telegram) operan sobre cada item por separado.

---

### Nodo 6: Filter — quedarse con lo relevante y nuevo

| Parámetro | Valor |
|-----------|-------|
| Tipo | Filter |
| Modo | AND (todas las condiciones deben cumplirse) |

Condiciones a configurar:

| # | Campo | Tipo | Operador | Valor |
|---|-------|------|----------|-------|
| 1 | `{{ $json.score.score_total }}` | Number | Greater than or equal | `70` |
| 2 | `{{ $json.ya_visto }}` | Boolean | Is equal to | `false` |

- **Condición 1 (score_total >= 70):** el servicio puntúa de 0 a 100; 70 es un
  umbral razonable para "oferta interesante". Ajústalo a tu criterio.
- **Condición 2 (ya_visto = false):** el servicio marca las ofertas que ya
  estaban en el storage de días anteriores. El Filter las excluye del digest
  para no recibir la misma oferta dos días seguidos; el servicio ya habrá
  actualizado su score si la descripción cambió.

**Filtrado alternativo por recommendation:** si quieres ser más selectivo,
añade una condición 3: `{{ $json.score.recommendation }}` is one of
`["strong_fit", "good_fit"]`.

---

### Nodo 7: Code — formatear el digest (recomendado)

| Parámetro | Valor |
|-----------|-------|
| Tipo | Code (JavaScript) |
| Mode | Run Once for All Items |

Este nodo agrupa todas las ofertas filtradas en un único mensaje para no
enviar un mensaje de Telegram por cada oferta (que puede ser ruidoso). Sin
este nodo, el nodo Telegram se ejecuta una vez por item — ambas opciones son
válidas.

**Snippet copy-paste:**

```javascript
const items = $input.all();
if (items.length === 0) {
  return [{ json: { text: 'No hay ofertas relevantes hoy.' } }];
}
const lines = items.map(i => {
  const j = i.json.job;
  const s = i.json.score;
  return `• *${j.title}* — ${j.company} (${j.location || 'ubicación desconocida'})\n`
       + `  Score: ${s.score_total} · ${s.recommendation}\n`
       + `  ${j.url || '(sin URL)'}`;
});
return [{
  json: {
    text: `*Ofertas de hoy (${items.length})*\n\n` + lines.join('\n\n'),
  },
}];
```

---

### Nodo 8: Telegram — enviar el digest

| Parámetro | Valor |
|-----------|-------|
| Tipo | Telegram |
| Operación | Send Message |
| Chat ID | Tu chat id (número o `@canal`) |
| Text | `={{ $json.text }}` |
| Additional Fields → Parse Mode | `Markdown` |

**Cómo crear el bot y obtener las credenciales:**

1. Abre Telegram y busca `@BotFather`.
2. Envía `/newbot` y sigue las instrucciones para crear el bot.
3. Copia el token que te da BotFather.
4. En n8n, ve a Credentials → New → Telegram API y pega el token.

**Cómo obtener tu Chat ID:**

- Envía un mensaje al bot que acabas de crear.
- Llama a `https://api.telegram.org/bot<TOKEN>/getUpdates` en el navegador.
- El `chat.id` aparece en el primer resultado.
- Alternativamente, envía un mensaje a `@userinfobot` en Telegram.

### Nodo 8-bis: Variante Email

Alternativa al nodo Telegram: usar el nodo "Send Email" (SMTP) o "Gmail".
El cuerpo del digest se construye igual en el Nodo 7; usa HTML en lugar de
Markdown si tu cliente de correo lo requiere (cambia la sintaxis del snippet:
`<b>...</b>` en lugar de `*...*`, `<a href="...">...</a>` en lugar de la URL
plana). Las credenciales SMTP/Gmail se configuran en n8n siguiendo la
documentación del nodo correspondiente.

---

## Seguridad

> **ADVERTENCIA:** Ninguna clave de API (RapidAPI, OpenAI, API_KEY del servicio)
> debe aparecer en este repositorio ni en la imagen Docker. Si alguna se filtró
> por error, rótala inmediatamente antes de continuar.

### Reglas obligatorias

- **`X-RapidAPI-Key` (JSearch) vive SOLO en n8n** como credencial de tipo
  "Header Auth". Nunca como texto plano en el nodo ni en el repositorio. Si se
  filtró antes, ir al dashboard de RapidAPI y rotar la key.

- **`API_KEY` del servicio** (cabecera `X-API-Key`) también se configura como
  credencial en n8n (Header Auth), no como texto plano. Para referenciarla desde
  n8n se puede usar `{{ $env.API_KEY }}` si se inyecta como variable de entorno
  de n8n.

- **En producción, activar siempre la autenticación del servicio.** Añadir
  `API_KEY=<valor-secreto>` al `.env` del servicio antes de exponerlo en internet.
  `GET /health` es la única ruta pública; todos los demás endpoints requieren
  `X-API-Key`.

- **No loguear claves en Code nodes.** Evita `console.log(apiKey)` o similar —
  los logs de n8n son accesibles desde la UI y podrían exponer el valor.

- **Token del bot de Telegram** — guardarlo como credencial "Telegram API" en n8n,
  no inline en ningún nodo.

---

## Mapeo de datos: `source` → mapper

El valor del campo `source` en el body de `/jobs/process` determina qué mapper
usa el servicio internamente para normalizar las ofertas crudas. Los valores
reconocidos son los siguientes:

| Valor `source` | Mapper usado | Campos esperados (clave) |
|---|---|---|
| `"arbeitnow"` | `arbeitnow_mapper` | `company_name`, `title`, `description` (HTML), `remote` (bool), `url`, `location`, `created_at` (Unix int) |
| `"jsearch"` | `jsearch_mapper` | `employer_name`, `job_title`, `job_description`, `job_apply_link`, `job_is_remote` (bool), `job_location` / `job_city`, `job_posted_at_datetime_utc` |
| cualquier otro | `generic_mapper` | best-effort sobre `company_name`/`company`/`employer`, `title`/`job_title`, `description`/`body`, `url`/`apply_url`, `remote`/`is_remote` |

**Regla clave:** las ofertas van crudas tal como las devuelve la API de empleo.
**No transformes los campos en n8n antes de enviarlos.** El servicio normaliza
internamente. Si añades una nueva fuente sin mapper dedicado, usa `"generic"`
(o cualquier string distinto de `"arbeitnow"` y `"jsearch"`) y el servicio
intentará mapear sobre convenciones comunes.

El contrato JSON completo está en
[README.md — Contrato POST /jobs/process](../README.md#contrato-post-jobsprocess).

---

## Programación y costes

### Frecuencia de ejecución

El cron `0 8 * * *` lanza el flujo una vez al día a las 08:00. Esto encaja bien
con el **free tier de JSearch** (RapidAPI), que tiene límite mensual de
peticiones: una ejecución diaria está muy por debajo del límite.

Si quieres mayor frecuencia (p.ej. dos veces al día), ajusta el cron
(`0 8,18 * * *`) y verifica que no superas el tier de JSearch.

### Timeout del nodo /jobs/process

Poner **300 000 ms** (5 minutos) como mínimo en Options → Timeout. El primer
run descarga el modelo BGE-M3 (~2.3 GB) para los embeddings; además, el scoring
hace una llamada a OpenAI por cada oferta única. Los runs posteriores usan el
modelo ya cacheado y son sensiblemente más rápidos.

### Coste estimado de OpenAI

El scoring usa `gpt-4o-mini` para el CVProfile y `gpt-4o` para el scoring de
cada oferta. Con 20-50 ofertas únicas diarias (tras deduplicación), el coste es
marginal (céntimos de euro por run). Puedes ajustar el modelo en el `.env` si
quieres reducir más el coste.

### Idempotencia y `ya_visto`

`ya_visto: true` en el response indica que esa oferta ya estaba en el storage
de días anteriores. El Filter del nodo 6 las excluye del digest de hoy, pero el
servicio las sigue procesando para actualizar el score si la descripción cambió.
Esto hace que el flujo sea idempotente: ejecutarlo dos veces en el mismo día no
duplica notificaciones.

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| HTTP 404 `No hay CVProfile cacheado` | El CV no se subió antes de ejecutar el flujo | `curl -X POST http://localhost:8000/cv/parse -F "file=@mi_cv.pdf"` |
| HTTP 401 `Invalid or missing API key` | Falta la cabecera `X-API-Key` o el valor es incorrecto | Añadir credencial Header Auth en n8n con el mismo valor de `API_KEY` del `.env` del servicio |
| `Connection refused` / no llega al servicio | URL incorrecta para el entorno | Mac/Win Docker: `host.docker.internal:8000`; Linux: IP del host o red compartida en compose; ver [README.md](../README.md#cómo-n8n-alcanza-el-servicio) |
| Timeout en el primer run | Primera descarga de BGE-M3 (~2.3 GB) + llamadas OpenAI | Subir el timeout del nodo a 300 000 ms o más; esperar a que el modelo se descargue |
| `results: []` o arrays vacíos | La API de empleo no devolvió datos o el campo `data` tiene otro nombre | Inspeccionar la respuesta cruda del HTTP Request node de Arbeitnow/JSearch y ajustar la ruta en el Code node |
| Ofertas relevantes no llegan por Telegram | El Filter es demasiado estricto o `ya_visto` siempre true | Bajar el umbral de score o revisar que /cv/parse se ejecutó con el CV correcto |
| JSearch devuelve 403 / 429 | Key de RapidAPI inválida, caducada o límite mensual alcanzado | Verificar la key en el dashboard de RapidAPI; rotar si es necesario |
| Telegram "Bad Request: can't parse entities" | El texto del digest tiene Markdown malformado (asteriscos sin cerrar) | Revisar el snippet del nodo 7; escapar caracteres especiales en `j.title` o `j.company` |

---

## Enlace al contrato JSON completo

Para el contrato JSON completo de `/jobs/process` (todos los campos de request
y response), la lista de endpoints disponibles y cómo exponer el servicio a n8n,
ver [README.md — Integración con n8n](../README.md#integración-con-n8n).
