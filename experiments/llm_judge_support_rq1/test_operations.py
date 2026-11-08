"""Operational-policy regression tests; synthetic clients and cloned journals only."""

import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import continue_experiment as op
import technical_corrections as corrections

p = op.p


class OperationalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = p.load_items()
        cls.pilot = p.pilot_items(cls.items)
        cls.official = p.HERE / 'outputs' / p.MODEL / 'v1.1/full'
        cls.protected = {path: p.file_hash(path) for path in cls.official.iterdir() if path.is_file()}

    @classmethod
    def tearDownClass(cls):
        if cls.protected != {path: p.file_hash(path) for path in cls.official.iterdir() if path.is_file()}:
            raise AssertionError('Official existing run was modified by offline tests')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output_root = self.root / 'outputs'
        self.operations = self.root / 'operations'
        self.directory = self.output_root / 'test'
        self.patch1 = patch.object(op.legacy, 'OUTPUT_ROOT', self.output_root)
        self.patch2 = patch.object(op, 'OPERATION_ROOT', self.operations)
        self.patch1.start()
        self.patch2.start()
        self.addCleanup(self.patch1.stop)
        self.addCleanup(self.patch2.stop)
        self.addCleanup(self.temp.cleanup)
        self.manifest = op.legacy.make_manifest(self.items, self.pilot, 'technical_pilot', 32768, 600.0)
        self.response_count = 0

    def client(self, fail_calls=(), fatal_calls=()):
        client = Mock()
        def create(**kwargs):
            self.response_count += 1
            n = self.response_count
            if n in fatal_calls:
                raise TimeoutError('synthetic transport interruption')
            judgment = {'verdict': 'supported', 'evidence_refs': ['foreign'] if n in fail_calls else [],
                        'rationale': 'Synthetic fixture explanation.', 'identified_gaps': []}
            return SimpleNamespace(id=f'msg_{n}', model=p.MODEL, _request_id=f'req_{n}',
                content=[SimpleNamespace(type='text', text=json.dumps(judgment))], stop_reason='end_turn',
                usage=SimpleNamespace(model_dump=lambda **kwargs: {'input_tokens': 10, 'output_tokens': 5}),
                model_dump=lambda **kwargs: {'id': f'msg_{n}', 'model': p.MODEL, 'stop_reason': 'end_turn'})
        client.messages.create.side_effect = create
        return client

    def clone_official(self):
        self.directory.mkdir(parents=True)
        for path in self.official.iterdir():
            if path.is_file():
                (self.directory / path.name).write_bytes(path.read_bytes())
        return p.strict_json((self.directory / 'manifest.json').read_text())['experiment']

    def execute(self, client, manifest=None, items=None):
        with redirect_stdout(io.StringIO()):
            return op.execute_continuation(client, self.directory, manifest or self.manifest,
                                           items or self.pilot, enabled=True)

    def test_continuation_is_explicit_opt_in(self):
        client = self.client()
        with self.assertRaisesRegex(ValueError, 'explicit'):
            op.execute_continuation(client, self.directory, self.manifest, self.pilot)
        client.messages.create.assert_not_called()
        self.assertFalse(self.directory.exists())

    def test_invalid_response_logged_and_next_pair_evaluated(self):
        client = self.client(fail_calls={1})
        summary, opdir = self.execute(client)
        self.assertEqual(client.messages.create.call_count, 3)
        self.assertEqual((summary['validated_judgments'], summary['invalid_pairs']), (2, 1))
        self.assertFalse(summary['complete'])
        pending = summary['pending_pairs'][0]
        self.assertEqual(pending['attempts'], 1)
        self.assertEqual(pending['gpt_classification'], 'applicable')
        failure = pending['validation_failures'][0]
        self.assertEqual(failure['validation_error'], 'Unknown or foreign evidence reference')
        event = p.read_rows(self.directory / 'events.jsonl')[failure['event_line'] - 1]
        self.assertEqual(event['validation_error'], failure['validation_error'])
        self.assertEqual(p.strict_json(event['response_metadata']['response_text'])['evidence_refs'], ['foreign'])
        self.assertEqual(event['response_metadata']['raw_text_blocks'], [event['response_metadata']['response_text']])
        self.assertEqual(p.read_rows(self.directory / 'events.jsonl')[-1]['status'], 'finished_with_pending')
        self.assertTrue((opdir / 'validation_summary.csv').exists())
        done, _, pending_keys = op.legacy.resume_state(self.directory, self.manifest, self.pilot)
        self.assertEqual(len(done), 2)
        self.assertEqual(pending_keys, {p.key(self.pilot[0])})

    def test_resume_defers_invalid_and_does_not_duplicate_completed(self):
        self.execute(self.client(fail_calls={1}))
        before = {name: (self.directory / name).read_bytes() for name in ('results.jsonl', 'attempts.jsonl', 'manifest.json')}
        client = self.client()
        summary, _ = self.execute(client)
        client.messages.create.assert_not_called()
        for name, content in before.items():
            self.assertEqual((self.directory / name).read_bytes(), content)
        self.assertEqual(summary['validated_judgments'], 2)
        self.assertEqual(summary['pending_pairs'][0]['attempts'], 1)

    def test_existing_attempt_at_limit_is_deferred_without_override(self):
        invalid = self.client(fail_calls={1, 2, 3})
        for number in range(3):
            with self.assertRaises(op.legacy.ResponseValidationError), redirect_stdout(io.StringIO()):
                op.legacy.execute(invalid, self.directory, self.manifest, self.pilot,
                                  retry_unfinished=number > 0)
        client = self.client()
        summary, _ = self.execute(client)
        self.assertEqual(client.messages.create.call_count, 2)
        self.assertEqual(summary['pending_pairs'][0]['attempts'], 3)
        self.assertTrue(summary['pending_pairs'][0]['attempt_limit_reached'])

    def test_real_260_run_clone_skips_p051_and_evaluates_579_unattempted(self):
        manifest = self.clone_official()
        before = {name: (self.directory / name).read_bytes() for name in
                  ('results.jsonl', 'attempts.jsonl', 'events.jsonl', 'manifest.json')}
        client = self.client()
        summary, opdir = self.execute(client, manifest, self.items)
        self.assertEqual(client.messages.create.call_count, 579)
        self.assertEqual(summary['validated_judgments'], 839)
        self.assertEqual(summary['invalid_or_pending_pairs'], 1)
        self.assertEqual(summary['total_attempts'], 841)
        self.assertEqual(summary['pending_pairs'][0]['pattern_id'], '051')
        self.assertEqual(summary['pending_pairs'][0]['attempts'], 2)
        self.assertEqual(len(summary['pending_pairs'][0]['validation_failures']), 2)
        self.assertEqual((self.directory / 'manifest.json').read_bytes(), before['manifest.json'])
        for name in ('results.jsonl', 'attempts.jsonl', 'events.jsonl'):
            self.assertTrue((self.directory / name).read_bytes().startswith(before[name]))
        prompts = [call.kwargs['messages'][0]['content'] for call in client.messages.create.call_args_list]
        self.assertTrue(prompts[0].startswith(p.original_prompt(self.items[261]['case'], self.items[261]['pattern'])))
        self.assertNotIn(p.build_prompt(self.items[260]), prompts)
        amendment = p.strict_json((opdir / 'amendment.json').read_text())
        self.assertEqual(amendment['deferred_attempted_pairs'], [['SYS02-US01', '051']])
        self.assertEqual(amendment['scientific_experiment_sha256'], p.digest(manifest))
        # Even a structurally valid rewrite of an old answer must fail prefix integrity.
        forged = p.read_rows(self.directory / 'results.jsonl')
        forged[0]['rationale'] = 'Altered historical rationale in a temporary test clone.'
        payload = p.strict_json(forged[0]['response_text'])
        payload['rationale'] = forged[0]['rationale']
        forged[0]['response_text'] = json.dumps(payload)
        (self.directory / 'results.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in forged))
        with self.assertRaisesRegex(ValueError, 'Historical journal prefix was altered'):
            op.inspect(self.directory, manifest, self.items)

    def test_old_failure_messages_replayed_without_rewriting_events(self):
        manifest = self.clone_official()
        old_events = (self.directory / 'events.jsonl').read_bytes()
        summary = op.validation_summary(self.directory, manifest, self.items)
        self.assertEqual(summary['validated_judgments'], 260)
        self.assertEqual(summary['never_attempted_pairs'], 579)
        failures = summary['pending_pairs'][0]['validation_failures']
        self.assertEqual(len(failures), 2)
        for failure in failures:
            self.assertEqual(failure['validation_error'], 'Unknown or foreign evidence reference')
            self.assertEqual(failure['error_source'], 'replayed_from_preserved_raw_response')
        self.assertEqual((self.directory / 'events.jsonl').read_bytes(), old_events)

    def test_manifest_and_source_mismatch_not_bypassed(self):
        self.execute(self.client())
        changed = copy.deepcopy(self.manifest)
        changed['configuration']['max_tokens'] += 1
        client = self.client()
        with self.assertRaisesRegex(ValueError, 'Manifest/provenance mismatch'):
            self.execute(client, changed)
        client.messages.create.assert_not_called()
        with patch.object(p, 'file_hash', return_value='changed'):
            with self.assertRaisesRegex(ValueError, 'Protocol/source changed'):
                self.execute(client)
        client.messages.create.assert_not_called()

    def test_operational_amendment_and_historical_prefix_integrity(self):
        _, opdir = self.execute(self.client(fail_calls={1}))
        path = opdir / 'amendment.json'
        original = path.read_bytes()
        changed = json.loads(original)
        changed['scientific_protocol_unchanged'] = False
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'amendment hash mismatch'):
            op.inspect(self.directory, self.manifest, self.pilot)
        path.write_bytes(original)
        with patch.object(op, 'operation_sources', return_value={'bad': 'hash'}):
            with self.assertRaisesRegex(ValueError, 'compatibility/provenance mismatch'):
                op.inspect(self.directory, self.manifest, self.pilot)

    def test_transport_failure_stops_and_retains_partial_summary(self):
        client = self.client(fatal_calls={2})
        with self.assertRaises(TimeoutError):
            self.execute(client)
        self.assertEqual(client.messages.create.call_count, 2)
        opdir = next(self.operations.iterdir())
        summary = p.strict_json((opdir / 'validation_summary.json').read_text())
        self.assertEqual(summary['validated_judgments'], 1)
        self.assertEqual(summary['unfinished_pairs'], 1)
        self.assertEqual(summary['never_attempted_pairs'], 1)
        client = self.client()
        result, _ = self.execute(client)
        self.assertEqual(client.messages.create.call_count, 1)
        self.assertEqual(result['validated_judgments'], 2)

    def test_saved_judgments_remain_strictly_validated(self):
        self.execute(self.client())
        path = self.directory / 'results.jsonl'
        original = path.read_bytes()
        path.write_bytes(original + original)
        client = self.client()
        with self.assertRaisesRegex(ValueError, 'duplicate validated'):
            self.execute(client)
        client.messages.create.assert_not_called()

    def test_preflight_without_sdk_is_read_only(self):
        manifest = self.clone_official()
        before = {path.name: path.read_bytes() for path in self.directory.iterdir()}
        with patch.dict(sys.modules, {'anthropic': None}), redirect_stdout(io.StringIO()):
            op.main(['--preflight', '--output-dir', str(self.directory), '--timeout', '600'])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.directory.iterdir()})
        self.assertFalse(self.operations.exists())

    def test_summary_reproducibility_and_exclusive_output(self):
        manifest = self.clone_official()
        one = op.validation_summary(self.directory, manifest, self.items)
        two = op.validation_summary(self.directory, manifest, self.items)
        self.assertEqual(op.json_text(one), op.json_text(two))
        path = self.operations / 'summary'
        path.mkdir(parents=True)
        op.save_summary(path, one)
        with self.assertRaises(FileExistsError):
            op.save_summary(path, two)

    def correction_fixture(self):
        self.execute(self.client(fail_calls={1}))
        summary = op.validation_summary(self.directory, self.manifest, self.pilot)
        failure = summary['pending_pairs'][0]['validation_failures'][0]
        plan = {
            'scientific_manifest_sha256': p.file_hash(self.directory / 'manifest.json'),
            'corrections': [{'attempt_id': failure['attempt_id'], 'raw_response_sha256': failure['raw_response_sha256'],
                'field': 'evidence_refs', 'replacement': ['SYS01-US01'], 'approved': True,
                'reason': 'Synthetic reviewer-approved identifier-only transcription correction.',
                'reviewed_by': 'offline-fixture-reviewer', 'approved_at': '2026-11-08T00:00:00+00:00'}],
        }
        path = self.root / 'plan.json'
        path.write_text(json.dumps(plan))
        return plan, path

    def test_explicit_reference_correction_is_separate_logged_and_reproducible(self):
        plan, path = self.correction_fixture()
        before = {f.name: f.read_bytes() for f in self.directory.iterdir()}
        first, logs = corrections.apply_plan(self.directory, self.manifest, self.pilot, path, self.operations / 'corrected1')
        second, _ = corrections.apply_plan(self.directory, self.manifest, self.pilot, path, self.operations / 'corrected2')
        self.assertEqual(first, second)
        self.assertEqual(first[0]['original_judgment']['evidence_refs'], ['foreign'])
        self.assertEqual(first[0]['corrected_analytical_judgment']['evidence_refs'], ['SYS01-US01'])
        for field in ('verdict', 'rationale', 'identified_gaps'):
            self.assertEqual(first[0]['original_judgment'][field], first[0]['corrected_analytical_judgment'][field])
        self.assertTrue(first[0]['not_an_original_validated_judgment'])
        self.assertEqual(before, {f.name: f.read_bytes() for f in self.directory.iterdir()})
        self.assertEqual(op.validation_summary(self.directory, self.manifest, self.pilot)['validated_judgments'], 2)
        for file in (self.operations / 'corrected1').iterdir():
            self.assertEqual(file.read_bytes(), (self.operations / 'corrected2' / file.name).read_bytes())

    def test_corrections_reject_semantic_edits_unapproved_or_wrong_sources(self):
        plan, path = self.correction_fixture()
        variants = []
        for field, value in (('approved', False), ('field', 'verdict'), ('replacement', ['foreign']),
                             ('raw_response_sha256', 'changed'), ('reason', '')):
            changed = copy.deepcopy(plan)
            changed['corrections'][0][field] = value
            variants.append(changed)
        changed = copy.deepcopy(plan)
        changed['corrections'][0]['verdict'] = 'unsupported'
        variants.append(changed)
        for number, changed in enumerate(variants):
            path.write_text(json.dumps(changed))
            with self.subTest(number=number), self.assertRaises(ValueError):
                corrections.apply_plan(self.directory, self.manifest, self.pilot, path,
                                       self.operations / f'bad{number}')
            self.assertFalse((self.operations / f'bad{number}').exists())


if __name__ == '__main__':
    unittest.main()
