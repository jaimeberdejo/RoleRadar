# CLAUDE.md — BuscadorDeEmpleo

## Qué es este proyecto
**Agregador inteligente de ofertas de empleo.** Un **servicio Python (FastAPI)** que
recibe ofertas, las **normaliza**, **deduplica** (semántico) y las **puntúa contra el
perfil real** del usuario (CV + ranking de puestos + preferencias). La orquestación
diaria (disparo, llamadas a APIs de empleo, entrega por email o telegram o en un dashboard propio) la hace **n8n** por
fuera, llamando a este servicio por HTTP.

### Doble propósito
1. **Herramienta real** para la búsqueda activa de empleo de Jaime (AI Engineer, base
   en Barcelona, abierto a remoto) y **pieza de portfolio** → la **calidad de ingeniería importa**.
2. **Proyecto final para consolidar TODO lo aprendido** en el curso de automatización con
   IA (`~/projects/AprendeAutomatizar/MENTOR.md`). Junta las 5 fases:
   - **Fase 1 (RPA + IA / n8n):** la orquestación externa que dispara y entrega.
   - **Fase 2 (IDP / lectura de documentos):** parseo del **CV en PDF** → `CVProfile`.
   - **Fase 3 (RAG / embeddings):** **deduplicación semántica** y matching CV↔oferta.
   - **Fase 4 (agentes / LLM):** el **scoring** con juicio del LLM.
   - **Fase 5 (integración):** este servicio + n8n, todo junto.


## Arquitectura general (LÉEME PRIMERO)
Esto es la VERSIÓN HÍBRIDA. Construye un SERVICIO Python (FastAPI) que expone
las piezas inteligentes vía API REST. La orquestación (disparo diario, llamadas
a las APIs de empleo, entrega por email) la hará n8n por fuera, llamando a este
servicio. Por tanto:
- TÚ construyes: el servicio Python con sus endpoints, la lógica de
  normalización, deduplicación semántica, scoring con LLM, y persistencia.
- n8n (fuera de scope de este código, pero diseña pensando en ello): dispara
  cada mañana, llama a las APIs de empleo, manda las ofertas crudas a tu
  servicio, recibe las puntuadas, y entrega el digest.

El servicio debe ser consumible por n8n vía HTTP con JSON limpio de entrada/salida.

## Contexto
Estoy en búsqueda activa como AI Engineer (base en Barcelona, abierto a remoto).
El sistema recibe ofertas, las puntúa contra MI perfil real (incluido mi CV) y
contra un RANKING de puestos a los que opto, elimina duplicados, persiste, y
devuelve las ofertas puntuadas y ordenadas. Lo usaré de verdad y lo enseñaré en
mi portfolio, así que la calidad de ingeniería importa.

## Stack
- Python 3.11+, deps con uv (fallback venv+pip)
- FastAPI + uvicorn para el servicio
- httpx async para cualquier llamada saliente
- Pydantic v2 + Instructor para structured outputs
- LLM scoring: API de Anthropic (claude), key desde ANTHROPIC_API_KEY
- Embeddings (dedup + matching CV): BGE-M3 (sentence-transformers o
  FlagEmbedding; elige y justifica)
- Parseo de CV: soporta PDF (mi CV está en PDF). Usa pymupdf para extraer texto.
- Persistencia: SQLite local (stdlib sqlite3), ruta vía SQLITE_DB_PATH (default
  data/jobs.db). [Actualizado 2026-05-23: Supabase/pgvector eliminado del alcance —
  herramienta personal local; el dedup calcula embeddings en memoria por run, así que
  pgvector no se usa.]
- Observabilidad: deja la integración con Langfuse preparada (interfaz) para
  trazar las llamadas de scoring.
- Tests: pytest. NUNCA hardcodees credenciales: .env + python-dotenv + .env.example

## Perfil del usuario (entrada de configuración)
El perfil debe ser configurable SIN tocar código, en un fichero (profile.yaml) y
en mi CV (fichero PDF). Define un schema Pydantic `UserProfile` que recoja:

- datos_personales: { nombre, email, telefono, ubicacion_actual, derecho_a_
  trabajar_en (ej. UE/España), idiomas: [{idioma, nivel}] }
- preferencias_ubicacion: {
    ciudades_preferidas: [str],        # ej. ["Barcelona"]
    pais: str,
    dispuesto_a_reubicarse: bool
  }
- preferencia_remoto: {
    modalidad_ideal: enum(remote/hybrid/onsite/indiferente),
    acepta_onsite_solo_en: [str]       # ciudades donde sí iría presencial
  }
- ranking_puestos: lista ORDENADA de puestos a los que opto, de mayor a menor
  prioridad. Ejemplo de partida (que ajustaré en profile.yaml):
      1. "Ingeniero de IA / AI Engineer"
      2. "Ingeniero de ML / ML Engineer"
      3. "Ingeniero de datos / Data Engineer"
      4. "MLOps Engineer"
  Cada entrada puede tener sinónimos/variantes para ayudar al match
  (ej. "AI Engineer", "LLM Engineer", "GenAI Engineer").
- expectativas (opcional): { salario_minimo, tipo_contrato_preferido }
- deal_breakers: [str]                 # cosas que descartan una oferta de plano
                                       # ej. "exige 5+ años", "presencial fuera de Barcelona"

El CV se parsea aparte (ver siguiente sección) y se combina con este perfil.

## Parseo del CV
Endpoint o función que recibe mi CV en PDF y extrae una representación
estructurada `CVProfile` con Pydantic + Instructor (LLM):
- experiencia: [{empresa, rol, duracion, tecnologias, logros}]
- skills_tecnicas: [str]
- formacion: [{titulo, institucion, año}]
- años_experiencia_total (estimado)
- dominios: [str]   # ej. finanzas, regulación

Este CVProfile se cachea (no re-parsear el CV en cada run; solo si cambia).
El scoring usará el CVProfile real, NO una lista de skills escrita a mano, para
que la comparación oferta-vs-candidato se base en mi experiencia verdadera.

## Modelo de datos de ofertas
Schema Pydantic `Job` que normaliza ofertas de cualquier fuente (las fuentes las
llamará n8n y me las enviará; mi servicio las normaliza):
- id (hash estable de empresa+titulo+ubicacion), title, company, location,
  remote (enum remote/hybrid/onsite/unknown), description, salary (opcional
  estructurado), url, source, posted_at, raw (payload original)

Endpoint que acepta una lista de ofertas crudas heterogéneas + un identificador
de fuente, y devuelve Jobs normalizados. El parseo por fuente debe estar aislado
y claramente marcado (no asumas formatos de API de memoria; deja funciones de
mapeo que yo ajustaré contra respuestas reales).

## Deduplicación (semántica, es una de las piezas "inteligentes")
Dos niveles:
1. Hash exacto: empresa + título normalizado.
2. Semántico: embeddings BGE-M3 de (título + empresa + primeras N palabras de
   descripción), agrupar por similitud coseno sobre umbral configurable.
Al deduplicar, conserva la oferta con descripción más completa y guarda las URLs
alternativas. Umbral configurable y justificado.

## Scoring con LLM — LA HEURÍSTICA (núcleo del proyecto)
Para cada oferta única, llamada al LLM con Instructor que devuelve `JobScore`:
- score_total (0-100)
- recommendation (enum strong_fit/good_fit/maybe/skip)
- desglose: {
    encaje_puesto (0-100),       # según el RANKING de puestos
    encaje_skills (0-100),       # oferta vs CVProfile real
    encaje_ubicacion (0-100),    # según preferencias + remoto
    encaje_seniority (0-100)     # nivel pedido vs mi experiencia real
  }
- puesto_detectado: str          # a qué entrada del ranking corresponde, o "fuera de ranking"
- rango_puesto: int|null         # posición en mi ranking (1 = top), null si no encaja ninguno
- reasons_for: [str]
- reasons_against: [str]         # honesto, sin inflar
- matched_skills: [str]          # mis skills reales que la oferta pide
- missing_requirements: [str]    # lo que piden y podría no cumplir
- deal_breaker_hit: bool + cual   # si dispara algún deal_breaker

REGLAS DE LA HEURÍSTICA (impleméntalas explícitamente, combinando lógica
determinista + juicio del LLM; no lo dejes todo al LLM a ciegas):

1. RANKING DE PUESTOS COMO PESO, NO COMO FILTRO BINARIO:
   - Una oferta que casa con el puesto nº1 del ranking recibe el máximo peso de
     encaje_puesto; cada posición más abajo reduce ese peso de forma graduada
     (define una función de decaimiento configurable, ej. lineal o por tramos).
   - Una oferta fuera del ranking no se descarta automáticamente, pero su
     encaje_puesto es bajo. Que el LLM razone si aun así merece "maybe".

2. UBICACIÓN Y REMOTO:
   - Si la oferta es remote y mi preferencia lo permite → encaje_ubicacion alto.
   - Si es onsite/hybrid, solo encaje alto si la ciudad está en mis ciudades
     preferidas o en acepta_onsite_solo_en. Si es presencial fuera de eso y no
     estoy dispuesto a reubicarme → encaje_ubicacion muy bajo (y posible
     deal_breaker).

3. SENIORITY:
   - Compara los años/nivel pedidos contra mi experiencia real del CVProfile.
   - Pedir bastante más de lo que tengo baja encaje_seniority y debe aparecer en
     missing_requirements, pero NO descarta solo (a veces los requisitos están
     inflados); que el LLM lo matice.

4. DEAL BREAKERS:
   - Si se dispara un deal_breaker, recommendation = skip y deal_breaker_hit=true,
     explicando cuál. Esto SÍ es filtro duro.

5. SCORE_TOTAL:
   - Combinación PONDERADA de los cuatro sub-encajes, con pesos configurables en
     profile.yaml (ej. puesto 35%, skills 30%, ubicación 20%, seniority 15%).
     Documenta los pesos por defecto y hazlos fáciles de ajustar.

El prompt al LLM debe incluir: mi CVProfile, mi ranking de puestos con sinónimos,
mis preferencias de ubicación/remoto, mis deal_breakers, y la oferta. Debe ser
HONESTO en reasons_against y missing_requirements: el valor es filtrar bien.

## Endpoints del servicio (lo que n8n consumirá)
- POST /cv/parse        → sube CV (PDF), devuelve y cachea CVProfile
- GET  /profile         → devuelve el UserProfile cargado
- POST /jobs/normalize  → recibe ofertas crudas + source, devuelve Jobs
- POST /jobs/process    → recibe ofertas crudas (de varias fuentes), hace
                          normalización + dedup + scoring y devuelve las ofertas
                          únicas puntuadas y ordenadas por score_total. Marca las
                          ya vistas en runs anteriores.
- POST /jobs/score      → (opcional, granular) puntúa una lista de Jobs ya
                          normalizados
- GET  /jobs/history    → ofertas guardadas con su score y fecha

Pensado para n8n: entradas y salidas JSON simples, errores con códigos HTTP
claros, y que una oferta mal formada no tumbe el batch entero (procesa lo que
puedas, reporta lo que falló).

## Persistencia
SQLite local (stdlib sqlite3, sin nube; ruta vía SQLITE_DB_PATH). Guarda
ofertas con fecha (histórico para ver evolución) y control de "ya notificadas"
para que n8n no repita ofertas entre días.
[Actualizado 2026-05-23: antes Supabase+pgvector; eliminado del alcance — el dedup
calcula embeddings en memoria por run, así que pgvector no aporta. Si en el futuro se
quisiera DB en red, el Protocol `app/storage/protocol.py` permite añadir otro backend.]

## Calidad de ingeniería (importa para portfolio)
- Estructura modular: api/ (endpoints), models/, cv/ (parseo), dedup/, scoring/
  (incluida la heurística), storage/, config/ (carga de profile.yaml).
- Type hints en todo. Manejo de errores por capa. Logging estructurado (cuántas
  ofertas entran, duplicados detectados, puntuadas, coste/nº llamadas LLM).
- Tests pytest: parseo CV (con fixture PDF de ejemplo), normalización por fuente,
  dedup (detecta duplicados obvios y casos semánticos), y sobre todo la
  HEURÍSTICA de scoring (que el ranking pesa bien, que un deal_breaker fuerza
  skip, que ubicación se evalúa correcto). Mockea LLM y embeddings donde toque.
- README: instalación, .env, cómo editar profile.yaml, cómo subir el CV, cómo
  arrancar el servicio, y una SECCIÓN dedicada a "Integración con n8n" (ver abajo).
- Incluye un profile.yaml de ejemplo prerrellenado y un par de ofertas de ejemplo
  (JSON) para probar /jobs/process de inmediato sin n8n.

## Sección README: Integración con n8n
Documenta (no implementes en n8n, solo explica) cómo se conecta:
- Qué nodos de n8n llaman a qué endpoints.
- Flujo: Schedule → HTTP a las APIs de empleo (Arbeitnow, JSearch, FlyByAPIs)
  → Merge → HTTP Request a POST /jobs/process de este servicio → Filter por
  score → guardar/entregar por email.
- Formato exacto del JSON que n8n debe mandar a /jobs/process y el que recibe.
- Cómo exponer el servicio para que n8n lo alcance (localhost en dev; nota sobre
  desplegarlo accesible en prod).

## Cómo quiero que trabajes (IMPORTANTE)
Aunque quiero el sistema completo, NO lo escribas todo de un tirón. Trabaja por
fases y PÁRATE a que yo confirme entre cada una:

FASE 1: Propón estructura de carpetas, los schemas Pydantic (UserProfile,
CVProfile, Job, JobScore con su desglose), el profile.yaml de ejemplo, y el
diseño de los endpoints. Para aquí y espera mi OK. Sin lógica todavía.

FASE 2: Parseo de CV (PDF → CVProfile) + su test con un PDF de ejemplo. Para y OK.

FASE 3: Normalización + deduplicación semántica + tests. Para y OK.

FASE 4: LA HEURÍSTICA de scoring (lógica determinista + LLM, ranking como peso,
ubicación, seniority, deal breakers, score ponderado) + tests exhaustivos de la
heurística. Para y OK. ← Es la fase más importante, dale el cuidado que merece.

FASE 5: Endpoints FastAPI que orquestan todo, persistencia (SQLite local;
Supabase eliminado del alcance 2026-05-23), control de ya-vistas, README con la
sección de n8n.

En cada fase explica las decisiones de diseño no triviales. Pregunta si algo no
está claro en vez de asumir. No metas dependencias pesadas innecesarias.

---

<!-- Lo de arriba es el spec autoritativo escrito a mano. Lo de abajo lo gestiona
     GSD entre marcadores <!-- GSD:* --> y se actualiza solo; no editar a mano. -->

<!-- GSD:project-start source:PROJECT.md -->
## Project

**BuscadorDeEmpleo**

Agregador inteligente de ofertas de empleo: un **servicio Python (FastAPI) headless**
que recibe ofertas crudas, las **normaliza**, **deduplica semánticamente** y las
**puntúa contra el perfil real de Jaime** (CV en PDF + ranking de puestos +
preferencias). La orquestación diaria (disparo, llamadas a APIs de empleo, entrega
por email/telegram) la hace **n8n por fuera**, consumiendo este servicio vía HTTP/JSON.

**Core Value:** Puntuar y filtrar ofertas con **honestidad** contra el perfil REAL de Jaime (su CV
verdadero, no skills escritas a mano), de forma que el ranking de puestos pese de
forma graduada y los deal-breakers filtren en duro. Si todo lo demás falla, **la
heurística de scoring** (FASE 4) debe funcionar y ser confiable.
<!-- GSD:project-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->