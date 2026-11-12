"""Offline synthetic integrity/coverage checks; no device, Frida or raw journal."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from summarize_callbacks import COUNTERS, HOST_SCHEMA, SCRIPT_SCHEMA, counts, summarize


def fixture(pid=101):
    rows = []
    sequence = 0
    stage = 'unclassified'
    total = counts()
    by_source = {}
    by_stage = {}
    collector = 'synthetic-collector-' + str(pid)
    run = 'synthetic-run-' + str(pid)

    def host(event, **fields):
        rows.append({'schema': HOST_SCHEMA, 'event': event, 'collector_id': collector,
                     'host_seq': len(rows) + 1, **fields})

    def script(event, **fields):
        nonlocal sequence
        sequence += 1
        rows.append({'schema': SCRIPT_SCHEMA, 'event': event, 'pid': pid, 'run_id': run,
                     'seq': sequence, 'stage': stage, 'collector_id': collector,
                     'host_seq': len(rows) + 1, **copy.deepcopy(fields)})

    def checkpoint(event, ready=True):
        script(event, ready=ready, calls_started=total['calls'], calls_completed=total['calls'],
               in_flight=0, totals=total, by_source=by_source, by_stage=by_stage)

    def callback(source):
        delta = counts()
        for key in ('calls', 'match', 'coordinate_match', 'address15_match', 'precision_match'):
            delta[key] = 1
        by_source.setdefault(source, counts())
        entry = by_stage.setdefault(stage, {'totals': counts(), 'by_source': {}})
        entry['by_source'].setdefault(source, counts())
        for key in COUNTERS:
            for target in (total, by_source[source], entry['totals'], entry['by_source'][source]):
                target[key] += delta[key]
        script('callback', source=source, delta=delta, process_totals=total, original_called_once=True)

    host('host_start')
    host('host_gap_start', reason='not_yet_ready', stage=stage, lost_callback_count=None)
    checkpoint('loaded', ready=False)
    checkpoint('ready')
    host('host_gap_end', stage=stage, duration_seconds=1.5, lost_callback_count=None)
    host('host_ready', pid=pid, run_id=run)
    stage = 'first_entry'
    checkpoint('stage')
    callback('SYSTEM')
    checkpoint('heartbeat')
    checkpoint('summary')
    stage = 'refresh'
    checkpoint('stage')
    callback('GAODE')
    checkpoint('heartbeat')
    checkpoint('summary')
    host('host_final_summary', pid=pid, run_id=run, persisted=True, script_seq=sequence, in_flight=0)
    host('host_stop')
    return rows


def renumber_host(rows):
    for index, row in enumerate(rows, 1):
        row['host_seq'] = index
    return rows


class SummaryTests(unittest.TestCase):
    def report(self, rows, suffix=''):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.jsonl'
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows) + suffix, encoding='utf-8')
            return summarize([path])

    def test_snapshots_are_not_double_counted_and_startup_stays_unknown(self):
        report = self.report(fixture())
        self.assertEqual(report['totals']['calls'], 2)
        self.assertEqual(report['totals']['match'], 2)
        self.assertEqual(report['status'], 'validated_observed_window')
        self.assertTrue(report['validation']['all_defined_stage_windows_closed'])
        self.assertFalse(report['coverage']['process_lifetime_complete'])
        self.assertIsNone(report['coverage']['startup_callback_count'])
        self.assertIsNone(report['host_gaps'][0]['lost_callback_count'])

    def test_failed_final_rpc_does_not_invalidate_earlier_closed_stage(self):
        rows = fixture()
        last_summary = [row for row in rows if row['event'] == 'summary'][-1]
        rows.remove(last_summary)
        marker = next(row for row in rows if row['event'] == 'host_final_summary')
        marker.update(persisted=False, script_seq=None)
        report = self.report(renumber_host(rows))
        self.assertEqual(report['status'], 'incomplete')
        self.assertFalse(report['issues'])
        self.assertTrue(report['coverage_issues'])
        windows = {row['stage']: row for row in report['stage_windows']}
        self.assertTrue(windows['first_entry']['complete_defined_window'])
        self.assertFalse(windows['refresh']['complete_defined_window'])

    def test_in_flight_final_is_not_closed(self):
        rows = fixture()
        last = [row for row in rows if row['event'] == 'summary'][-1]
        last.update(calls_started=3, in_flight=1)
        report = self.report(rows)
        self.assertEqual(report['status'], 'incomplete')
        self.assertFalse(report['runs'][0]['final_summary_in_flight_zero'])
        self.assertFalse(report['issues'])

    def test_in_flight_callback_keeps_entry_stage_after_stage_switch(self):
        rows = fixture()
        first = next(row for row in rows if row['event'] == 'callback')
        rows.remove(first)
        boundary = next(index for index, row in enumerate(rows)
                        if row['event'] == 'stage' and row['stage'] == 'refresh')
        for row in rows[:boundary + 1]:
            if row['event'] in ('heartbeat', 'summary') or row is rows[boundary]:
                row.update(totals=counts(), by_source={}, by_stage={},
                           calls_started=1, calls_completed=0, in_flight=1)
        rows.insert(boundary + 1, first)
        sequence = 0
        for row in rows:
            if row['schema'] == SCRIPT_SCHEMA:
                sequence += 1
                row['seq'] = sequence
        next(row for row in rows if row['event'] == 'host_final_summary')['script_seq'] = sequence
        report = self.report(renumber_host(rows))
        self.assertEqual(report['totals']['calls'], 2)
        self.assertEqual(report['totals']['match'], 2)
        self.assertFalse(report['issues'])
        self.assertTrue(report['validation']['sequence_and_checkpoint_checks_pass'])
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual({row['stage']: row['calls'] for row in report['groups']},
                         {'first_entry': 1, 'refresh': 1})
        self.assertTrue(all(window['cross_stage_in_flight'] for window in report['stage_windows']))
        self.assertTrue(all(not window['complete_defined_window'] for window in report['stage_windows']))
        first_window = next(window for window in report['stage_windows'] if window['stage'] == 'first_entry')
        self.assertFalse(first_window['closed'])
        self.assertEqual(first_window['late_callback_count'], 1)
        self.assertIn('late_callback_after_stage_boundary', {row['code'] for row in report['coverage_issues']})

    def test_duplicate_callback_is_rejected_and_not_counted_twice(self):
        rows = fixture()
        index = next(index for index, row in enumerate(rows) if row['event'] == 'callback')
        rows.insert(index + 1, copy.deepcopy(rows[index]))
        report = self.report(renumber_host(rows))
        self.assertEqual(report['totals']['calls'], 2)
        self.assertEqual(report['status'], 'invalid')
        self.assertEqual(report['runs'][0]['sequence']['duplicate_count'], 1)

    def test_missing_callback_detects_sequence_hole_and_checkpoint_disagreement(self):
        rows = fixture()
        first = next(row for row in rows if row['event'] == 'callback')
        rows.remove(first)
        report = self.report(renumber_host(rows))
        self.assertEqual(report['totals']['calls'], 1)
        self.assertTrue(report['runs'][0]['sequence']['missing_ranges'])
        self.assertIn('checkpoint_totals_mismatch', {row['code'] for row in report['issues']})

    def test_out_of_order_is_rejected_even_if_every_record_arrives(self):
        rows = fixture()
        index = next(index for index, row in enumerate(rows) if row['event'] == 'callback')
        rows[index], rows[index + 1] = rows[index + 1], rows[index]
        report = self.report(renumber_host(rows))
        self.assertEqual(report['totals']['calls'], 2)
        self.assertEqual(report['runs'][0]['sequence']['out_of_order_count'], 1)
        self.assertFalse(report['runs'][0]['sequence']['valid'])

    def test_corrupt_count_equation_fails(self):
        rows = fixture()
        first = next(row for row in rows if row['event'] == 'callback')
        first['delta']['match'] = 2
        report = self.report(rows)
        self.assertIn('callback_count_equation_failed', {row['code'] for row in report['issues']})

    def test_growth_mid_line_is_incomplete_not_a_silent_missing_record(self):
        report = self.report(fixture(), suffix='{"schema":')
        self.assertEqual(report['totals']['calls'], 2)
        self.assertEqual(report['warnings'][0]['code'], 'trailing_partial_line')
        self.assertEqual(report['status'], 'incomplete')

    def test_host_gap_inside_stage_prevents_complete_coverage(self):
        rows = fixture()
        index = next(index for index, row in enumerate(rows) if row['event'] == 'callback')
        collector = rows[0]['collector_id']
        rows[index:index] = [
            {'schema': HOST_SCHEMA, 'event': 'host_gap_start', 'collector_id': collector, 'reason': 'disconnected', 'stage': 'first_entry'},
            {'schema': HOST_SCHEMA, 'event': 'host_gap_end', 'collector_id': collector, 'stage': 'first_entry', 'duration_seconds': 2},
        ]
        report = self.report(renumber_host(rows))
        self.assertEqual(report['status'], 'incomplete')
        first = next(window for window in report['stage_windows'] if window['stage'] == 'first_entry')
        self.assertFalse(first['complete_defined_window'])
        self.assertIsNone(report['host_gaps'][1]['lost_callback_count'])

    def test_two_process_runs_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for pid in (101, 202):
                path = Path(directory) / f'synthetic-{pid}.jsonl'
                path.write_text(''.join(json.dumps(row) + '\n' for row in fixture(pid)), encoding='utf-8')
                paths.append(path)
            report = summarize(paths)
        self.assertEqual(report['totals']['calls'], 4)
        self.assertEqual(len(report['runs']), 2)
        self.assertEqual(len(report['groups']), 4)
        self.assertEqual(report['status'], 'validated_observed_window')


if __name__ == '__main__':
    unittest.main()
