# ── BuscadorDeEmpleo — Dockerfile ────────────────────────────────────────────
# Base: imagen oficial de Astral (uv + Python 3.13 ya incluidos).
# Elegida sobre "python:3.13-slim + RUN pip install uv" porque:
#   - Es la forma canónica recomendada por Astral para producción.
#   - Evita un layer extra de instalación de uv.
#   - Python 3.13 coincide con requires-python del pyproject.toml.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# ── Dependencias (cache-friendly) ────────────────────────────────────────────
# Copiar solo los manifiestos primero para aprovechar el cache de layers de Docker.
# El código fuente (que cambia más frecuentemente) se copia después.
COPY pyproject.toml uv.lock ./

# Instalar dependencias de producción (sin el grupo dev/tests).
# --frozen: usa exactamente uv.lock sin resolver de nuevo.
# --no-dev: excluye dependencias del grupo [dev] (pytest, etc.).
RUN uv sync --frozen --no-dev

# ── Código fuente ─────────────────────────────────────────────────────────────
COPY app/ ./app/

# Copiar data/ para el profile.yaml.
# NOTA: la DB jobs.db NO se copia — viene del volumen montado en runtime.
COPY data/ ./data/

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000

# Ruta explícita del cache de HuggingFace dentro del contenedor.
# Permite montar el volumen en una ruta conocida sin depender de $HOME del
# usuario del contenedor (que varía según cómo se construya la imagen).
ENV HF_HOME=/app/.cache/huggingface

# NOTE: BGE-M3 (~2.3 GB) se descarga en la primera llamada a /jobs/process.
# Montar volumen hf_cache en /app/.cache/huggingface para persistir el modelo
# entre reinicios del contenedor y evitar re-descargas (ver docker-compose.yml).

# SECRETS: OPENAI_API_KEY se inyecta NUNCA en esta imagen.
# Se inyecta en runtime vía env_file en docker-compose.yml.
# No hay ARG ni ENV con credenciales en este Dockerfile.

CMD ["uv", "run", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
# --host 0.0.0.0: crítico para que el servicio sea accesible desde fuera del contenedor.
# Sin --reload: modo producción; reload requiere watchfiles y es para desarrollo local.
