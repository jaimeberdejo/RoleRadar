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
# Ruta explícita del cache de HuggingFace dentro del contenedor.
# Permite montar el volumen en una ruta conocida sin depender de $HOME del
# usuario del contenedor (que varía según cómo se construya la imagen).
ENV HF_HOME=/app/.cache/huggingface

# Copiar el entrypoint del worker y crear el directorio de la UI.
# El worker.py es el entrypoint del contenedor `worker` en docker-compose.yml.
# ui/ contiene la app Streamlit (Phase 10); el placeholder asegura que el
# directorio exista en la imagen antes de que compose inyecte el command.
COPY worker.py ./
RUN mkdir -p ui

# SECRETS: OPENAI_API_KEY nunca se inyecta en esta imagen.
# Se inyecta en runtime vía env_file en docker-compose.yml.
# No hay ARG ni ENV con credenciales en este Dockerfile.

# Neutral CMD — cada servicio define su propio `command:` en docker-compose.yml.
# ui:     uv run streamlit run ui/app.py --server.port 8501
# worker: uv run python worker.py
CMD ["uv", "run", "python", "-c", "print('Use: docker compose up')"]
