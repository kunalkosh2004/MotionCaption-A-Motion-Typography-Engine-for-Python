"""Animation engine: segments + theme → per-word keyframe timelines.

The engine is a pure stage: for each word it builds a ``WordItem`` whose
``region`` is a ``RegionTimeline`` covering the whole word lifespan. The
template selected by ``AnimationConfig.strategy`` decides the motion; the
theme supplies the easing identities. Rendering and exporters only ever
sample these timelines.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from motion_caption.animations.templates import ANIMATION_REGISTRY, TemplateContext
from motion_caption.models.keyframe import RegionTimeline
from motion_caption.models.transcript import EmphasisMode, Segment, Word
from motion_caption.themes.spec import ResolvedTheme


class WordItem(BaseModel):
    """One animated word: its text, timing, emphasis and keyframe region."""

    text: str
    start: float
    end: float
    importance: float = 0.0
    emphasis: EmphasisMode = EmphasisMode.NONE
    region: RegionTimeline

    model_config = {"arbitrary_types_allowed": True}


class AnimationConfig(BaseModel):
    """Selection and tuning of an animation template."""

    strategy: str = "fade"
    in_window: float = Field(default=0.2, gt=0.0, le=1.0)
    out_window: float = Field(default=0.15, gt=0.0, le=1.0)
    params: dict[str, float] = Field(default_factory=dict)


_WORD_TIMED_STRATEGIES = frozenset({"karaoke"})


def animate_word(
    word: Word,
    theme: ResolvedTheme,
    config: AnimationConfig,
    *,
    start: float,
    end: float,
) -> WordItem:
    """Build the animated region for one word over ``[start, end]``."""
    template = ANIMATION_REGISTRY.get(config.strategy)
    context = TemplateContext(
        start=start,
        end=end,
        emphasis=word.emphasis,
        easings=theme.easing_specs,
        in_window=config.in_window,
        out_window=config.out_window,
        params=config.params,
    )
    return WordItem(
        text=word.text,
        start=word.start,
        end=word.end,
        importance=word.importance,
        emphasis=word.emphasis,
        region=template(context),
    )


def build_word_items(
    segments: Sequence[Segment],
    theme: ResolvedTheme,
    config: AnimationConfig | None = None,
) -> list[WordItem]:
    """Build one ``WordItem`` per word in every segment.

    Segment-level strategies animate the whole caption in/out on the segment
    timing; word-level strategies (e.g. ``karaoke``) use each word's own
    timestamps.
    """
    config = config or AnimationConfig()
    word_timed = config.strategy in _WORD_TIMED_STRATEGIES
    items: list[WordItem] = []
    for segment in segments:
        for word in segment.words:
            if word_timed:
                start, end = word.start, word.end
            else:
                start, end = segment.start, segment.end
            items.append(animate_word(word, theme, config, start=start, end=end))
    return items


def animate_segment(
    segment: Segment,
    theme: ResolvedTheme,
    config: AnimationConfig | None = None,
) -> list[WordItem]:
    """Convenience wrapper around ``build_word_items`` for one segment."""
    return build_word_items([segment], theme, config)
