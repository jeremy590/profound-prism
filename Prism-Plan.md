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
        ┌──────────────┬───────────┴───┬──────────────┬──────────────┐
       CMO            SEO             PM            Brand            PR     ← five Prisms
        │              │              │              │              │
   each Prism = a declarative slice (dimensions + filters) + framing + downstream agent

  Regional was dropped: the org runs every prompt in the US region only, so there is
  no cross-market signal to split. Re-add a localisation Prism if multi-region data
  is ever enabled (the writes_prompts field on the schema is reserved for it).
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

## Curation mode — not every Prism is curated by prompt

A key finding from grading: the five Prisms split into two curation modes.

- **Prompt-curated** — *which prompts feed this lens* is a real per-prompt question, answered by the Claude classifier (see below): **CMO, PM, Brand**.
- **Citation-curated** — the lens is a property of the *citation report* (which domains/URLs/source-types get cited), not of individual prompts; it applies across **all** prompts and is sliced by domain/url instead: **SEO, PR**.

So the classifier only labels prompts for CMO / PM / Brand. SEO and PR consume the whole prompt set and slice the citations frame.

## How a Prism slices **prompts** (the 195)

Same prompt set, different selector per role. Only PM *transforms* prompts (LLM clustering); the rest filter.

| Prism | mode | `prompt_treatment` | What it selects |
|---|---|---|---|
| CMO | prompt | `new` | newest / top-line / category-defining prompts — emerging search themes |
| PM | prompt | `cluster` | use-case & capability prompts → **clustered into use-case themes** (LLM) |
| Brand | prompt | `sentiment_shift` | opinion / characterisation prompts driving a WoW sentiment move |
| SEO | citation | `lost_citation` | *all* prompts; sliced by owned URL/domain citation deltas |
| PR | citation | `third_party` | *all* prompts; sliced by third-party domain / url / source-type |

## How a Prism slices **topics** (the 15)

Same 15 topics, different treatment.

| Prism | `topic_treatment` | What it does |
|---|---|---|
| CMO | `growth` | which topics are gaining volume / theme momentum |
| SEO | `decay` | topic-level visibility & citation decline (period delta) |
| PM | `cluster` | topics as the clustering taxonomy for use-cases |
| Brand | `theme` | topic ≈ sentiment theme |
| PR | `leaderboard` | topic used to map cited domains to beats (pitch routing) |

---

## Read-side vs write-side Prisms

All five current Prisms are **read-side** — non-destructive query templates + framing over the cached base. No writes to Profound.

The `writes_prompts` flag (+ approval gate) on the schema is **reserved**: if multi-region data is ever enabled, a localisation Prism would use it to propose region-specific prompt variants via `PATCH /v1/org/categories/{id}/prompts`. Until then, nothing writes.

---

## Layer-later enrichments (out of v1 critical path)

Each bolts onto one Prism as a single node; each ships without it:
- **DataForSEO People Also Ask** → PM adjacent-question demand (creds already in `.env`).
- **Reddit sentiment** → PM competitor profiles / Brand cross-check (Idea 3).
- **Business KPI join (GA4/GSC/Shopify)** → CMO commercial overlay — tie visibility to sessions/revenue (Max's "$1M fix"; data-dependent).

---

## Open coordination points

1. Frame format + cache location with the base-pull session (proposal above).
2. The visibility-by-`prompt` dimension question (flagged above) — must be tested live.
3. Period-delta convention: every Prism compares periods, not absolutes. Base pull should fetch the current window **and** the prior window of equal length so deltas are computable in-memory.
