import argparse
import json
import sys
from pathlib import Path


INTELLIGENCE_DIR = Path(__file__).resolve().parents[1]
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from signals.ai_generator import ai_available
from signals.ai_generator import env_config
from signals.ai_generator import generate_ai_signals
from signals.extractor import build_heuristic_signals
from signals.loader import load_candidates
from signals.loader import resolve_date
from signals.models import SignalBuildResult


ROOT = INTELLIGENCE_DIR.parents[1]
SIGNALS_DIR = ROOT / "intelligence" / "signals"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build PAOS intelligence signals from candidate pool."
    )
    parser.add_argument("--category", required=True)
    parser.add_argument("--date", default="today")
    parser.add_argument(
        "--mode",
        choices=["auto", "ai", "heuristic"],
        default="auto",
    )
    return parser.parse_args()


def output_path_for(date, category):
    return SIGNALS_DIR / date / f"{category}.jsonl"


def write_signals(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=True) + "\n")


def build_signal_layer(category, date, mode="auto"):
    resolved_date = resolve_date(date)
    input_path, candidates = load_candidates(date=resolved_date, category=category)
    generation_mode = "heuristic"
    fallback_used = False
    diagnostics = {
        "input_path": str(input_path),
        "generation_mode": "heuristic",
        "fallback_used": False,
        "ai_provider": env_config().get("provider") or None,
        "ai_model": env_config().get("model") or None,
    }

    if mode == "heuristic":
        signals, themes, heuristic_diagnostics = build_heuristic_signals(candidates)
        diagnostics.update(heuristic_diagnostics)
    else:
        try:
            if mode == "ai" and not ai_available():
                raise RuntimeError("AI mode requested but AI configuration is unavailable.")
            if mode in {"auto", "ai"}:
                signals, themes, ai_diagnostics = generate_ai_signals(
                    category=category,
                    candidates=candidates,
                )
                generation_mode = "ai"
                diagnostics.update(ai_diagnostics)
                diagnostics["generation_mode"] = "ai"
        except Exception as exc:
            if mode == "ai":
                raise
            fallback_used = True
            diagnostics["fallback_used"] = True
            diagnostics["ai_error"] = str(exc)
            signals, themes, heuristic_diagnostics = build_heuristic_signals(candidates)
            diagnostics.update(heuristic_diagnostics)
            diagnostics["generation_mode"] = "heuristic"

    if mode == "heuristic":
        generation_mode = "heuristic"

    output_path = output_path_for(resolved_date, category)
    write_signals(output_path, signals)

    return SignalBuildResult(
        date=resolved_date,
        category=category,
        candidates_loaded=len(candidates),
        themes_detected=themes,
        signals_generated=len(signals),
        output_path=output_path,
        generation_mode=generation_mode,
        fallback_used=fallback_used,
        diagnostics=diagnostics,
    )


def print_result(result):
    print("Signal Build")
    print(f"date: {result.date}")
    print(f"category: {result.category}")
    print(f"candidates_loaded: {result.candidates_loaded}")
    print(f"themes_detected: {len(result.themes_detected)}")
    print(f"signals_generated: {result.signals_generated}")
    print(f"generation_mode: {result.generation_mode}")
    print(f"fallback_used: {result.fallback_used}")
    print(f"output_path: {result.output_path}")
    print("diagnostics:")
    for key, value in result.diagnostics.items():
        print(f"  {key}: {value}")


def main():
    args = parse_args()
    result = build_signal_layer(category=args.category, date=args.date, mode=args.mode)
    print_result(result)


if __name__ == "__main__":
    main()
