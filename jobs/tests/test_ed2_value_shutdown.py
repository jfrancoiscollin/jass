"""Exercise actual controller termination and cleanup without engine or data reads."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(sys.platform.startswith('linux'),'Linux process groups')
class ShutdownTests(unittest.TestCase):
    def test_sigterm_unwinds_actual_role_worker_cleanup(self):
        script=r'''
import os,signal,subprocess,sys,time
from pathlib import Path
from jobs.tools import ed2_value_pipeline as p
from jobs.tools.ed2_value_entrypoint import install_shutdown_handlers
root=Path(sys.argv[1]); real_popen=subprocess.Popen
worker='import os,subprocess,sys,time;from pathlib import Path;child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);Path(sys.argv[1]).write_text(str(os.getpid())+" "+str(child.pid));time.sleep(60)'
serial=0
def spawn(*args,**kwargs):
 global serial
 path=root/('worker-'+str(serial)); serial+=1
 return real_popen([sys.executable,'-c',worker,str(path)],**kwargs)
p.subprocess.Popen=spawn
p.groups_for=lambda *a:[dict(rows=list(range(8)))]
p.teacher_deadline=lambda *a:60
install_shutdown_handlers()
p.role_search(root,root/'unused-scan','train',root,root,{})
'''
        def active(pid):
            try:
                state=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1][0]
                return state!='Z'
            except FileNotFoundError:
                return False
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); pids=[]
            proc=subprocess.Popen([sys.executable,'-c',script,td],cwd=ROOT,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                stop=time.monotonic()+10
                while time.monotonic()<stop:
                    files=list(root.glob('worker-*'))
                    if len(files)==8 and all(f.stat().st_size for f in files): break
                    if proc.poll() is not None: self.fail(proc.communicate()[1])
                    time.sleep(.02)
                self.assertEqual(len(files),8)
                pids=[int(x) for f in files for x in f.read_text().split()]
                self.assertEqual(len(pids),16)
                proc.send_signal(signal.SIGTERM)
                out,err=proc.communicate(timeout=8)
                self.assertEqual(proc.returncode,143,(out,err))
                stop=time.monotonic()+3
                while any(active(pid) for pid in pids) and time.monotonic()<stop: time.sleep(.02)
                self.assertFalse(any(active(pid) for pid in pids))
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()
                for pid in pids:
                    try: os.kill(pid,signal.SIGKILL)
                    except ProcessLookupError: pass

if __name__=='__main__':unittest.main()
