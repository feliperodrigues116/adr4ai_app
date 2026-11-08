"""Offline mapping, completeness, source-preservation and descriptive-analysis tests."""
import copy
import csv
import io
import json
import unittest
import triangulate as t


class TriangulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = t.snapshot()
        cls.cases, cls.ratings, cls.mapping, cls.spec = t.validate_and_join()
        cls.source = (t.ROOT / cls.spec['authoritative_source']).read_bytes().decode(cls.spec['encoding'])
        cls.table = list(csv.reader(io.StringIO(cls.source, newline='')))
        cls.selected = {t.a.c.record_key(row) for row in cls.cases}
        cls.result = t.outputs(cls.cases, cls.ratings, cls.mapping, cls.spec)
        cls.stats = t.describe(cls.cases, cls.ratings)

    def serialize(self, table):
        out = io.StringIO(newline='')
        csv.writer(out).writerows(table)
        return out.getvalue()

    def test_36_unique_exact_matches_180_ratings(self):
        self.assertEqual(len(self.cases), 36)
        self.assertEqual(len(self.selected), 36)
        self.assertEqual(len(self.ratings), 180)
        self.assertEqual(self.stats['cases_per_system'], {'SYS01': 7, 'SYS02': 12, 'SYS03': 8, 'SYS04': 9})
        self.assertTrue(all(r['support_record_origin'] == 'official_api_validated' for r in self.cases))
        self.assertEqual(self.stats['support_counts'], {'supported': 21, 'partially_supported': 15, 'unsupported': 0})

    def test_all_column_headers_preserved(self):
        self.assertEqual(len(self.mapping), 225)
        self.assertEqual(sum(r['column_kind'] == 'case' for r in self.mapping), 216)
        for m in self.mapping:
            self.assertEqual(m['source_header'], self.table[0][m['source_column'] - 1])
        for r in self.ratings:
            self.assertEqual(r['source_header'], self.table[0][r['source_column'] - 1])
            self.assertEqual(r['raw_rating'], self.table[r['source_csv_record'] - 1][r['source_column'] - 1])

    def test_comments_and_raw_scores_preserved(self):
        for r in self.cases:
            raw = self.table[r['source_csv_record'] - 1]
            self.assertEqual(r['comment_raw'], raw[r['comment_source_column'] - 1])
            for q in t.QUESTIONS:
                self.assertEqual(r[q + '_raw'], raw[r[q + '_source_column'] - 1])
                self.assertEqual(r[q], int(r[q + '_raw']))
        self.assertEqual(self.stats['comments_nonempty_including_whitespace'], 8)
        self.assertEqual(self.stats['comments_with_nonwhitespace_text'], 7)
        self.assertTrue(any(r['comment_raw'] == ' ' for r in self.cases))

    def test_missing_or_invalid_rating_rejected(self):
        r = self.ratings[0]
        for value in ('', '0', '6', 'five', ' 5', '5.0'):
            table = copy.deepcopy(self.table)
            table[r['source_csv_record'] - 1][r['source_column'] - 1] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                t.parse_csv(self.serialize(table), self.selected, self.spec)

    def test_unknown_duplicate_or_missing_case_header_rejected(self):
        r = self.ratings[0]
        index = r['source_column'] - 1
        for header in (self.table[0][index].replace(r['user_story_id'], 'SYS99-US01'), self.table[0][index + 1], 'Unidentified rating'):
            table = copy.deepcopy(self.table)
            table[0][index] = header
            with self.subTest(header=header), self.assertRaises(ValueError):
                t.parse_csv(self.serialize(table), self.selected, self.spec)

    def test_duplicate_missing_and_foreign_system_rows_rejected(self):
        for mode in ('duplicate', 'missing', 'foreign'):
            table = copy.deepcopy(self.table)
            if mode == 'duplicate':
                table[1][4] = table[2][4]
            elif mode == 'missing':
                table.pop()
            else:
                table[1][4] = 'SYS99 - Unknown'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                t.parse_csv(self.serialize(table), self.selected, self.spec)

    def test_cross_system_value_rejected(self):
        table = copy.deepcopy(self.table)
        r = self.ratings[0]
        foreign_record = next(i for i in range(1, len(table)) if i != r['source_csv_record'] - 1)
        table[foreign_record][r['source_column'] - 1] = '5'
        with self.assertRaises(ValueError):
            t.parse_csv(self.serialize(table), self.selected, self.spec)

    def test_wrong_width_or_malformed_header_rejected(self):
        table = copy.deepcopy(self.table)
        table[1].pop()
        with self.assertRaises(ValueError):
            t.parse_csv(self.serialize(table), self.selected, self.spec)
        table = copy.deepcopy(self.table)
        table[0][5] = '[bad case header]'
        with self.assertRaises(ValueError):
            t.parse_csv(self.serialize(table), self.selected, self.spec)

    def test_no_float_averaging_or_imputation_in_join(self):
        for r in self.cases:
            self.assertTrue(all(type(r[q]) is int and 1 <= r[q] <= 5 for q in t.QUESTIONS))
        self.assertEqual({r['question'] for r in self.ratings}, set(t.QUESTIONS))

    def test_csv_case_roundtrip_preserves_human_and_claude_text(self):
        exported = list(csv.DictReader(io.StringIO(self.result['case_triangulation.csv'])))
        self.assertEqual(len(exported), 36)
        for row, case in zip(exported, self.cases):
            self.assertEqual(row['comment_raw'], case['comment_raw'])
            self.assertEqual(row['claude_rationale'], case['claude_rationale'])
            self.assertEqual(json.loads(row['claude_identified_gaps']), case['claude_identified_gaps'])
            self.assertEqual(json.loads(row['claude_evidence_refs']), case['claude_evidence_refs'])
            self.assertEqual(row['pattern_id'], case['pattern_id'])

    def test_group_marginals_and_percentages(self):
        overall = t.matrix(self.cases)
        self.assertEqual(sum(r['count'] for r in overall), 36)
        for field in ('system_id', 'user_story_id'):
            grouped = t.matrix(self.cases, field)
            self.assertEqual(sum(r['count'] for r in grouped), 36)
            for row in overall:
                self.assertEqual(sum(r['count'] for r in grouped if r['claude_support_verdict'] == row['claude_support_verdict'] and r['Q5'] == row['Q5']), row['count'])
        self.assertTrue(all(r['within_verdict_percent'] is None for r in overall if r['claude_support_verdict'] == 'unsupported'))

    def test_original_source_hash_and_deterministic_no_mutation(self):
        self.assertEqual(t.p.file_hash(t.ROOT / self.spec['authoritative_source']), self.spec['authoritative_source_sha256'])
        self.assertEqual(self.result, t.outputs(self.cases, self.ratings, self.mapping, self.spec))
        self.assertEqual(self.before, t.snapshot())

    def test_persisted_output_provenance(self):
        path = t.HERE / 'provenance.json'
        self.assertTrue(path.exists(), 'Run triangulate.py before persisted-output validation')
        prov = json.loads(path.read_text())
        for name, sha in prov['input_source_sha256'].items():
            self.assertEqual(t.p.file_hash(t.ROOT / name), sha)
        for name, sha in prov['output_sha256'].items():
            self.assertEqual(t.p.file_hash(t.HERE / name), sha)


if __name__ == '__main__':
    unittest.main()
