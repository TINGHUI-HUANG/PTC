"""Record live Gemini readings for the example requests. Needs your own key in .env or the environment.

  py -3.11 tools/record_readings.py --check          find an endpoint and model that answer
  py -3.11 tools/record_readings.py --list-models    models the key can call (Gemini API endpoint only)
  py -3.11 tools/record_readings.py                  record every example request
  py -3.11 tools/record_readings.py --only B,E       record some of them
  py -3.11 tools/record_readings.py --out data/stability_run.json   a second run, not replayed by the app
  py -3.11 tools/record_readings.py --recheck        recheck the recorded replies; no key, no model call

The key is never printed or saved. Each recording is appended to data/recorded_readings.json with
what was sent, the raw reply and an automatic check against the prompt's success criteria.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from checker import readings, restate, schema, simulator  # noqa: E402

PROBE = "Turn on the hallway light when I arrive home."
STORE = ROOT / "data" / "recorded_readings.json"
NOTE = ("Live Gemini replies to the example requests, recorded with tools/record_readings.py. The web app "
        "replays the latest successful recording of a request, so reviewers need no key. 'context' is "
        "exactly what was sent; 'check' is the automatic check against the prompt's success criteria.")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def as_sent(text):
    """The reply exactly as the model sent it: (what the checker would have to fix, readings sent)."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ["the reply is not valid JSON"], 0
    sent = payload.get("readings") if isinstance(payload, dict) else None
    return schema.raw_problems(payload), len(sent) if isinstance(sent, list) else 0


def criteria(spec, generated, scenarios):
    """The success criteria a program can check (docs/prompt_log.md lists all of them).

    C1 and C3 judge the reply as sent, before the checker's lenient reading fills in or drops anything;
    C4 compares the readings in all 24 states and events (simulator.state_cases)."""
    problems, count = as_sent(generated.raw_text)
    result = {"C1 shape as sent": not problems}
    if spec.get("expect", "in_scope") == "in_scope":
        result["C2 vocabulary"] = not generated.unsupported
        result["C3 1-3 readings as sent"] = 1 <= count <= schema.MAX_READINGS
        if len(generated.readings) < 2:
            result["C4 readings differ"] = "n/a (one reading)"
        else:
            result["C4 readings differ"] = not simulator.distinct(generated.readings, scenarios)[1]
    else:
        result["C5 declined"] = bool(generated.unsupported) and not generated.readings
    return result


def verdict(check):
    return ", ".join(f"{name} {'pass' if ok is True else 'FAIL' if ok is False else ok}" for name, ok in check.items())


def separated_by_library(readings_, scenarios):
    """Whether the five library scenarios alone tell every pair of readings apart."""
    rows = {tuple(simulator.simulate(r, s) for s in scenarios) for r in readings_}
    return len(rows) == len(readings_)


def recheck(store_path=STORE):
    """Recompute the criteria from the stored raw replies (the latest successful one per request)."""
    specs = load_json(ROOT / "data" / "requests.json")["requests"]
    scenarios = load_json(ROOT / "data" / "scenarios.json")["scenarios"]
    store = load_json(store_path)["recordings"]
    print(f"Rechecking the latest successful recording of each request in {store_path.relative_to(ROOT)}; "
          "no model call.\n")
    for spec in specs:
        ok = [r for r in store if r["request_id"] == spec["id"] and not r.get("error")]
        if not ok:
            print(f"  {spec['id']}: no successful recording")
            continue
        record = ok[-1]
        generated = readings.interpret(spec["text"], record["raw_text"], {"kind": "recorded"}, record["context"])
        problems, count = as_sent(record["raw_text"])
        print(f"  {spec['id']} ({record['time'][:16]}, {count} reading(s) sent): {verdict(criteria(spec, generated, scenarios))}")
        if problems:
            print(f"      the checker had to fix: {'; '.join(problems)}")
        if len(generated.readings) > 1:
            print(f"      the five library scenarios tell them apart: "
                  f"{'yes' if separated_by_library(generated.readings, scenarios) else 'no'}")
        print(describe(generated))
    return 0


def describe(generated):
    lines = []
    if generated.unsupported:
        lines.append(f"      unsupported: {'; '.join(generated.unsupported)}")
    for r in generated.readings:
        try:
            text = restate.reading_text(r)
        except KeyError:
            text = json.dumps(r["rules"])
        lines.append(f"      {r['id']} ({r['label']}): {text}")
    return "\n".join(lines)


def check(key):
    endpoints = [os.environ["GEMINI_ENDPOINT"]] if os.environ.get("GEMINI_ENDPOINT") else list(readings.ENDPOINTS)
    models = [os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else list(readings.MODEL_CANDIDATES)
    context = readings.build_context(PROBE)
    for endpoint in endpoints:
        for model in models:
            started = time.time()
            try:
                text, meta = readings.call(context, endpoint, model, key, timeout=60)
            except readings.GeneratorError as error:
                print(f"  {endpoint:15} {model:24} failed: {error}")
                continue
            print(f"  {endpoint:15} {model:24} OK in {time.time() - started:.1f} s "
                  f"(model version {meta.get('model_version')})")
            settings = {"endpoint": endpoint, "model": model, "model_version": meta.get("model_version"),
                        "checked": readings.now()}
            (ROOT / "data" / "live_config.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
            print(f"Saved endpoint and model (no key) to data/live_config.json.\nReply to the test request: {text}")
            return 0
    print("No endpoint and model answered. Check the key, or set GEMINI_MODEL to a model from --list-models.")
    return 1


def list_models(key):
    request = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                                     headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            models = json.loads(response.read().decode("utf-8")).get("models", [])
    except urllib.error.HTTPError as error:
        print(f"Listing failed: HTTP {error.code}. Vertex AI express keys cannot list models; use --check.")
        return 1
    for m in models:
        if "generateContent" in m.get("supportedGenerationMethods", []):
            print(f"  {m['name'].removeprefix('models/'):40} {m.get('displayName', '')}")
    return 0


def record(key, only, version, pause, store_path=STORE):
    endpoint, model = readings.live_settings()
    specs = load_json(ROOT / "data" / "requests.json")["requests"]
    if only:
        specs = [s for s in specs if s["id"] in set(only.split(","))]
    scenarios = load_json(ROOT / "data" / "scenarios.json")["scenarios"]
    store = load_json(store_path) if store_path.exists() else {"note": NOTE, "recordings": []}
    print(f"Recording {len(specs)} request(s) with {endpoint} / {model}, prompt {version}.")
    failures = 0
    for i, spec in enumerate(specs):
        if i:
            time.sleep(pause)
        context = readings.build_context(spec["text"], version)
        entry = {"request_id": spec["id"], "request": spec["text"], "time": readings.now(), "endpoint": endpoint,
                 "model": model, "prompt_version": version, "temperature": readings.TEMPERATURE, "context": context}
        started = time.time()
        try:
            text, meta = readings.call(context, endpoint, model, key)
        except readings.GeneratorError as error:
            entry["error"] = str(error)
            failures += 1
            print(f"  {spec['id']}: failed: {error}")
        else:
            entry.update(latency_s=round(time.time() - started, 1), model_version=meta.get("model_version"),
                         finish_reason=meta.get("finish_reason"), raw_text=text)
            generated = readings.interpret(spec["text"], text, {"kind": "live"}, context)
            entry["check"] = criteria(spec, generated, scenarios)
            entry["as_sent_problems"] = as_sent(text)[0]
            print(f"  {spec['id']}: {verdict(entry['check'])} ({entry['latency_s']} s)\n{describe(generated)}")
        store["recordings"].append(entry)
        store_path.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved to {store_path.relative_to(ROOT)}.")
    return 1 if failures else 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="find an endpoint and model that answer")
    parser.add_argument("--list-models", action="store_true", help="list models (Gemini API endpoint only)")
    parser.add_argument("--only", help="comma-separated request ids, for example B,E")
    parser.add_argument("--prompt", default=readings.PROMPT_VERSION, help="prompt version, for example v1")
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between calls (free-tier rate limits)")
    parser.add_argument("--out", help="write to this file instead (the app only replays data/recorded_readings.json)")
    parser.add_argument("--recheck", action="store_true",
                        help="recheck the stored replies against the criteria; needs no key and calls no model")
    args = parser.parse_args()
    if args.recheck:
        return recheck(ROOT / args.out if args.out else STORE)
    key = readings.api_key()
    if not key:
        print("No GEMINI_API_KEY in the environment or in .env (see .env.example).")
        return 1
    print("Key found (not shown).")
    if args.list_models:
        return list_models(key)
    if args.check:
        return check(key)
    return record(key, args.only, args.prompt, args.pause, ROOT / args.out if args.out else STORE)


if __name__ == "__main__":
    sys.exit(main())
