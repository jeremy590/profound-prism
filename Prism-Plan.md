# Prism — Overlay Plan

How we split one shared Profound data beam into six role-specific views. Each view is a **Prism**.

> Naming: we do **not** use the word "persona". Profound has a native `persona` field on prompts — it's poorly named and, in our org, **null on all 195 prompts**, so it carries no signal. We ignore that dimension entirely. Our role lenses are **Prisms** and live only in our orchestrator; they are never sent to Profound.

---

## The model

```
                 ┌─────────────────────────────────────┐
   Profound API  │           BASE PULL (once)          │
   ───────────▶  │  finest-grain flattened report      │
                 │  frames + cached org metadata       │
                 └──────────────────┬──────────────────┘
                                    │  (in-memory, ~zero extra API calls)
        ┌──────────┬──────────┬─────┴────┬──────────┬──────────┐
       CMO        SEO        PM        Brand        PR       Regional   ← six Prisms
        │          │          │          │          │          │
   each Prism = a declarative slice (dimensions + filters) + framing + downstream agent
```

A **Prism** is a config, not a copy of the data. It selects how the *same* prompts and topics get sliced and framed for one role.

| Prism part | Source (`Cowork docs/Personas.md`) | Becomes |
|---|---|---|
| `goal` | the **Description** | the downstream agent's system goal |
| `questions[]` | **Questions at log-on** | preloaded FAQ chips on the dashboard |
| `slices[]` | **Profound data to pull** | in-memory groupby/filter specs over the base frames |
| `prompt_treatment` | (implicit per role) | how this Prism uses the 195 prompts |
| `topic_treatment` | (implicit per role) | how this Prism uses the 15 topics |

---

## Locked decisions

1. **Pull at the finest grain, once. Roll up in memory.** The base pull fetches each core report with the widest dimension list it supports (minus `persona`), in single wide calls — *not* per-prompt loops. Every Prism is then an in-memory groupby over the cached frames, costing ~zero extra API calls. This is what keeps us under the 600 req/hr/key limit.
2. **Prisms live as declarative config** (`prisms/*.yaml`), validated by a Pydantic schema (`prisms/_schema.py`). Editable without touching orchestrator code; trivially swappable for Python objects later if needed.
3. **Profound's native `persona` dimension is dropped everywhere.** No `dimensions: ["persona"]`, no `persona_filter`. Our Prisms replace the concept.

---

## Finest-grain base pull (the contract with the API-pull session)

Each report is pulled with its widest supported dimension set **minus `persona`**, then run through the `flatten_report()` helper and cached as a frame. The Prism layer reads these frames; it does not call Profound directly (except the layer-later enrichments).

| Report | Finest dimensions (base pull) | Metrics |
|---|---|---|
| **visibility** | `date, asset_name, model, region, topic, tag` | `visibility_score, share_of_voice, average_position, mentions_count, executions` |
| **citations** | `date, model, region, root_domain, url, topic, prompt, tag` | `count, citation_share` |
| **sentiment** | `date, asset_name, theme, sentiment_type, topic, model, region` | `positive, negative, occurrences` |
| **referrals** (v2) | `date, domain` | per-domain referral counts |
| **bots** (v2) | `date, domain, bot_provider` | per-domain crawler hits |
| `list_prompts` | full prompt records (id, text, topic, tags, status) | — |

**⚠️ Verify before locking:** the PM Prism wants visibility sliced by **prompt**, but the REST reference does *not* list `prompt` among visibility dimensions (only citations does). Confirm whether `dimensions: ["prompt"]` is valid on `/v1/reports/visibility` — if not, PM use-case visibility must be derived from the citations frame instead. Flag for the base-pull session to test against the live org.

**Frame format / location** — coordinate with the base-pull session. Proposal: cached flattened frames at `cache/<report>.parquet` (or `.json`), columns named exactly as the dimension + metric keys above. Org metadata (categories, topics, tags, regions, models) cached separately and refreshed on a slow timer.

---

## How a Prism slices **prompts** (the 195)

Same prompt set, different selector per role. Only PM *transforms* prompts (LLM clustering); the rest filter.

| Prism | `prompt_treatment` | What it selects |
|---|---|---|
| CMO | `new` | newest prompts only — emerging search themes |
| SEO | `lost_citation` | prompts where an owned URL lost citation share |
| PM | `cluster` | prompts mentioning the product → **clustered into use-case themes** (LLM) |
| Brand | `sentiment_shift` | prompts driving a material WoW sentiment move → raw answers for phrase extraction |
| PR | `third_party` | prompts feeding third-party (non-owned) citations |
| Regional | `localisation` | prompts that don't translate cleanly across markets ("running indoors in Dubai") |

## How a Prism slices **topics** (the 15)

Same 15 topics, different treatment.

| Prism | `topic_treatment` | What it does |
|---|---|---|
| CMO | `growth` | which topics are gaining volume / theme momentum |
| SEO | `decay` | topic-level visibility & citation decline (period delta) |
| PM | `cluster` | topics as the clustering taxonomy for use-cases |
| Brand | `theme` | topic ≈ sentiment theme |
| PR | `leaderboard` | topic = category scope for the citation leaderboard |
| Regional | `region_divergence` | topic **× region** — where a topic wins in one market, loses in another |

---

## Read-side vs write-side Prisms

- **Read-side (5 of 6):** non-destructive. The Prism is a query template + framing over the cached base. No writes to Profound.
- **Write-side (Regional only):** proposes *mutating the prompt set* — adding region-localised prompt variants via `PATCH /v1/org/categories/{id}/prompts`. This is the one Prism that changes Profound's own state, so it is **architecturally separate and gated behind human approval** (`writes_prompts: true` + an approval checkpoint). Never auto-applied.

---

## Layer-later enrichments (out of v1 critical path)

Each bolts onto one Prism as a single node; each ships without it:
- **DataForSEO People Also Ask** → PM adjacent-question demand (creds already in `.env`).
- **Reddit sentiment** → PM competitor profiles / Brand cross-check (Idea 3).
- **Business KPI join (GA4/GSC/Shopify)** → Regional AI-vs-business divergence quadrant (this is the headline insight, but data-dependent).

---

## Open coordination points

1. Frame format + cache location with the base-pull session (proposal above).
2. The visibility-by-`prompt` dimension question (flagged above) — must be tested live.
3. Period-delta convention: every Prism compares periods, not absolutes. Base pull should fetch the current window **and** the prior window of equal length so deltas are computable in-memory.
