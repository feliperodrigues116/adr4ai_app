"""Offline checks of original evidence, the explicit correction, and analytical coverage."""

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import consolidate as c


class ConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.items, cls.done, cls.corrected, cls.review = c.prepare_records()

    def test_both_responses_reviewed_without_conflating_rationales(self):
        a, b = self.review['failed_responses']
        self.assertEqual(a['judgment']['verdict'], 'supported')
        self.assertEqual(b['judgment']['verdict'], 'supported')
        self.assertEqual(a['judgment']['identified_gaps'], [])
        self.assertEqual(b['judgment']['identified_gaps'], [])
        self.assertNotEqual(a['judgment']['rationale'], b['judgment']['rationale'])
        self.assertNotEqual(a['response_metadata']['response_id'], b['response_metadata']['response_id'])
        self.assertIn('The user story also asks the system to generate an initial document', a['judgment']['rationale'])
        self.assertIn('The story is about generating an initial document from a registered record', b['judgment']['rationale'])

    def test_single_identifier_correction_preserves_every_other_scientific_field(self):
        old, new = self.corrected['original_judgment'], self.corrected['corrected_analytical_judgment']
        self.assertEqual(old['evidence_refs'][:2], new['evidence_refs'][:2])
        self.assertEqual(old['evidence_refs'][2], 'SYS02-US01-US01')
        self.assertEqual(new['evidence_refs'][2], 'SYS02-US01')
        self.assertEqual(sum(x != y for x, y in zip(old['evidence_refs'], new['evidence_refs'])), 1)
        for field in ('verdict', 'rationale', 'identified_gaps'):
            self.assertEqual(old[field], new[field])
        self.assertEqual(self.corrected['source_attempt_id'], self.review['failed_responses'][0]['source_failure']['attempt_id'])

    def test_unique_story_identifier_and_original_requirement_evidence(self):
        item = next(item for item in self.items if c.p.key(item) == c.PAIR)
        self.assertEqual(item['case']['user_story_id'], 'SYS02-US01')
        self.assertIn('gere um documento inicial de acordo com o registro cadastrado', item['case']['user_story'])
        valid = {item['case']['user_story_id']} | {a['acceptance_criterion_id'] for a in item['case']['acceptance_criteria']}
        self.assertNotIn('SYS02-US01-US01', valid)
        self.assertIn('SYS02-US01', valid)
        with self.assertRaisesRegex(ValueError, 'Unknown or foreign'):
            c.p.validate_judgment(self.corrected['original_judgment'], item['case'])
        c.p.validate_judgment(self.corrected['corrected_analytical_judgment'], item['case'])

    def test_exact_839_plus_one_complete_cartesian_coverage(self):
        counts = c.validate_analytical(self.rows, self.items, self.done, self.corrected)
        self.assertEqual(counts, {'official_api_validated': 839, 'technically_corrected_analytical': 1})
        self.assertEqual(len({c.record_key(row) for row in self.rows}), 840)
        self.assertEqual({c.record_key(row) for row in self.rows}, {c.p.key(item) for item in self.items})
        self.assertEqual(len({row['user_story_id'] for row in self.rows}), 12)
        self.assertEqual(len({row['pattern_id'] for row in self.rows}), 70)

    def test_duplicate_missing_or_mislabeled_record_is_rejected(self):
        for kind in ('duplicate', 'missing', 'mislabel', 'hash'):
            rows = copy.deepcopy(self.rows)
            if kind == 'duplicate':
                rows[-1] = copy.deepcopy(rows[0])
            elif kind == 'missing':
                rows.pop()
            elif kind == 'hash':
                rows[0]['source_record_sha256'] = 'bad'
            else:
                corrected = next(row for row in rows if c.record_key(row) == c.PAIR)
                corrected['official_api_validated'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                c.validate_analytical(rows, self.items, self.done, self.corrected)

    def test_changed_original_or_corrected_judgment_is_rejected(self):
        for key in (c.PAIR, c.record_key(self.rows[0])):
            rows = copy.deepcopy(self.rows)
            row = next(row for row in rows if c.record_key(row) == key)
            row['judgment']['rationale'] = 'Changed rationale'
            with self.assertRaises(ValueError):
                c.validate_analytical(rows, self.items, self.done, self.corrected)

    def test_schema_and_reference_errors_are_rejected(self):
        for field, value in (('evidence_refs', ['SYS01-US01']), ('verdict', 'agree'),
                             ('identified_gaps', 'none'), ('rationale', None)):
            rows = copy.deepcopy(self.rows)
            next(row for row in rows if c.record_key(row) == c.PAIR)['judgment'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                c.validate_analytical(rows, self.items, self.done, self.corrected)

    def test_csv_roundtrip_preserves_scientific_text_arrays_and_origin(self):
        parsed = list(csv.DictReader(io.StringIO(c.serialize_csv(self.rows))))
        self.assertEqual(len(parsed), 840)
        for row, original in zip(parsed, self.rows):
            self.assertEqual(row['rationale'], original['judgment']['rationale'])
            self.assertEqual(json.loads(row['evidence_refs']), original['judgment']['evidence_refs'])
            self.assertEqual(json.loads(row['identified_gaps']), original['judgment']['identified_gaps'])
            self.assertEqual(row['record_origin'], original['record_origin'])
            self.assertEqual(row['pattern_id'], original['pattern_id'])

    def test_reproduction_is_byte_identical_and_source_preserving(self):
        before = c.input_hashes()
        names = ('analytical_judgments.jsonl', 'analytical_judgments.csv', 'validation_report.json', 'analysis_provenance.json')
        previous = {name: (c.HERE / name).read_bytes() for name in names}
        subprocess.run([sys.executable, '-B', str(c.HERE / 'consolidate.py')], check=True, capture_output=True)
        self.assertEqual(previous, {name: (c.HERE / name).read_bytes() for name in names})
        self.assertEqual(before, c.input_hashes())
        audit = c.p.strict_json((c.HERE / 'analysis_provenance.json').read_text())
        for name, sha in audit['output_sha256'].items():
            self.assertEqual(hashlib.sha256((c.HERE / name).read_bytes()).hexdigest(), sha)


if __name__ == '__main__':
    unittest.main()
