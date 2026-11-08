"""Offline analytical, validation, integrity, and reproduction checks; no APIs."""

from collections import Counter
import copy
import csv
from fractions import Fraction
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as analysis


class MetricTests(unittest.TestCase):
    def rows(self, cells):
        return [{'gpt_classification': g, 'claude_classification': c}
                for (g, c), count in cells.items() for _ in range(count)]

    def test_known_three_category_matrix(self):
        a, n, u = analysis.CATEGORIES
        rows = self.rows({(a, a): 2, (a, n): 1, (n, a): 1, (n, n): 2, (u, u): 4})
        m = analysis.agreement_metrics(rows)
        self.assertEqual(m['agreements'], 8)
        self.assertEqual(m['overall_agreement'], 0.8)
        self.assertAlmostEqual(m['expected_agreement_from_marginals'], 0.34)
        self.assertAlmostEqual(m['cohens_kappa'], float(Fraction(23, 33)))
        self.assertEqual(m['positive_jaccard'], 0.5)
        self.assertAlmostEqual(m['positive_dice_agreement'], 2/3)
        self.assertAlmostEqual(m['gpt_selected_overlap_fraction'], 2/3)

    def test_zero_denominator_is_undefined_not_perfect(self):
        u = 'insufficient_information'
        m = analysis.agreement_metrics(self.rows({(u, u): 3}))
        self.assertEqual(m['overall_agreement'], 1)
        for field in ('cohens_kappa', 'positive_jaccard', 'positive_dice_agreement',
                      'gpt_selected_overlap_fraction', 'claude_selected_overlap_fraction'):
            self.assertIsNone(m[field])
        with self.assertRaises(ValueError):
            analysis.agreement_metrics([])

    def test_asymmetric_positive_sets_and_negative_kappa(self):
        rows = self.rows({('applicable', 'not_applicable'): 2, ('not_applicable', 'applicable'): 1})
        m = analysis.agreement_metrics(rows)
        self.assertEqual(m['gpt_applicable'], 2)
        self.assertEqual(m['claude_applicable'], 1)
        self.assertEqual(m['positive_jaccard'], 0)
        self.assertLess(m['cohens_kappa'], 0)

    def test_json_rejects_duplicates_nonfinite_and_truncation(self):
        for text in ('{"a": 1, "a": 2}', '{"a": NaN}', '{"a": Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                analysis.strict_json(text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.jsonl'
            for text in ('', '{}', '{}\n\n', '[]\n'):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    analysis.read_jsonl(path)


class FrozenDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pairs = analysis.runner.dataset()
        cls.claude_path = analysis.locate_official()
        cls.gpt_rows = analysis.read_jsonl(analysis.GPT_PATH)
        cls.claude_rows = analysis.read_jsonl(cls.claude_path)
        cls.gpt = analysis.validate_records(cls.gpt_rows, cls.pairs, 'GPT')
        cls.claude = analysis.validate_records(cls.claude_rows, cls.pairs, 'Claude')

    def test_complete_universe(self):
        self.assertEqual(len(self.gpt), 840)
        self.assertEqual(set(self.gpt), set(self.claude))
        self.assertEqual(set(Counter(k[0] for k in self.gpt).values()), {70})
        self.assertEqual(set(Counter(k[1] for k in self.gpt).values()), {12})
        self.assertEqual(sum(r['classification'] == 'applicable' for r in self.gpt.values()), 36)

    def test_frozen_matrix_and_selection_sets(self):
        rows = analysis.comparison_rows(self.pairs, self.gpt, self.claude)
        m = analysis.agreement_metrics(rows)
        expected_matrix = [[21, 4, 11], [0, 26, 5], [9, 498, 266]]
        observed = Counter((r['gpt_classification'], r['claude_classification']) for r in rows)
        self.assertEqual([[observed[g, c] for c in analysis.CATEGORIES] for g in analysis.CATEGORIES], expected_matrix)
        gp = {k for k, r in self.gpt.items() if r['classification'] == 'applicable'}
        cp = {k for k, r in self.claude.items() if r['classification'] == 'applicable'}
        self.assertEqual((len(gp & cp), len(gp | cp), len(gp - cp), len(cp - gp)), (21, 45, 15, 9))
        self.assertEqual(m['agreements'], 313)
        self.assertEqual(m['both_applicable'], len(gp & cp))
        expected = Fraction(36 * 30 + 31 * 528 + 773 * 282, 840 ** 2)
        kappa = (Fraction(313, 840) - expected) / (1 - expected)
        self.assertEqual(m['cohens_kappa'], float(kappa))

    def test_missing_duplicate_and_foreign_identifiers_rejected(self):
        missing = copy.deepcopy(self.gpt_rows[:-1])
        duplicate = copy.deepcopy(self.gpt_rows)
        duplicate[-1] = copy.deepcopy(duplicate[0])
        foreign = copy.deepcopy(self.gpt_rows)
        foreign[0]['pattern_id'] = '999'
        numeric = copy.deepcopy(self.gpt_rows)
        numeric[0]['pattern_id'] = 1
        for rows in (missing, duplicate, foreign, numeric):
            with self.assertRaises(ValueError):
                analysis.validate_records(rows, self.pairs, 'GPT')

    def test_invalid_schema_or_cross_story_evidence_rejected(self):
        for field, value in (('classification', 'unknown'), ('rationale', 7),
                             ('requirement_refs', ['SYS02-US01']),
                             ('requirement_refs', []), ('requirement_refs', 'SYS01-US01')):
            rows = copy.deepcopy(self.gpt_rows)
            rows[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                analysis.validate_records(rows, self.pairs, 'GPT')
        rows = copy.deepcopy(self.gpt_rows)
        del rows[0]['rationale']
        with self.assertRaises(ValueError):
            analysis.validate_records(rows, self.pairs, 'GPT')

    def test_gpt_configuration_mismatch_rejected(self):
        rows = copy.deepcopy(self.gpt_rows)
        rows[0]['model'] = 'unexpected'
        with self.assertRaises(ValueError):
            analysis.validate_records(rows, self.pairs, 'GPT')

    def test_official_provenance_and_execution_audit(self):
        manifest, audit = analysis.validate_claude(self.claude_path, self.claude, self.pairs)
        self.assertEqual(manifest['mode'], 'full')
        self.assertEqual(manifest['configuration']['output_config']['effort'], 'high')
        self.assertEqual(audit['attempts'], 840)
        self.assertEqual(audit['executions'], 1)
        self.assertEqual(audit['failure_events'], 0)
        self.assertEqual(audit['attempts_without_validated_result'], 0)

    def test_claude_row_tampering_rejected(self):
        for field, value in (('input_sha256', 'bad'), ('prompt_sha256', 'bad'),
                             ('experiment_sha256', 'bad'), ('response_model', 'unexpected'),
                             ('effort', 'low'), ('thinking', {'type': 'disabled'}),
                             ('stop_reason', 'max_tokens'), ('attempt_id', 'missing')):
            rows = copy.deepcopy(self.claude)
            rows[next(iter(rows))][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                analysis.validate_claude(self.claude_path, rows, self.pairs)

    def test_manifest_tampering_and_missing_completion_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in ('manifest.json', 'attempts.jsonl', 'events.jsonl'):
                (directory / name).write_bytes((self.claude_path.parent / name).read_bytes())
            manifest_path = directory / 'manifest.json'
            original = manifest_path.read_bytes()
            for field in ('inputs_sha256', 'prompts_sha256', 'schema_sha256', 'instructions_sha256'):
                wrapper = json.loads(original)
                wrapper['experiment'][field] = 'bad'
                manifest_path.write_text(json.dumps(wrapper))
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'provenance mismatch'):
                    analysis.validate_claude(directory / 'results.jsonl', self.claude, self.pairs)
            manifest_path.write_bytes(original)
            events = analysis.read_jsonl(directory / 'events.jsonl')
            (directory / 'events.jsonl').write_text(json.dumps(events[0]) + '\n')
            with self.assertRaisesRegex(ValueError, 'no final completion'):
                analysis.validate_claude(directory / 'results.jsonl', self.claude, self.pairs)

    def test_pilot_and_ambiguous_discovery_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            def candidate(name, mode):
                p = directory / name
                p.mkdir()
                (p / 'results.jsonl').write_text('{}\n')
                (p / 'manifest.json').write_text(json.dumps({'experiment': {
                    'mode': mode, 'configuration': {'model': analysis.MODEL}}}))
                return p / 'results.jsonl'
            candidate('pilot', 'technical_pilot')
            with self.assertRaises(ValueError):
                analysis.locate_official(directory)
            official = candidate('full', 'full')
            self.assertEqual(analysis.locate_official(directory), official)
            candidate('second_full', 'full')
            with self.assertRaises(ValueError):
                analysis.locate_official(directory)

    def test_pair_text_roundtrip_and_group_reconciliation(self):
        rows = analysis.comparison_rows(self.pairs, self.gpt, self.claude)
        text = analysis.csv_text(rows)
        parsed = list(csv.DictReader(io.StringIO(text)))
        for row in parsed:
            key = row['user_story_id'], row['pattern_id']
            for prefix, source in (('gpt', self.gpt[key]), ('claude', self.claude[key])):
                self.assertEqual(row[prefix + '_rationale'], source['rationale'])
                self.assertEqual(json.loads(row[prefix + '_requirement_refs']), source['requirement_refs'])
        overall = analysis.agreement_metrics(rows)
        for field in ('user_story_id', 'system', 'pattern_id'):
            groups = analysis.group_metrics(rows, field)
            for count in ('pairs', 'agreements', 'disagreements', 'both_applicable',
                          'gpt_applicable', 'claude_applicable'):
                self.assertEqual(sum(r[count] for r in groups), overall[count])

    def test_multiline_unicode_and_reference_order_preserved(self):
        row = {'pattern_id': '001', 'rationale': '  ação, "quoted"\nsecond line  ',
               'refs': json.dumps(['AC02', 'US01', 'AC01'])}
        restored = list(csv.DictReader(io.StringIO(analysis.csv_text([row]))))[0]
        self.assertEqual(restored, row)

    def test_reproducible_outputs_without_input_mutation(self):
        originals = [analysis.GPT_PATH, self.claude_path, *self.claude_path.parent.glob('*.json*')]
        hashes = {p: analysis.file_hash(p) for p in originals}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            m1, files1 = analysis.run_analysis(output_dir=directory)
            first = {p.name: p.read_bytes() for p in directory.iterdir()}
            m2, files2 = analysis.run_analysis(output_dir=directory)
            self.assertEqual(m1, m2)
            self.assertEqual(files1, files2)
            self.assertEqual(first, {p.name: p.read_bytes() for p in directory.iterdir()})
            provenance = json.loads((directory / 'analysis_provenance.json').read_text())
            for name, expected in provenance['output_sha256'].items():
                self.assertEqual(analysis.file_hash(directory / name), expected)
        self.assertEqual(hashes, {p: analysis.file_hash(p) for p in originals})


if __name__ == '__main__':
    unittest.main()
