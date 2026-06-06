# Agent Sketches — Six Personas, Six Workflows

Node-by-node sketches for each persona's agent, written in Profound's vocabulary (Answer Engine Insights, Prompt Volumes, Agent Analytics, Brand Kit, Profound Docs, Slack, Iteration, plus standard LLM/Web/Scrape nodes). Each is a starting graph — meant to be readable in the Agent Builder, not final.

Conventions used below:
- `[Node Type]` — a single node
- `→` — wire from one node to the next
- `⟳ for each:` — Iteration node, with the nested steps it runs per item
- `🧍 approval` — human-in-the-loop checkpoint

---

## 1. Commercial Director — Weekly Executive Brief

**Trigger:** Scheduled, Monday 07:00 local
**Inputs:** `category_id`, current week range
**Output:** Exec brief in Profound Docs + summary post in `#execs`

```
[Start]
  → [AEI — Visibility]            (metrics: visibility_score, share_of_voice; period delta)
  → [AEI — Sentiment]              (positive, negative, occurrences; period delta)
  → [AEI — Visibility — Competitors]  (asset_filter = top 5 rivals)
  → [Prompt Volumes — New Prompts]    (last 7d, vs prior 28d baseline)
  → [Agent Analytics — Referrals]     (AI-driven session count, period delta)
  → ⟳ for each competitor:
        [AEI — Share of Voice delta]
        [LLM — Classify move]    (gain / hold / lose)
  → [LLM — Summarise]              (Brand Kit + all upstream context; 3–5 items max, CMO voice)
  → [LLM — Risk Flag]              (anything genuinely red?)
  → [Profound Docs — Exec Brief]
  → [Slack — #execs]               (3-bullet TL;DR + Docs link)
🧍 approval (optional, gates email distribution)
  → [Email distribution]           (optional)
```

**Why this shape:** the brief has to fit in five bullets. The two-pass LLM (Summarise → Risk Flag) prevents the agent from drowning the CMO in detail.

---

## 2. SEO Lead — Citation Recovery

**Trigger:** Weekly, plus on-demand
**Inputs:** `category_id`, list of owned domains
**Output:** Prioritised list of pages to refresh + a brief per page, in Profound Docs and a Sheet

```
[Start]
  → [AEI — Citations]              (dimensions: [url]; owned domains; period delta)
  → [Filter — Top Losers]          (biggest citation drops, traffic-weighted)
  → ⟳ for each declining page:
        [Web Page Scrape]            (our current content)
        [AEI — Citations]            (same prompts; who wins the citation now?)
        [Web Page Scrape]            (winning competitor page)
        [LLM — Gap Analysis]         (coverage diff: what they have, we don't)
        [LLM — Refresh Brief]        (structured to AI-citation format)
        [Brand Kit]                  (voice + style)
  → [Sheets — Output Table]        (URL, citation drop, traffic impact, brief link)
  → [Profound Docs — Briefs Collection]
  → [Slack — #seo]                 ("N pages need refresh this week")
🧍 approval (writer assignment)
  → [CMS node — WordPress/Sanity/Framer]  (when refresh is approved & written)
```

**Why this shape:** the diff-against-competitor step is what makes the brief actionable rather than generic "rewrite this." Sheets output gives the SEO lead a board they can prioritise on.

---

## 3. Product Manager — Use-Case Tracker

**Trigger:** Weekly
**Inputs:** `category_id`, `product_name` / asset ID
**Output:** Use-case dossier (clustered prompts, growing/shrinking, adjacent questions) in Profound Docs

```
[Start]
  → [AEI — Prompts]                (last 30d, mentioning product)
  → [AEI — Visibility]             (dimensions: [prompt])
  → [LLM — Cluster Prompts]        (group into use-case themes, e.g. "AI design support", "AI therapy")
  → [AEI — Visibility — Period 2]  (prior 30d, same clustering)
  → [LLM — Trend Classify]         (growing / stable / shrinking per cluster)
  → ⟳ for each top cluster:
        [AEI — Citations]            (dimensions: [prompt]; what gets cited here?)
        [AEI — Prompt Answers]       (sample raw AI answers, limit=10)
        [LLM — Feature Extract]      (what features does AI attribute to us in this use-case?)
        [LLM — Competitor Mentions]  (which rivals get recommended for the same use-case?)
  → [DataForSEO — People Also Ask]  (LAYER LATER — for top cluster prompts → adjacent demand)
  → [LLM — Adjacent-Question Gaps]  (what are people asking that we don't answer?)
  → [Profound Docs — Use-Case Dossier]
  → [Slack — #product]              (use-case-of-the-week + biggest mover)
```

**Why this shape:** clustering is the heart of it — raw prompts are noise; clustered themes are signal. DataForSEO PAA bolts on cleanly as a single node so the v1 ships without it.

---

## 4. Brand Lead — Sentiment Theme Watch

**Trigger:** Daily (light) + weekly (deep)
**Inputs:** `category_id`, brand asset + competitor asset list
**Output:** Sentiment shift report + draft positioning briefs (risk responses + opportunity claims)

```
[Start]
  → [AEI — Sentiment]              (theme_filter: all themes; asset_filter: us + competitors)
  → [Statistical — Shift Detection] (themes with material WoW % change, signed)
  → ⟳ for each shifted theme:
        [AEI — Prompt Answers]       (filtered to theme; raw text driving the shift)
        [LLM — Phrase Extract]       (the actual characterisations changing)
        [AEI — Sentiment — Competitors]  (same theme, side-by-side)
  → [Branch:]
       ├─ if positive shift on competitor → [LLM — Opportunity Brief]   (positioning angle to claim)
       └─ if negative shift on us        → [LLM — Risk Response Brief]  (talking points + comms angles)
  → [Brand Kit]                    (voice consistency on all briefs)
  → [Profound Docs — Brand Intel Pack]
  → [Slack — #brand]
🧍 approval (mandatory before any external comms use)
```

**Why this shape:** sentiment-only doesn't drive action — the *why* (phrase extraction from raw answers) is what makes the brief usable. Branch logic stops the agent producing irrelevant briefs on themes that didn't move.

---

## 5. PR / Earned Media Lead — Citation Outreach

**Trigger:** Weekly + on-demand for campaigns
**Inputs:** `category_id`, list of owned domains, campaign hook (optional)
**Output:** Ranked target list + personalised pitch drafts in `#pr-targets` for review

```
[Start]
  → [AEI — Citations]              (dimensions: [root_domain]; period last 90d; exclude owned)
  → [Filter — Target Domains]      (high citation share in category, NOT citing us, citing competitors)
  → [Rank]                         (citation_share × competitor presence)
  → ⟳ for each target domain (top N):
        [AEI — Citations]            (dimensions: [url]; this domain's top-cited pages in category)
        [Web Page Scrape]            (top page → extract author/editor)
        [Clay / Apollo enrichment]   (LAYER LATER — author → email + recent posts)
        [Web Page Scrape]            (author's last 3 articles for personalisation)
        [LLM — Pitch Draft]          (Brand Kit + campaign hook + author voice match)
  → [Profound Docs — Pitch Pack]
  → [Slack — #pr-targets]          (drafts queued for review)
🧍 approval (mandatory — no auto-send)
  → [Noble node]                   (push approved list to Noble for handled outreach)
  → [PartnerStack node]            (match approved domains against PartnerStack network for affiliate angle)
```

**Why this shape:** this is the closest agent to Profound's own canonical example (CTO's "find top 10 third-party pages citing our brand, draft pitches" demo). Noble and PartnerStack as terminal nodes pick up exactly where the human approval ends.

---

## 6. Regional / Global Marketing Lead — AI-vs-Business Market Divergence

**Trigger:** Monthly + on-demand when AI or commercial signals diverge in any market
**Inputs:**
- `category_id`
- Priority region list (e.g. UK, US, AU, CA, DE)
- **Business KPI feed per region** — required, not optional. At minimum: GA4 or GSC sessions + conversion rate. Ideally: ecommerce revenue (Shopify / equivalent).

**Output:** Per-region brief pack + a cross-market AI-vs-business divergence quadrant in Profound Docs

```
[Start]
  → [List Regions]                 (confirm region taxonomy)

  PARALLEL FAN-OUT — AI side:
  → [AEI — Visibility]             (dimensions: [region]; period delta)
  → [AEI — Citations]              (dimensions: [root_domain, region])
  → [AEI — Sentiment]              (region_filter: all priority regions)
  → [Agent Analytics — Referrals]  (AI traffic per region, per market-specific domain)

  PARALLEL FAN-OUT — Business side:
  → [Business KPI Connector]       (GA4 / GSC / Shopify per region: sessions, conv rate, revenue, period delta)

  → ⟳ for each region:
        [Build AI Profile]           (visibility, sentiment, top 10 citing sources, period delta)
        [LLM — Authoritative-Source Classify]  (which sources are local authorities? NHS, govt, trade press, etc.)
        [Build Commercial Profile]   (sessions, conversion, revenue, period delta — for this market)
        [LLM — Divergence Detect]    (does AI performance line up with commercial reality? where don't they agree?)
        [LLM — Diagnose]             (source-authority gap? prompt-set gap? content gap? translation gap?)
        [LLM — Recommended Action]   (per region: localise content / add regional prompts / pursue local source / no-op)

  → [Cross-Market Compare]
        [LLM — Quadrant Map]         (2x2: AI good × Biz good | AI good × Biz bad | AI bad × Biz good | AI bad × Biz bad)
        [LLM — Why-Diff]             (UK winning vs AU losing: which sources / themes / prompts drive the divergence?)
        [LLM — Prompt Localisation Check]  (flag prompts that don't translate — "running indoors" Dubai vs Switzerland)

  → [Profound Docs — Per-Region Briefs]    (each lead with the AI-vs-business divergence headline)
  → [Profound Docs — Cross-Market Quadrant Summary]
  → ⟳ Slack routing:
        for each region → [Slack — local market channel]    (#marketing-uk, #marketing-au, etc.)
  → [Slack — #global-marketing]    (quadrant + 3 biggest divergences)
🧍 approval (mandatory for any prompt-set changes — routes to prompt-set owner)
```

**Why this shape — and why the business KPI feed is now core, not a layer-later:**

Max's actual unsolved problem isn't "I can't see country differences" — he can. It's that **visibility doesn't connect to commercial reality**. His exact example: ACP feeds drove **3× sessions from OpenAI; visibility didn't move at all**. So a regional leaderboard without commercial overlay reproduces the same problem he already has, just sliced by country.

Joining business KPIs per region flips this. The headline insight changes from "which market is winning AI?" to "**where is AI performance lying to us?**" That's the question with no current answer in the market. Four quadrants come out of it, each prescriptive:

- **AI good × Biz good** — keep going; this is the playbook to copy elsewhere.
- **AI good × Biz bad** — AI is winning attention but the funnel is broken; product / conversion / localisation issue downstream.
- **AI bad × Biz good** — commercial momentum without AI support; risk of decay as AI search share grows. Invest in AEO here urgently.
- **AI bad × Biz bad** — deprioritise or rebuild market entry strategy.

The other two upgrades that come with promoting business KPIs to core:

1. **Diagnose node** now has the data to attribute *why* a divergence exists — source authority gap (NHS-vs-Australian-health-ministry), prompt-set gap (some prompts don't translate), content gap (no local content), or translation gap (content exists but isn't in market language).
2. **Recommended Action node** can be prescriptive per region rather than generic. "Localise content for AU" only makes sense when we know AU has commercial traction but no AI visibility. Same recommendation in a market with no commercial signal would be wasted effort.

The prompt-localisation check stays where it was — Max's "running indoors Dubai vs trail running Switzerland" point is the v1 prompt-set quality gate. Combined with the divergence quadrant, this is the agent he was describing in the call, not adjacent to it.

---

## Cross-cutting design choices

A few patterns appear in every agent for a reason:

- **Period delta on every report call.** Profound's reports return a snapshot; the signal is in the change. Every agent compares periods, not absolutes.
- **Iteration nodes do the heavy lift.** Rather than write one giant LLM prompt, each agent fans out per item (per page, per cluster, per theme, per region) and the LLM works on focused context per loop. Closer to how an analyst would think.
- **Brand Kit reads on every drafting step.** Tone is enforced at the LLM-node level, not bolted on at the end.
- **Two-pass LLM where the audience is senior.** Summarise → re-pass for risk/insight prevents the agent producing thorough-but-unread briefs.
- **Profound Docs as the artifact home; Slack as the notifier.** Matches Profound's stated 2026 direction ("work needs a home") — Docs is where the human reviews and edits; Slack is where they get told to look.
- **Human-in-the-loop gates the irreversible step.** Brief generation is free; publishing, outreach, and external comms always gate.
- **"Layer later" tags** mark nodes that aren't strictly required for v1 — DataForSEO PAA, Clay/Apollo enrichment, business-KPI joins. Each agent ships without them; each lands cleanly when added.
