"""Exercise deployment command selection with fake Git/Docker; never build or deploy."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class UpdateScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        shutil.copyfile(Path(__file__).parents[1]/'update.sh', self.root/'update.sh')
        (self.root/'.env').write_text('APP_PASSWORD=synthetic-test-only\n')
        tools=self.root/'bin';tools.mkdir()
        (tools/'git').write_text('''#!/bin/bash
case "$1 $2" in
  'branch --show-current') echo server ;;
  'status --porcelain') [[ "${TEST_DIRTY:-0}" == 0 ]] || echo ' M compose.yaml' ;;
  'rev-parse --short') echo abcdef ;;
esac
exit 0
''')
        (tools/'docker').write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$TEST_CALL_LOG"
if [[ "$*" == *'config --quiet'* && "${TEST_FAIL_CONFIG:-0}" == 1 ]]; then exit 1; fi
exit 0
''')
        for file in tools.iterdir():file.chmod(0o755)
        self.env={**os.environ,'PATH':str(tools)+os.pathsep+os.environ['PATH'],'TEST_CALL_LOG':str(self.root/'calls')}
        # A parent shell must not supply deployment-specific encryption settings.
        self.env.pop('DATA_ENCRYPTION_KEY_FILE',None)

    def tearDown(self):self.tmp.cleanup()

    def run_update(self,*args):
        result=subprocess.run(['bash',str(self.root/'update.sh'),*args],cwd='/',env=self.env,capture_output=True,text=True)
        log=(self.root/'calls').read_text() if (self.root/'calls').exists() else ''
        return result,log

    def test_external_proxy_is_persisted_and_only_app_is_updated(self):
        (self.root/'compose.server-local.yaml').write_text('services: {}\n')
        result,log=self.run_update('--external-proxy')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('-f compose.yaml -f compose.server-local.yaml build app',log)
        self.assertIn('up -d --no-deps --wait --wait-timeout 120 app',log)
        self.assertTrue((self.root/'.external-proxy-deployment').exists())
        result,log=self.run_update()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(log.count('up -d --no-deps --wait --wait-timeout 120 app'),2)
        self.assertNotIn('up -d --wait ',log)

    def test_default_deployment_still_starts_full_stack(self):
        result,log=self.run_update()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('compose -f compose.yaml build\n',log)
        self.assertIn('up -d --wait --wait-timeout 120\n',log)
        self.assertFalse((self.root/'.external-proxy-deployment').exists())

    def test_missing_override_and_failed_validation_never_build(self):
        result,log=self.run_update('--external-proxy')
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn(' build',log)
        (self.root/'compose.server-local.yaml').write_text('services: {}\n')
        self.env['TEST_FAIL_CONFIG']='1'
        result,log=self.run_update('--external-proxy')
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn(' build',log)
        self.assertNotIn(' up ',log)
        self.assertFalse((self.root/'.external-proxy-deployment').exists())

    def test_encryption_guard_and_external_proxy_combine(self):
        (self.root/'.encrypted-deployment').touch()
        (self.root/'compose.server-local.yaml').write_text('services: {}\n')
        result,log=self.run_update('--external-proxy')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('refusing to switch to plaintext',result.stderr)
        self.assertNotIn(' build',log)
        result,log=self.run_update('--external-proxy','--encrypted')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('-f compose.encrypted.yaml -f compose.server-local.yaml build app',log)

    def test_tracked_changes_are_not_overwritten(self):
        self.env['TEST_DIRTY']='1'
        result,log=self.run_update('--external-proxy')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('local source changes',result.stderr)
        self.assertEqual(log,'')
