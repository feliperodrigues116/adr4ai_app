"""Offline tests: fake SDK only, never instantiate an Anthropic client."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_experiment as runner


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pairs = runner.dataset()
        cls.case, cls.pattern = cls.pairs[0]
        cls.config = runner.request_config(runner.DEFAULT_MODEL, runner.DEFAULT_MAX_TOKENS)

    def assessment(self, classification="applicable"):
        return {"classification": classification,
                "requirement_refs": [self.case["user_story_id"]], "rationale": "Test evidence."}

    def client(self, assessment=None, stop="end_turn"):
        client = Mock()
        client.messages.create.return_value = SimpleNamespace(
            stop_reason=stop, model=self.config["model"], id="msg_test", _request_id="req_test",
            content=[SimpleNamespace(type="text", text=json.dumps(assessment or self.assessment()))],
            usage=SimpleNamespace(model_dump=lambda **kwargs: {"input_tokens": 10, "output_tokens": 20}))
        return client

    def manifest(self, pairs):
        return runner.provenance(pairs, self.config, "technical_pilot", "offline-fake", 120)

    def test_all_840_unique_original_prompts(self):
        self.assertEqual(len(self.pairs), 840)
        self.assertEqual(len({(c["user_story_id"], p["id"]) for c, p in self.pairs}), 840)
        import assess_pattern
        self.assertIs(runner.build_prompt, assess_pattern.build_prompt)
        self.assertIs(runner.validate_assessment, assess_pattern.validate_assessment)
        self.assertIs(runner.INSTRUCTIONS, assess_pattern.INSTRUCTIONS)
        self.assertIs(runner.ASSESSMENT_SCHEMA, assess_pattern.ASSESSMENT_SCHEMA)
        self.assertEqual(runner.digest(runner.INSTRUCTIONS),
                         "5ecfb8b8d039de2df68a6248ba168e1d490c48747f16e94f92a413d56a8560b5")
        self.assertEqual(runner.digest([runner.build_prompt(c, p) for c, p in self.pairs]),
                         "6b7fcf7310270cd602732147d086ffc8de16853ff037ca18c57198f76386da56")
        for case, pattern in self.pairs:
            restricted = {k: pattern[k] for k in ("id", "name", "motivation", "solution", "consequences")}
            self.assertEqual(runner.build_prompt(case, pattern), runner.build_prompt(case, restricted))

    def test_exact_request_no_prior_results_or_extra_instructions(self):
        client = self.client()
        runner.assess(client, self.case, self.pattern, self.config)
        self.assertEqual(client.messages.create.call_args.kwargs, {
            **self.config, "messages": [{"role": "user", "content": runner.build_prompt(self.case, self.pattern)}]})
        self.assertEqual(self.config["system"], runner.INSTRUCTIONS)
        self.assertEqual(self.config["output_config"]["format"]["schema"], runner.ASSESSMENT_SCHEMA)
        self.assertEqual(self.config["output_config"]["effort"], "high")
        self.assertEqual(self.config["thinking"], {"type": "adaptive"})
        self.assertEqual(self.config["model"], "claude-sonnet-5-5")
        self.assertEqual(self.config["max_tokens"], 32768)

    def test_thinking_blocks_are_not_parsed_as_assessment(self):
        for thinking in (SimpleNamespace(type="thinking", thinking="not JSON"),
                         SimpleNamespace(type="redacted_thinking", data="opaque")):
            client = self.client()
            client.messages.create.return_value.content.insert(0, thinking)
            assessment, metadata = runner.assess(client, self.case, self.pattern, self.config)
            self.assertEqual(assessment, self.assessment())
            self.assertEqual(metadata["content_block_types"], [thinking.type, "text"])
            self.assertNotIn("not JSON", json.dumps(metadata))

    def test_missing_or_multiple_answers_rejected_with_thinking(self):
        thinking = SimpleNamespace(type="thinking", thinking="")
        text = SimpleNamespace(type="text", text=json.dumps(self.assessment()))
        for blocks in ([thinking], [thinking, text, text], [text, SimpleNamespace(type="tool_use")]):
            client = self.client()
            client.messages.create.return_value.content = blocks
            with self.assertRaises(runner.ResponseValidationError):
                runner.assess(client, self.case, self.pattern, self.config)

    def test_all_classifications(self):
        for label in ("applicable", "not_applicable", "insufficient_information"):
            assessment, meta = runner.assess(self.client(self.assessment(label)), self.case, self.pattern, self.config)
            self.assertEqual(assessment["classification"], label)
            self.assertEqual(meta["usage"]["output_tokens"], 20)

    def test_invalid_assessments_rejected(self):
        bad = [dict(self.assessment(), classification="unknown"),
               dict(self.assessment(), requirement_refs=[]),
               dict(self.assessment(), requirement_refs=["SYS99-US01"]),
               dict(self.assessment(), requirement_refs="SYS01-US01"),
               dict(self.assessment(), rationale=42), dict(self.assessment(), extra=True),
               {"classification": "applicable"}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.assess(self.client(value), self.case, self.pattern, self.config)

    def test_incomplete_refused_malformed_or_wrong_model(self):
        for stop in ("max_tokens", "refusal", "tool_use", "pause_turn", "stop_sequence", None):
            with self.subTest(stop=stop), self.assertRaises(ValueError):
                runner.assess(self.client(stop=stop), self.case, self.pattern, self.config)
        for content in ([], [SimpleNamespace(type="text", text="not JSON")],
                        [SimpleNamespace(type="tool_use")]):
            client = self.client()
            client.messages.create.return_value.content = content
            with self.assertRaises(ValueError):
                runner.assess(client, self.case, self.pattern, self.config)
        client = self.client()
        client.messages.create.return_value.model = "other-model"
        with self.assertRaises(ValueError):
            runner.assess(client, self.case, self.pattern, self.config)

    def test_incremental_resume_and_configuration_rejection(self):
        pairs = self.pairs[:2]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = self.manifest(pairs)
            client = self.client()
            runner.execute(client, directory, pairs, manifest)
            self.assertEqual(client.messages.create.call_count, 2)
            runner.execute(client, directory, pairs, manifest)
            self.assertEqual(client.messages.create.call_count, 2)
            self.assertEqual(len(runner.rows(directory / "results.jsonl")), 2)
            row = runner.rows(directory / "results.jsonl")[0]
            self.assertEqual(row["model"], "claude-sonnet-5-5")
            self.assertEqual(row["response_model"], row["model"])
            self.assertEqual(row["effort"], "high")
            self.assertEqual(row["thinking"], {"type": "adaptive"})
            changed = copy.deepcopy(manifest)
            changed["configuration"]["max_tokens"] += 1
            with self.assertRaisesRegex(ValueError, "Manifest mismatch"):
                runner.execute(client, directory, pairs, changed)
            saved = runner.rows(directory / "results.jsonl")
            saved[0]["requirement_refs"] = ["unknown"]
            (directory / "results.jsonl").write_text("".join(json.dumps(x) + "\n" for x in saved))
            with self.assertRaises(ValueError):
                runner.execute(client, directory, pairs, manifest)

    def test_resume_rejects_changed_reasoning_and_actual_model(self):
        pairs = self.pairs[:1]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            manifest = self.manifest(pairs)
            runner.execute(self.client(), directory, pairs, manifest)
            for field, replacement in (("effort", "low"), ("thinking", {"type": "disabled"}),
                                       ("response_model", "claude-other"), ("stop_reason", "max_tokens")):
                path = directory / "results.jsonl"
                original = path.read_text()
                row = json.loads(original)
                row[field] = replacement
                path.write_text(json.dumps(row) + "\n")
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "provenance mismatch"):
                    runner.resume_state(directory, manifest, pairs)
                path.write_text(original)
            for field, value in (("effort", "low"), ("thinking", {"type": "disabled"})):
                changed = copy.deepcopy(manifest)
                if field == "effort":
                    changed["configuration"]["output_config"][field] = value
                else:
                    changed["configuration"][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Manifest mismatch"):
                    runner.resume_state(directory, changed, pairs)

    def test_pilot_cannot_resume_as_full_experiment(self):
        pairs = self.pairs[:1]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            pilot = self.manifest(pairs)
            runner.execute(self.client(), directory, pairs, pilot)
            official = copy.deepcopy(pilot)
            official["mode"] = "full"
            client = self.client()
            with self.assertRaisesRegex(ValueError, "Manifest mismatch"):
                runner.execute(client, directory, pairs, official)
            client.messages.create.assert_not_called()

    def test_sonnet_cannot_modify_or_resume_fable_pilot(self):
        pairs = self.pairs[:1]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fable = self.manifest(pairs)
            fable["configuration"] = runner.request_config("claude-fable-5-1", runner.DEFAULT_MAX_TOKENS)
            client = self.client()
            client.messages.create.return_value.model = "claude-fable-5-1"
            runner.execute(client, directory, pairs, fable)
            original = {p.name: p.read_bytes() for p in directory.iterdir()}
            sonnet_client = self.client()
            with self.assertRaisesRegex(ValueError, "Manifest mismatch"):
                runner.execute(sonnet_client, directory, pairs, self.manifest(pairs))
            sonnet_client.messages.create.assert_not_called()
            self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, original)

    def test_failure_requires_explicit_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            pairs = self.pairs[:1]
            manifest = self.manifest(pairs)
            client = self.client(stop="max_tokens")
            with self.assertRaises(ValueError):
                runner.execute(client, directory, pairs, manifest)
            self.assertFalse((directory / "results.jsonl").exists())
            failure = runner.rows(directory / "events.jsonl")[-1]
            self.assertEqual(failure["response_metadata"]["stop_reason"], "max_tokens")
            self.assertEqual(failure["response_metadata"]["response_model"], runner.DEFAULT_MODEL)
            self.assertEqual(failure["attempt_id"], runner.rows(directory / "attempts.jsonl")[0]["attempt_id"])
            client = self.client()
            with self.assertRaisesRegex(ValueError, "Unfinished attempts"):
                runner.execute(client, directory, pairs, manifest)
            client.messages.create.assert_not_called()
            runner.execute(client, directory, pairs, manifest, retry_unfinished=True)
            client.messages.create.assert_called_once()

    def test_truncated_duplicate_and_locked_journals(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            pairs = self.pairs[:1]
            manifest = self.manifest(pairs)
            runner.execute(self.client(), directory, pairs, manifest)
            path = directory / "results.jsonl"
            original = path.read_bytes()
            path.write_bytes(original + original)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                runner.resume_state(directory, manifest, pairs)
            path.write_bytes(original[:-1])
            with self.assertRaisesRegex(ValueError, "Truncated"):
                runner.resume_state(directory, manifest, pairs)
            with runner.locked(directory):
                with self.assertRaisesRegex(ValueError, "Another runner"):
                    with runner.locked(directory):
                        pass

    def test_default_dry_run_does_not_import_sdk(self):
        with patch.dict(sys.modules, {"anthropic": None}), patch.object(runner, "locked") as lock:
            runner.main([])
            lock.assert_not_called()

    def test_cli_default_model_override_and_separate_directories(self):
        fake_sdk = MagicMock()
        for mode_args, expected_mode in ((["--pilot", "3"], "technical_pilot"),
                                         (["--full-run"], "full")):
            for model_args, expected_model in (([], "claude-sonnet-5-5"),
                                               (["--model", "claude-fable-5-1"], "claude-fable-5-1"),
                                               (["--model", "claude-explicit"], "claude-explicit")):
                with patch.dict(sys.modules, {"anthropic": fake_sdk}), \
                     patch.dict("os.environ", {"ANTHROPIC_API_KEY": "offline-test-key"}), \
                     patch.object(runner.importlib.metadata, "version", return_value=runner.SDK_VERSION), \
                     patch.object(runner, "locked") as lock, patch.object(runner, "execute") as execute:
                    runner.main(mode_args + model_args)
                    directory = lock.call_args.args[0]
                    self.assertEqual(directory.name, expected_mode)
                    self.assertEqual(directory.parent.name, expected_model)
                    self.assertNotEqual(directory, Path(runner.__file__).resolve().parent / "outputs" / "technical_pilot")
                    manifest = execute.call_args.args[3]
                    self.assertEqual(manifest["configuration"]["model"], expected_model)
                    self.assertEqual(manifest["configuration"]["output_config"]["effort"], "high")
                    self.assertEqual(len(execute.call_args.args[2]), 3 if expected_mode == "technical_pilot" else 840)

    def test_unverified_sdk_rejected_before_client_creation(self):
        fake_sdk = Mock()
        with patch.dict(sys.modules, {"anthropic": fake_sdk}), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "offline-test-key"}), \
             patch.object(runner.importlib.metadata, "version", return_value="0.0.0"), \
             self.assertRaises(SystemExit):
            runner.main(["--pilot", "1"])
        fake_sdk.Anthropic.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("anthropic"), "Install pinned SDK for mock-transport check")
    def test_actual_sdk_request_serialization_and_adaptive_response(self):
        import anthropic
        import httpx2

        self.assertEqual(anthropic.__version__, runner.SDK_VERSION)
        requests = []

        def handle(request):
            requests.append(json.loads(request.content))
            return httpx2.Response(200, headers={"request-id": "req_mock"}, json={
                "id": "msg_mock", "type": "message", "role": "assistant", "model": runner.DEFAULT_MODEL,
                "content": [{"type": "thinking", "thinking": "", "signature": "opaque"},
                            {"type": "text", "text": json.dumps(self.assessment())}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": 1000}})

        with httpx2.Client(transport=httpx2.MockTransport(handle)) as http_client:
            with anthropic.Anthropic(api_key="offline-test-key", http_client=http_client,
                                     base_url="https://offline.invalid", max_retries=0,
                                     timeout=runner.DEFAULT_TIMEOUT) as client:
                result, metadata = runner.assess(client, self.case, self.pattern, self.config)
        self.assertEqual(result, self.assessment())
        self.assertEqual(requests, [{**self.config, "messages": [
            {"role": "user", "content": runner.build_prompt(self.case, self.pattern)}]}])
        self.assertEqual(metadata["request_id"], "req_mock")
        self.assertEqual(metadata["content_block_types"], ["thinking", "text"])

    def test_cli_guards(self):
        for args in (["--pilot", "0"], ["--pilot", "11"], ["--pilot", "1", "--full-run"],
                     ["--model", "other"], ["--max-tokens", "0"], ["--timeout", "nan"]):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                runner.main(args)


if __name__ == "__main__":
    unittest.main()
