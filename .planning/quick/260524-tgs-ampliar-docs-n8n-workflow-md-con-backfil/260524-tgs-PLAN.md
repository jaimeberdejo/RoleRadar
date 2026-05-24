---
phase: quick
plan: 260524-tgs
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/N8N-WORKFLOW.md
autonomous: true
requirements:
  - DOC-01
must_haves:
  truths:
    - "El diagrama del flujo refleja los dos nodos nuevos (Historial + Modo de búsqueda) entre el Schedule y los HTTP de fuentes"
    - "Existe la sección 'Nodo 1.5: Detección de primer run (backfill de 2 meses)' con los dos subnodos (HTTP Historial y Code Modo de búsqueda) y sus snippets exactos"
    - "El Nodo 2b (JSearch) muestra los query params como expresiones que vienen del Code 'Modo de búsqueda', y la subsección multi-query apunta a ese Code sin duplicar lista de queries"
    - "El snippet del Nodo 3 incluye el filtro de 60 días con la variable corte"
    - "El Troubleshooting tiene la fila sobre Always Output Data"
    - "No hay sección ni Code node duplicado que emita queries de forma independiente al Code 'Modo de búsqueda'"
  artifacts:
    - path: "docs/N8N-WORKFLOW.md"
      provides: "Documentación actualizada del workflow n8n con backfill"
      contains: "Nodo 1.5"
  key_links:
    - from: "Sección Nodo 2b multi-query"
      to: "Nodo 1.5 Code Modo de búsqueda"
      via: "referencia textual explícita"
      pattern: "Modo de búsqueda"
---

<objective>
Ampliar `docs/N8N-WORKFLOW.md` para documentar la estrategia de backfill de ~2 meses en el primer run del workflow n8n. En runs posteriores se usa una ventana diaria estrecha (`3days`). La detección de "primer run" es automática: se consulta `GET /jobs/history?limit=1` y si la respuesta es `[]` (BD vacía), es primer run.

Purpose: Que cualquier persona que monte el workflow n8n desde cero tenga instrucciones exactas y copy-paste para activar el backfill automático, sin tener que tocar código Python ni tests.

Output: `docs/N8N-WORKFLOW.md` actualizado con diagrama revisado, nueva sección Nodo 1.5, Nodo 2b y Nodo 3 reconciliados, y una nueva fila en Troubleshooting.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@docs/N8N-WORKFLOW.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Actualizar docs/N8N-WORKFLOW.md con backfill y reconciliación</name>
  <files>docs/N8N-WORKFLOW.md</files>
  <action>
Editar `docs/N8N-WORKFLOW.md` aplicando los cinco cambios descritos a continuación, en el mismo estilo y tono que el resto del fichero (español, tablas Markdown, fences con lenguaje, citas con `>`).

---

**A. Diagrama del flujo** — sustituir el bloque ```...``` existente (líneas ~11-27) por este:

```
Schedule Trigger (08:00)
  │
  ├─ HTTP GET /jobs/history?limit=1    (¿BD vacía = primer run?)
  │
  └─ Code "Modo de búsqueda"           (primer run → ventana 2 meses; si no → 3days;
  │                                     emite 1 item por query)
  │
  ├─ HTTP Request → Arbeitnow API          → array offers (arbeitnow)
  └─ HTTP Request → JSearch (RapidAPI)     → array offers (jsearch, itera por query)
          ↓
  Code (construir ProcessRequest + filtro 60 días en backfill)
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

**B. Nueva sección "Nodo 1.5"** — insertarla entre el bloque `---` que cierra el Nodo 1 (Schedule) y el encabezado `### Nodo 2a` (justo antes de la línea `### Nodo 2a: HTTP Request — Arbeitnow`). Contenido exacto:

---

```markdown
### Nodo 1.5: Detección de primer run (backfill de 2 meses)

#### Por qué

El servicio puntúa cada oferta con OpenAI, así que lanzar una ventana ancha CADA
día desperdiciaría coste. La solución: usar una ventana ancha **solo la primera
vez** (backfill de ~2 meses) y una ventana estrecha el resto. La deduplicación
del servicio absorbe el solape entre días, y el flag `ya_visto` evita que lleguen
las mismas ofertas por Telegram dos veces.

Limitación de JSearch: el parámetro `date_posted` solo acepta `all | today | 3days | week | month`
(no hay "2 meses" nativo). En modo backfill se usa `all` y el Code node del
Nodo 3 aplica un filtro de 60 días sobre el campo `job_posted_at_timestamp` de
cada oferta.

#### Nodo: HTTP Request "Historial"

| Parámetro | Valor |
|-----------|-------|
| Nombre del nodo | `Historial` |
| Método | GET |
| URL | `http://host.docker.internal:8000/jobs/history` (misma base que `/jobs/process`; ver tabla de URLs del Nodo 4) |
| Query params | `limit` = `1` |
| Cabecera | `X-API-Key` con la credencial Header Auth del servicio (si la autenticación está activa; igual que en el Nodo 4) |
| Options → Always Output Data | **ON** — imprescindible |

> **Por qué Always Output Data.** `GET /jobs/history` devuelve un array
> `list[HistoryItem]` (vacío `[]` cuando la BD está vacía, es decir, en el primer
> run). Sin esta opción, n8n no emite ningún item cuando recibe `[]` y el flujo se
> corta antes de llegar al Code siguiente. Con la opción activada, n8n siempre
> emite al menos un item (con json vacío), y el Code "Modo de búsqueda" puede
> evaluar si hay filas reales.

Cada `HistoryItem` tiene los campos: `id`, `title`, `company`, `score_total`,
`recommendation`, `first_seen`, `last_seen`, `score`.

#### Nodo: Code "Modo de búsqueda"

| Parámetro | Valor |
|-----------|-------|
| Tipo | Code (JavaScript) |
| Mode | Run Once for All Items |

Este nodo reemplaza el Code de lista de queries que antes se describía en la
subsección multi-query del Nodo 2b. Ahora hace dos cosas a la vez: **decide la
ventana de búsqueda** (primer run vs. diario) y **emite un item por query**, que
el nodo JSearch itera.

```javascript
// ¿Hay ofertas ya guardadas? BD vacía = primer run = backfill de 2 meses.
const filas = $('Historial').all().filter(i => i.json && i.json.id);
const primerRun = filas.length === 0;

const datePosted = primerRun ? 'all'  : '3days';
const numPages   = primerRun ? '10'   : '1';

// Un puesto de tu ranking por línea (ajusta a tu profile.yaml):
const puestos = [
  'AI Engineer in Barcelona',
  'ML Engineer in Barcelona',
  'Data Engineer remote',
  'MLOps Engineer remote',
];

return puestos.map(query => ({
  json: { query, date_posted: datePosted, num_pages: numPages },
}));
```

> **Por qué filtrar por `i.json.id`.** Cuando la BD está vacía, `Always Output
> Data` mete un item con json vacío (sin `id`). Filtrando por `i.json.id` solo
> cuentan las filas reales. En el primer run `filas.length === 0` → `primerRun =
> true` → se usa `all` con 10 páginas (histórico ancho). A partir del segundo run,
> `3days` con 1 página (incremental; el solape lo absorbe el dedup del servicio).

---
```

---

**C. Nodo 2b — actualizar query params y reconciliar multi-query**

En la tabla de query parameters del Nodo 2b, reemplazar los valores fijos por expresiones. La tabla debe quedar:

| Parámetro | Valor (expresión n8n) | Descripción |
|-----------|------------------------|-------------|
| `query` | `={{ $json.query }}` | Viene del Code "Modo de búsqueda" (Nodo 1.5) |
| `page` | `1` | Página de resultados |
| `num_pages` | `={{ $json.num_pages }}` | 10 en primer run, 1 en diario |
| `date_posted` | `={{ $json.date_posted }}` | `all` en primer run, `3days` en diario |

A continuación, reemplazar la subsección `#### Buscar varios puestos a la vez (multi-query)` completa por el siguiente texto que reconcilia sin duplicar:

```markdown
#### Buscar varios puestos a la vez (multi-query)

El nodo JSearch itera una vez por item de entrada: el **Code "Modo de búsqueda"
(Nodo 1.5)** emite un item por puesto (con `query`, `date_posted` y `num_pages`)
y JSearch ejecuta una llamada HTTP por cada uno. No necesitas un Code node
adicional aquí; la lista de puestos y la ventana de búsqueda viven en el Nodo 1.5.

> **Duplicados:** si dos queries devuelven la misma oferta, **el servicio la
> deduplica** (hash exacto + semántico con BGE-M3). Manda todo crudo sin
> preocuparte.
>
> **Rate limit:** cada query es **1 llamada a RapidAPI**. 4 queries/día ≈
> 120/mes — revisa tu tier de JSearch y reduce queries o frecuencia si vas justo.

**Para añadir más fuentes** (FlyByAPIs u otras): añadir otro nodo HTTP Request
con el nombre correspondiente y añadir una entrada más en el array `sources`
del Code node con el valor `"source"` apropiado (`"generic"` para cualquier
fuente sin mapper dedicado).
```

---

**D. Nodo 3 — reemplazar el snippet con el filtro de 60 días**

Reemplazar el bloque ```javascript...``` del Nodo 3 (el snippet actual con `const arbeitnow` y `const jsearch`) por:

```javascript
const arbeitnow = $('Arbeitnow').first().json.data || [];

// JSearch emite un item por query (ver Nodo 1.5). .all() + flatMap junta todas las ofertas.
let jsearch = $('JSearch').all().flatMap(i => i.json.data || []);

// Backfill: recorta a los últimos 60 días por job_posted_at_timestamp (Unix s).
// No-op en modo diario (date_posted=3days ya las acota); conserva las que no traen timestamp.
const corte = Math.floor(Date.now() / 1000) - 60 * 24 * 60 * 60;
jsearch = jsearch.filter(o => !o.job_posted_at_timestamp || o.job_posted_at_timestamp >= corte);

return [{
  json: {
    sources: [
      { source: 'arbeitnow', offers: arbeitnow },
      { source: 'jsearch',   offers: jsearch   },
    ],
  },
}];
```

Añadir justo debajo del snippet (antes del párrafo "Si los nodos 2a/2b...") este párrafo explicativo:

> **Filtro de 60 días:** en modo backfill (`date_posted=all`), JSearch puede
> devolver ofertas muy antiguas. El filtro por `job_posted_at_timestamp` (campo
> Unix en segundos presente en las respuestas de JSearch) recorta a los últimos
> 60 días. En modo diario (`date_posted=3days`) el filtro es prácticamente un
> no-op porque las ofertas ya están acotadas por la API; y si falta el campo
> timestamp, la oferta pasa igualmente (no se descarta por falta de dato).

---

**E. Troubleshooting — añadir fila al final de la tabla**

Añadir esta fila al final de la tabla de Troubleshooting (antes del `---` o fin de la tabla):

| El flujo no hace nada el primer día / no llegan ofertas | El nodo `Historial` no tiene `Always Output Data` activado: devolvió `[]` → 0 items → el flujo se corta antes del Code "Modo de búsqueda" | Activar `Options → Always Output Data` en el nodo `Historial` |

---

**Reglas de coherencia a verificar antes de guardar:**

- El fichero NO debe contener dos Code nodes distintos que emitan la lista de queries. La subsección multi-query del Nodo 2b ya no debe tener su propio snippet de Code con la lista de puestos — ese snippet fue reemplazado por la redacción del punto C.
- Las referencias internas existentes ("ver Nodo 3", "ver Nodo 2b", "ver Nodo 4") deben seguir siendo válidas.
- No tocar los nodos 4-8, la sección Seguridad, Mapeo, Programación y costes, ni el enlace final al README, salvo lo indicado explícitamente.
  </action>
  <verify>
    <automated>grep -c "Nodo 1.5" /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/docs/N8N-WORKFLOW.md</automated>
  </verify>
  <done>
- `docs/N8N-WORKFLOW.md` contiene la sección "Nodo 1.5" con los dos subnodos (HTTP Historial + Code Modo de búsqueda) y sus snippets exactos.
- El diagrama ASCII refleja los dos nodos nuevos entre Schedule y los HTTP de fuentes.
- El Nodo 2b muestra los cuatro query params como expresiones y la subsección multi-query no duplica el Code de queries.
- El snippet del Nodo 3 incluye la variable `corte` y el filtro de 60 días.
- La tabla de Troubleshooting tiene la nueva fila sobre `Always Output Data`.
- El fichero es Markdown válido (no hay fences sin cerrar ni encabezados rotos).
  </done>
</task>

</tasks>

<verification>
```bash
# Confirmar que la sección Nodo 1.5 existe
grep -n "Nodo 1.5" docs/N8N-WORKFLOW.md

# Confirmar que el snippet del Code "Modo de búsqueda" está presente
grep -n "primerRun" docs/N8N-WORKFLOW.md

# Confirmar que el filtro de 60 días está en el Nodo 3
grep -n "corte" docs/N8N-WORKFLOW.md

# Confirmar que NO hay dos snippets con la lista de puestos (no debe haber dos return con 'AI Engineer in Barcelona')
grep -c "AI Engineer in Barcelona" docs/N8N-WORKFLOW.md
# Debe ser 1 (solo en el Code "Modo de búsqueda", no en multi-query del 2b)

# Confirmar que los query params de JSearch son expresiones
grep -n 'date_posted.*\$json' docs/N8N-WORKFLOW.md

# Confirmar la fila de Troubleshooting sobre Always Output Data
grep -n "Always Output Data" docs/N8N-WORKFLOW.md
```
</verification>

<success_criteria>
`docs/N8N-WORKFLOW.md` actualizado y coherente:
- Diagrama revisado con los dos nodos nuevos.
- Sección Nodo 1.5 completa (HTTP Historial + Code Modo de búsqueda, snippets exactos, explicaciones).
- Nodo 2b con expresiones en query params y subsección multi-query reconciliada (sin Code duplicado).
- Nodo 3 con filtro de 60 días y párrafo explicativo.
- Troubleshooting con la nueva fila.
- Un solo lugar en el fichero que emite la lista de queries (Nodo 1.5); el Nodo 2b ya no tiene su propio snippet de Code con puestos.
</success_criteria>

<output>
Tras completar la tarea, crear `.planning/quick/260524-tgs-ampliar-docs-n8n-workflow-md-con-backfil/260524-tgs-SUMMARY.md` con:
- Qué se cambió y por qué (decisiones de edición no triviales).
- Verificación ejecutada y resultado.
- Commit hash.
</output>
