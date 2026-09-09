import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
DEPS = ROOT / 'tools/migration'
BUILD = Path(json.loads((ROOT / 'output/build-result.json').read_text())['build_directory'])
JAVA_HOME = Path(os.environ.get('JAVA_HOME', r'C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot'))
TESTS = BUILD / 'tests'
TESTS.mkdir(exist_ok=True)
PROGRAM = BUILD / 'classes'
BASE = [str(TESTS), str(PROGRAM), str(DEPS / 'android.jar'), str(DEPS / 'service/classes.jar'), str(DEPS / 'interface/classes.jar')]
WITH_API = BASE + [str(DEPS / 'api/classes.jar')]
sources = sorted((ROOT / 'migration/tests').rglob('*.java'))
subprocess.run([str(JAVA_HOME / 'bin/javac.exe'), '-encoding', 'UTF-8', '-cp', os.pathsep.join(WITH_API), '-d', str(TESTS), *map(str, sources)], check=True)
for name, classpath in [('ModernModuleTest', WITH_API), ('LocationTransferTest', WITH_API), ('AppIsolationTest', BASE)]:
    subprocess.run([str(JAVA_HOME / 'bin/java.exe'), '-ea', '-cp', os.pathsep.join(classpath), name], check=True)
