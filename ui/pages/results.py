"""Results page (UI-03, UI-04, UI-07, UI-08) — BuscadorDeEmpleo v2.0.

This page is the centre of the app. It provides:
  - UI-03: Sortable/filterable st.dataframe of all scored offers.
  - UI-04: Full score breakdown on row selection (4 sub-scores, reasons,
           skills, deal-breaker info, apply URL link).
  - UI-07/SC4: "Run now" button that launches the shared pipeline in a
               background thread (non-blocking), disables while running,
               refreshes on completion.
  - UI-08: "Re-score stored" behind a cost/count confirmation (no re-fetch).

Design constraints (from CONTEXT.md):
  - D-04/D-05: background thread, embedder injected (no 2nd BGE-M3 load).
  - D-06: double-run guard via _RUN_STATUS["running"] + start_run() guard.
  - D-09: rescore_stored does NOT re-fetch; description not stored → encaje_skills neutral.
  - D-10: st.dataframe on_select="rerun" + selection_mode="single-row".
  - T-10-05-01: OPENAI_API_KEY shown as boolean only — value NEVER rendered.
  - T-10-05-04: url/remote accessed via .get() — no KeyError on missing keys.

Security (threat model, 10-05):
  - T-10-05-01: `bool(os.getenv("OPENAI_API_KEY"))` only; value never passed to st.*.
  - T-10-05-02: button disabled while _RUN_STATUS["running"]; start_run() double-run guard.
  - T-10-05-03: Re-score shows N jobs + OpenAI presence before running.
  - T-10-05-04: row.get("url") — absent URL skipped silently.
  - T-10-05-05: background thread lives in services.py; never calls st.*.

Page-render body is gated by streamlit.runtime.exists() so importing this
module under pytest does not require a Streamlit runtime (D-12 pattern).
"""
from __future__ import annotations

import os

from ui.results_logic import (
    build_results_df,
    filter_history,
    run_status_label,
)


def _render() -> None:
    """Streamlit page body for Results (UI-03/04/07/08)."""
    import streamlit as st

    import ui.services as _svc
    from ui.services import get_embedder, get_storage, start_run

    st.header("Resultados")

    # ------------------------------------------------------------------
    # UI-07/SC4: Run now button + live status fragment
    # ------------------------------------------------------------------
    col_run, col_rescore = st.columns([1, 1])

    with col_run:
        if st.button(
            "▶ Run now",
            disabled=_svc._RUN_STATUS["running"],
            type="primary",
            key="btn_run_now",
        ):
            started = start_run()
            if started:
                # WR-05: clear any stale completed-run headline before the new run.
                st.session_state.pop("_last_run_summary", None)
                st.rerun()

    # If a previous poll stashed a completed-run headline, render it so it
    # survives across reruns (WR-05). It is shown once the run is no longer
    # in progress and is cleared on the next explicit Run now.
    _last_summary = st.session_state.get("_last_run_summary")
    if _last_summary and not _svc._RUN_STATUS["running"]:
        st.success(_last_summary)

    # Polling fragment — D-04: only fragments rerun every 2 s while running
    @st.fragment(run_every="2s" if _svc._RUN_STATUS["running"] else None)
    def _poll():
        state, msg = run_status_label(_svc._RUN_STATUS)
        if state == "running":
            st.status(msg, state="running")
        elif state == "done":
            st.success(msg)
            # WR-05: stash the completed summary BEFORE clearing the result so
            # the headline survives the rerun (the count is otherwise discarded).
            st.session_state["_last_run_summary"] = msg
            # WR-01: clear through the lock-guarded service helper, not by
            # reaching into the module global, so we never race the thread.
            _svc.clear_run_result()
            st.rerun()
        elif state == "error":
            st.error(msg)
            # WR-01: clear the error through the lock-guarded service helper.
            _svc.clear_run_error()

    _poll()

    # ------------------------------------------------------------------
    # UI-08: Re-score stored (no fetch) button + cost/count confirmation
    # ------------------------------------------------------------------
    with col_rescore:
        if st.button("↻ Re-score stored", key="btn_rescore"):
            st.session_state["_rescore_confirm"] = True

    if st.session_state.get("_rescore_confirm"):
        storage = get_storage()
        n_jobs = len(storage.get_history(limit=10000))

        # T-10-05-01: show OpenAI as boolean — NEVER the key value
        openai_present = bool(os.getenv("OPENAI_API_KEY"))
        openai_label = "OpenAI configurado: ✓" if openai_present else "OpenAI: ✗"

        st.warning(
            f"Esto re-puntúa **{n_jobs}** ofertas con los pesos actuales "
            f"(sin re-buscar). "
            f"Si hay OPENAI_API_KEY, hará **{n_jobs}** llamadas LLM. "
            f"({openai_label})\n\n"
            f"**Nota:** se re-aplican los pesos y se recalculan los ejes "
            f"deterministas (puesto, ubicación, seniority) y los deal-breakers. "
            f"El eje **encaje_skills se PRESERVA del scoring original** — no se "
            f"recalcula ni se degrada, porque la descripción no se almacena (WR-07). "
            f"Útil para ajustar pesos y deal-breakers sin perder el match de skills.\n\n"
            f"¿Continuar?"
        )
        confirm_col, cancel_col = st.columns([1, 1])
        with confirm_col:
            if st.button("Sí, re-puntuar", key="btn_rescore_confirm"):
                from app.pipeline import rescore_stored  # noqa: PLC0415

                with st.spinner("Re-puntuando…"):
                    res = rescore_stored(
                        storage=get_storage(),
                        embedder=get_embedder(),
                        profile_path=None,
                    )
                st.session_state["_rescore_confirm"] = False
                st.success(f"Re-puntuadas {res.scored} ofertas.")
                st.rerun()
        with cancel_col:
            if st.button("Cancelar", key="btn_rescore_cancel"):
                st.session_state["_rescore_confirm"] = False
                st.rerun()

    # ------------------------------------------------------------------
    # UI-03: List + filters
    # ------------------------------------------------------------------
    storage = get_storage()
    history = storage.get_history(limit=500)

    if not history:
        st.info("No hay ofertas puntuadas todavía. Pulsa «Run now» o espera al worker.")
        return

    # Filters
    filter_col1, filter_col2 = st.columns([1, 2])
    with filter_col1:
        min_score = st.slider("Score mínimo", 0, 100, 0, key="results_min_score")
    with filter_col2:
        recs = st.multiselect(
            "Recomendación",
            options=["strong_fit", "good_fit", "maybe", "skip"],
            default=["strong_fit", "good_fit", "maybe"],
            key="results_recs",
        )

    filtered = filter_history(history, min_score, recs)
    df = build_results_df(filtered)

    if filtered:
        event = st.dataframe(
            df[["Título", "Empresa", "Score", "Recomendación"]],
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="results_df",
        )
    else:
        st.info("No hay ofertas que cumplan los filtros seleccionados.")
        return

    # ------------------------------------------------------------------
    # UI-04: Detail breakdown on row selection
    # ------------------------------------------------------------------
    if event.selection.rows:
        row_idx = int(df.iloc[event.selection.rows[0]]["_idx"])
        row = filtered[row_idx]
        score = row["score"]

        with st.expander("Detalle completo", expanded=True):
            # 4 sub-scores
            desglose = score.get("desglose", {})
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Encaje puesto", desglose.get("encaje_puesto", "—"))
            m2.metric("Encaje skills", desglose.get("encaje_skills", "—"))
            m3.metric("Encaje ubicación", desglose.get("encaje_ubicacion", "—"))
            m4.metric("Encaje seniority", desglose.get("encaje_seniority", "—"))

            # Puesto detectado + ranking
            puesto_detectado = score.get("puesto_detectado", "—")
            rango_puesto = score.get("rango_puesto")
            rango_txt = f"(ranking #{rango_puesto})" if rango_puesto else "(fuera de ranking)"
            st.write(f"**Puesto detectado:** {puesto_detectado} {rango_txt}")

            # Reasons
            reasons_for = score.get("reasons_for") or []
            reasons_against = score.get("reasons_against") or []
            if reasons_for:
                st.write("**Razones a favor:**")
                for r in reasons_for:
                    st.write(f"- {r}")
            if reasons_against:
                st.write("**Razones en contra:**")
                for r in reasons_against:
                    st.write(f"- {r}")

            # Skills
            matched = score.get("matched_skills") or []
            missing = score.get("missing_requirements") or []
            if matched:
                st.write(f"**Skills coincidentes:** {', '.join(matched)}")
            if missing:
                st.write(f"**Requisitos faltantes:** {', '.join(missing)}")

            # Deal-breaker info
            if score.get("deal_breaker_hit"):
                cual = score.get("deal_breaker_cual") or ""
                st.warning(f"Deal-breaker: {cual}")

            # Apply URL — T-10-05-04: use .get(), skip silently if absent/empty
            url = row.get("url")
            if url:
                st.link_button("Ver oferta", url)


# Gate: only run the page body when a Streamlit runtime is active.
# Keeps the module import-safe for unit tests (D-12 pattern).
try:
    from streamlit.runtime import exists as _st_running

    if _st_running():
        _render()
except Exception:  # noqa: BLE001
    # Not in a Streamlit context — module imported for testing only.
    pass
