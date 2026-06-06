"""Prism schema — the declarative overlay applied to the shared Profound data beam.

A Prism is loaded from a YAML file in this directory, validated against these
models, then executed as an in-memory slice over the cached base-pull frames.
No Prism calls Profound directly (except layer-later enrichments).

Deliberately does NOT use Profound's native `persona` dimension — see Prism-Plan.md.
"""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

Report = Literal["visibility", "citations", "sentiment", "referrals", "bots"]

# Curation mode per prism:
#   prompt-curated (classify per prompt): CMO, PM, Brand
#   citation-curated (apply across all prompts, slice by domain/url/source): SEO, PR
PromptTreatment = Literal[
    "new",             # CMO — newest prompts, emerging themes        [prompt-curated]
    "lost_citation",   # SEO — citation-driven, sliced by url/domain  [citation-curated]
    "cluster",         # PM  — cluster prompts into use-case themes    [prompt-curated]
    "sentiment_shift", # Brand — prompts driving a WoW sentiment move  [prompt-curated]
    "third_party",     # PR  — citation-driven, sliced by domain/url   [citation-curated]
]

TopicTreatment = Literal[
    "growth",       # CMO
    "decay",        # SEO
    "cluster",      # PM
    "theme",        # Brand
    "leaderboard",  # PR
]


class ReportSlice(BaseModel):
    """One groupby/filter over a cached base-pull frame.

    `dimensions`/`filters`/`metrics` use the same keys as the flattened frame
    columns. `period_delta` rolls the current window against the prior window
    of equal length (both fetched by the base pull).
    """

    report: Report
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, Union[list[str], str]] = Field(default_factory=dict)
    metrics: list[str] = Field(default_factory=list)
    period_delta: bool = True
    order_by: Optional[str] = None
    limit: Optional[int] = None


class DispatchRule(BaseModel):
    """One CMO→specialist hand-off. When a breach of `when` is detected, run
    the downstream Profound agent `agent`, scoped by `scope`.

    `agent` is resolved by name against the live org at run time; if no such
    agent exists yet the dispatch is recorded as `would_dispatch` (guarded),
    so the orchestrator ships before the specialist graphs are built.
    """

    when: Literal[
        "engine_gap",                # gap to category leader on an engine → SEO
        "negative_sentiment_theme",  # net-negative theme → Brand
        "owned_domain_undercited",   # owned domain low citation share → PR
    ]
    agent: str                       # downstream agent NAME (resolved to id at run time)
    scope: Literal["topic", "engine", "theme", "domain", "region"] = "region"


class Thresholds(BaseModel):
    """Level-based gates (one snapshot, no deltas). A breach fires the brief's
    escalation items and the matching dispatch rule."""

    engine_gap_pts: float = 10.0     # gap (pts) to leader on an engine that warrants a flag
    net_sentiment: float = 0.0       # net (pos−neg) below this on a theme = reputation escalation
    pack_spread_pts: float = 0.03    # top-pack mean-SoV spread below this → frame as "winnable"
    visibility_rank_max: int = 3     # rank worse than this in a (model,region) = competitive concern


class Prism(BaseModel):
    """A role lens over the shared data beam."""

    role: str                       # "cmo" | "seo" | "pm" | "brand" | "pr"
    title: str                      # human label for the dashboard
    goal: str                       # downstream agent's system goal (from the Description)
    questions: list[str]            # preloaded FAQ chips
    slices: list[ReportSlice]
    prompt_treatment: PromptTreatment
    topic_treatment: TopicTreatment
    writes_prompts: bool = False    # reserved (multi-region localisation); gated by approval
    # Orchestrator config — present on the CMO prism (the router); optional elsewhere.
    thresholds: Optional[Thresholds] = None
    dispatch: list[DispatchRule] = Field(default_factory=list)
    # NB: list[str]/dict[...] subscripts kept (valid on 3.9+ via __future__ annotations);
    # only PEP-604 `X | Y` unions are avoided for 3.9 compatibility.

    def requires_approval(self) -> bool:
        return self.writes_prompts
