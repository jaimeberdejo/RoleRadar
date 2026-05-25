"""
Deterministic seniority rule engine for BuscadorDeEmpleo.

Purpose
-------
Compute `encaje_seniority` (0-100) from the raw job description text and the
candidate's total years of experience (`anios_candidato`), using ONLY stdlib
`re` — no LLM, no embeddings, no torch.

Why deterministic (no LLM)?
CONTEXT.md SCORE-12: all four numeric sub-scores must be produced without an
OpenAI call so the heuristic works even when `OPENAI_API_KEY` is absent.
LLM calls are deferred to an optional enrichment step (prose reasons only).

None = neutral = 50
If `anios_candidato` is None (the cached CVProfile was parsed without extracting
years, e.g. the CV didn't mention totals), we return a neutral 50.  Treating
None as 0 would unfairly penalise every offer when the CV hasn't been
re-parsed yet — this was flagged as a STATE blocker in the planning context.

Ratio mapping (documented here, implemented in `evaluar_seniority`)
--------------------------------------------------------------------
We compare `ratio = anios_candidato / anos_requeridos` and map to a score:

    ratio >= 1.5  →  100  (significantly exceeds — we want to keep strong fits)
    ratio >= 1.0  →   85  (meets or slightly exceeds)
    ratio >= 0.7  →   65  (close but under — "requisitos inflados" are common)
    ratio >= 0.5  →   45  (notably below)
    ratio >= 0.3  →   25  (significantly below)
    ratio <  0.3  →   10  (very junior for a senior role)

Why low seniority doesn't force skip (CLAUDE.md rule 3)
--------------------------------------------------------
Requirements are often inflated.  A 5-year ask for a "senior" role may really
mean 3 years of strong work.  We lower the score and surface it in
`seniority_nota` (which `scorer.py` propagates to `missing_requirements`), but
we never set a score to 0 — that would collapse `score_total` unfairly and
bypass the LLM's ability to decide "maybe".  Only an explicit `deal_breaker`
trigger forces a `skip` recommendation (scorer.py responsibility).

No app.dedup imports
--------------------
This module is intentionally isolated: `re`, `dataclasses`, `logging` only.
scorer.py passes `cv_profile.anios_experiencia_total` as a plain float/None
so there is no circular dep and scoring tests load without torch.
"""
from __future__ import annotations

import dataclasses
import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex (module-level: one-time cost; linear worst-case on the text)
# ---------------------------------------------------------------------------
# Matches patterns such as:
#   "5+ years",  "5 years",  "at least 5 years",  "minimum 5 years",
#   "5 años",    "5+ años",  "5-7 years" (captures the lower bound "5"),
#   "5 to 7 years" (captures "5")
#
# The lower bound of a range is always the FIRST digit group.  We handle both
# hyphen ranges ("5-7 years") and "to" ranges ("5 to 7 years") explicitly so
# the captured group is always the lower bound, not the upper.
#
# Pattern order: hyphen-range first (longer match), then "+" / "to" range,
# then bare number.
#
# ReDoS note (T-07-06): digit groups `(\d+)` are bounded; alternation
# `years?|años?` is literal — no catastrophic backtracking path.
# Regex is applied to typical job descriptions (< 10 k chars).
_RE_ANOS = re.compile(
    r"(\d+)\s*(?:[+]|\s*[-]\s*\d+|\s*to\s*\d+)?\s*"
    r"(?:years?|a[ñn]os?)\s*(?:of\s*)?(?:experience|experiencia)?",
    re.IGNORECASE,
)

# Level keywords → approximate equivalent years for the scoring comparison.
# Ordered from most common / highest priority to least so that a search finds
# "mid-level" before "mid" (if we were doing substring search — actually we
# use a case-folded `in` check).
_NIVEL_ANIOS: dict[str, float] = {
    "junior": 1.0,
    "mid-level": 3.0,
    "mid level": 3.0,
    "senior": 5.0,
    "lead": 7.0,
    "staff": 8.0,
    "principal": 9.0,
    "director": 10.0,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class SeniorityResult:
    """Result of the deterministic seniority evaluation.

    Attributes:
        encaje_seniority: Integer 0-100. Never 0 for a known candidate (rule 3).
        seniority_nota: Human-readable note. NEVER empty — used by scorer.py
            to populate missing_requirements on the fallback (no-LLM) path.
        anos_requeridos: Years parsed from the job description. None if no
            explicit requirement found.
    """

    encaje_seniority: int           # 0-100
    seniority_nota: str             # always non-empty
    anos_requeridos: float | None   # parsed from description, None if not found


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _parse_anos_requeridos(description: str) -> float | None:
    """Extract the required years of experience from a job description.

    Strategy:
    1. Try the numeric regex first (most reliable signal).
       Returns the first captured digit group as a float.
    2. Fall back to level keyword look-up (_NIVEL_ANIOS).
       Returns the mapped approximate-years value for the first match found.
    3. Return None if no signal found.

    Args:
        description: Raw job description text (any language).

    Returns:
        Required years as float, or None if no requirement is detected.
    """
    # 1. Numeric pattern
    match = _RE_ANOS.search(description)
    if match:
        anos = float(match.group(1))
        logger.debug("_parse_anos_requeridos: numeric match → %.1f years", anos)
        return anos

    # 2. Level keyword
    lower_desc = description.lower()
    for keyword, anos in _NIVEL_ANIOS.items():
        if keyword in lower_desc:
            logger.debug(
                "_parse_anos_requeridos: keyword match '%s' → %.1f years", keyword, anos
            )
            return anos

    logger.debug("_parse_anos_requeridos: no signal found in description")
    return None


def _ratio_to_score(ratio: float) -> int:
    """Map experience ratio (candidate / required) to a 0-100 integer score.

    Rationale documented at module level.  The mapping is intentionally
    non-linear at the boundaries: we cap at 100 (exceeding requirement by any
    amount is fine) and floor at 10 (never 0 — rule 3).
    """
    if ratio >= 1.5:
        return 100
    if ratio >= 1.0:
        return 85
    if ratio >= 0.7:
        return 65
    if ratio >= 0.5:
        return 45
    if ratio >= 0.3:
        return 25
    return 10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def evaluar_seniority(
    job_description: str,
    anios_candidato: float | None,
) -> SeniorityResult:
    """Evaluate seniority fit deterministically.

    Parses required years / level from `job_description` and compares against
    `anios_candidato` (cv_profile.anios_experiencia_total).  No LLM, no
    embeddings — stdlib only.

    Args:
        job_description: Full text of the job posting.
        anios_candidato: Candidate's total years of experience from CVProfile.
            Pass ``None`` if the CV didn't yield an estimate; returns neutral 50.

    Returns:
        SeniorityResult with encaje_seniority (0-100), a human-readable
        seniority_nota, and the parsed anos_requeridos.

    Examples:
        >>> evaluar_seniority("5+ years Python experience", None).encaje_seniority
        50
        >>> evaluar_seniority("2+ years experience", 4.0).encaje_seniority
        100
    """
    # ------------------------------------------------------------------
    # Step 1 — unknown candidate experience → neutral path
    # ------------------------------------------------------------------
    if anios_candidato is None:
        logger.debug("evaluar_seniority: anios_candidato=None → neutral 50")
        return SeniorityResult(
            encaje_seniority=50,
            seniority_nota=(
                "Experiencia del candidato desconocida (CV sin años estimados)"
            ),
            anos_requeridos=None,
        )

    # ------------------------------------------------------------------
    # Step 2 — parse required years from description
    # ------------------------------------------------------------------
    anos_requeridos = _parse_anos_requeridos(job_description)

    if anos_requeridos is None:
        # No explicit requirement → generous assumption
        logger.debug(
            "evaluar_seniority: no requirement signal → score=75 "
            "(anios_candidato=%.1f)",
            anios_candidato,
        )
        return SeniorityResult(
            encaje_seniority=75,
            seniority_nota="Sin requisito de años explícito en la oferta",
            anos_requeridos=None,
        )

    # ------------------------------------------------------------------
    # Step 3 — compare and map to score
    # ------------------------------------------------------------------
    if anos_requeridos == 0.0:
        # "0-2 years" or "0+ years" → entry-level role with no meaningful floor.
        # Treat as "no signal" → generous assumption (same as anos_requeridos=None path).
        logger.debug(
            "evaluar_seniority: anos_requeridos=0 → treating as no signal "
            "(anios_candidato=%.1f)",
            anios_candidato,
        )
        return SeniorityResult(
            encaje_seniority=75,
            seniority_nota="Sin requisito de años explícito en la oferta (0 interpretado como sin requisito)",
            anos_requeridos=None,
        )

    ratio = anios_candidato / anos_requeridos
    score = _ratio_to_score(ratio)
    # Clamp to [0, 100] — defensive even though _ratio_to_score already does
    score = max(0, min(100, score))

    if ratio >= 1.0:
        nota = (
            f"El candidato tiene {anios_candidato:.0f} años vs "
            f"{anos_requeridos:.0f} requeridos — cumple"
        )
    else:
        nota = (
            f"El candidato tiene {anios_candidato:.0f} años vs "
            f"{anos_requeridos:.0f} requeridos — por debajo del requisito"
        )

    logger.debug(
        "evaluar_seniority: anios_candidato=%.1f, anos_requeridos=%.1f, "
        "ratio=%.2f → score=%d",
        anios_candidato,
        anos_requeridos,
        ratio,
        score,
    )

    return SeniorityResult(
        encaje_seniority=score,
        seniority_nota=nota,
        anos_requeridos=anos_requeridos,
    )
