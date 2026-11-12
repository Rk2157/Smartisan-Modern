'use strict';

// One passive observation point: i71.d(String, boolean, DtLocation).
// No factory/listener/helper hook, DEX load, preferences write or location request.
// The host must append and flush every send() payload as JSONL. Callback records
// carry their own delta, stage and run_id, so process death cannot erase history
// already received by the host. Heartbeats contain cumulative cross-stage totals.
const runId = String(Process.id) + '-' + String(Date.now());
let sequence = 0;
let currentStage = 'unclassified';
let ready = false;
let setupFailed = false;
let callsStarted = 0;
let callsCompleted = 0;
let inFlight = 0;
const stages = {};
const sources = {};
function emptyCounts() {
  return { calls: 0, match: 0, mismatch: 0, uncomparable: 0,
    coordinate_match: 0, coordinate_mismatch: 0, address15_match: 0, address15_mismatch: 0,
    precision_match: 0, precision_mismatch: 0, observer_error: 0,
    null_count: 0, null_dto: 0, null_snapshot: 0, original_error: 0 };
}
const totals = emptyCounts();
function emit(event, body) {
  const record = { schema: 'smartisan.callback-statistics.v1', event: event,
    pid: Process.id, run_id: runId, seq: ++sequence, timestamp_ms: Date.now(),
    stage: currentStage, ...(body || {}) };
  try { send(record); } catch (_) {}
  return record;
}
function cumulative() {
  return JSON.parse(JSON.stringify({ ready: ready, setup_failed: setupFailed,
    calls_started: callsStarted, calls_completed: callsCompleted, in_flight: inFlight,
    totals: totals, by_source: sources, by_stage: stages }));
}
function addCounts(target, delta) { for (const key of Object.keys(target)) target[key] += delta[key] || 0; }
function commit(stage, source, delta) {
  if (sources[source] === undefined) sources[source] = emptyCounts();
  if (stages[stage] === undefined) stages[stage] = { totals: emptyCounts(), by_source: {} };
  if (stages[stage].by_source[source] === undefined) stages[stage].by_source[source] = emptyCounts();
  addCounts(totals, delta);
  addCounts(sources[source], delta);
  addCounts(stages[stage].totals, delta);
  addCounts(stages[stage].by_source[source], delta);
}
rpc.exports = {
  setStage(stage) {
    if (!['unclassified', 'first_entry', 'refresh', 'reentry', 'after_restart'].includes(stage)) throw new Error('UnknownStage');
    const previous = currentStage;
    currentStage = stage;
    return emit('stage', { previous_stage: previous, ...cumulative() });
  },
  summary() { return emit('summary', cumulative()); }
};
emit('loaded', cumulative());
setInterval(function () { emit('heartbeat', cumulative()); }, 10000);

Java.perform(function () {
  function cast(value, klass) { return value === null ? null : Java.cast(value, klass); }
  function errorType(error) { return String(error).split(':')[0]; }
  try {
    const app = Java.use('android.app.ActivityThread').currentApplication();
    if (app === null || String(app.getPackageName()) !== 'com.alibaba.android.rimet') throw new Error('WrongPackageOrApplicationNotReady');
    const System = Java.use('java.lang.System');
    const Method = Java.use('java.lang.reflect.Method');
    const moduleName = 'com.fuck.android.rimet.modern.ModernModule';
    let Module = null;
    let moduleFactory = null;
    for (const loader of Java.enumerateClassLoadersSync()) {
      try {
        const candidate = Java.ClassFactory.get(loader).use(moduleName);
        Module = candidate;
        moduleFactory = Java.ClassFactory.get(candidate.class.getClassLoader());
        break;
      } catch (_) {}
    }
    if (Module === null) throw new Error('ModuleClassNotFound');
    let module = null;
    moduleFactory.choose(moduleName, {
      onMatch(value) { module = Java.retain(value); return 'stop'; },
      onComplete() {}
    });
    if (module === null) throw new Error('ModuleInstanceNotFound');
    const readProfile = Module.class.getDeclaredMethod('readProfile', Java.array('java.lang.Class', []));
    readProfile.setAccessible(true);
    const noArgs = Java.array('java.lang.Object', []);
    const Profile = moduleFactory.use('com.fuck.android.rimet.profile.Profile');
    const SnapshotLocation = moduleFactory.use('com.amap.api.location.AMapLocation');
    const installedField = Module.class.getDeclaredField('installed');
    installedField.setAccessible(true);
    const installed = [];
    Java.synchronized(module, function () {
      const set = cast(installedField.get(module), Java.use('java.util.Set'));
      const values = set.toArray();
      for (let i = 0; i < values.length; i++) installed.push(Java.retain(cast(values[i], Method)));
    });
    const factoryMethods = installed.filter(method => String(method.getDeclaringClass().getName()) === 'com.alibaba.android.rimet.model.DtLocation' &&
      ['fromLocation', 'fromAMapLocation'].includes(String(method.getName())));
    const hasSystemFactory = factoryMethods.some(method => String(method.getName()) === 'fromLocation');
    const hasGaodeFactory = factoryMethods.some(method => String(method.getName()) === 'fromAMapLocation');
    if (installed.length < 8 || !hasSystemFactory || !hasGaodeFactory) throw new Error('InstalledFactoryHooksMissing');
    // Use the actual model definition recorded by the installed factory hook.
    // This avoids scanning all loaded classes or guessing a patch class loader.
    const modelClass = factoryMethods[0].getDeclaringClass();
    const targetFactory = Java.ClassFactory.get(modelClass.getClassLoader());
    const Model = targetFactory.use('com.alibaba.android.rimet.model.DtLocation');
    let Service = null;
    for (const name of ['i71', 'defpackage.i71']) {
      try { Service = targetFactory.use(name); break; } catch (_) {}
    }
    if (Service === null) throw new Error('DownstreamClassNotFound');
    const boolType = Java.use('java.lang.Boolean').TYPE.value;
    const method = Service.class.getMethod('d', Java.array('java.lang.Class', [Java.use('java.lang.String').class, boolType, Model.class]));
    if (installed.some(existing => existing.equals(method))) throw new Error('ObserverWouldOverlapInstalledHook');
    const original = Service.d.overload('java.lang.String', 'boolean', 'com.alibaba.android.rimet.model.DtLocation');
    if (original.implementation !== null) throw new Error('ExistingObserverOnTarget');
    const addressFields = ['District','PoiName','Country','BuildingId','AdCode','Description','CityCode',
      'Street','Province','Floor','Address','City','Road','AoiName','StreetNum'];
    function sourceName(dto) {
      if (dto === null) return 'UNKNOWN';
      const service = dto.getServiceType();
      if (service === null) return 'UNKNOWN';
      // getName(), not name(): this enum has a private field named name.
      const name = String(service.getName()).toUpperCase();
      return ['SYSTEM','GAODE','GOOGLE','WIFI','SYSTEM_GPS','SYSTEM_NETWORK','SYSTEM_FUSED'].includes(name) ? name : 'OTHER';
    }
    function observe(dto, event) {
      event.null_dto = dto === null;
      event.source = sourceName(dto);
      const profile = cast(readProfile.invoke(module, noArgs), Profile);
      const snapshot = profile === null ? null : cast(profile.c(), SnapshotLocation);
      event.null_snapshot = snapshot === null;
      if (dto === null || snapshot === null) { event.comparable = false; return; }
      const latitudeDifference = Math.abs(dto.getLatitude() - snapshot.getLatitude());
      const longitudeDifference = Math.abs(dto.getLongitude() - snapshot.getLongitude());
      const wrappedLongitudeDifference = Math.min(longitudeDifference, 360 - longitudeDifference);
      const latitudeMetres = latitudeDifference * Math.PI / 180 * 6371000;
      const longitudeMetres = wrappedLongitudeDifference * Math.PI / 180 * 6371000 * Math.abs(Math.cos(snapshot.getLatitude() * Math.PI / 180));
      event.coordinate_match = Number.isFinite(latitudeMetres) && Number.isFinite(longitudeMetres) && latitudeMetres <= 5.001 && longitudeMetres <= 5.001;
      event.precision_match = dto.getAltitude() === snapshot.getAltitude() && dto.getAccuracy() === snapshot.getAccuracy();
      let mismatches = 0;
      for (const field of addressFields) {
        const getter = 'get' + field;
        const actual = dto[getter]();
        const expected = snapshot[getter]();
        if ((actual === null) !== (expected === null) || String(actual) !== String(expected)) mismatches++;
      }
      event.address_fields_compared = 15;
      event.address_mismatch_count = mismatches;
      event.address15_match = mismatches === 0;
      event.comparable = true;
      event.match = event.coordinate_match && event.precision_match && event.address15_match;
    }
    original.implementation = function (businessType, continuous, location) {
      const stageAtEntry = currentStage;
      const callNumber = ++callsStarted;
      inFlight++;
      let returned;
      let thrown = null;
      // Exactly one call, with all original arguments. The logger/metrics method
      // completes before observation; its return value/exception is untouched.
      try { returned = original.call(this, businessType, continuous, location); }
      catch (error) { thrown = error; }
      const event = { call_number: callNumber, stage: stageAtEntry, source: 'UNKNOWN', continuous: !!continuous,
        original_called_once: true, original_error: thrown !== null, observer_error: false, comparable: false };
      try { observe(cast(location, Model), event); }
      catch (error) { event.observer_error = true; event.observer_error_type = errorType(error); }
      const delta = emptyCounts();
      delta.calls = 1;
      delta.match = event.comparable && event.match ? 1 : 0;
      delta.mismatch = event.comparable && !event.match ? 1 : 0;
      delta.uncomparable = event.comparable ? 0 : 1;
      if (event.coordinate_match !== undefined) delta[event.coordinate_match ? 'coordinate_match' : 'coordinate_mismatch'] = 1;
      if (event.address15_match !== undefined) delta[event.address15_match ? 'address15_match' : 'address15_mismatch'] = 1;
      if (event.precision_match !== undefined) delta[event.precision_match ? 'precision_match' : 'precision_mismatch'] = 1;
      delta.observer_error = event.observer_error ? 1 : 0;
      delta.null_dto = event.null_dto ? 1 : 0;
      delta.null_snapshot = event.null_snapshot ? 1 : 0;
      delta.null_count = event.null_dto || event.null_snapshot ? 1 : 0;
      delta.original_error = event.original_error ? 1 : 0;
      commit(stageAtEntry, event.source, delta);
      callsCompleted++;
      inFlight--;
      emit('callback', { ...event, delta: delta, process_totals: { ...totals } });
      if (thrown !== null) throw thrown;
      return returned;
    };
    ready = true;
    emit('ready', { ...cumulative(), installed_hook_count: installed.length,
      factory_hooks: factoryMethods.map(value => String(value.getName())),
      observer_target: String(Service.class.getName()) + '#d',
      observer_loader_identity_hash: System.identityHashCode(Service.class.getClassLoader()),
      model_loader_identity_hash: System.identityHashCode(modelClass.getClassLoader()),
      factory_methods_untouched: true, listener_methods_untouched: true, helper_methods_untouched: true });
  } catch (error) {
    setupFailed = true;
    emit('setup_error', { ...cumulative(), error_type: errorType(error) });
  }
});
