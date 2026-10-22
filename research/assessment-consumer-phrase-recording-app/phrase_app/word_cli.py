"""Explicit single-word wrapper around the unchanged frozen research CLI."""
import argparse
from pathlib import Path
import sys

PROTOTYPE = Path(__file__).resolve().parents[3] / "research/audio-head/local_wav_prototype"
sys.path.insert(0, str(PROTOTYPE))
from cli import run  # noqa: E402
from common import Refused, allowed_input, parse, read  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--prompt-json", type=Path, required=True)
    context = parser.add_mutually_exclusive_group(required=True)
    context.add_argument("--recognition-only", action="store_true")
    context.add_argument("--age-years", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        allowed_input(args.prompt_json)
        prompt = parse(read(args.prompt_json.absolute(), 512_000))
        receipt = run(args.wav, prompt, args.age_years, args.output, mode="word")
        return 0 if receipt["status"] in ("abstain", "recognition_only", "research_scores") else 1
    except (Refused, OSError, ValueError, KeyError, TypeError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
