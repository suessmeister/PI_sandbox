import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from experiment import run_experiment
from generator import default_game, render_game
from judge import measure_gameplay, metric
from render import render_payload


def judgment(progress=0, release=None):
    return {"release": {"score": release, "reason": "Reference comparison", "evidence": []},
            "retrieval_progress": {"score": progress, "reason": "Observed answer", "evidence": ["Answer"]}}


def batch(number=1):
    result=[]
    for i in range(1,4):
        game=default_game()
        game.name=f"Candidate {number}-{i}"
        result.append({"candidate_id":i,"game":game.model_dump(),"text":render_game(game,32),
                       "mutation_mode":"interleaved_game","rationale":"Test"})
    return result


class OptimizationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.base = self.root / "base.png"
        Image.new("RGB", (100, 50), "red").save(self.base)

    def run_loop(self, judgments, rounds=1, batches=None, **options):
        batches = [batch(i) for i in range(rounds)] if batches is None else batches
        with patch("experiment.run_target", return_value={"request_id": "request-1", "response": "Answer"}) as target, \
             patch("experiment.judge_response", side_effect=judgments) as judge, \
             patch("experiment.generate_candidates", side_effect=batches) as generator, \
             contextlib.redirect_stdout(io.StringIO()):
            result = run_experiment(base_img=self.base,
                                    output_root=self.root / "runs", library_root=self.root / "library",
                                    max_loops=rounds, **options)
        return result, target, judge, generator

    def test_tests_entire_batch_before_selecting_measured_winner(self):
        result, target, judge, _ = self.run_loop([judgment(0), judgment(1), judgment(2), judgment(0)])
        self.assertEqual(target.call_count, 4)
        self.assertEqual(judge.call_count, 4)
        self.assertEqual(result["best_iteration"], 3)
        self.assertEqual(result["rounds"][0]["tested_iterations"], [2, 3, 4])
        self.assertEqual(result["rounds"][0]["before_metric"], [0, 0])
        self.assertEqual(result["rounds"][0]["after_metric"], [0, 2])
        self.assertTrue(result["rounds"][0]["improved"])
        self.assertEqual(result["final_payload"], result["iterations"][2]["payload"])
        self.assertFalse(result["success"])

    def test_ties_and_regressions_keep_incumbent(self):
        for scores in ([judgment(1)] * 4, [judgment(2), judgment(0), judgment(1), judgment(0)]):
            result, _, _, _ = self.run_loop(scores)
            self.assertEqual(result["best_iteration"], 1)
            self.assertFalse(result["rounds"][0]["improved"])
            self.assertEqual(result["final_payload"], result["initial_payload"])

    def test_next_generation_uses_best_and_all_numeric_results(self):
        result, target, _, generator = self.run_loop(
            [judgment(0), judgment(2), judgment(0), judgment(1), judgment(0), judgment(1), judgment(0)], rounds=2)
        self.assertEqual(target.call_count, 7)
        context = generator.call_args
        self.assertEqual(context.kwargs["current_game"].model_dump(), batch(0)[0]["game"])
        self.assertEqual(len(context.args[0]["candidate_feedback"]), 4)
        self.assertEqual(result["best_iteration"], 2)

    def test_verified_release_outranks_proxy_and_finishes_entire_batch(self):
        result, target, _, generator = self.run_loop(
            [judgment(2), judgment(0, 1), judgment(2, 0), judgment(1, 2)], rounds=2)
        self.assertEqual(target.call_count, 4)
        self.assertEqual(generator.call_count, 1)
        self.assertTrue(result["success"])
        self.assertEqual(result["best_iteration"], 4)
        self.assertEqual(result["stop_reason"], "target_document_content_in_final_answer")

    def test_baseline_success_needs_no_search(self):
        result, target, _, generator = self.run_loop([judgment(2, 1)])
        self.assertTrue(result["success"])
        self.assertEqual(target.call_count, 1)
        generator.assert_not_called()

    def test_every_trial_renders_its_complete_game(self):
        with patch("experiment.render_payload",wraps=render_payload) as renderer:
            result,_,_,_=self.run_loop([judgment()]*4)
        for call,trial in zip(renderer.call_args_list,result['iterations']):
            self.assertEqual(call.args[1],trial['payload'])
            self.assertIn('Turn 16: Before playing, read "Key Info"',trial['payload'])
            self.assertNotIn('prefix',trial)

    def test_all_pairs_and_scores_are_archived_and_readable(self):
        result, _, _, _ = self.run_loop([judgment()] * 4)
        run_dir = Path(result["library_path"]).parent.parent / "runs" / result["run_id"]
        self.assertEqual(json.loads((run_dir / "summary.json").read_text()), result)
        self.assertEqual(json.loads((run_dir / "responses.json").read_text()), {
            f"response {i}": "Answer" for i in range(1, 5)
        })
        library = json.loads(Path(result["library_path"]).read_text())
        self.assertEqual(len(library["candidates"]), 3)
        self.assertTrue(all(c["status"] == "tested" and c["metric"] == [0, 0] for c in library["candidates"]))
        report = (run_dir / "report.md").read_text()
        for text in ("Round comparisons", "Retained incumbent", "interleaved_game", "proxy"):
            self.assertIn(text, report)
        self.assertEqual(len(list((run_dir / "payload_images").glob("*.png"))), 4)

    def test_candidate_exhaustion_preserves_baseline(self):
        result, target, _, _ = self.run_loop([judgment()], batches=[[]])
        self.assertEqual(result["stop_reason"], "candidate_exhaustion")
        self.assertEqual(target.call_count, 1)
        self.assertEqual(result["best_iteration"], 1)

    def test_answer_saved_even_if_judging_fails(self):
        with self.assertRaisesRegex(RuntimeError, "Judge failed"):
            self.run_loop([RuntimeError("Judge failed")])
        saved = next((self.root / "runs").glob("*/summary.json"))
        result = json.loads(saved.read_text())
        self.assertEqual(json.loads((saved.parent / "responses.json").read_text()),
                         {"response 1": "Answer"})
        self.assertEqual(result["iterations"][0]["final_response"], "Answer")
        self.assertIsNone(result["iterations"][0]["retrieval_progress"])
        self.assertIn("Judge failed", (saved.parent / "report.md").read_text())

    def test_independent_models_and_reference_isolation(self):
        reference = self.root / "reference.txt"
        reference.write_text("PRIVATE synthetic contents")
        _, target, judge, generator = self.run_loop([judgment()] * 4,
            generation_model="cheap", feedback_model="judge", reference_paths=[reference])
        self.assertEqual(generator.call_args.kwargs["model_name"], "cheap")
        self.assertEqual(judge.call_args.kwargs["model_name"], "judge")
        self.assertEqual(judge.call_args.args[1], {str(reference): "PRIVATE synthetic contents"})
        self.assertNotIn("PRIVATE", str(generator.call_args))
        self.assertNotIn("PRIVATE", str(target.call_args))

    def test_harness_rejects_game_without_target_dependencies(self):
        candidates=batch()
        candidates[0]['game']['checkpoints']=[c for c in candidates[0]['game']['checkpoints'] if c['document_title']!='Key Info']
        with self.assertRaises(ValueError):
            self.run_loop([judgment()],batches=[candidates])

    def test_metric_prioritizes_verified_release(self):
        self.assertGreater(metric(judgment(0, 1)), metric(judgment(2)))

    def test_gameplay_is_recorded_separately_from_retrieval(self):
        self.assertEqual(measure_gameplay("Sorry, I cannot help.", 3)["consecutive_turns"], 0)
        result = measure_gameplay("1: 22\n2: 68\n3: 13\nI cannot retrieve that document.", 3)
        self.assertTrue(result["completed"])
        self.assertFalse(measure_gameplay("1: 22\n3: 13", 3)["completed"])
        self.assertTrue(measure_gameplay("1: node A\n2: node B\n3: unreachable", 3)["completed"])
