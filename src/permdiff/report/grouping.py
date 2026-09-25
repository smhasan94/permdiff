"""Group transitions by class plus configurable fields, with deterministic samples (FR-16)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence

from permdiff.errors import ConfigError
from permdiff.models import Frozen, Transition, TransitionClass

DEFAULT_SAMPLES = 3
DEFAULT_GROUP_BY: tuple[str, ...] = ("tool",)
DEFAULT_MAX_GROUPS = 50

_CLASS_RANK: dict[TransitionClass, int] = {
    TransitionClass.WIDENING: 0,
    TransitionClass.TIGHTENING: 1,
    TransitionClass.CANT_EVALUATE: 2,
    TransitionClass.ATTRIBUTION_CHANGE: 3,
    TransitionClass.UNCHANGED: 4,
}


def _changed_decision(t: Transition) -> tuple[str, ...]:
    """Reasons from the side that explains the transition: head unless only base errored."""
    decision = t.base if (t.base.is_error and not t.head.is_error) else t.head
    return decision.reasons


GROUP_FIELDS: dict[str, Callable[[Transition], str]] = {
    "tool": lambda t: t.call.tool.name,
    "resource.type": lambda t: t.call.resource.type or "-",
    "agent": lambda t: t.call.agent.id,
    "principal": lambda t: t.call.principal.id,
    "reason": lambda t: (_changed_decision(t) or ("-",))[0],
}
"""``--group-by`` fields. Grouping runs on the redacted report, so principal ids are hashed."""


def validate_group_by(fields: Sequence[str]) -> tuple[str, ...]:
    cleaned = tuple(dict.fromkeys(f.strip() for f in fields if f.strip()))
    unknown = [f for f in cleaned if f not in GROUP_FIELDS]
    if unknown:
        msg = (
            f"--group-by: unknown field(s) {', '.join(unknown)}; "
            f"choose from {', '.join(GROUP_FIELDS)}"
        )
        raise ConfigError(msg)
    return cleaned or DEFAULT_GROUP_BY


class GroupKey(Frozen):
    cls: TransitionClass
    parts: tuple[tuple[str, str], ...]
    """``(field, value)`` pairs in ``--group-by`` order."""

    @property
    def label(self) -> str:
        """Bare value for the default single ``tool`` key, else ``field=value`` pairs."""
        if len(self.parts) == 1 and self.parts[0][0] == "tool":
            return self.parts[0][1]
        return ", ".join(f"{field}={value}" for field, value in self.parts)


class Group(Frozen):
    key: GroupKey
    count: int
    samples: tuple[Transition, ...]
    reasons: tuple[str, ...]
    """Distinct reasons across the group, most common first (at most three)."""

    @property
    def cls(self) -> TransitionClass:
        return self.key.cls

    @property
    def label(self) -> str:
        return self.key.label

    @property
    def effects(self) -> str:
        """``deny → allow`` style summary from the first sample."""
        first = self.samples[0]
        return f"{first.base.effect.value} → {first.head.effect.value}"


def _top_reasons(members: Sequence[Transition], limit: int = 3) -> tuple[str, ...]:
    counter: Counter[str] = Counter(r for t in members for r in _changed_decision(t))
    return tuple(reason for reason, _ in counter.most_common(limit))


def group_transitions(
    transitions: Sequence[Transition],
    *,
    by: Sequence[str] = DEFAULT_GROUP_BY,
    samples: int = DEFAULT_SAMPLES,
    include_unchanged: bool = False,
    include_attribution: bool = False,
) -> tuple[Group, ...]:
    """Groups sorted widening first, then by count descending, then label (AC-16.3)."""
    fields = validate_group_by(by)
    buckets: dict[GroupKey, list[Transition]] = defaultdict(list)
    for t in transitions:
        if t.cls is TransitionClass.UNCHANGED and not include_unchanged:
            continue
        if t.cls is TransitionClass.ATTRIBUTION_CHANGE and not include_attribution:
            continue
        key = GroupKey(cls=t.cls, parts=tuple((f, GROUP_FIELDS[f](t)) for f in fields))
        buckets[key].append(t)
    groups = [
        Group(
            key=key,
            count=len(members),
            samples=tuple(sorted(members, key=lambda t: t.call.id)[: max(samples, 0)]),
            reasons=_top_reasons(members),
        )
        for key, members in buckets.items()
    ]
    groups.sort(key=lambda g: (_CLASS_RANK[g.cls], -g.count, g.label))
    return tuple(groups)
