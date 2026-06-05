"""
Phase2 单元测试：layer2_filter 评分逻辑 + analyzer JSON 解析，均不需要真实 API。
运行：cd intel && python3 -m pytest tests/test_phase2.py -v
     或直接：cd intel && python3 tests/test_phase2.py
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.layer2_filter import score_title, filter_by_layer2
from services.analyzer import _parse_json_from_text, analyze_item, batch_analyze


# ─── Layer2 评分测试 ───────────────────────────────────────────────────────────

class TestLayer2Score(unittest.TestCase):

    def test_category_term_scores_2(self):
        # "防坠落" = category (+2), no signal word → 2
        self.assertEqual(score_title("防坠落安全绳"), 2)

    def test_category_plus_signal_scores_3(self):
        score = score_title("EHS管理技术展会报告")
        self.assertEqual(score, 3)

    def test_noise_term_subtracts(self):
        # "EHS" = category (+2), "招聘" = noise (-2) → 0
        score = score_title("EHS安全工程师招聘啦")
        self.assertEqual(score, 0)

    def test_pure_noise_is_negative(self):
        score = score_title("最新招聘信息优质岗位")
        self.assertLess(score, 0)

    def test_irrelevant_title_scores_0(self):
        score = score_title("今天天气很好适合出行")
        self.assertEqual(score, 0)

    def test_english_category_term(self):
        score = score_title("New wearable safety device launched in Shanghai")
        self.assertGreaterEqual(score, 2)

    def test_filter_splits_correctly(self):
        items = [
            {"title": "EHS传感器展会报告"},      # +3 → pass
            {"title": "今日招聘信息"},            # -2 → reject
            {"title": "工业安全系统新标准"},       # +3 → pass
            {"title": "随机新闻"},                # 0 → reject (min_score=1)
        ]
        passed, rejected = filter_by_layer2(items)
        self.assertEqual(len(passed), 2)
        self.assertEqual(len(rejected), 2)

    def test_layer2_score_added_to_item(self):
        items = [{"title": "EHS技术展览"}]
        passed, _ = filter_by_layer2(items)
        self.assertIn("layer2_score", passed[0])
        self.assertGreaterEqual(passed[0]["layer2_score"], 2)


# ─── Analyzer JSON 解析测试 ────────────────────────────────────────────────────

class TestParseJsonFromText(unittest.TestCase):

    def test_plain_json(self):
        raw = '{"category": "ehs_tech", "priority": "high"}'
        result = _parse_json_from_text(raw)
        self.assertEqual(result["category"], "ehs_tech")

    def test_code_block_json(self):
        raw = '```json\n{"category": "smart_ppe", "priority": "medium"}\n```'
        result = _parse_json_from_text(raw)
        self.assertEqual(result["category"], "smart_ppe")

    def test_bare_code_block(self):
        raw = '```\n{"category": "other"}\n```'
        result = _parse_json_from_text(raw)
        self.assertEqual(result["category"], "other")


# ─── analyze_item fallback 测试（mock API 失败） ────────────────────────────────

class TestAnalyzeItemFallback(unittest.TestCase):

    def test_api_failure_returns_fallback(self):
        item = {"title": "EHS管理新技术", "snippet": "摘要内容", "source_keyword": "EHS管理"}
        with patch("services.analyzer._call_deepseek", side_effect=RuntimeError("网络超时")):
            result = analyze_item(item)
        self.assertEqual(result["category"], "other")
        self.assertEqual(result["priority"], "low")
        self.assertIn("analyzed_at", result)

    def test_api_success_returns_correct_fields(self):
        mock_response = """{
            "category": "ehs_tech",
            "priority": "high",
            "summary_zh": "某企业发布EHS智能管理系统",
            "ciosh_relevance": "high",
            "ciosh_action": "可引进展商品类：EHS科技",
            "keywords": ["EHS", "智能管理", "工业安全"],
            "new_keyword_suggestion": "EHS智能系统"
        }"""
        item = {"title": "EHS智能系统发布", "snippet": "正文摘要", "source_keyword": "EHS管理"}
        with patch("services.analyzer._call_deepseek", return_value=mock_response):
            result = analyze_item(item)
        self.assertEqual(result["category"], "ehs_tech")
        self.assertEqual(result["priority"], "high")
        self.assertEqual(result["keywords"], ["EHS", "智能管理", "工业安全"])
        self.assertEqual(result["new_keyword_suggestion"], "EHS智能系统")

    def test_invalid_category_falls_back_to_other(self):
        mock_response = '{"category": "nonexistent", "priority": "high", "summary_zh": "test", "ciosh_relevance": "medium", "ciosh_action": "", "keywords": [], "new_keyword_suggestion": null}'
        item = {"title": "test", "snippet": "", "source_keyword": "test"}
        with patch("services.analyzer._call_deepseek", return_value=mock_response):
            result = analyze_item(item)
        self.assertEqual(result["category"], "other")


# ─── batch_analyze 测试 ────────────────────────────────────────────────────────

class TestBatchAnalyze(unittest.TestCase):

    def test_skips_duplicates(self):
        items = [
            {"title": "A", "snippet": "", "source_keyword": "kw", "is_duplicate": 1},
            {"title": "B", "snippet": "", "source_keyword": "kw", "is_duplicate": 0},
        ]
        mock_resp = '{"category":"ehs_tech","priority":"low","summary_zh":"B","ciosh_relevance":"low","ciosh_action":"","keywords":[],"new_keyword_suggestion":null}'
        with patch("services.analyzer._call_deepseek", return_value=mock_resp):
            results = batch_analyze(items)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "B")

    def test_respects_limit(self):
        items = [{"title": f"item{i}", "snippet": "", "source_keyword": "kw"} for i in range(10)]
        mock_resp = '{"category":"other","priority":"low","summary_zh":"x","ciosh_relevance":"low","ciosh_action":"","keywords":[],"new_keyword_suggestion":null}'
        with patch("services.analyzer._call_deepseek", return_value=mock_resp):
            results = batch_analyze(items, limit=3)
        self.assertEqual(len(results), 3)


# ─── keyword_evolver 测试（纯逻辑，不需要 DB）─────────────────────────────────

from services.keyword_evolver import apply_evolution, extract_new_keywords


class TestApplyEvolution(unittest.TestCase):

    def _base_db(self, words_and_tiers: list[tuple[str, int]]) -> dict:
        return {
            "version": "2026-W23",
            "last_updated": "2026-06-02",
            "keywords": [
                {
                    "word": w, "tier": t, "status": "active",
                    "hit_count_total": 0, "hit_count_quality": 0,
                    "yield_rate": 0.0, "last_hit": None,
                }
                for w, t in words_and_tiers
            ],
            "evolution_log": [],
        }

    def test_yield_rate_updated(self):
        db = self._base_db([("EHS管理", 1)])
        stats = {"EHS管理": {"total": 10, "quality": 3, "yield_rate": 0.3}}
        db, retired, added = apply_evolution(db, stats, [])
        kw = db["keywords"][0]
        self.assertEqual(kw["yield_rate"], 0.3)
        self.assertEqual(kw.get("low_yield_weeks", 0), 0)
        self.assertEqual(retired, [])

    def test_retire_after_two_low_yield_weeks(self):
        db = self._base_db([("低效词", 1)])
        db["keywords"][0]["low_yield_weeks"] = 1  # 已经低效 1 周
        stats = {"低效词": {"total": 20, "quality": 0, "yield_rate": 0.0}}
        db, retired, added = apply_evolution(db, stats, [])
        self.assertIn("低效词", retired)
        self.assertEqual(db["keywords"][0]["status"], "retired")

    def test_no_retire_first_low_yield_week(self):
        db = self._base_db([("新词", 1)])
        stats = {"新词": {"total": 20, "quality": 0, "yield_rate": 0.0}}
        db, retired, added = apply_evolution(db, stats, [])
        self.assertEqual(retired, [])
        self.assertEqual(db["keywords"][0]["status"], "active")
        self.assertEqual(db["keywords"][0].get("low_yield_weeks"), 1)

    def test_low_yield_resets_on_recovery(self):
        db = self._base_db([("恢复词", 1)])
        db["keywords"][0]["low_yield_weeks"] = 1
        stats = {"恢复词": {"total": 10, "quality": 4, "yield_rate": 0.4}}
        db, retired, added = apply_evolution(db, stats, [])
        self.assertEqual(db["keywords"][0].get("low_yield_weeks"), 0)
        self.assertEqual(retired, [])

    def test_new_candidate_added_as_tier3(self):
        db = self._base_db([("EHS管理", 1)])
        db, retired, added = apply_evolution(db, {}, ["防坠落智能设备"])
        self.assertIn("防坠落智能设备", added)
        new_kw = next(k for k in db["keywords"] if k["word"] == "防坠落智能设备")
        self.assertEqual(new_kw["tier"], 3)
        self.assertEqual(new_kw["added_by"], "auto")
        self.assertEqual(new_kw["status"], "active")

    def test_duplicate_candidate_not_added(self):
        db = self._base_db([("EHS管理", 1)])
        db, _, added = apply_evolution(db, {}, ["EHS管理"])
        self.assertNotIn("EHS管理", added)
        self.assertEqual(len(db["keywords"]), 1)

    def test_version_and_last_updated_always_set(self):
        db = self._base_db([])
        db, _, _ = apply_evolution(db, {}, [], today="2026-06-09")
        self.assertEqual(db["last_updated"], "2026-06-09")
        self.assertIn("W", db["version"])

    def test_evolution_log_appended(self):
        db = self._base_db([("旧词", 1)])
        db["keywords"][0]["low_yield_weeks"] = 1
        stats = {"旧词": {"total": 10, "quality": 0, "yield_rate": 0.0}}
        db, retired, added = apply_evolution(db, stats, ["新候选词"])
        self.assertEqual(len(db["evolution_log"]), 1)
        log = db["evolution_log"][0]
        self.assertIn("旧词", log["retired"])
        self.assertIn("新候选词", log["added"])


if __name__ == "__main__":
    unittest.main()
