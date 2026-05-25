"""CV upload page (UI-01) — thin Streamlit page.

Delegates the cache-first resolution logic to ui.cv_logic.resolve_cv_profile
so the core behaviour is unit-testable without a Streamlit runtime.

States (per 10-UI-SPEC.md):
- empty:   No file uploaded → info banner with Spanish copy.
- cache hit: Render CVProfile with a caption noting it came from cache (no re-parse).
- cache miss: Spinner while parsing, then render CVProfile.
- error: st.error with Spanish copy; keep the uploader so the user can retry.

Security (threat model T-10-04-01 / T-10-04-02):
- st.file_uploader(type=["pdf"]) restricts at the widget level.
- PDF bytes are only forwarded through the sha256-keyed cache and parse_cv;
  they are never written to arbitrary paths by this page.
- NEVER displays secrets.
"""
from __future__ import annotations

import streamlit as st

from ui.cv_logic import resolve_cv_profile


def _render_cv_profile(profile) -> None:
    """Render a parsed CVProfile using Streamlit built-in widgets."""
    st.subheader("Resumen")
    if profile.anios_experiencia_total is not None:
        st.metric("Años de experiencia estimados", f"{profile.anios_experiencia_total:.1f}")

    if profile.dominios:
        st.write("**Dominios:**", ", ".join(profile.dominios))

    if profile.skills_tecnicas:
        st.subheader("Skills técnicas")
        st.write(", ".join(profile.skills_tecnicas))

    if profile.experiencia:
        st.subheader("Experiencia")
        for exp in profile.experiencia:
            with st.expander(f"{exp.rol} — {exp.empresa}"):
                if exp.duracion:
                    st.write(f"**Duración:** {exp.duracion}")
                if exp.tecnologias:
                    st.write(f"**Tecnologías:** {', '.join(exp.tecnologias)}")
                if exp.logros:
                    for logro in exp.logros:
                        st.write(f"- {logro}")

    if profile.formacion:
        st.subheader("Formación")
        for form in profile.formacion:
            parts = [form.titulo]
            if form.institucion:
                parts.append(form.institucion)
            if form.anio:
                parts.append(str(form.anio))
            st.write(" | ".join(parts))


# ── Page body ────────────────────────────────────────────────────────────────

st.header("CV")

uploaded = st.file_uploader(
    "Sube tu CV en PDF — se cachea y no se vuelve a parsear si no cambia.",
    type=["pdf"],
)

if uploaded is None:
    st.info("Aún no has subido un CV. El scoring de skills usará un perfil vacío.")
else:
    pdf_bytes: bytes = uploaded.read()

    try:
        with st.spinner("Procesando CV…"):
            profile, was_cached = resolve_cv_profile(pdf_bytes)

        if was_cached:
            st.caption("Perfil cargado de caché (mismo PDF, no se re-parsea).")
        else:
            st.success("CV parseado y guardado en caché.")

        _render_cv_profile(profile)

    except Exception as exc:  # noqa: BLE001
        st.error(
            f"No se pudo parsear el CV: {exc}. Revisa que sea un PDF válido."
        )
