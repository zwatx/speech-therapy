import copy
import unittest

from speechocean_r_label_audit import derive_one_r, selected_json_objects


def fixture():
    aggregate = {"accuracy": 8, "completeness": 10, "fluency": 8, "prosodic": 8,
                 "total": 8, "text": "SAY BEAR", "words": [
                     {"text": "BEAR", "phones": ["B", "EH0", "R"],
                      "phones-accuracy": [2, 2, 1.0]}]}
    detailed = {"accuracy": [8] * 5, "completeness": [1] * 5,
                "fluency": [8] * 5, "prosodic": [8] * 5, "total": [8] * 5,
                "text": "SAY BEAR", "words": [
                    {"text": "BEAR", "ref-phones": "B EH0 R",
                     "phones": ["B EH0 (R)", "B EH0 {R}", "B EH0 R",
                                "B EH0 (R)", "B EH0 [L] R"]}]}
    return aggregate, detailed


class SelectiveParsingTests(unittest.TestCase):
    def test_only_requested_train_object_is_decoded(self):
        data = (b'{"train":{"words":[]},'
                b'"test":{"unparsed":"brace } and quote \\"", "rating":NaN}}')
        self.assertEqual(selected_json_objects(data, {"train"}), {"train": {"words": []}})

    def test_duplicate_or_missing_selected_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            selected_json_objects(b'{"train":{},"train":{}}', {"train"})
        with self.assertRaisesRegex(ValueError, "missing"):
            selected_json_objects(b'{"other":{}}', {"train"})


class RaterReconstructionTests(unittest.TestCase):
    def test_five_scores_are_derived_from_annotation_grammar(self):
        aggregate, detailed = fixture()
        self.assertEqual(derive_one_r(aggregate, detailed), (1.0, (0, 1, 2, 0, 2)))

    def test_multi_r_is_excluded(self):
        aggregate, detailed = fixture()
        aggregate["words"].append(copy.deepcopy(aggregate["words"][0]))
        detailed["words"].append(copy.deepcopy(detailed["words"][0]))
        self.assertIsNone(derive_one_r(aggregate, detailed))

    def test_malformed_annotation_and_aggregate_mismatch_rejected(self):
        aggregate, detailed = fixture()
        detailed["words"][0]["phones"][0] = "B EH0 (R"
        with self.assertRaisesRegex(ValueError, "Malformed rater phone token"):
            derive_one_r(aggregate, detailed)
        aggregate, detailed = fixture()
        aggregate["words"][0]["phones-accuracy"][2] = 1.2
        with self.assertRaisesRegex(ValueError, "aggregate differs"):
            derive_one_r(aggregate, detailed)

    def test_canonical_mismatch_rejected_even_if_r_token_exists(self):
        aggregate, detailed = fixture()
        detailed["words"][0]["phones"][0] = "B AH0 (R)"
        with self.assertRaisesRegex(ValueError, "Rater phone sequence differs"):
            derive_one_r(aggregate, detailed)


if __name__ == "__main__":
    unittest.main()
