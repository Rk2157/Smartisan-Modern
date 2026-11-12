#!/usr/bin/env python3
"""Summarize durable callback JSONL without counting cumulative snapshots twice.

Only callback.delta records contribute counts. Script/host sequences and all
cumulative checkpoints are independently checked. Startup/reconnect gaps have
an unknown callback count; a report never claims complete process-lifetime
coverage. This tool has no device connection or device identifier requirement.
JSON/CSV reports retain process/session IDs and gap timestamps for integrity;
they are not de-identified public reports. Publish only a separate aggregate
report with those fields removed, never the raw journal or detailed reports.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys


COUNTERS = (
    'calls', 'match', 'mismatch', 'uncomparable', 'coordinate_match',
    'coordinate_mismatch', 'address15_match', 'address15_mismatch',
    'precision_match', 'precision_mismatch', 'observer_error', 'null_count',
    'null_dto', 'null_snapshot', 'original_error',
)
SCRIPT_SCHEMA = 'smartisan.callback-statistics.v1'
HOST_SCHEMA = 'smartisan.callback-host.v1'
SOURCES = {'SYSTEM', 'GAODE', 'GOOGLE', 'WIFI', 'SYSTEM_GPS', 'SYSTEM_NETWORK',
           'SYSTEM_FUSED', 'UNKNOWN', 'OTHER'}


def counts():
    return dict.fromkeys(COUNTERS, 0)


def add(target, delta):
    for key in COUNTERS:
        target[key] += delta[key]


def valid_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def normalized_counts(value):
    if not isinstance(value, dict) or any(not valid_integer(value.get(key)) for key in COUNTERS):
        return None
    return {key: value[key] for key in COUNTERS}


def missing_ranges(sequences):
    previous = 0
    ranges = []
    for sequence in sorted(set(sequences)):
        if sequence > previous + 1:
            ranges.append([previous + 1, sequence - 1])
        previous = sequence
    return ranges


def sequence_check(values):
    seen = set()
    maximum = 0
    duplicates = 0
    out_of_order = 0
    for value in values:
        if value in seen:
            duplicates += 1
        elif value < maximum:
            out_of_order += 1
        seen.add(value)
        maximum = max(maximum, value)
    gaps = missing_ranges(seen)
    return {'valid': not gaps and not duplicates and not out_of_order,
            'first': min(seen) if seen else None, 'last': max(seen) if seen else None,
            'missing_ranges': gaps, 'duplicate_count': duplicates,
            'out_of_order_count': out_of_order}


def summarize(paths):
    issues = []
    coverage_issues = []
    warnings = []
    records = []
    event_counts = Counter()

    def issue(code, row=None, **extra):
        item = {'code': code, **extra}
        if row is not None:
            item.update(input_index=row['_input'], line=row['_line'])
            if row.get('schema') == SCRIPT_SCHEMA:
                item.update(pid=row.get('pid'), run_id=row.get('run_id'), seq=row.get('seq'))
        issues.append(item)

    for index, path in enumerate(paths):
        data = path.read_bytes()  # A bounded snapshot also works while a collector appends.
        lines = data.splitlines(keepends=True)
        for number, raw in enumerate(lines, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
                if not isinstance(row, dict):
                    raise ValueError('ObjectRequired')
            except (ValueError, UnicodeDecodeError):
                if number == len(lines) and not raw.endswith(b'\n'):
                    warnings.append({'code': 'trailing_partial_line', 'input_index': index, 'line': number})
                else:
                    issues.append({'code': 'invalid_json_record', 'input_index': index, 'line': number})
                continue
            row.update(_input=index, _line=number, _order=len(records))
            records.append(row)
            event_counts[str(row.get('event', 'missing'))] += 1

    runs = {}
    host_sequences = defaultdict(list)
    collectors = defaultdict(list)
    for row in records:
        collector = row.get('collector_id')
        if isinstance(collector, str):
            collectors[collector].append(row)
            if valid_integer(row.get('host_seq')) and row['host_seq'] > 0:
                host_sequences[collector].append(row['host_seq'])
            else:
                issue('invalid_host_sequence', row)
        if row.get('schema') != SCRIPT_SCHEMA:
            continue
        pid, run_id, sequence = row.get('pid'), row.get('run_id'), row.get('seq')
        if not valid_integer(pid) or pid == 0 or not isinstance(run_id, str) or not run_id or not valid_integer(sequence) or sequence == 0:
            issue('invalid_script_identity_or_sequence', row)
            continue
        key = (pid, run_id)
        run = runs.setdefault(key, {'pid': pid, 'run_id': run_id, 'arrival': [], 'records': {}, 'errors': 0})
        run['arrival'].append(sequence)
        if sequence not in run['records']:
            run['records'][sequence] = row
        elif {k: v for k, v in row.items() if not k.startswith('_') and k not in ('host_seq', 'host_utc', 'collector_id')} != {
                k: v for k, v in run['records'][sequence].items() if not k.startswith('_') and k not in ('host_seq', 'host_utc', 'collector_id')}:
            issue('conflicting_duplicate_script_record', row)

    host_sequence_results = []
    for collector, sequences in host_sequences.items():
        result = sequence_check(sequences)
        host_sequence_results.append({'collector_id': collector, **result})
        if not result['valid']:
            issues.append({'code': 'host_sequence_invalid', 'collector_id': collector})

    # Gap windows remain unknown even if they contain zero observed callbacks.
    gaps = []
    collector_stopped = {}
    for collector, rows in collectors.items():
        opened = None
        collector_stopped[collector] = any(row.get('event') == 'host_stop' for row in rows)
        for row in rows:
            event = row.get('event')
            if event == 'host_gap_start':
                if opened is not None:
                    issue('nested_host_gap_start', row)
                opened = {'collector_id': collector, 'reason': row.get('reason'),
                          'stage_at_start': row.get('stage'), 'start_host_seq': row.get('host_seq'),
                          'start_utc': row.get('host_utc'), 'end_host_seq': None, 'end_utc': None,
                          'open': True, 'callbacks_unobserved': True, 'lost_callback_count': None}
            elif event == 'host_gap_end':
                if opened is None:
                    issue('host_gap_end_without_start', row)
                    continue
                opened.update(end_host_seq=row.get('host_seq'), end_utc=row.get('host_utc'),
                              duration_seconds=row.get('duration_seconds'), open=False)
                gaps.append(opened)
                opened = None
            elif event == 'host_gap_open_at_stop' and opened is not None:
                opened['duration_seconds_at_stop'] = row.get('duration_seconds')
        if opened is not None:
            gaps.append(opened)

    grouped = defaultdict(counts)
    overall = counts()
    run_reports = []
    windows = []
    checkpoint_checks = 0
    final_markers = defaultdict(list)
    for row in records:
        if row.get('event') == 'host_final_summary':
            final_markers[(row.get('pid'), row.get('run_id'))].append(row)

    for identity, run in sorted(runs.items()):
        sequence = sequence_check(run['arrival'])
        if not sequence['valid']:
            issues.append({'code': 'script_sequence_invalid', 'pid': identity[0], 'run_id': identity[1]})
        total = counts()
        by_source = defaultdict(counts)
        by_stage = {}
        callbacks = []
        summaries = []
        current_window = None
        previous_windows = []
        ordered = [run['records'][key] for key in sorted(run['records'])]

        def expected_stages():
            return {stage: {'totals': entry['totals'], 'by_source': dict(entry['by_source'])}
                    for stage, entry in by_stage.items()}

        for row in ordered:
            event = row.get('event')
            if event == 'stage' and row.get('ready') is True:
                crossing = valid_integer(row.get('in_flight')) and row['in_flight'] > 0
                if crossing:
                    coverage_issues.append({'code': 'cross_stage_in_flight', 'pid': identity[0],
                                            'run_id': identity[1], 'seq': row['seq'],
                                            'from_stage': current_window['stage'] if current_window else row.get('previous_stage'),
                                            'to_stage': row.get('stage'), 'in_flight': row['in_flight']})
                if current_window is not None:
                    current_window.update(end_seq=row['seq'], end_host_seq=row.get('host_seq'),
                                          closed_by='next_stage_with_in_flight' if crossing else 'next_stage',
                                          closed=not crossing, in_flight_at_boundary=row.get('in_flight', 0),
                                          calls_started_at_boundary=row.get('calls_started'), late_callback_count=0)
                    current_window['cross_stage_in_flight'] = current_window['cross_stage_in_flight'] or crossing
                    windows.append(current_window)
                    previous_windows.append(current_window)
                    current_window = None
                if row.get('stage') != 'unclassified':
                    current_window = {'pid': identity[0], 'run_id': identity[1], 'stage': row.get('stage'),
                                      'collector_id': row.get('collector_id'), 'start_seq': row['seq'],
                                      'start_host_seq': row.get('host_seq'), 'end_seq': None,
                                      'end_host_seq': None, 'closed_by': None, 'closed': False,
                                      'cross_stage_in_flight': crossing}
            if event == 'callback':
                delta = normalized_counts(row.get('delta'))
                if delta is None:
                    issue('invalid_callback_delta', row)
                    continue
                if delta['calls'] != 1 or delta['calls'] != delta['match'] + delta['mismatch'] + delta['uncomparable']:
                    issue('callback_count_equation_failed', row)
                if row.get('original_called_once') is not True:
                    issue('original_call_contract_failed', row)
                source = row.get('source')
                stage = row.get('stage')
                if source not in SOURCES or not isinstance(stage, str) or not stage:
                    issue('invalid_callback_source_or_stage', row)
                    continue
                if current_window is None or stage != current_window['stage']:
                    if stage != 'unclassified':
                        # The JS captures stage at entry. A call already in flight
                        # may legitimately finish after the stage RPC checkpoint.
                        candidates = [window for window in previous_windows if window['stage'] == stage
                                      and valid_integer(window['in_flight_at_boundary'])
                                      and window['in_flight_at_boundary'] > window['late_callback_count']
                                      and (not valid_integer(row.get('call_number')) or
                                           valid_integer(window['calls_started_at_boundary']) and
                                           row['call_number'] <= window['calls_started_at_boundary'])]
                        if candidates:
                            window = candidates[-1]
                            window['late_callback_count'] += 1
                            coverage_issues.append({'code': 'late_callback_after_stage_boundary',
                                                    'pid': identity[0], 'run_id': identity[1],
                                                    'seq': row['seq'], 'stage': stage,
                                                    'boundary_seq': window['end_seq']})
                        else:
                            issue('callback_outside_explicit_stage_window', row)
                add(total, delta)
                add(overall, delta)
                add(by_source[source], delta)
                stage_entry = by_stage.setdefault(stage, {'totals': counts(), 'by_source': defaultdict(counts)})
                add(stage_entry['totals'], delta)
                add(stage_entry['by_source'][source], delta)
                add(grouped[(stage, source, identity[0], identity[1])], delta)
                callbacks.append(row)
                if normalized_counts(row.get('process_totals')) != total:
                    issue('callback_process_totals_mismatch', row)
            if 'totals' in row:
                checkpoint_checks += 1
                if normalized_counts(row['totals']) != total:
                    issue('checkpoint_totals_mismatch', row)
                if row.get('by_source') != dict(by_source):
                    issue('checkpoint_sources_mismatch', row)
                if row.get('by_stage') != expected_stages():
                    issue('checkpoint_stages_mismatch', row)
                started, completed, in_flight = (row.get(key) for key in ('calls_started', 'calls_completed', 'in_flight'))
                if not all(valid_integer(value) for value in (started, completed, in_flight)) or completed != total['calls'] or started != completed + in_flight:
                    issue('checkpoint_in_flight_equation_failed', row)
            if event == 'summary':
                summaries.append(row)

        last_summary = summaries[-1] if summaries else None
        last_callback_seq = callbacks[-1]['seq'] if callbacks else 0
        final = final_markers.get(identity, [])
        final_marker = final[-1] if final else None
        final_summary_totals_match = last_summary is not None and normalized_counts(last_summary.get('totals')) == total
        final_summary_in_flight_zero = last_summary is not None and last_summary.get('in_flight') == 0
        final_summary_covers_callbacks = last_summary is not None and last_summary['seq'] >= last_callback_seq
        persisted_final = final_marker is not None and final_marker.get('persisted') is True and last_summary is not None and final_marker.get('script_seq') == last_summary['seq']
        final_verified = bool(persisted_final and final_summary_totals_match and final_summary_in_flight_zero and final_summary_covers_callbacks)
        if final_marker is not None and not final_verified:
            coverage_issues.append({'code': 'final_summary_not_closed_or_consistent',
                                    'pid': identity[0], 'run_id': identity[1],
                                    'input_index': final_marker['_input'], 'line': final_marker['_line']})
        if current_window is not None:
            if final_verified:
                current_window.update(end_seq=last_summary['seq'], end_host_seq=last_summary.get('host_seq'),
                                      closed_by='persisted_final_summary', closed=True)
            windows.append(current_window)
        run_reports.append({'pid': identity[0], 'run_id': identity[1], 'sequence': sequence,
                            'totals': total, 'by_source': dict(by_source), 'by_stage': expected_stages(),
                            'final_summary_present': last_summary is not None,
                            'final_summary_totals_equal_deltas': final_summary_totals_match,
                            'final_summary_in_flight_zero': final_summary_in_flight_zero,
                            'final_summary_covers_all_callbacks': final_summary_covers_callbacks,
                            'persisted_final_summary_verified': final_verified,
                            'checkpoint_errors': sum(item.get('run_id') == identity[1] and item.get('pid') == identity[0]
                                                     for item in issues),
                            'process_lifetime_complete': False, 'startup_before_ready_unobserved': True})

    run_lookup = {(row['pid'], row['run_id']): row for row in run_reports}
    for window in windows:
        matching_gaps = []
        for gap_index, gap in enumerate(gaps):
            if window['collector_id'] != gap['collector_id']:
                continue
            a = window['start_host_seq']
            b = window['end_host_seq']
            c = gap['start_host_seq']
            d = gap['end_host_seq']
            if None in (a, c) or (b is None or c < b) and (d is None or d > a):
                matching_gaps.append(gap_index)
        end_seq = window['end_seq']
        prefix = [value for value in runs[(window['pid'], window['run_id'])]['arrival'] if end_seq is not None and value <= end_seq]
        prefix_sequence_valid = bool(end_seq is not None and sequence_check(prefix)['valid'])
        prefix_errors = [item for item in issues if item.get('run_id') == window['run_id'] and item.get('pid') == window['pid']
                         and isinstance(item.get('seq'), int) and end_seq is not None and item['seq'] <= end_seq]
        host_prefix = [row['host_seq'] for row in collectors.get(window['collector_id'], [])
                       if valid_integer(row.get('host_seq')) and window['end_host_seq'] is not None and row['host_seq'] <= window['end_host_seq']]
        host_prefix_valid = bool(host_prefix and sequence_check(host_prefix)['valid'])
        window['overlapping_gap_indexes'] = matching_gaps
        window['prefix_sequence_valid'] = prefix_sequence_valid and host_prefix_valid
        window['prefix_checkpoint_error_count'] = len(prefix_errors)
        window['complete_defined_window'] = bool(window['closed'] and not matching_gaps and
                                                  not window['cross_stage_in_flight'] and prefix_sequence_valid
                                                  and host_prefix_valid and not prefix_errors)

    rows = []
    for (stage, source, pid, run_id), total in sorted(grouped.items()):
        relevant = [window for window in windows if (window['stage'], window['pid'], window['run_id']) == (stage, pid, run_id)]
        rows.append({'stage': stage, 'source': source, 'pid': pid, 'run_id': run_id,
                     **total, 'errors': total['observer_error'] + total['original_error'],
                     'stage_window_complete': bool(relevant and all(window['complete_defined_window'] for window in relevant)),
                     'sequence_valid': run_lookup[(pid, run_id)]['sequence']['valid']})

    stopped = bool(collectors) and all(collector_stopped.values())
    closed = bool(run_reports) and all(run['persisted_final_summary_verified'] for run in run_reports)
    named_windows_closed = bool(windows) and all(window['complete_defined_window'] for window in windows)
    if issues:
        status = 'invalid'
    elif stopped and closed and named_windows_closed and not warnings:
        status = 'validated_observed_window'
    elif stopped:
        status = 'incomplete'
    else:
        status = 'in_progress'
    return {'schema': 'smartisan.callback-summary.v1', 'status': status,
            'input_count': len(paths), 'record_count': len(records), 'event_counts': dict(event_counts),
            'totals': overall, 'groups': rows, 'runs': run_reports,
            'host_sequences': host_sequence_results, 'host_gaps': gaps, 'stage_windows': windows,
            'checkpoint_checks': checkpoint_checks, 'issues': issues, 'coverage_issues': coverage_issues, 'warnings': warnings,
            'validation': {'sequence_and_checkpoint_checks_pass': not issues,
                           'collector_stopped': stopped, 'all_run_final_summaries_verified': closed,
                           'all_defined_stage_windows_closed': named_windows_closed,
                           'count_equation_pass': overall['calls'] == overall['match'] + overall['mismatch'] + overall['uncomparable']},
            'coverage': {'scope': 'Only observed i71.d callbacks in explicitly staged, ready windows',
                         'process_lifetime_complete': False, 'startup_callback_count': None,
                         'gap_callback_count': None, 'unobserved_gap_count': len(gaps),
                         'unobserved_counts_are_unknown_not_zero': True,
                         'does_not_establish': ['complete_process_lifetime', 'attendance_acceptance', 'anti_risk_pass']}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', type=Path, nargs='+', help='One or more durable callback JSONL journals')
    parser.add_argument('--json', type=Path, dest='json_output', help='Write detailed JSON (retains process/session metadata)')
    parser.add_argument('--csv', type=Path, dest='csv_output', help='Write stage/source/process counts (retains process/session metadata)')
    parser.add_argument('--require-closed', action='store_true', help='Fail unless collectors and defined stages have verified final closure')
    args = parser.parse_args(argv)
    output_paths = [path.resolve() for path in (args.json_output, args.csv_output) if path is not None]
    if len(output_paths) != len(set(output_paths)) or set(output_paths).intersection(path.resolve() for path in args.inputs):
        parser.error('Summary outputs must differ from each other and every input journal')
    try:
        report = summarize(args.inputs)
    except OSError as error:
        parser.exit(2, f'Cannot read input ({type(error).__name__}).\n')
    for output in (args.json_output, args.csv_output):
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
    if args.json_output is not None:
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.csv_output is not None:
        columns = ['stage', 'source', 'pid', 'run_id', *COUNTERS, 'errors', 'stage_window_complete', 'sequence_valid']
        with args.csv_output.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(report['groups'])
    total = report['totals']
    print(f"{report['status']}: calls={total['calls']} match={total['match']} mismatch={total['mismatch']} "
          f"uncomparable={total['uncomparable']} observer_error={total['observer_error']} "
          f"original_error={total['original_error']} null={total['null_count']}")
    print(f"runs={len(report['runs'])} issues={len(report['issues'])} warnings={len(report['warnings'])} "
          f"unknown_host_gaps={len(report['host_gaps'])}; process-lifetime/startup counts remain unknown.")
    closed = report['validation']['collector_stopped'] and report['validation']['all_run_final_summaries_verified'] and report['validation']['all_defined_stage_windows_closed']
    return 1 if report['issues'] or args.require_closed and (not closed or report['warnings']) else 0


if __name__ == '__main__':
    sys.exit(main())
