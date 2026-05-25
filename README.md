# BuscadorDeEmpleo — Agregador inteligente de ofertas de empleo

App **Python standalone** que busca ofertas de empleo automáticamente, las
**deduplica semánticamente** (BGE-M3 local) y las **puntúa con honestidad
contra el perfil real de Jaime** (CV en PDF + ranking de puestos + preferencias).
El scoring funciona **100 % local** sin ninguna clave de OpenAI; OpenAI es
enriquecimiento opcional que añade razonamientos detallados.

La app se compone de dos procesos:
- **`ui`** — Streamlit multipage en `http://localhost:8501`: sube el CV, configura
  la búsqueda, navega y filtra resultados, ajusta pesos, y lanza un run manual.
- **`worker`** — APScheduler que busca ofertas (JSearch vía RapidAPI), puntúa y
  entrega el digest (Telegram o email) de forma autónoma cada X horas.

Ambos arrancan con un solo `docker compose up` y comparten el mismo volumen de datos.

**Doble propósito:** herramienta real para la búsqueda activa de empleo como
AI Engineer (base Barcelona, abierto a remoto) + pieza de portfolio que consolida
RAG/embeddings, scoring local-first con LLM opcional, parseo de documentos PDF y
entrega de notificaciones.

---

## Tabla de contenidos

1. [Arquitectura](#arquitectura)
2. [Instalación](#instalación)
3. [Configuración `.env`](#configuración-env)
4. [Editar el perfil (`data/profile.yaml`)](#editar-el-perfil)
5. [Arrancar la app (Docker)](#arrancar-la-app-docker)
6. [Usar la app](#usar-la-app)
7. [Entrega del digest](#entrega-del-digest)
8. [Nota de seguridad](#nota-de-seguridad)
9. [Stack](#stack)
10. [Correr los tests](#correr-los-tests)
11. [Legado: n8n (retirado en v2.0)](#legado-n8n-retirado-en-v20)

---

## Arquitectura

```
┌─────────────────────────────────┐   ┌───────────────────────────────────┐
│  ui  (Streamlit :8501)          │   │  worker  (APScheduler)            │
│  • Sube CV → parsea/cachea      │   │  • Busca ofertas (JSearch)        │
│  • Configura búsqueda           │   │  • Dedup semántico (BGE-M3)       │
│  • Navega/filtra resultados     │   │  • Scoring local-first + LLM opt. │
│  • Ajusta pesos y deal-breakers │   │  • Entrega digest (Telegram/SMTP) │
│  • Lanza "Run now" en hilo bg   │   │  • Marca ofertas como vistas      │
└────────────┬────────────────────┘   └────────────┬──────────────────────┘
             │                                     │
             └─────────────┬───────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  data/  (volumen named) │
              │  ├── jobs.db (SQLite)   │
              │  └── profile.yaml       │
              └─────────────────────────┘
```

Los dos servicios se construyen desde **una sola imagen** (`buscadordeempleo:latest`).
La tabla `settings` (en SQLite) actúa como bus de configuración cross-process: la UI
edita pesos, deal-breakers y parámetros de búsqueda; el worker los lee en cada run
sin necesidad de reiniciar Docker.

`data/profile.yaml` es la identidad editada a mano: ranking de puestos, datos
personales, preferencias de ubicación.

El modelo BGE-M3 (~2.3 GB) se descarga la primera vez en el volumen `hf_cache`
(también named) y se reutiliza en todos los arranques siguientes.

---

## Instalación

**Requisitos:** Python 3.11+ y [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/jaimeberdejo/BuscadorDeEmpleo.git
cd BuscadorDeEmpleo
uv sync
```

`uv sync` instala todas las dependencias del `pyproject.toml` en el entorno
virtual gestionado por uv. No hace falta activar el venv manualmente: todos los
comandos se prefijan con `uv run`.

**Fallback sin uv:**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Para el uso diario, el camino recomendado es Docker (ver
[Arrancar la app (Docker)](#arrancar-la-app-docker)).

---

## Configuración `.env`

```bash
cp .env.example .env
```

Edita `.env` y establece las claves necesarias:

| Variable | Requerida | Descripción |
|---|---|---|
| `RAPIDAPI_KEY` | **Sí** (para el worker) | Clave de JSearch vía RapidAPI — el worker la usa para buscar ofertas |
| `OPENAI_API_KEY` | **No** (opcional) | Scoring funciona 100 % local sin esta clave; si se define, añade reasons_for/against y matched/missing skills vía LLM |
| `OPENAI_MODEL_CV` | No | Modelo para parseo de CV (default: `gpt-4o-mini`) |
| `OPENAI_MODEL_SCORING` | No | Modelo para scoring (default: `gpt-4o`) |
| `SQLITE_DB_PATH` | No | Ruta del fichero SQLite (default: `data/jobs.db`) |
| `TELEGRAM_BOT_TOKEN` | No | Token del bot de Telegram para el digest; requiere también `TELEGRAM_CHAT_ID` |
| `TELEGRAM_CHAT_ID` | No | ID del chat de Telegram destino; ambas vars necesarias para activar el canal |
| `SMTP_HOST` | No | Servidor SMTP (ej. `smtp.gmail.com`); requiere también las demás vars SMTP |
| `SMTP_PORT` | No | Puerto SMTP (default: `587`) |
| `SMTP_USER` | No | Usuario/remitente SMTP |
| `SMTP_PASSWORD` | No | Contraseña SMTP |
| `SMTP_TO` | No | Destinatario del digest (por defecto = `SMTP_USER`, autoenvío) |
| `LANGFUSE_PUBLIC_KEY` | No | Activa el tracing LLM con Langfuse (stub; requiere también `LANGFUSE_SECRET_KEY`) |
| `LANGFUSE_SECRET_KEY` | No | Clave secreta de Langfuse |

> `.env` está en `.gitignore` y en `.dockerignore` — nunca se commitea ni se
> copia en la imagen Docker. Si no existe, `docker compose` falla con un mensaje
> de error claro antes de arrancar.

---

## Editar el perfil

El perfil de identidad se configura en `data/profile.yaml` **sin tocar código**.
Contiene:

- `datos_personales`: nombre, email, ubicación, idiomas.
- `preferencias_ubicacion`: ciudades preferidas, país, si está dispuesto a reubicarse.
- `preferencia_remoto`: modalidad ideal (`remote`/`hybrid`/`onsite`/`indiferente`),
  ciudades donde acepta presencial.
- `ranking_puestos`: lista **ordenada** de puestos a los que opta (el primero tiene
  el mayor peso en el scoring). Cada entrada incluye sinónimos para el match.
- `deal_breakers`: condiciones que descartan una oferta en duro (p. ej.
  `"exige 5+ años de experiencia"`, `"presencial fuera de Barcelona"`).
- `pesos`: ponderación del `score_total` (puesto, skills, ubicación, seniority).
  Deben sumar 1.0. Estos pesos también son editables desde la página **Configuración**
  de la UI sin tocar el fichero.
- `dedup_umbral`: similitud coseno a partir de la cual dos ofertas se consideran
  duplicadas (default: `0.85`).

Ejemplo incluido (`data/profile.yaml`):

```yaml
ranking_puestos:
  - titulo: "Ingeniero de IA / AI Engineer"
    sinonimos: ["AI Engineer", "LLM Engineer", "GenAI Engineer"]
  - titulo: "Ingeniero de ML / ML Engineer"
    sinonimos: ["ML Engineer", "Machine Learning Engineer"]

deal_breakers:
  - "exige 5+ años de experiencia"
  - "presencial fuera de Barcelona"

pesos:
  puesto: 0.35
  skills: 0.30
  ubicacion: 0.20
  seniority: 0.15
```

---

## Arrancar la app (Docker)

### Primera vez (build + arranque)

```bash
docker compose up --build
```

La primera vez tarda más porque:
1. Se construye la imagen (instala todas las dependencias con uv, ~1-2 min).
2. El primer run del worker descarga el modelo BGE-M3 (~2.3 GB) desde HuggingFace
   y lo guarda en el volumen `hf_cache`. Los runs siguientes usan la caché.

Una vez construida la imagen, arranque habitual:

```bash
docker compose up -d
```

Esto levanta **ambos servicios**:
- `ui` — Streamlit en `http://localhost:8501`
- `worker` — APScheduler en background (sin puerto expuesto)

Para parar:

```bash
docker compose down
```

### Persistencia

Los datos sobreviven a `docker compose restart` gracias a dos named volumes:

| Volumen | Punto de montaje | Qué contiene |
|---|---|---|
| `data` | `/app/data` | SQLite (`jobs.db`) + perfil (`profile.yaml`) |
| `hf_cache` | `/app/.cache/huggingface` | Modelo BGE-M3 (~2.3 GB, descargado la primera vez) |

Para inspeccionar o hacer backup de la DB:

```bash
docker volume inspect buscadordeempleo_data
# La ruta real en el host aparece en "Mountpoint"
```

### Arranque sin Docker (desarrollo)

Para desarrollar o depurar sin Docker, abre dos terminales:

```bash
# Terminal 1 — UI
uv run streamlit run ui/app.py --server.port 8501

# Terminal 2 — Worker
uv run python worker.py
```

Asegúrate de que `.env` está presente y que `SQLITE_DB_PATH` apunta al mismo
fichero en ambos procesos.

---

## Usar la app

Abre `http://localhost:8501` en el navegador. La app tiene cinco páginas accesibles
desde la barra lateral:

### CV

Sube el PDF de tu CV. La app calcula un hash del fichero: si el perfil ya está
cacheado, lo muestra sin re-parsear; si es nuevo o cambiado, llama al parser (LLM
si `OPENAI_API_KEY` está definida, de lo contrario extracción básica) y guarda el
`CVProfile` resultante.

El `CVProfile` extraído incluye: experiencia (empresa, rol, tecnologías, logros),
skills técnicas, formación, años de experiencia total y dominios. El scoring usa
este perfil real — no una lista de skills escrita a mano.

### Search Config (Búsqueda)

Configura los parámetros que el worker usa para buscar ofertas en JSearch:

- **País / idioma** del mercado objetivo.
- **Puesto(s)** a buscar (uno o varios términos).
- **Fecha mínima** de publicación (`month`, `3days`, `today`).
- **Tipo de empleo** (full-time, part-time, contractor, etc.).
- **Solo remoto** (toggle).

Los cambios se persisten en la tabla `settings`. El worker los leerá en el
siguiente run **sin necesidad de reiniciar Docker**.

### Results (Resultados)

Lista paginable y ordenable de todas las ofertas puntuadas. Columnas principales:
título, empresa, `score_total`, recomendación. Filtros: slider de puntuación
mínima y multiselect por recomendación (`strong_fit`, `good_fit`, `maybe`, `skip`).

Al expandir una fila se muestra el desglose completo:
- Los 4 sub-scores: encaje_puesto, encaje_skills, encaje_ubicación, encaje_seniority.
- `reasons_for` / `reasons_against` (honesto).
- `matched_skills` / `missing_requirements`.
- Si se ha disparado algún deal-breaker.
- URL de aplicación directa.

**"▶ Run now"** — lanza una búsqueda y scoring inmediata en un hilo de fondo.
La UI muestra un spinner y se actualiza automáticamente al terminar. El botón se
deshabilita mientras el run está en progreso para evitar runs concurrentes desde
la UI.

**"↻ Re-score stored"** — re-puntúa las ofertas ya almacenadas en la base de datos
con los pesos y parámetros actuales, sin volver a buscar. Útil después de editar
pesos o deal-breakers en la página de Configuración. Muestra una advertencia con el
número de ofertas a re-puntuar (y posibles llamadas LLM si `OPENAI_API_KEY` está
definida) antes de confirmar.

### Settings (Configuración)

Edita los parámetros operativos del scoring sin tocar `profile.yaml`:

- **Pesos del score** (puesto, skills, ubicación, seniority): deben sumar 1.0.
  La UI valida esto antes de guardar.
- **Deal-breakers**: lista editable, uno por línea. Se persiste en la tabla
  `settings` y el worker la usa en el siguiente run.
- **Umbral de notificación**: puntuación mínima para incluir una oferta en el digest.

Los secretos (Telegram, SMTP, OpenAI) se muestran **solo como booleanos** (✓/✗) —
la UI nunca expone los valores reales de las claves.

### Status (Estado)

Panel de estado del scheduler:

- Último run: timestamp + contadores (buscadas, deduplicadas, puntuadas, nuevas, notificadas).
- Próximo run estimado (último + `schedule_interval_hours`).
- Historial de runs recientes en tabla.

Si el worker aún no ha ejecutado ningún run, muestra el mensaje correspondiente.

---

## Entrega del digest

Después de cada run, el worker envía las nuevas ofertas que superen el umbral
(`strong_fit` y `good_fit` por defecto) a **un solo canal de notificación**:

1. **Telegram** — si `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` están definidos.
2. **Email (SMTP)** — si Telegram no está configurado y `SMTP_HOST` + credenciales están presentes.
3. **Sin notificación** — si ninguno está configurado (skip silencioso; las ofertas
   se puntúan y guardan igualmente).

Solo se notifican ofertas **nuevas** (no vistas en runs anteriores). Las ofertas se
marcan como vistas tras una entrega exitosa, por lo que no se repiten en el siguiente run.

---

## Nota de seguridad

La UI de Streamlit **no tiene autenticación integrada** — es una herramienta personal
local. Mientras solo sea accesible desde `localhost`, no hay riesgo de exposición.

Si la expones fuera de localhost (en un servidor o VPS), **pon la UI detrás de un
reverse proxy con autenticación** (por ejemplo, Nginx + autenticación básica, Caddy,
Traefik) o accede únicamente a través de VPN. Sin esta capa, cualquier persona con
acceso a la red puede usar la UI.

En v2.0 no existe ningún endpoint HTTP público ni autenticación por cabecera — la
app es standalone y no expone ninguna API REST.

---

## Stack

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Gestión de dependencias | uv |
| UI | Streamlit (multipage via `st.navigation`) |
| Scheduler | APScheduler 3.x (BlockingScheduler en proceso worker) |
| Cliente JSearch | httpx async |
| Modelos de datos | Pydantic v2 + Instructor (structured outputs) |
| LLM (enriquecimiento, opcional) | OpenAI API — `OPENAI_API_KEY` opcional; scoring funciona sin él |
| Embeddings (deduplicación + scoring) | BGE-M3 local (FlagEmbedding / sentence-transformers) |
| Persistencia | SQLite local (stdlib `sqlite3`, modo WAL) |
| Tests | pytest |
| Tracing LLM (opcional) | Langfuse stub (no-op sin configuración) |

---

## Correr los tests

```bash
uv run pytest -q
```

La suite cubre: parseo de CV, normalización por fuente, deduplicación semántica,
la heurística de scoring local-first (ranking como peso, deal-breakers, ubicación,
seniority), el cliente JSearch, el pipeline worker, las notificaciones (Telegram y
SMTP) y los helpers de UI.

---

## Legado: n8n (retirado en v2.0)

En v1.0, la orquestación (disparo diario, llamadas a las APIs de empleo, entrega
del digest) la hacía **n8n** por fuera, consumiendo un servicio FastAPI headless
mediante una llamada HTTP. En **v2.0** la app hace su propio fetch (JSearch vía
RapidAPI) y entrega el digest directamente; n8n ya no es necesario.

La documentación histórica del workflow n8n se conserva en
[`docs/archive/n8n/`](docs/archive/n8n/) como referencia, pero ya no forma parte
de la configuración activa.
