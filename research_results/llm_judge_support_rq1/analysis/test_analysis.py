"""Offline regression checks of data integrity, denominators, coding and exports."""
from collections import Counter
import copy
import csv
import io
import json
from pathlib import Path
import unittest
import analyze as a


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = a.source_snapshot()
        cls.rows, cls.origins, _ = a.validate_sources()
        cls.book = json.loads((a.HERE / 'codebook.json').read_text())
        cls.annotations = json.loads((a.HERE / 'applicable_partial_coding.json').read_text())
        cls.outputs = a.build_outputs(cls.rows, cls.annotations, cls.book, cls.origins)
        cls.stats, cls.insuff, cls.matches, cls.signals = a.summarize(cls.rows, cls.annotations, cls.book)

    def test_exact_coverage_and_origins(self):
        self.assertEqual(len(self.rows), 840)
        self.assertEqual(len({a.c.record_key(r) for r in self.rows}), 840)
        self.assertEqual(self.origins, {'official_api_validated': 839, 'technically_corrected_analytical': 1})
        self.assertEqual(self.stats['gpt_classifications'], {'applicable': 36, 'not_applicable': 31, 'insufficient_information': 773})

    def test_matrix_regression(self):
        table = {(r['gpt_classification'], r['verdict']): r['count'] for r in a.breakdown(self.rows) if r['gpt_classification'] != 'all'}
        expected = {'applicable': [21, 15, 0], 'not_applicable': [30, 1, 0], 'insufficient_information': [345, 427, 1]}
        for label, counts in expected.items():
            self.assertEqual([table[label, v] for v in a.VERDICTS], counts)
        self.assertEqual(self.stats['support_verdicts'], {'supported': 396, 'partially_supported': 443, 'unsupported': 1})

    def test_percentages_and_empty_denominator(self):
        self.assertIsNone(a.percentage(0, 0))
        self.assertAlmostEqual(a.percentage(15, 36), 41.666667)
        for r in a.breakdown(self.rows, 'user_story_id'):
            if r['denominator']:
                self.assertAlmostEqual(r['within_category_percent'], 100 * r['count']/r['denominator'], places=5)
            else:
                self.assertIsNone(r['within_category_percent'])

    def test_group_marginals_reconcile(self):
        for field in ('system', 'user_story_id'):
            grouped = a.breakdown(self.rows, field)
            for label in a.CLASSES:
                for verdict in a.VERDICTS:
                    self.assertEqual(sum(r['count'] for r in grouped if r['gpt_classification'] == label and r['verdict'] == verdict),
                                     sum(r['gpt_classification'] == label and r['judgment']['verdict'] == verdict for r in self.rows))

    def test_applicable_system_results(self):
        expected = {'System_01': [4, 3], 'System_02': [5, 7], 'System_03': [6, 2], 'System_04': [6, 3]}
        for system, counts in expected.items():
            self.assertEqual([sum(r['system'] == system and r['gpt_classification'] == 'applicable' and r['judgment']['verdict'] == v for r in self.rows) for v in a.VERDICTS[:2]], counts)

    def test_manual_coding_quotes_and_completeness(self):
        self.assertTrue(a.validate_coding(self.rows, self.annotations, self.book))
        self.assertEqual(self.stats['qualitative_code_counts']['A7'], 7)
        for annotation in self.annotations:
            self.assertTrue(set(annotation['codes']) - {'A7'})

    def test_reject_missing_duplicate_unknown_and_changed_quote_annotations(self):
        bad_variants = [self.annotations[:-1], self.annotations[:-1] + [self.annotations[0]]]
        for field, value in [('codes', ['UNKNOWN']), ('evidence', [{'field': 'identified_gaps[0]', 'quote': 'invented'}]), ('recorded_verdict', 'unsupported')]:
            bad = copy.deepcopy(self.annotations)
            bad[0][field] = value
            bad_variants.append(bad)
        for bad in bad_variants:
            with self.subTest(bad=bad[0].get('codes')):
                with self.assertRaises((ValueError, RuntimeError)):
                    a.validate_coding(self.rows, bad, self.book)

    def test_raw_signal_counts_and_exact_evidence(self):
        self.assertEqual(self.stats['text_signal_unique_case_counts'], {'I1': 418, 'I2': 372, 'I3': 204, 'I4': 26, 'I5': 391, 'I6': 67})
        index = {a.c.record_key(r): r for r in self.insuff}
        self.assertEqual(len(index), 428)
        for m in self.matches:
            judgment = index[a.c.record_key(m)]['judgment']
            text = judgment['rationale'] if m['field'] == 'rationale' else judgment['identified_gaps'][int(m['field'].split('[')[1][:-1])]
            self.assertEqual(m['verbatim_text'], text)
        self.assertEqual(self.stats['boundary_gap_and_no_incompatibility_signal_intersection'], len(self.signals['I2'] & self.signals['I3']))

    def test_signal_field_scope_and_case_deduplication(self):
        row = copy.deepcopy(self.insuff[0])
        row['judgment']['rationale'] = 'No incompatibility exists.'
        row['judgment']['identified_gaps'] = ['No incompatibility exists.', 'No incompatibility exists.']
        matches = a.text_matches(row, self.book)
        self.assertEqual([m['field'] for m in matches if m['signal'] == 'I3'], ['rationale'])

    def test_csv_roundtrip_preserves_original_texts(self):
        source = {a.c.record_key(r): r for r in self.rows}
        for name, n in [('applicable_decisions.csv', 36), ('not_applicable_decisions.csv', 31), ('insufficient_information_review.csv', 428)]:
            exported = list(csv.DictReader(io.StringIO(self.outputs[name])))
            self.assertEqual(len(exported), n)
            for row in exported:
                original = source[a.c.record_key(row)]
                for field in ('verdict', 'rationale'):
                    self.assertEqual(row[field], original['judgment'][field])
                for field in ('evidence_refs', 'identified_gaps'):
                    self.assertEqual(json.loads(row[field]), original['judgment'][field])
                self.assertEqual(row['record_origin'], original['record_origin'])

    def test_correction_sensitivity(self):
        corrected = [r for r in self.rows if r['record_origin'] == 'technically_corrected_analytical']
        self.assertEqual(len(corrected), 1)
        self.assertEqual(a.c.record_key(corrected[0]), ('SYS02-US01', '051'))
        self.assertEqual(corrected[0]['gpt_classification'], 'not_applicable')
        self.assertEqual(corrected[0]['judgment']['verdict'], 'supported')
        original = [r for r in self.rows if r['record_origin'] == 'official_api_validated']
        self.assertEqual(Counter(r['judgment']['verdict'] for r in original), {'supported': 395, 'partially_supported': 443, 'unsupported': 1})

    def test_reject_duplicate_and_invalid_reference(self):
        _, items, done, corrected, _ = a.c.prepare_records()
        duplicate = self.rows[:-1] + [self.rows[0]]
        with self.assertRaises((ValueError, RuntimeError)):
            a.c.validate_analytical(duplicate, items, done, corrected)
        bad = copy.deepcopy(self.rows)
        bad[0]['judgment']['evidence_refs'] = ['SYS99-US99']
        with self.assertRaises((ValueError, RuntimeError)):
            a.c.validate_analytical(bad, items, done, corrected)

    def test_reject_changed_verdict_rationale_and_gaps(self):
        _, items, done, corrected, _ = a.c.prepare_records()
        for field, value in [('verdict', 'unsupported'), ('rationale', 'Changed rationale'), ('identified_gaps', ['Invented gap'])]:
            bad = copy.deepcopy(self.rows)
            bad[0]['judgment'][field] = value
            with self.assertRaises((ValueError, RuntimeError)):
                a.c.validate_analytical(bad, items, done, corrected)

    def test_deterministic_build_and_no_source_mutation(self):
        again = a.build_outputs(self.rows, self.annotations, self.book, self.origins)
        self.assertEqual(self.outputs, again)
        self.assertEqual(a.source_snapshot(), self.before)

    def test_generated_output_hashes(self):
        path = a.HERE / 'analysis_provenance.json'
        if not path.exists():
            self.skipTest('Run analyze.py before verifying persisted reports')
        provenance = json.loads(path.read_text())
        for name, sha in provenance['output_sha256'].items():
            self.assertEqual(a.p.file_hash(a.HERE / name), sha)
        for name, sha in provenance['source_sha256'].items():
            self.assertEqual(a.p.file_hash(a.ROOT / name), sha)


if __name__ == '__main__':
    unittest.main()
