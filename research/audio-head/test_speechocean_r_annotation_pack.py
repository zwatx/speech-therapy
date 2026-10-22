import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import speechocean_r_annotation_pack as pack


class ReviewerPackTests(unittest.TestCase):
    def test_local_packs_blind_source_fields_and_repair_corrupt_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.json").write_text("{}\n")
            source = root / "source"
            source.mkdir()
            rows = []
            for index in range(40):
                payload = b"RIFF" + bytes([index]) * 32
                audio = source / f"source-{index:02d}.wav"
                audio.write_bytes(payload)
                rows.append({
                    "sourceId": f"source-{index:02d}",
                    "speakerId": f"speaker-{index:02d}",
                    "age": 9,
                    "aggregateRScore": 0.4,
                    "fiveRaterScores": [0, 0, 0, 0, 2],
                    "reviewerId": f"{index + 1000:016x}",
                    "wavPath": str(audio),
                    "wavSha256": hashlib.sha256(payload).hexdigest(),
                    "targetPrompt": "Read a word",
                    "targetWord": "word",
                    "wordIndexZeroBased": 2,
                    "phoneIndexWithinWordZeroBased": 1,
                })
            local_packs = root / "local-reviewer-packs"
            with (patch.object(pack, "source_rows", return_value=(rows, b"q" * 32)),
                  patch.object(pack, "OUTPUT", root),
                  patch.object(pack, "PACK_ROOT", local_packs)):
                report = pack.prepare_packs()
                self.assertTrue(report["independentPresentationOrders"])
                orders = []
                for reviewer in pack.PACK_NAMES:
                    directory = local_packs / reviewer
                    queue = json.loads((directory / "queue.json").read_text())
                    self.assertEqual(stat.S_IMODE(local_packs.stat().st_mode), 0o700)
                    self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
                    self.assertEqual(stat.S_IMODE((directory / "media").stat().st_mode), 0o700)
                    self.assertEqual(stat.S_IMODE((directory / "queue.json").stat().st_mode), 0o600)
                    self.assertEqual(len(queue["items"]), 40)
                    orders.append([item["reviewerId"] for item in queue["items"]])
                    self.assertEqual(len(list((directory / "media").glob("*.wav"))), 40)
                    encoded = json.dumps(queue)
                    self.assertNotIn("source-", encoded)
                    self.assertNotIn("speaker-", encoded)
                    self.assertNotIn("aggregateRScore", encoded)
                    self.assertNotIn("fiveRaterScores", encoded)
                    for item in queue["items"]:
                        self.assertEqual(stat.S_IMODE(
                            (directory / item["audioFile"]).stat().st_mode), 0o600)
                        self.assertEqual(set(item), {
                            "reviewerId", "audioFile", "targetPrompt", "targetWord",
                            "wordIndexZeroBased", "phoneIndexWithinWordZeroBased",
                        })
                        self.assertEqual(
                            hashlib.sha256((directory / item["audioFile"]).read_bytes()).hexdigest(),
                            next(row["wavSha256"] for row in rows
                                 if row["reviewerId"] == item["reviewerId"]),
                        )
                self.assertNotEqual(*orders)
                damaged = local_packs / "reviewer-a" / "media" / f"{rows[0]['reviewerId']}.wav"
                damaged.write_bytes(b"corrupted")
                damaged.chmod(0o644)
                (local_packs / "reviewer-b" / "media" / f"{rows[1]['reviewerId']}.wav").chmod(0o644)
                (local_packs / "reviewer-a" / "queue.json").chmod(0o644)
                (local_packs / "reviewer-b" / "media").chmod(0o755)
                second = pack.prepare_packs()
                self.assertEqual(second, report)
                self.assertEqual(hashlib.sha256(damaged.read_bytes()).hexdigest(),
                                 rows[0]["wavSha256"])
                self.assertEqual(stat.S_IMODE(damaged.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE((local_packs / "reviewer-b" / "media" /
                                               f"{rows[1]['reviewerId']}.wav").stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE((local_packs / "reviewer-a" / "queue.json").stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE((local_packs / "reviewer-b" / "media").stat().st_mode), 0o700)
                linked = local_packs / "reviewer-a" / "media" / f"{rows[2]['reviewerId']}.wav"
                original = Path(rows[2]["wavPath"])
                linked.unlink()
                original.chmod(0o644)
                linked.hardlink_to(original)
                pack.prepare_packs()
                self.assertEqual(stat.S_IMODE(original.stat().st_mode), 0o644)
                self.assertEqual(stat.S_IMODE(linked.stat().st_mode), 0o600)
                self.assertEqual(linked.stat().st_nlink, 1)
                self.assertEqual(linked.read_bytes(), original.read_bytes())
                (local_packs / "reviewer-a" / "media" / "stale.wav").write_bytes(b"old run")
                with self.assertRaisesRegex(ValueError, "stale or unexpected"):
                    pack.prepare_packs()
                redirected = root / "redirected"
                redirected.symlink_to(root, target_is_directory=True)
                with patch.object(pack, "PACK_ROOT", redirected / "local-reviewer-packs"):
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        pack.prepare_packs()


if __name__ == "__main__":
    unittest.main()
