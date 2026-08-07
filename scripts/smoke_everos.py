"""Phase 4 smoke: record a Case, then find it back with a *paraphrased* query.

Deliberately paraphrased — an exact-string match would prove nothing about
retrieval. Also round-trips a Skill through the EverOS-shaped markdown layout.

Two tiers, because retrieval quality depends on which backend is live:

* **Tier A (always required)** — a near paraphrase: same intent, different
  wording and word order, some shared content vocabulary. A BM25-class
  retriever must find this, so the local markdown backend must pass it.
* **Tier B (required only with a live EverOS server)** — a distant paraphrase
  sharing *no* content words. Only embeddings + reranker can match that, so it
  is reported as SKIP when the local backend is in use, never as a pass.

    uv run python scripts/smoke_everos.py
"""

from __future__ import annotations

import sys

from amort.config import get_settings
from amort.skills.recorder import RunRecorder
from amort.skills.store_everos import (
    Skill,
    fingerprint,
    get_store,
    load_skill,
    record_case,
    search_skill,
)

SYSTEM = "You are a support triage agent. Use the provided tools."
TASK = "Triage all open support tickets from the last 7 days and assign them to queues."
TOOLS = ["fetch_tickets", "get_customer", "search_kb", "classify", "check_sla", "assign_queue"]

# Tier A — near paraphrase. Not a substring of TASK: different verb, different
# word order, different framing; overlapping domain vocabulary.
PARAPHRASE = "route this week's unresolved customer support ticket backlog to the right queue"

# Tier B — distant paraphrase. Zero shared content words with the Case. Needs
# embeddings; lexical retrieval cannot and should not claim to match this.
PARAPHRASE_HARD = "sort inbound complaints into the correct teams by urgency"


def main() -> int:
    settings = get_settings()
    settings.ensure_dirs()
    store = get_store()
    print(f"memory backend : {store.backend_name}")
    print(f"memory root    : {settings.memory_dir}")
    print(f"everos base_url: {settings.everos_base_url} (mode={settings.everos_mode})")

    fp = fingerprint(SYSTEM, TASK, TOOLS)
    print(f"fingerprint    : {fp}")

    # --- 1. record a dummy run as a Case ------------------------------------
    rec = RunRecorder(lane="baseline", mode="cold", system=SYSTEM, user_msg=TASK, tool_names=TOOLS)
    rec.llm_step("claude-haiku-4-5-20251001", input_tokens=12_400, output_tokens=880, cost_usd=0.0154, wall_ms=3100)
    rec.tool_step("fetch_tickets", args={"range": "last_7_days"}, output=[1, 2, 3], wall_ms=12)
    rec.tool_step("classify", args={"tickets": "$steps.1.output"}, output=["billing"], wall_ms=8)
    rec.tool_step("check_sla", args={"tickets": "$steps.2.output"}, output=[True], wall_ms=5)
    rec.tool_step("assign_queue", args={"queues": ["billing", "tech"]}, output={"ok": True}, wall_ms=6)
    rec.llm_step("claude-haiku-4-5-20251001", input_tokens=9_100, output_tokens=1_240, cost_usd=0.0135, wall_ms=2600)
    case = rec.finish(final_output={"tickets": 3, "queues": ["billing"]})

    case_id = record_case(case)
    print(f"\n[1] record_case -> {case_id}")

    case_files = sorted(settings.cases_dir.glob("agent_case-*.md"))
    assert case_files, f"no case markdown written under {settings.cases_dir}"
    print(f"    markdown: {case_files[-1].relative_to(settings.memory_dir)}")

    # --- 2. find the Case back by paraphrase --------------------------------
    hit = store.search_case(PARAPHRASE)
    assert hit is not None, "search_case found nothing"
    found, score = hit
    found_id = found.get("case_id") or found.get("id")
    print(f'[2] search_case("{PARAPHRASE[:46]}…") -> {found_id} score={score:.3f}')
    assert score > 0, "paraphrase scored 0 — retrieval is not working"

    # --- 3. round-trip a Skill through the markdown layout ------------------
    skill = Skill(
        skill_id="skl_smoke_triage",
        name="triage_support_tickets",
        description="Triage open support tickets into queues with SLA flags.",
        task_fingerprint=fp,
        status="candidate",
        body=(
            "# Skill: Triage inbound support tickets\n"
            "## Trigger\nWhen the task asks to triage/classify open support tickets into queues.\n"
            "## Steps\n1. tool: fetch_tickets\n2. tool: classify\n3. tool: check_sla\n4. tool: assign_queue\n"
        ),
        source_case_ids=[case_id],
        tools_required=["fetch_tickets", "classify", "check_sla", "assign_queue"],
    )
    md_path = store.write_skill(skill)
    print(f"[3] write_skill -> {md_path}")

    # A decoy, so retrieval has to *discriminate* rather than return the only row.
    decoy = Skill(
        skill_id="skl_smoke_invoices",
        name="reconcile_monthly_invoices",
        description="Reconcile monthly vendor invoices against the ledger and flag mismatches.",
        task_fingerprint="fp_decoy",
        status="candidate",
        body=(
            "# Skill: Reconcile monthly vendor invoices\n"
            "## Trigger\nWhen the task asks to reconcile invoices or vendor billing against the ledger.\n"
            "## Steps\n1. tool: fetch_invoices\n2. tool: match_ledger\n3. tool: flag_mismatch\n"
        ),
        source_case_ids=[],
        tools_required=["fetch_invoices", "match_ledger", "flag_mismatch"],
    )
    store.write_skill(decoy)
    print(f"    decoy skill written: {decoy.skill_id}")

    # --- 4. retrieve it by paraphrase, and by exact fingerprint -------------
    by_text = search_skill("", PARAPHRASE)
    assert by_text is not None, "search_skill(paraphrase) found nothing"
    print(f"[4] search_skill(paraphrase)   -> {by_text.skill_id} score={by_text.score:.3f} src={by_text.source}")
    assert by_text.score > 0, "near paraphrase scored 0 — lexical retrieval is broken"
    assert by_text.skill_id == skill.skill_id, (
        f"paraphrase retrieved the decoy ({by_text.skill_id}) instead of {skill.skill_id}"
    )

    by_fp = search_skill(fp, PARAPHRASE)
    assert by_fp is not None and by_fp.exact_fingerprint, "fingerprint lookup did not hit"
    print(f"[5] search_skill(fingerprint)  -> {by_fp.skill_id} exact={by_fp.exact_fingerprint} confident={by_fp.is_confident}")

    loaded = load_skill(skill.skill_id)
    assert loaded.task_fingerprint == fp, "frontmatter round-trip lost task_fingerprint"
    assert loaded.tools_required == skill.tools_required, "frontmatter round-trip lost tools_required"
    print(f"[6] load_skill                 -> {loaded.skill_id} tools={loaded.tools_required}")

    # --- 5. fingerprint stability ------------------------------------------
    same = fingerprint(SYSTEM, "Triage all open support tickets from the last 3 days and assign them to queues.", TOOLS)
    diff = fingerprint(SYSTEM, "Write a haiku about queues.", TOOLS)
    assert same == fp, "date-shifted rephrasing changed the fingerprint"
    assert diff != fp, "a different task collided with this fingerprint"
    print("[7] fingerprint stable across date shift ✓ / distinct for a different task ✓")

    # --- 6. tier B: distant paraphrase (needs embeddings) -------------------
    hard = search_skill("", PARAPHRASE_HARD)
    if store.backend_name == "everos":
        assert hard is not None and hard.score > 0, (
            "EverOS server is live but the distant paraphrase found nothing — "
            "check that [embedding] and [rerank] providers are configured"
        )
        print(f"[8] tier B distant paraphrase   -> {hard.skill_id} score={hard.score:.3f} (everos hybrid)")
    else:
        got = f"{hard.skill_id} score={hard.score:.3f}" if hard else "no hit"
        print(f"[8] tier B distant paraphrase   -> SKIP ({got}) — needs a live EverOS server (embeddings)")
        print("    lexical retrieval cannot match zero-overlap paraphrases; not counted as a pass.")

    print("\nPHASE 4 SMOKE: PASS" + ("" if store.backend_name == "everos" else "  [tier B skipped]"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
