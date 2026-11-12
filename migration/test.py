import json
import os
from pathlib import Path
import subprocess

from java_tools import java_tool

ROOT = Path(__file__).resolve().parent.parent
DEPS = ROOT / 'tools/migration'
BUILD = Path(json.loads((ROOT / 'output/build-result.json').read_text())['build_directory'])
JAVA = java_tool('java')
JAVAC = java_tool('javac')
TESTS = BUILD / 'tests'
TESTS.mkdir(exist_ok=True)
PROGRAM = BUILD / 'classes'
BASE = [str(TESTS), str(PROGRAM), str(DEPS / 'android.jar'), str(DEPS / 'service/classes.jar'), str(DEPS / 'interface/classes.jar')]
WITH_API = BASE + [str(DEPS / 'api/classes.jar')]
sources = sorted((ROOT / 'migration/tests').rglob('*.java'))
subprocess.run([str(JAVAC), '-encoding', 'UTF-8', '-cp', os.pathsep.join(WITH_API), '-d', str(TESTS), *map(str, sources)], check=True)
for name, classpath in [('ModernModuleTest', WITH_API), ('LocationTransferTest', WITH_API), ('AppIsolationTest', BASE)]:
    subprocess.run([str(JAVA), '-ea', '-cp', os.pathsep.join(classpath), name], check=True)
