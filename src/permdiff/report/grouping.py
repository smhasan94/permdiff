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


ReasonsOf = Callable[[Transition], tuple[str, ...]]


def changed_reasons(t: Transition) -> tuple[str, ...]:
    return _changed_decision(t)


def _top_reasons(
    members: Sequence[Transition], reasons_of: ReasonsOf, limit: int = 3
) -> tuple[str, ...]:
    counter: Counter[str] = Counter(r for t in members for r in reasons_of(t))
    return tuple(reason for reason, _ in counter.most_common(limit))


def group_transitions(
    transitions: Sequence[Transition],
    *,
    by: Sequence[str] = DEFAULT_GROUP_BY,
    samples: int = DEFAULT_SAMPLES,
    include_unchanged: bool = False,
    include_attribution: bool = False,
    principal_key: Callable[[str], str] | None = None,
    sample_transform: Callable[[Transition], Transition] | None = None,
    reasons_of: ReasonsOf = changed_reasons,
) -> tuple[Group, ...]:
    """Groups sorted widening first, then by count descending, then label (AC-16.3).

    ``principal_key`` maps principal ids for grouping (the redactor's hash),
    ``sample_transform`` redacts only the sampled transitions, and ``reasons_of`` yields
    already-scrubbed reason text per member, so a 100K corpus is never copied whole.
    """
    fields = validate_group_by(by)
    extractors = dict(GROUP_FIELDS)
    if principal_key is not None:
        extractors["principal"] = lambda t: principal_key(t.call.principal.id)
    buckets: dict[GroupKey, list[Transition]] = defaultdict(list)
    for t in transitions:
        if t.cls is TransitionClass.UNCHANGED and not include_unchanged:
            continue
        if t.cls is TransitionClass.ATTRIBUTION_CHANGE and not include_attribution:
            continue
        key = GroupKey(cls=t.cls, parts=tuple((f, extractors[f](t)) for f in fields))
        buckets[key].append(t)
    transform = sample_transform or (lambda t: t)
    groups = [
        Group(
            key=key,
            count=len(members),
            samples=tuple(
                transform(t) for t in sorted(members, key=lambda t: t.call.id)[: max(samples, 0)]
            ),
            reasons=_top_reasons(members, reasons_of),
        )
        for key, members in buckets.items()
    ]
    groups.sort(key=lambda g: (_CLASS_RANK[g.cls], -g.count, g.label))
    return tuple(groups)
