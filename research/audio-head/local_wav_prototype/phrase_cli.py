"""Explicit short-phrase research preview; no recording or clinical feedback."""
import argparse
from pathlib import Path

from bindings import configuration
from cli import run
from common import Refused, allowed_input, canonical, parse, read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, required=True, help="Existing mono 16 kHz PCM16 WAV, 0.1–4 seconds")
    parser.add_argument("--prompt-json", type=Path, required=True, help="Explicit schema-2 canonical phrase, 2–8 words")
    parser.add_argument("--age-years", type=int, required=True, help="Genuinely known completed child age, 6–12")
    parser.add_argument("--output", type=Path, required=True, help="Fresh direct child of outputs/local-phrase-prototype")
    args = parser.parse_args()
    created = False
    try:
        configuration()
        allowed_input(args.prompt_json)
        prompt = parse(read(args.prompt_json.absolute(), 512000))
        existed = args.output.exists()
        try:
            result = run(args.wav, prompt, args.age_years, args.output, mode="phrase-v1")
        finally:
            created = not existed and args.output.exists()
        print(canonical({"mode": "phrase-v1", "status": result["status"], "reason": result["reason"],
              "scoredOccurrences": sum(t.get("subjectiveCorpusRatingProbabilities") is not None for t in result["targets"]),
              "cleanupConfirmed": result["cleanupConfirmed"], "elapsedSeconds": result["elapsedSeconds"],
              "receipt": str(args.output.absolute() / "receipt.json"), "researchOnly": True,
              "learnerFeedbackEligible": False, "clinicalUseEligible": False}).decode())
        return 0 if result["status"] in ("abstain", "research_scores") else 1
    except Refused as error:
        print(canonical({"status": "failed" if created else "refused_before_execution",
                         "reason": str(error), "researchOnly": True}).decode())
        return 1 if created else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(canonical({"status": "failed" if created else "refused_before_execution",
                         "reason": "receipt_or_execution_failed" if created else "input_unreadable_or_invalid",
                         "exceptionType": type(error).__name__, "researchOnly": True}).decode())
        return 1 if created else 2


if __name__ == "__main__":
    raise SystemExit(main())
