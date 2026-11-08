"""Offline support-protocol tests. Real SDK calls are intercepted in memory."""

from collections import Counter
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from contextlib import redirect_stdout

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('rq1_support_runner', HERE / 'run_experiment.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
p = runner.p


def protected_hashes():
    roots = [p.ROOT / name for name in ('experiments', 'research_results', 'data', 'catalogs')]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for root in roots for path in root.rglob('*') if path.is_file()
            and not path.is_relative_to(HERE) and '__pycache__' not in path.parts}


class SupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protected = protected_hashes()
        cls.items = p.load_items()
        cls.pilot = p.pilot_items(cls.items)

    @classmethod
    def tearDownClass(cls):
        if protected_hashes() != cls.protected:
            raise AssertionError('A previous experiment, report, or original input was modified')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output_patch = patch.object(runner, 'OUTPUT_ROOT', self.root)
        self.output_patch.start()
        self.directory = self.root / 'technical_pilot'
        self.manifest = runner.make_manifest(self.items, self.pilot, 'technical_pilot', 32768, 600)
        self._response_number = 0
        self.addCleanup(self.output_patch.stop)
        self.addCleanup(self.temp.cleanup)

    def judgment(self, verdict='supported'):
        return {'verdict': verdict, 'evidence_refs': [], 'rationale': 'The supplied evidence supports this verdict.',
                'identified_gaps': []}

    def client(self, judgment=None, stop_reason='end_turn', thinking=False):
        client = Mock()
        def response(**kwargs):
            self._response_number += 1
            block = SimpleNamespace(type='text', text=json.dumps(judgment or self.judgment()))
            blocks = [SimpleNamespace(type='thinking', thinking='not an assessment'), block] if thinking else [block]
            return SimpleNamespace(id=f'msg_{self._response_number}', model=p.MODEL,
                _request_id=f'req_{self._response_number}', content=blocks, stop_reason=stop_reason,
                usage=SimpleNamespace(model_dump=lambda **kwargs: {'input_tokens': 100, 'output_tokens': 20}),
                model_dump=lambda **kwargs: {'id': f'msg_{self._response_number}', 'model': p.MODEL,
                                             'stop_reason': stop_reason})
        client.messages.create.side_effect = response
        return client

    def test_840_unique_pairs_and_original_category_counts(self):
        self.assertEqual(len(self.items), 840)
        self.assertEqual(len({p.key(i) for i in self.items}), 840)
        self.assertEqual(Counter(i['gpt_assessment']['classification'] for i in self.items), p.EXPECTED_COUNTS)
        self.assertEqual(set(Counter(i['case']['user_story_id'] for i in self.items).values()), {70})
        self.assertEqual(set(Counter(i['pattern']['id'] for i in self.items).values()), {12})

    def test_exact_original_inputs_and_gpt_associations_for_all_pairs(self):
        cases = {c['user_story_id']: c for c in p.load_requirement_cases(p.ROOT / 'data/user_histories_orig.csv')}
        patterns = {r['id']: r for r in p.load_patterns(p.ROOT / 'catalogs/patterns')}
        assessments = {(r['user_story_id'], r['pattern_id']): r for r in p.read_rows(p.GPT_PATH)}
        for item in self.items:
            story, pattern = p.key(item)
            self.assertEqual(item['case'], cases[story])
            self.assertEqual(item['pattern'], {f: patterns[pattern][f] for f in p.PATTERN_FIELDS})
            self.assertEqual(item['gpt_assessment'], assessments[story, pattern])
            prompt = p.build_prompt(item)
            self.assertTrue(prompt.startswith(p.original_prompt(cases[story], patterns[pattern]) + '\n\nORIGINAL GPT ASSESSMENT'))
            self.assertTrue(prompt.endswith(assessments[story, pattern]['rationale']))
        bad = copy.deepcopy(self.items[0])
        bad['gpt_assessment']['pattern_id'] = '070'
        with self.assertRaisesRegex(ValueError, 'association mismatch'):
            p.build_prompt(bad)

    def test_all_category_prompts_have_only_original_case_pattern_and_gpt_assessment(self):
        for item in self.pilot:
            gpt = item['gpt_assessment']
            expected = (p.original_prompt(item['case'], item['pattern']) + '\n\nORIGINAL GPT ASSESSMENT\n\n'
                        + 'Classification:\n' + gpt['classification']
                        + '\n\nRequirement references:\n' + json.dumps(gpt['requirement_refs'], ensure_ascii=False)
                        + '\n\nRationale:\n' + gpt['rationale'])
            self.assertEqual(p.build_prompt(item), expected)

    def test_preparation_reads_no_blind_outcomes_comparisons_adrs_or_expert_material(self):
        opened = []
        original_open = Path.open
        def tracked(path, *args, **kwargs):
            opened.append(path.resolve())
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', tracked):
            p.load_items()
        allowed = {path.resolve() for path in p.source_paths()} | {HERE / 'source_baseline.json'}
        self.assertTrue(set(opened) <= allowed, set(opened) - allowed)
        self.assertNotIn(p.ROOT / 'experiments/llm_judge_rq1/outputs', opened)

    def test_neutrality_structure_and_fixed_instructions(self):
        self.assertEqual(p.INSTRUCTIONS, (HERE / 'instructions.txt').read_text())
        for text in ('Neither agreement nor disagreement is intrinsically preferable',
                     'Multiple possible architectural solutions',
                     'Do not search for deficiencies', 'overlook material deficiencies',
                     'Absence of positive applicability evidence alone',
                     'Do not penalize appropriate acknowledgment of uncertainty'):
            self.assertIn(text, p.INSTRUCTIONS)
        self.assertNotIn('36', p.INSTRUCTIONS)
        self.assertNotIn('773', p.INSTRUCTIONS)
        self.assertEqual(p.request_config()['thinking'], {'type': 'adaptive'})
        self.assertEqual(p.request_config()['output_config']['effort'], 'high')
        self.assertEqual(p.request_config()['model'], 'claude-sonnet-5-5')

    def test_baseline_detects_source_inventory_and_hash_changes(self):
        with patch.object(p, 'file_hash', return_value='modified'):
            with self.assertRaisesRegex(ValueError, 'source inventory/hash mismatch'):
                p.verify_sources()
        paths = p.source_paths()
        with patch.object(p, 'source_paths', return_value=paths[:-1]):
            with self.assertRaises(ValueError):
                p.verify_sources()

    def test_strict_schema_and_all_verdicts_accept_empty_gaps(self):
        p.validate_schema()
        self.assertFalse(p.SCHEMA['additionalProperties'])
        self.assertEqual(set(p.SCHEMA['required']), {'verdict', 'evidence_refs', 'rationale', 'identified_gaps'})
        for verdict in p.VERDICTS:
            for item in self.pilot:
                p.validate_judgment(self.judgment(verdict), item['case'])
        judgment = self.judgment('partially_supported')
        judgment['identified_gaps'] = ['A concrete material ambiguity.']
        p.validate_judgment(judgment, self.pilot[0]['case'])

    def test_invalid_judgments_and_foreign_refs_are_rejected(self):
        for field, bad in (('verdict', 'agree'), ('verdict', []), ('rationale', 3), ('rationale', '  '),
                           ('evidence_refs', ['SYS02-US01']), ('evidence_refs', ['invented']),
                           ('evidence_refs', 'SYS01-US01'), ('identified_gaps', 'gap'),
                           ('identified_gaps', [1])):
            value = self.judgment()
            value[field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                p.validate_judgment(value, self.pilot[0]['case'])
        for value in ([], dict(self.judgment(), unexpected=True), {'verdict': 'supported'}):
            with self.assertRaises(ValueError):
                p.validate_judgment(value, self.pilot[0]['case'])
        valid = self.judgment()
        valid['evidence_refs'] = ['SYS01-US01', 'SYS01-US01-AC01']
        p.validate_judgment(valid, self.pilot[0]['case'])

    def test_pilot_is_deterministic_and_has_one_of_each_category(self):
        self.assertEqual([p.key(i) for i in self.pilot],
                         [('SYS01-US01', '001'), ('SYS01-US01', '022'), ('SYS01-US01', '002')])
        self.assertEqual([i['gpt_assessment']['classification'] for i in self.pilot], list(p.CLASSIFICATIONS))
        self.assertEqual(self.pilot, p.pilot_items(p.load_items()))

    def test_exact_delivery_and_thinking_response_parsing(self):
        client = self.client(thinking=True)
        judgment, metadata = runner.judge(client, self.pilot[0], p.request_config())
        self.assertEqual(judgment, self.judgment())
        self.assertEqual(client.messages.create.call_args.kwargs,
                         {**p.request_config(), 'messages': [{'role': 'user', 'content': p.build_prompt(self.pilot[0])}]})
        self.assertEqual(metadata['content_block_types'], ['thinking', 'text'])
        self.assertNotIn('not an assessment', json.dumps(metadata))

    def test_incomplete_refused_and_invalid_responses_are_never_repaired(self):
        for stop in ('max_tokens', 'refusal', 'pause_turn', 'tool_use', None):
            with self.subTest(stop=stop), self.assertRaises(runner.ResponseValidationError):
                runner.judge(self.client(stop_reason=stop), self.pilot[0], p.request_config())
        for text in ('not JSON', '{"verdict":"supported","verdict":"unsupported"}',
                     '{"verdict":NaN}', '```json\n{}\n```'):
            client = self.client()
            response = client.messages.create()
            response.content[0].text = text
            client.messages.create.side_effect = None
            client.messages.create.return_value = response
            with self.assertRaises(runner.ResponseValidationError):
                runner.judge(client, self.pilot[0], p.request_config())
        for blocks in ([], [SimpleNamespace(type='tool_use')],
                       [SimpleNamespace(type='text', text='{}'), SimpleNamespace(type='text', text='{}')]):
            client = self.client()
            response = client.messages.create()
            response.content = blocks
            client.messages.create.side_effect = None
            client.messages.create.return_value = response
            with self.assertRaises(runner.ResponseValidationError):
                runner.judge(client, self.pilot[0], p.request_config())
        client = self.client()
        response = client.messages.create()
        response.model = 'claude-other'
        client.messages.create.side_effect = None
        client.messages.create.return_value = response
        with self.assertRaises(runner.ResponseValidationError):
            runner.judge(client, self.pilot[0], p.request_config())

    def test_incremental_resume_does_not_repeat_completed_pairs(self):
        client = self.client()
        runner.execute(client, self.directory, self.manifest, self.pilot)
        self.assertEqual(client.messages.create.call_count, 3)
        runner.execute(client, self.directory, self.manifest, self.pilot)
        self.assertEqual(client.messages.create.call_count, 3)
        done, _, pending = runner.resume_state(self.directory, self.manifest, self.pilot)
        self.assertEqual(len(done), 3)
        self.assertFalse(pending)
        for record in done.values():
            self.assertEqual(record['validation_status'], 'validated')
            self.assertIn(record['gpt_classification'], p.CLASSIFICATIONS)
            self.assertEqual(record['response_model'], p.MODEL)
        events = p.read_rows(self.directory / 'events.jsonl')
        self.assertTrue(events[-1]['coverage_validated'])

    def test_interrupted_partial_run_resumes_only_remaining_pairs(self):
        client = self.client()
        responder = client.messages.create.side_effect
        calls = 0
        def fail_second(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise TimeoutError('offline synthetic timeout')
            return responder(**kwargs)
        client.messages.create.side_effect = fail_second
        with self.assertRaises(TimeoutError):
            runner.execute(client, self.directory, self.manifest, self.pilot)
        self.assertEqual(len(p.read_rows(self.directory / 'results.jsonl')), 1)
        done, counts, pending = runner.resume_state(self.directory, self.manifest, self.pilot)
        self.assertEqual(set(done), {p.key(self.pilot[0])})
        self.assertEqual(pending, {p.key(self.pilot[1])})
        client = self.client()
        with self.assertRaisesRegex(ValueError, 'retry-unfinished'):
            runner.execute(client, self.directory, self.manifest, self.pilot)
        client.messages.create.assert_not_called()
        runner.execute(client, self.directory, self.manifest, self.pilot, retry_unfinished=True)
        self.assertEqual(client.messages.create.call_count, 2)
        self.assertEqual(len(p.read_rows(self.directory / 'results.jsonl')), 3)
        attempts = p.read_rows(self.directory / 'attempts.jsonl')
        self.assertEqual([a['attempt_number'] for a in attempts], [1, 1, 2, 1])

    def test_failure_logging_and_attempt_limit(self):
        client = self.client(stop_reason='max_tokens')
        for attempt in range(1, 4):
            with self.assertRaises(runner.ResponseValidationError):
                runner.execute(client, self.directory, self.manifest, self.pilot, retry_unfinished=attempt > 1)
            event = p.read_rows(self.directory / 'events.jsonl')[-1]
            self.assertEqual(event['response_metadata']['stop_reason'], 'max_tokens')
            self.assertEqual(event['response_metadata']['response_model'], p.MODEL)
        with self.assertRaisesRegex(ValueError, 'Attempt limit'):
            runner.execute(client, self.directory, self.manifest, self.pilot, retry_unfinished=True)
        self.assertEqual(client.messages.create.call_count, 3)
        self.assertFalse((self.directory / 'results.jsonl').exists())

    def test_pilot_and_official_paths_and_manifests_are_isolated(self):
        pilot_dir, _, pilot, _ = runner.prepare('technical_pilot', 32768, 600)
        full_dir, _, full, _ = runner.prepare('full', 32768, 600)
        self.assertNotEqual(pilot_dir, full_dir)
        self.assertEqual((len(pilot), len(full)), (3, 840))
        self.assertEqual(pilot_dir.parent.name, p.PROTOCOL_VERSION)
        self.assertEqual(pilot_dir.parent.parent.name, p.MODEL)
        runner.execute(self.client(), self.directory, self.manifest, self.pilot)
        original = {f.name: f.read_bytes() for f in self.directory.iterdir()}
        official = runner.make_manifest(self.items, self.items, 'full', 32768, 600)
        with self.assertRaisesRegex(ValueError, 'Manifest/provenance mismatch'):
            runner.resume_state(self.directory, official, self.items)
        self.assertEqual({f.name: f.read_bytes() for f in self.directory.iterdir()}, original)

    def test_manifest_records_full_prompts_and_all_source_provenance(self):
        for item, record in zip(self.pilot, self.manifest['planned_items']):
            self.assertEqual(record['prompt_text'], p.build_prompt(item))
            self.assertEqual(record['prompt_sha256'], p.digest(record['prompt_text']))
            self.assertEqual(record['input_sha256'], p.digest(item))
        self.assertEqual(self.manifest['source_file_sha256'], p.verify_sources())
        self.assertEqual(self.manifest, runner.make_manifest(self.items, self.pilot, 'technical_pilot', 32768, 600))
        runner.execute(self.client(), self.directory, self.manifest, self.pilot)
        changed = copy.deepcopy(self.manifest)
        changed['configuration']['max_tokens'] += 1
        with self.assertRaises(ValueError):
            runner.resume_state(self.directory, changed, self.pilot)

    def test_v1_1_is_exactly_one_neutral_clarification_without_verdict_changes(self):
        revision = p.strict_json((HERE / 'protocol_revision.json').read_text())
        previous_path = p.ROOT / revision['previous_pilot_manifest']
        previous = p.strict_json(previous_path.read_text())['experiment']
        old_instructions = previous['configuration']['system']
        marker = '\n\nReturn exactly one support verdict:'
        self.assertEqual(p.INSTRUCTIONS, old_instructions.replace(
            marker, '\n\n' + revision['added_clarification'] + marker))
        self.assertEqual(p.INSTRUCTIONS.split(marker)[1], old_instructions.split(marker)[1])
        self.assertEqual(p.SCHEMA, previous['configuration']['output_config']['format']['schema'])
        for clause in ('nonempty requirement_refs only for applicable',
                       'empty references are valid for not_applicable and insufficient_information',
                       'absent architectural details may correctly justify the classification',
                       'limitations in the justification or evidential support',
                       'neither determines nor favors any support verdict'):
            self.assertIn(clause, revision['added_clarification'])

    def test_v1_1_revision_hashes_and_manifest_version(self):
        revision = p.strict_json((HERE / 'protocol_revision.json').read_text())
        self.assertEqual(revision['protocol_version'], p.PROTOCOL_VERSION)
        self.assertEqual(revision['protocol_id'], p.PROTOCOL_ID)
        self.assertEqual(revision['instructions_sha256_raw_utf8'], p.file_hash(HERE / 'instructions.txt'))
        self.assertEqual(revision['instructions_sha256_canonical_json'], p.digest(p.INSTRUCTIONS))
        self.assertEqual(revision['previous_pilot_manifest_sha256'],
                         p.file_hash(p.ROOT / revision['previous_pilot_manifest']))
        self.assertEqual(self.manifest['protocol_id'], p.PROTOCOL_ID)
        self.assertEqual(self.manifest['protocol_version'], 'v1.1')
        self.assertEqual(self.manifest['instructions_sha256'], revision['instructions_sha256_canonical_json'])

    def test_v1_pilot_is_preserved_and_cannot_resume_as_v1_1(self):
        revision = p.strict_json((HERE / 'protocol_revision.json').read_text())
        previous_dir = (p.ROOT / revision['previous_pilot_manifest']).parent
        originals = {f.name: f.read_bytes() for f in previous_dir.iterdir() if f.is_file()}
        self.directory.mkdir()
        for name, content in originals.items():
            (self.directory / name).write_bytes(content)
        client = self.client()
        with self.assertRaisesRegex(ValueError, 'Manifest/provenance mismatch'):
            runner.execute(client, self.directory, self.manifest, self.pilot)
        client.messages.create.assert_not_called()
        self.assertEqual({f.name: f.read_bytes() for f in self.directory.iterdir()}, originals)
        self.assertEqual({f.name: f.read_bytes() for f in previous_dir.iterdir() if f.is_file()}, originals)
        default, _, _, _ = runner.prepare('technical_pilot', 32768, 600)
        self.assertEqual(default.relative_to(self.root).parts, (p.MODEL, 'v1.1', 'technical_pilot'))

    def test_protocol_sources_are_verified_before_request(self):
        client = self.client()
        with patch.object(p, 'file_hash', return_value='changed'):
            with self.assertRaisesRegex(ValueError, 'Protocol/source changed'):
                runner.execute(client, self.directory, self.manifest, self.pilot)
        client.messages.create.assert_not_called()
        self.assertFalse((self.directory / 'manifest.json').exists())

    def test_saved_result_tampering_and_duplicate_prevention(self):
        runner.execute(self.client(), self.directory, self.manifest, self.pilot)
        path = self.directory / 'results.jsonl'
        original = path.read_bytes()
        records = p.read_rows(path)
        for field, value in (('verdict', 'unsupported'), ('response_model', 'other'),
                             ('input_sha256', 'changed'), ('effort', 'low'),
                             ('evidence_refs', ['SYS02-US01']), ('gpt_classification', 'not_applicable')):
            changed = copy.deepcopy(records)
            changed[0][field] = value
            path.write_text(''.join(json.dumps(r) + '\n' for r in changed))
            with self.subTest(field=field), self.assertRaises(ValueError):
                runner.resume_state(self.directory, self.manifest, self.pilot)
        path.write_bytes(original + original)
        with self.assertRaisesRegex(ValueError, 'duplicate validated'):
            runner.resume_state(self.directory, self.manifest, self.pilot)

    def test_truncated_journals_fail_without_discarding_bytes(self):
        runner.execute(self.client(), self.directory, self.manifest, self.pilot)
        for name in ('results.jsonl', 'attempts.jsonl', 'events.jsonl'):
            path = self.directory / name
            original = path.read_bytes()
            path.write_bytes(original[:-1])
            with self.assertRaisesRegex(ValueError, 'Truncated'):
                runner.resume_state(self.directory, self.manifest, self.pilot)
            self.assertEqual(path.read_bytes(), original[:-1])
            path.write_bytes(original)

    def test_output_paths_cannot_target_previous_artifacts_or_symlinks(self):
        for path in (p.ROOT / 'experiments/pattern_selection/outputs',
                     p.ROOT / 'experiments/llm_judge_rq1/outputs', p.ROOT / 'research_results', self.root):
            with self.subTest(path=path), self.assertRaises(ValueError):
                runner.check_directory(path)
        self.directory.mkdir()
        (self.directory / 'manifest.json').symlink_to(p.GPT_PATH)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            runner.check_directory(self.directory)

    def test_output_inventory_or_lock_conflicts_are_rejected(self):
        with runner.locked(self.directory):
            with self.assertRaisesRegex(ValueError, 'Another support runner'):
                with runner.locked(self.directory):
                    pass
        (self.directory / 'unknown.txt').write_text('do not overwrite')
        with self.assertRaisesRegex(ValueError, 'Unknown files'):
            runner.check_directory(self.directory)

    def test_default_preflight_does_not_import_sdk_or_write_outputs(self):
        with patch.dict(sys.modules, {'anthropic': None}), redirect_stdout(io.StringIO()) as captured:
            runner.main([])
        self.assertIn('OFFLINE PREFLIGHT PASSED', captured.getvalue())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_preflight_validates_configuration_and_paths_offline(self):
        for tokens, timeout in ((0, 600), (32768, 0), (32768, float('nan')), (32768, float('inf'))):
            with self.assertRaises(ValueError):
                runner.prepare('full', tokens, timeout)
        with self.assertRaises(ValueError):
            runner.prepare('full', 32768, 600, p.ROOT / 'experiments/llm_judge_rq1/outputs')
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            runner.main(['--pilot', '--full-run'])

    @unittest.skipUnless(importlib.util.find_spec('anthropic'), 'Install pinned SDK for mock-transport checks')
    def test_real_sdk_serialization_and_rate_limit_metadata_without_network(self):
        import anthropic
        import httpx2
        self.assertEqual(anthropic.__version__, p.SDK_VERSION)
        captured = []
        def transport(request):
            captured.append(json.loads(request.content))
            if len(captured) == 2:
                return httpx2.Response(429, headers={'request-id': 'req_limited', 'retry-after': '30'},
                                       json={'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'Synthetic rate limit'}})
            return httpx2.Response(200, headers={'request-id': 'req_mock'}, json={
                'id': 'msg_mock', 'type': 'message', 'role': 'assistant', 'model': p.MODEL,
                'content': [{'type': 'thinking', 'thinking': '', 'signature': 'opaque'},
                            {'type': 'text', 'text': json.dumps(self.judgment())}],
                'stop_reason': 'end_turn', 'stop_sequence': None,
                'usage': {'input_tokens': 100, 'output_tokens': 20}})
        with httpx2.Client(transport=httpx2.MockTransport(transport)) as http:
            with anthropic.Anthropic(api_key='offline-only-key', http_client=http,
                                     base_url='https://offline.invalid', max_retries=0, timeout=600) as client:
                judgment, metadata = runner.judge(client, self.pilot[0], p.request_config())
                self.assertEqual(judgment, self.judgment())
                self.assertEqual(metadata['request_id'], 'req_mock')
                with self.assertRaises(anthropic.RateLimitError):
                    runner.execute(client, self.directory, self.manifest, self.pilot)
        self.assertEqual(captured[0], {**p.request_config(),
                         'messages': [{'role': 'user', 'content': p.build_prompt(self.pilot[0])}]})
        self.assertEqual(len(captured), 2)  # SDK retries are disabled, including on 429.
        failure = p.read_rows(self.directory / 'events.jsonl')[-1]
        self.assertEqual(failure['status_code'], 429)
        self.assertEqual(failure['request_id'], 'req_limited')
        self.assertEqual(failure['retry_after'], '30')


if __name__ == '__main__':
    unittest.main()
