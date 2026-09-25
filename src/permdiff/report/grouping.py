"""Group transitions by (class, tool) with deterministic samples (FR-16 subset used by E1)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from permdiff.models import Frozen, Transition, TransitionClass

DEFAULT_SAMPLES = 3

_CLASS_RANK: dict[TransitionClass, int] = {
    TransitionClass.WIDENING: 0,
    TransitionClass.TIGHTENING: 1,
    TransitionClass.CANT_EVALUATE: 2,
    TransitionClass.ATTRIBUTION_CHANGE: 3,
    TransitionClass.UNCHANGED: 4,
}


class Group(Frozen):
    cls: TransitionClass
    key: str
    count: int
    samples: tuple[Transition, ...]

    @property
    def effects(self) -> str:
        """``deny → allow`` style summary from the first sample."""
        first = self.samples[0]
        return f"{first.base.effect.value} → {first.head.effect.value}"


def group_transitions(
    transitions: Sequence[Transition],
    *,
    samples: int = DEFAULT_SAMPLES,
    include_unchanged: bool = False,
    include_attribution: bool = False,
) -> tuple[Group, ...]:
    """Groups sorted widening first, then by count descending, then key (AC-16.3)."""
    buckets: dict[tuple[TransitionClass, str], list[Transition]] = defaultdict(list)
    for t in transitions:
        if t.cls is TransitionClass.UNCHANGED and not include_unchanged:
            continue
        if t.cls is TransitionClass.ATTRIBUTION_CHANGE and not include_attribution:
            continue
        buckets[(t.cls, t.call.tool.name)].append(t)
    groups = [
        Group(
            cls=cls,
            key=key,
            count=len(members),
            samples=tuple(sorted(members, key=lambda t: t.call.id)[:samples]),
        )
        for (cls, key), members in buckets.items()
    ]
    groups.sort(key=lambda g: (_CLASS_RANK[g.cls], -g.count, g.key))
    return tuple(groups)
