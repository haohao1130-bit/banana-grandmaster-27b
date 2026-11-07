from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.setup_environment import prepare_environment, run_logged


class SetupTests(unittest.TestCase):
    def test_partial_environment_is_archived_and_pip_is_bootstrapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);env=root/'.venv';env.mkdir()
            (env/'previous-file').write_text('preserve me')
            commands=[]
            with patch('tools.setup_environment.environment_info',side_effect=[
                    {'version':[3,13],'prefix':'/base'},None]):
                prepare_environment(root,'base-python',lambda cmd,log:commands.append(cmd))
            archived=list(root.glob('.venv-before-setup-*'))
            self.assertEqual(len(archived),1)
            self.assertEqual((archived[0]/'previous-file').read_text(),'preserve me')
            self.assertIn('--without-pip',commands[0])
            self.assertIn('--system-site-packages',commands[0])
            self.assertEqual(commands[1][:6],['base-python','-m','pip','--python',str(env/'bin/python'),'install'])
            self.assertFalse(any('apt-get' in cmd for cmd in commands))

    def test_matching_environment_still_gets_pip_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);env=root/'.venv';env.mkdir();commands=[]
            with patch('tools.setup_environment.environment_info',side_effect=[
                    {'version':[3,13],'prefix':'/base'},
                    {'version':[3,13],'prefix':str(env)}]):
                prepare_environment(root,'base-python',lambda cmd,log:commands.append(cmd))
            self.assertNotIn('venv',commands[0])
            self.assertIn('--python',commands[0])
            self.assertFalse(list(root.glob('.venv-before-setup-*')))

    def test_install_failure_keeps_real_error_in_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'setup.log'
            with self.assertRaisesRegex(RuntimeError,'exit 7'):
                run_logged([sys.executable,'-c',
                            'import sys;print("ERROR: concrete test failure",file=sys.stderr);sys.exit(7)'],log)
            self.assertIn('ERROR: concrete test failure',log.read_text())


if __name__=='__main__':unittest.main()
