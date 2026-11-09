import unittest
import json
from io import BytesIO
from unittest.mock import patch

from crawler_platform.query_planner import enabled_aliases, generate_terms, validate_terms


def empty_plan():
    return {kind: {language: [] for language in ("zh", "en")}
            for kind in ("translations", "synonyms", "related")}


class QueryPlannerTests(unittest.TestCase):
    def test_preserves_manual_aliases_and_disables_related(self):
        plan = empty_plan()
        plan["translations"]["en"] = ["embodied AI"]
        plan["synonyms"]["en"] = ["Embodied AI", "embodied intelligence"]
        plan["related"]["en"] = ["robotics"]
        self.assertEqual(["manual"], enabled_aliases(plan, "具身智能", ["manual"]))
        self.assertEqual(["manual", "embodied AI", "embodied intelligence"],
                         enabled_aliases(plan, "具身智能", ["manual"],
                                         ["embodied AI", "embodied intelligence", "robotics"]))

    def test_rejects_extra_keys_and_unsafe_terms(self):
        plan = empty_plan()
        plan["other"] = {}
        with self.assertRaises(ValueError):
            validate_terms(plan, "具身智能")
        del plan["other"]
        plan["synonyms"]["en"] = ["AI; DROP TABLE"]
        with self.assertRaises(ValueError):
            validate_terms(plan, "具身智能")

    def test_provider_response_is_validated_without_exposing_key(self):
        plan = empty_plan()
        plan["translations"]["en"] = ["embodied AI"]
        response = {"model": "deepseek-flash", "usage": {"total_tokens": 9},
                    "choices": [{"message": {"content": json.dumps(plan)}}]}
        body = json.dumps(response).encode("utf-8")
        class Response(BytesIO):
            pass
        def open_request(request, timeout):
            self.assertEqual("Bearer secret", request.get_header("Authorization"))
            self.assertEqual(45, timeout)
            return Response(body)
        with patch("crawler_platform.query_planner.urlopen", open_request):
            result = generate_terms("具身智能", api_key="secret", opener=open_request)
        self.assertEqual("embodied AI", result["terms"]["translations"]["en"][0])
        self.assertEqual(9, result["usage"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
