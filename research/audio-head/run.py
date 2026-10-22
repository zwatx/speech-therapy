"""Run from any directory with this script's isolated Python environment."""
import argparse
from pathlib import Path

from data import load_manifest, make_fixtures
from pipeline import infer, train


def main():
    parser = argparse.ArgumentParser(description="Local engineering-only phone-head experiments")
    sub = parser.add_subparsers(dest="command", required=True)
    fixtures = sub.add_parser("fixtures", help="Generate labeled tones, not human speech")
    fixtures.add_argument("directory", type=Path)
    fixtures.add_argument("--seed", type=int, default=7)
    validate = sub.add_parser("validate")
    validate.add_argument("manifest", type=Path)
    fit = sub.add_parser("train")
    fit.add_argument("manifest", type=Path)
    fit.add_argument("output", type=Path)
    fit.add_argument("--encoder", choices=["spectral-engineering-v1", "wav2vec2-base",
                                          "wavlm-base-plus", "hubert-base-ls960"], default="wav2vec2-base")
    fit.add_argument("--steps", type=int, default=200)
    fit.add_argument("--seed", type=int, default=7)
    fit.add_argument("--head-seed", type=int, help="Optional independent head initialization seed; omission preserves legacy behavior")
    fit.add_argument("--learning-rate", type=float, default=0.01)
    predict = sub.add_parser("infer")
    predict.add_argument("checkpoint", type=Path)
    predict.add_argument("audio", type=Path)
    predict.add_argument("output", type=Path)
    for command in (fit, predict):
        command.add_argument("--cache", type=Path, default=Path(__file__).parent / "outputs" / "model-cache")
        command.add_argument("--allow-model-download", action="store_true",
                             help="Allow fetching the selected pinned upstream encoder snapshot (about 380 MB)")
    args = parser.parse_args()
    try:
        if args.command == "fixtures":
            print(make_fixtures(args.directory, args.seed))
        elif args.command == "validate":
            _, rows = load_manifest(args.manifest)
            print(f"Validated {len(rows)} engineering fixtures across disjoint splits.")
        elif args.command == "train":
            report = train(args.manifest, args.output, args.encoder, args.cache, args.steps,
                           args.seed, args.learning_rate, args.allow_model_download, head_seed=args.head_seed)
            print(f"Saved {args.output / 'report.json'}")
            print(f"Train CTC loss: {report['initialTrain']['ctcLoss']:.5f} -> {report['splits']['train']['ctcLoss']:.5f}")
            print("Engineering-only, uncalibrated, productionEligible=false, learnerFeedbackEligible=false")
        else:
            result = infer(args.checkpoint, args.audio, args.output, args.cache, args.allow_model_download)
            print(f"Exported {len(result['frames'])} normalized frame posteriors to {args.output}")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Experiment failed: {exc}\n")


if __name__ == "__main__":
    main()
