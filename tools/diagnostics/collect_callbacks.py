#!/usr/bin/env python3
"""Durable host collector for the passive Smartisan callback-statistics agent.

Run with test-venv/bin/python. This program never starts/stops an Android app:
its sole adb operation is pidof for the fixed DingTalk package. The parent task
must prepare and later remove the diagnostic server and port forward.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

import frida
import frida_tools


PACKAGE = 'com.alibaba.android.rimet'
STAGES = {'unclassified', 'first_entry', 'refresh', 'reentry', 'after_restart'}
HERE = Path(__file__).resolve().parent


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class Journal:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open('a', encoding='utf-8')
        self.lock = threading.RLock()
        self.sequence = 0
        self.collector_id = str(uuid.uuid4())
        self.closed = False

    def write(self, record):
        with self.lock:
            if self.closed:
                return
            self.sequence += 1
            row = dict(record)
            row.update(host_utc=utc_now(), host_seq=self.sequence, collector_id=self.collector_id)
            self.file.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
            self.file.flush()
            os.fsync(self.file.fileno())

    def host(self, event, **fields):
        self.write({'schema': 'smartisan.callback-host.v1', 'event': event, **fields})

    def close(self):
        with self.lock:
            self.closed = True
            self.file.flush()
            os.fsync(self.file.fileno())
            self.file.close()


class Connection:
    def __init__(self, pid):
        self.pid = pid
        self.session = None
        self.script = None
        self.started = time.monotonic()
        self.ready = threading.Event()
        self.detached = threading.Event()
        self.setup_error = threading.Event()
        self.condition = threading.Condition()
        self.last_sequences = {}
        self.run_id = None
        self.applied_stage = None
        self.host_ready = False
        self.detached_reason = None
        self.detached_at = None


class Collector:
    def __init__(self, args):
        self.args = args
        self.journal = Journal(args.output)
        self.stage = 'unclassified'
        self.stop = False
        self.stop_reason = 'max_seconds'
        self.last_control_error = None
        self.last_summary_token = None
        self.summary_tokens = []
        self.connection = None
        self.gap_start = None
        self.setup_failures = 0
        self.print_lock = threading.Lock()
        bridge = Path(frida_tools.__file__).resolve().parent / 'bridges' / 'java.js'
        self.source = bridge.read_text(encoding='utf-8') + '\n;globalThis.Java = bridge;\n' + args.script.read_text(encoding='utf-8')

    def stdout(self, event, **fields):
        with self.print_lock:
            print(json.dumps({'event': event, **fields}, ensure_ascii=False), flush=True)

    def error(self, operation, error=None, **fields):
        # Exception messages/stacks may contain app data; record types only.
        self.journal.host('host_error', operation=operation,
                          error_type=type(error).__name__ if error is not None else None, **fields)

    def gap(self, reason, since=None):
        if self.gap_start is None:
            self.gap_start = since if since is not None else time.monotonic()
            self.journal.host('host_gap_start', reason=reason, stage=self.stage,
                              callbacks_unobserved=True, lost_callback_count=None)

    def end_gap(self):
        if self.gap_start is not None:
            self.journal.host('host_gap_end', duration_seconds=round(time.monotonic() - self.gap_start, 3),
                              stage=self.stage, callbacks_unobserved=True, lost_callback_count=None)
            self.gap_start = None

    def poll_control(self):
        try:
            control = json.loads(self.args.control.read_text(encoding='utf-8'))
            if not isinstance(control, dict):
                raise ValueError('ControlMustBeObject')
            requested = control.get('stage', self.stage)
            if requested not in STAGES:
                raise ValueError('InvalidStage')
            self.stage = requested
            if control.get('stop') is True:
                self.stop, self.stop_reason = True, 'control_stop'
            if 'summary_token' in control:
                token = hashlib.sha256(json.dumps(control['summary_token'], sort_keys=True).encode()).hexdigest()
                if token != self.last_summary_token:
                    self.last_summary_token = token
                    self.summary_tokens.append(token)
            self.last_control_error = None
        except (OSError, ValueError, TypeError) as error:
            marker = type(error).__name__
            if marker != self.last_control_error:
                self.error('read_control', error)
                self.last_control_error = marker

    def pid(self):
        try:
            result = subprocess.run([self.args.adb, '-s', self.args.serial, 'shell', 'pidof', PACKAGE],
                                    capture_output=True, text=True, timeout=5, check=False)
            values = result.stdout.split()
            if result.returncode != 0 or not values:
                return None
            if len(values) != 1 or not values[0].isdecimal() or int(values[0]) <= 0:
                self.error('pidof_ambiguous', pid_count=len(values))
                return None
            return int(values[0])
        except (OSError, subprocess.TimeoutExpired) as error:
            self.error('pidof', error)
            return None

    @staticmethod
    def native_call(function, timeout=10):
        cancellable = frida.Cancellable()
        timer = threading.Timer(timeout, cancellable.cancel)
        timer.daemon = True
        timer.start()
        try:
            with cancellable:
                return function()
        finally:
            timer.cancel()

    def on_message(self, connection, message, data):
        if message.get('type') == 'send':
            payload = message.get('payload')
            row = dict(payload) if isinstance(payload, dict) else {'event': 'script_payload', 'payload': payload}
            row.update(record_type='script', attached_pid=connection.pid)
            if data is not None:
                row['binary_bytes_omitted'] = len(data)
            self.journal.write(row)
            run_id, sequence = row.get('run_id'), row.get('seq')
            if isinstance(run_id, str) and isinstance(sequence, int):
                with connection.condition:
                    previous = connection.last_sequences.get(run_id, 0)
                    if sequence != previous + 1:
                        self.journal.host('host_sequence_gap', pid=connection.pid, run_id=run_id,
                                          expected_seq=previous + 1, received_seq=sequence,
                                          duplicate_or_out_of_order=sequence <= previous)
                    connection.last_sequences[run_id] = max(previous, sequence)
                    connection.run_id = run_id
                    connection.condition.notify_all()
            event = row.get('event')
            if event == 'ready':
                connection.ready.set()
            elif event == 'setup_error':
                connection.setup_error.set()
            elif event == 'summary':
                self.stdout('summary', pid=connection.pid, run_id=run_id, stage=row.get('stage'),
                            calls_started=row.get('calls_started'), calls_completed=row.get('calls_completed'),
                            in_flight=row.get('in_flight'), totals=row.get('totals'))
        elif message.get('type') == 'error':
            self.error('script_runtime', pid=connection.pid, run_id=connection.run_id,
                       line_number=message.get('lineNumber'), column_number=message.get('columnNumber'))
            connection.setup_error.set()

    def on_detached(self, connection, reason, crash=None):
        connection.detached_reason = str(reason)
        connection.detached_at = time.monotonic()
        connection.detached.set()
        self.journal.host('host_detach', pid=connection.pid, run_id=connection.run_id,
                          reason=str(reason), crash_present=crash is not None, stage=self.stage)
        self.stdout('detach', pid=connection.pid, run_id=connection.run_id, reason=str(reason))

    def attach(self, pid):
        connection = Connection(pid)
        self.connection = connection
        try:
            device = self.native_call(lambda: frida.get_device_manager().add_remote_device(self.args.host))
            connection.session = self.native_call(lambda: device.attach(pid))
            connection.session.on('detached', lambda reason, crash=None: self.on_detached(connection, reason, crash))
            self.journal.host('host_attach', pid=pid, stage=self.stage, observer_ready=False)
            connection.script = self.native_call(lambda: connection.session.create_script(self.source, name='callback-statistics'))
            connection.script.on('message', lambda message, data: self.on_message(connection, message, data))
            connection.script.set_log_handler(lambda level, text: self.journal.host('host_script_console', level=level, text_omitted=True))
            self.native_call(connection.script.load)
        except Exception as error:
            self.error('attach_or_load', error, pid=pid)
            self.close_connection(connection)

    def rpc(self, connection, method, *arguments):
        done = threading.Event()
        outcome = {}
        def invoke():
            try:
                outcome['result'] = getattr(connection.script.exports_sync, method)(*arguments)
            except Exception as error:
                outcome['error'] = error
            finally:
                done.set()
        threading.Thread(target=invoke, daemon=True).start()
        if not done.wait(5):
            self.error('rpc_timeout', method=method, pid=connection.pid)
            return None
        if 'error' in outcome:
            self.error('rpc', outcome['error'], method=method, pid=connection.pid)
            return None
        result = outcome.get('result')
        if not isinstance(result, dict) or not isinstance(result.get('seq'), int):
            self.error('rpc_invalid_record', method=method, pid=connection.pid)
            return None
        # send() delivery and fsync must finish before treating the RPC as durable.
        deadline = time.monotonic() + 3
        with connection.condition:
            while connection.last_sequences.get(result.get('run_id'), 0) < result['seq']:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.error('rpc_send_not_persisted', method=method, pid=connection.pid)
                    return None
                connection.condition.wait(min(remaining, 0.2))
        return result

    def close_connection(self, connection):
        if connection.script is not None:
            try:
                self.native_call(connection.script.unload, 3)
            except Exception as error:
                self.error('unload', error, pid=connection.pid)
        if connection.session is not None and not connection.detached.is_set():
            try:
                self.native_call(connection.session.detach, 3)
            except Exception as error:
                self.error('detach', error, pid=connection.pid)
        if self.connection is connection:
            self.connection = None

    def run(self):
        deadline = time.monotonic() + self.args.max_seconds
        self.journal.host('host_start', package=PACKAGE, max_seconds=self.args.max_seconds)
        self.gap('not_yet_ready')
        try:
            while not self.stop and time.monotonic() < deadline:
                self.poll_control()
                if self.stop:
                    break
                connection = self.connection
                if connection is None:
                    pid = self.pid()
                    if pid is not None:
                        self.attach(pid)
                    time.sleep(1)
                    continue
                if connection.detached.is_set():
                    self.gap(connection.detached_reason or 'target_detached', connection.detached_at)
                    self.close_connection(connection)
                    time.sleep(1)
                    continue
                if connection.setup_error.is_set() or (not connection.ready.is_set() and time.monotonic() - connection.started > 30):
                    self.setup_failures += 1
                    self.error('observer_setup', pid=connection.pid, attempt=self.setup_failures)
                    self.gap('observer_setup_failed')
                    self.close_connection(connection)
                    if self.setup_failures >= 3:
                        self.stop, self.stop_reason = True, 'three_setup_failures'
                        break
                    time.sleep(2)
                    continue
                if connection.ready.is_set():
                    if connection.applied_stage != self.stage:
                        result = self.rpc(connection, 'set_stage', self.stage)
                        if result is None:
                            self.gap('stage_rpc_failed')
                            self.close_connection(connection)
                            continue
                        connection.applied_stage = result['stage']
                        self.journal.host('host_stage_applied', pid=connection.pid, run_id=connection.run_id,
                                          stage=connection.applied_stage, script_seq=result['seq'])
                        self.stdout('stage', pid=connection.pid, run_id=connection.run_id, stage=connection.applied_stage)
                    if not connection.host_ready:
                        connection.host_ready = True
                        self.end_gap()
                        self.journal.host('host_ready', pid=connection.pid, run_id=connection.run_id,
                                          stage=connection.applied_stage, startup_before_ready_unobserved=True)
                        self.stdout('ready', pid=connection.pid, run_id=connection.run_id, stage=connection.applied_stage)
                    if self.summary_tokens:
                        token = self.summary_tokens.pop(0)
                        self.journal.host('host_summary_request', pid=connection.pid, token_sha256=token)
                        if self.rpc(connection, 'summary') is None:
                            self.gap('summary_rpc_failed')
                            self.close_connection(connection)
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_reason = 'keyboard_interrupt'
        except Exception as error:
            self.error('collector', error)
            self.stop_reason = 'collector_error'
        finally:
            connection = self.connection
            if connection is not None:
                if connection.ready.is_set() and not connection.detached.is_set():
                    final = self.rpc(connection, 'summary')
                    self.journal.host('host_final_summary', pid=connection.pid, run_id=connection.run_id,
                                      persisted=final is not None, script_seq=final.get('seq') if final else None,
                                      in_flight=final.get('in_flight') if final else None)
                    if final is None or final.get('in_flight', 0) != 0:
                        self.gap('final_summary_incomplete')
                    time.sleep(0.3)
                self.close_connection(connection)
            if self.gap_start is not None:
                self.journal.host('host_gap_open_at_stop', duration_seconds=round(time.monotonic() - self.gap_start, 3),
                                  callbacks_unobserved=True, lost_callback_count=None)
            self.journal.host('host_stop', reason=self.stop_reason, setup_failures=self.setup_failures)
            time.sleep(0.2)
            self.journal.close()
        return 1 if self.stop_reason in {'three_setup_failures', 'collector_error'} else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--script', type=Path, default=HERE / 'callback_statistics.js')
    parser.add_argument('--serial', required=True, help='ADB serial of the single authorized device')
    parser.add_argument('--host', default='127.0.0.1:27043')
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--max-seconds', type=float, default=900)
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 86400:
        parser.error('--max-seconds must be between 1 and 86400')
    return Collector(args).run()


if __name__ == '__main__':
    sys.exit(main())
