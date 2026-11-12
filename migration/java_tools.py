"""Locate JDK tools without assuming a Windows executable suffix."""
import os
from pathlib import Path
import shutil


def java_tool(name):
    executable = name + ('.exe' if os.name == 'nt' else '')
    java_home = os.environ.get('JAVA_HOME')
    if java_home:
        return Path(java_home) / 'bin' / executable
    discovered = shutil.which(executable)
    if discovered:
        return Path(discovered)
    if os.name == 'nt':
        # Keep the original local Windows fallback; CI supplies JAVA_HOME.
        return Path(r'C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot') / 'bin' / executable
    raise RuntimeError(f'Cannot find {executable}; set JAVA_HOME to a JDK 17 installation')
