import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release_helper', Path(__file__).with_name('release.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
HEAD = 'a' * 40

class ReleasePreparationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env_file = Path(self.tmp.name) / 'env'
        self.env = patch.dict(os.environ, {
            'GITHUB_EVENT_NAME': 'workflow_dispatch', 'INPUT_TAG': 'v0.4-beta5-api102.1',
            'INPUT_PRERELEASE': 'true', 'GITHUB_REPOSITORY': 'owner/repo',
            'GITHUB_RUN_NUMBER': '7', 'GITHUB_ENV': str(self.env_file),
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_manual_version_and_monotonic_code(self):
        with patch.object(release, 'api', return_value=None): release.prepare()
        text = self.env_file.read_text()
        self.assertIn('APP_VERSION_NAME=0.4-beta5-api102.1\n', text)
        self.assertIn('APP_VERSION_CODE=1007\n', text)
        self.assertIn('RELEASE_PRERELEASE=true\n', text)

    def test_reject_shell_and_environment_injection(self):
        for tag in ['v1\nEVIL=true', 'v1;whoami', 'v1$(whoami)', '../v1', 'v1/x', '']:
            with self.subTest(tag=tag), patch.dict(os.environ, {'INPUT_TAG': tag}), patch.object(release, 'api') as api:
                with self.assertRaises(ValueError): release.prepare()
                api.assert_not_called()

    def test_existing_release_is_not_overwritten(self):
        with patch.object(release, 'api', return_value={'id': 1}):
            with self.assertRaisesRegex(ValueError, 'already exists'): release.prepare()

    def test_wrong_commit_tag_is_rejected(self):
        with patch.object(release, 'api', side_effect=[None, {'object': {'type': 'commit', 'sha': 'b'*40}}]), \
             patch.object(release.subprocess, 'check_output', return_value=HEAD):
            with self.assertRaisesRegex(ValueError, 'checked-out commit'): release.prepare()

    def test_annotated_tag_is_resolved(self):
        with patch.object(release, 'api', side_effect=[None, {'object': {'type': 'tag', 'sha': 'c'*40}},
                                                     {'object': {'type': 'commit', 'sha': HEAD}}]), \
             patch.object(release.subprocess, 'check_output', return_value=HEAD):
            release.prepare()
        self.assertTrue(self.env_file.exists())

    def test_stable_push_tag(self):
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF_NAME': 'v1.0.0'}), \
             patch.object(release, 'api', return_value=None): release.prepare()
        self.assertIn('RELEASE_PRERELEASE=false\n', self.env_file.read_text())

    def test_upstream_beta_name_does_not_force_prerelease(self):
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF_NAME': 'v0.4-beta5-api102.2'}), \
             patch.object(release, 'api', return_value=None): release.prepare()
        self.assertIn('RELEASE_PRERELEASE=false\n', self.env_file.read_text())

    def test_manual_release_defaults_to_stable(self):
        os.environ.pop('INPUT_PRERELEASE')
        with patch.object(release, 'api', return_value=None): release.prepare()
        self.assertIn('RELEASE_PRERELEASE=false\n', self.env_file.read_text())

    def test_manual_false_is_stable(self):
        with patch.dict(os.environ, {'INPUT_PRERELEASE': 'false'}), \
             patch.object(release, 'api', return_value=None): release.prepare()
        self.assertIn('RELEASE_PRERELEASE=false\n', self.env_file.read_text())

    def test_modified_apk_cannot_be_packaged(self):
        root = Path(self.tmp.name)
        (root / 'output').mkdir()
        (root / 'output/build-result.json').write_text(json.dumps({'apk': 'test.apk', 'sha256': 'bad'}))
        (root / 'output/static-verification.json').write_text(json.dumps({'sha256': 'bad'}))
        (root / 'output/test.apk').write_bytes(b'changed')
        with patch.object(release, 'ROOT', root):
            with self.assertRaisesRegex(ValueError, 'verified build'): release.package()

if __name__ == '__main__':
    unittest.main()
