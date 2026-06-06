# Profound Hackathon — Ideas

Working doc for hackathon concepts. Both ideas below were pulled from the Max x Jeremy call on 2026-06-01.

---

## Idea 1 — Role-Aware Reporting Dashboard (with global/market layer)

**The pitch:** A centralised Profound dashboard that personalises what it surfaces based on the user's job title/role. When you log in, it pre-loads the questions (and visualisations) that role actually cares about, presented as a chat interface with preloaded FAQs.

**Why it works for Profound:**
- Uses their existing agents + insights → "insights to actions" story they're proud of.
- Profound has global clients, so the country-comparison layer lands directly with their ICP.
- Hackathon judges (Lily Ray et al.) reward something Profound can *sell*, not just a cool toy. A dashboard is sellable.

**Role examples:**
- **CMO / Marketing lead:** visibility delta vs. last period, north-star metric, country-level performance gaps.
- **Product manager:** most frequent prompts about specific products, accuracy of product data in AI responses, content gaps.
- **Regional / market lead:** "Why is the UK winning and Australia losing?" — which sources (e.g. NHS vs. Aus health ministry) drive citations in each market, what to localise.
- **Finance:** top-of-funnel prompts about the brand, sentiment, sized exposure.

**Differentiators to build in:**
- Country/market comparison view — surface *why* visibility differs (source mix, prompt mix, citation patterns). This is the bit Max said is missing today.
- Reddit sentiment / third-party sources pulled in as supporting context.
- Preloaded FAQ chips per role so users don't start at a blank prompt box.
- Same dashboard pattern Jeremy is building for LEGO — proven concept, just productised on Profound's data.

**Open questions:**
- Do we ship as a Profound-native view or as an external dashboard that pulls Profound's API?
- How do we handle prompts that don't translate across markets (e.g. running indoors in Dubai vs. trail running in Switzerland — same intent, different prompt)?

---

## Idea 2 — "Where Did My Search Traffic Go?" (Organic → AI citation tracker)

**The pitch:** A view aimed at CMOs watching traditional organic traffic decline. Connects GSC losers to AI citation presence so you can answer: *did we lose the customer, or did the touchpoint just move?*

**The flow:**
1. Pull biggest GSC click/impression losers (page-level).
2. For each losing page, check if there's an AI Overview on the equivalent query (Profound already scrapes these).
3. Take the content of that losing article, turn it into a representative prompt, and check if the brand is cited in the AI response.
4. Output a simple status per page:
   - ✅ Green check — you're cited; impression just moved into AI. Touchpoint preserved.
   - ❌ Red X — you've lost the session *and* the touchpoint. Action needed.
5. Layer in intent signal — if the page was informational (no historic conversions), exposure via citation is the win. If it was commercial, red X is much more urgent.

**Why it works for Profound:**
- Directly answers the question every CMO is being asked right now: "What's happening to our search traffic?"
- Connects Profound's data to GSC — gives the visibility score business context it currently lacks (Max's biggest unsolved problem: visibility doesn't tie to sessions or revenue).
- Simpler to build than Idea 1 → ships in hackathon time.
- Naturally sells more of Profound's platform (more prompts monitored, more pages tracked).

**Open questions:**
- GSC connection — assume OAuth at demo time, or pre-load a sample account?
- Intent classification — rules-based or LLM?
- Do we frame the red Xs as a content brief generator (next step: rewrite to win the citation)?

---

## Idea 3 — Competitor Product Profiles via Reddit Sentiment

**The pitch:** Extend the Product Manager agent with an external sentiment layer pulled from Reddit. For every competitor product Profound surfaces against our use-cases, the agent automatically builds a profile of what real users *like* and *dislike* about that product — pulled from Reddit threads and comments — and folds it into the insights brief. Profound tells us "what AI says about competitor products"; Reddit tells us "what humans say." Side-by-side is way more powerful than either alone.

**Why it works for Profound:**
- Reddit is already one of the most heavily-cited sources by AI engines. Profound's citation reports surface this constantly. Going upstream to read the source itself is a natural extension of their data layer, not a detour from it.
- It hooks straight into the Product Manager agent's "Competitor Mentions" step (Agent #3 in `Agent-Sketches.md`). Instead of stopping at *"competitor X is being recommended for this use-case,"* the agent answers *why* — what users praise it for and what they complain about.
- Ties to Jeremy's own comment on the call: "there may be one or two third party sources I can pull into it like Reddit sentiment, drag that into it." This idea operationalises that.
- Cross-applies cleanly to the Brand persona too — sentiment themes from Reddit reinforce or contradict what Profound's `get_sentiment_report` is showing in AI answers.

**The flow:**
1. Product Manager agent identifies the top N competitor products Profound surfaces for the brand's use-cases.
2. For each competitor product → query Reddit (official API or a wrapped scraper) for recent threads/comments mentioning it.
3. LLM clusters the Reddit signal into "praise themes" and "complaint themes" per product.
4. Output: a comparative card per competitor — Profound visibility on the left, Reddit praise/complaint themes on the right.
5. Feed into the PM's brief as *positioning ammunition*: "Competitor X is winning the 'AI design support' use-case in Profound. On Reddit, users praise it for [theme] but complain about [theme] — opportunity to own [counter-positioning angle]."

**Why it's hackathon-friendly:**
- Reddit data is rich, accessible, and well-suited to LLM clustering.
- Single new "node" conceptually — drops into the existing PM agent without rebuilding the graph.
- Demo-able with one real competitor product; judges grok the value instantly because the two data sources contradict and complement each other in obvious ways.

**Open questions:**
- Reddit access path — official API (OAuth), Apify Reddit scraper, or DataForSEO's Reddit endpoints? Each has different rate limits and cost profiles.
- v1 surface — top 3 praise + top 3 complaint themes per competitor, or fuller sentiment distribution with example quotes?
- Should it cross-pollinate to the Brand agent automatically, or stay PM-scoped for v1?
- Do we cache Reddit pulls per competitor (they don't change minute-to-minute), and refresh weekly?

---

## Notes from the call worth keeping nearby

- Max's "$1M fix" framing: a north-star AI metric that ties to business goals/revenue. Neither idea fully solves it, but Idea 2 chips at it by linking AI citation presence to GSC loss.
- Avoid: fully automated content production lines. Both Jeremy and Max think it's BS and judges likely do too.
- The PKI/Peak hackathon lesson: winners built things Peak could *sell*, not the coolest engineering. Same will apply here — bias the build toward something Profound's GTM team would immediately wire into a demo.
