# Load .env into os.environ for local runs (uv run / streamlit run). In Docker the
# `env_file: .env` directive handles this, but a local launch needs load_dotenv() or
# secrets in .env (RAPIDAPI_KEY, OPENAI_API_KEY, TELEGRAM_*, SMTP_*) are silently ignored.
# Kept in the entry point (not app/ core) so the core stays import-clean.
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import streamlit as st

# st.set_page_config MUST be the first Streamlit call in the script.
# Calling it after any other st.* call raises StreamlitAPIException (Pitfall 6).
st.set_page_config(page_title="BuscadorDeEmpleo", page_icon=":material/work:", layout="wide")

cv_page       = st.Page("pages/cv.py",       title="CV",            icon=":material/description:")
search_page   = st.Page("pages/search.py",   title="Búsqueda",      icon=":material/search:")
results_page  = st.Page("pages/results.py",  title="Resultados",    icon=":material/work:", default=True)
settings_page = st.Page("pages/settings.py", title="Configuración", icon=":material/settings:")
status_page   = st.Page("pages/status.py",   title="Estado",        icon=":material/schedule:")

pg = st.navigation([cv_page, search_page, results_page, settings_page, status_page])
pg.run()
