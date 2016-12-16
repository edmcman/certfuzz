'''
Created on Oct 22, 2014

@author: adh
'''
from certfuzz.runners.runner_base import Runner
from distutils.spawn import find_executable
from certfuzz.runners.errors import RunnerError
import os
import subprocess
import logging
from certfuzz.runners.errors import RunnerNotFoundError
import shlex
from certfuzz.helpers.misc import quoted
from certfuzz.fuzztools.zzuflog import ZzufLog

logger = logging.getLogger(__name__)


_zzuf_basename = 'zzuf'
_zzuf_loc = None

_use_cert_version_of_zzuf = False


def _find_zzuf():
    global _zzuf_loc
    _zzuf_loc = find_executable(_zzuf_basename)


def _verify_zzuf_installed():
    if _zzuf_loc is None:
        _find_zzuf()
    # if it's still None, we have a problem
    if _zzuf_loc is None:
        raise RunnerNotFoundError('Unable to locate {}, $PATH={}'.format(_zzuf_basename, os.environ['PATH']))


def check_runner():
    global _use_cert_version_of_zzuf

    _verify_zzuf_installed()

    result = subprocess.check_output(['zzuf', '-h'])

    for line in result.split(os.linesep):
        check_for = ('--opmode <mode>', 'null')

        if all(x in line for x in check_for):
            _use_cert_version_of_zzuf = True

class ZzufRunner(Runner):
    def __init__(self, options, cmd_template, fuzzed_file, workingdir_base):
        Runner.__init__(self, options, cmd_template, fuzzed_file, workingdir_base)

        self._zzuf_log_basename = 'zzuf_log.txt'
        self.zzuf_log_path = os.path.join(self.workingdir, self._zzuf_log_basename)
        self._quiet = options.get('hideoutput', True)

        self._cmd_template = cmd_template
        self._cmd = self._cmd_template.substitute(SEEDFILE=quoted(fuzzed_file))
        self._cmd_parts = shlex.split(self._cmd)
        self._cmd_parts[0] = os.path.expanduser(self._cmd_parts[0])

        self._zzuf_args = None
        self._construct_zzuf_args()
        logger.debug('_zzuf_args=%s', self._zzuf_args)

    def _construct_zzuf_args(self):
        _verify_zzuf_installed()

        args = [_zzuf_loc]
        if self._quiet:
            args.append('--quiet')

        _opmode = 'copy'
        if _use_cert_version_of_zzuf:
            _opmode = 'null'

        args.extend(['--signal',
                     '--ratio=0.0',
                     '--seed=0',
                     '--max-crashes=1',
                     '--max-memory=%s' % self.maxmemory,
                     '--max-usertime=%s' % self.runtimeout,
                     '--opmode=%s' % _opmode,
                     '--include=%s' % self.fuzzed_file,
                     ])


        self._zzuf_args = args

    def _run(self):
        if not len(self._zzuf_args):
            raise RunnerError('_zzuf_args is empty')

        with open(self.fuzzed_file, 'rb') as ff, open(self.zzuf_log_path, 'wb') as zo:
            cmd2run = self._zzuf_args + self._cmd_parts
            logger.debug('RUN_CMD: {}'.format(' '.join(cmd2run)))
            rc = subprocess.call(cmd2run, cwd=self.workingdir, stdin=ff, stderr=zo)

            if rc != 0:
                self.saw_crash = True

    def _postrun(self):
        if not self.saw_crash:
            logger.debug('No crash seen')
            return

        # we must have seen a crash
        # get the results
        zzuf_log = ZzufLog(self.zzuf_log_path)

        # dump zzuflog into our log
        logger.debug("ZzufLog:")
        from pprint import pformat
        for line in pformat(zzuf_log.__dict__).splitlines():
            logger.debug(line)

        # Don't generate cases for killed process or out-of-memory
        # In the default mode, zzuf will report a signal. In copy (and exit code) mode, zzuf will
        # report the exit code in its output log.  The exit code is 128 + the signal number.
        self.saw_crash = zzuf_log.crash_logged()


_runner_class = ZzufRunner
