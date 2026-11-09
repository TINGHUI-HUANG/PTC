"""Deterministic simulator: the light's state at the end of a scenario.

Outcomes shown to the person come from here, not from the model's own description of its
rule: the simulated outcome is observed, the model's summary would only be a claim (Lecture 12).
"""
from itertools import product

from .schema import EFFECT


def fires(rule, state, event):
    """A rule fires when its events include this one and its conditions all hold just after it."""
    return event in rule["when"] and all(state[c] for c in rule["if"])


def simulate(reading, scenario):
    """Apply each event to the state; every rule that fires sets the light. A rule that does not
    fire leaves the light as it was."""
    state = dict(scenario["start"])
    for _time, event in scenario["events"]:
        key, value = EFFECT[event]
        state[key] = value
        for rule in reading["rules"]:
            if fires(rule, state, event):
                state["light"] = rule["do"]
    return state["light"]


def table(readings, scenarios):
    """{scenario id: {reading id: outcome}}"""
    return {s["id"]: {r["id"]: simulate(r, s) for r in readings} for s in scenarios}


def state_cases():
    """Every possible state and supported single event (events update their state first)."""
    for home, dark, light in product((False, True), (False, True), ("off", "on")):
        for event in EFFECT:
            yield {"start": {"home": home, "dark": dark, "light": light},
                   "events": [["", event]]}


def moments():
    """(state just after the event, event) for every case in state_cases()."""
    for case in state_cases():
        state = dict(case["start"])
        event = case["events"][0][1]
        key, value = EFFECT[event]
        state[key] = value
        yield state, event


def conflicts(reading):
    """Report simultaneous opposite actions, independent of rule ordering."""
    return any(len({r["do"] for r in reading["rules"] if fires(r, state, event)}) > 1
               for state, event in moments())


def dead_rules(reading):
    """Rules that fire in no possible state: their conditions cannot hold just after their own
    events. "When you leave home, if you are home" is one, because leaving makes "home" false."""
    cases = list(moments())
    return [r for r in reading["rules"] if not any(fires(r, state, event) for state, event in cases)]


def reachable_actions(reading):
    """The actions the reading can take in some state, which may be fewer than the ones it names."""
    dead = dead_rules(reading)
    return {r["do"] for r in reading["rules"] if r not in dead}


def distinct(readings, scenarios):
    """Merge only readings equivalent across every supported state and event."""
    cases = list(state_cases())
    kept, merged, seen = [], [], {}
    for r in readings:
        signature = tuple(simulate(r, s) for s in cases)
        if signature in seen:
            merged.append((r["id"], seen[signature]))
        else:
            seen[signature] = r["id"]
            kept.append(r)
    return kept, merged
