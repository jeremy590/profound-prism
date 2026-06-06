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
    # NB: list[str]/dict[...] subscripts kept (valid on 3.9+ via __future__ annotations);
    # only PEP-604 `X | Y` unions are avoided for 3.9 compatibility.

    def requires_approval(self) -> bool:
        return self.writes_prompts
