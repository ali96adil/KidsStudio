"""M44 bounded POSIX model process-group lifecycle.

subprocess.run(timeout=...) terminates only the top-level child. ML
inference can spawn Python workers that survive it. This helper creates
a fresh process group and sends TERM followed by KILL to the entire group
on timeout, success, subprocess failure or interruption. It cannot
police intentionally detached setsid/daemonized descendants; use an
OS-level sandbox for untrusted runners.

No shell, inherited OAuth/HMAC secrets, stdout/stderr buffering or retries.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import time


class ModelProcessError(ValueError):
    pass


def _terminate_group(pid:int,*,grace_seconds:float=0.15)->None:
    if not isinstance(pid,int) or pid<2:
        return
    try:
        os.killpg(pid,signal.SIGTERM)
    except ProcessLookupError:
        return
    # A short grace gives child workers a chance to release resources.
    time.sleep(grace_seconds)
    try:
        os.killpg(pid,signal.SIGKILL)
    except ProcessLookupError:
        pass


def bounded_model_process(args:list[str],*,stdin,stdout,stderr,
                          timeout:int,env:dict[str,str],
                          check:bool=False)->subprocess.CompletedProcess:
    """One POSIX subprocess and full process-group cleanup, even after exit.

    Adapter output is deliberately discarded; the only authenticated
    evidence is the separately hashed private JSON bound to original
    source/checkpoint bytes by the calling M43 pilot.
    """
    if (os.name!="posix" or
        not isinstance(args,list) or not args or
        any(not isinstance(s,str) or not s or "\x00" in s for s in args) or
        not isinstance(timeout,int) or not 1<=timeout<=900 or
        check is not False or stdin is not subprocess.DEVNULL or
        stdout is not subprocess.PIPE or stderr is not subprocess.PIPE or
        not isinstance(env,dict) or any(
            not isinstance(k,str) or not isinstance(v,str)
            for k,v in env.items())):
        raise ModelProcessError("Bounded POSIX model protocol only.")
    if any(k.upper() in env for k in (
        "KIDS_STUDIO_SCENE_QA_RUNNER_KEY","GOOGLE_CLIENT_SECRET",
        "OPENAI_API_KEY","GITHUB_TOKEN")):
        raise ModelProcessError("Never inherit credentials into local AI.")
    if not Path(args[0]).is_absolute():
        raise ModelProcessError("Absolute SHA-pinned runner path required.")
    process=None
    try:
        process=subprocess.Popen(args,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            start_new_session=True,close_fds=True,env=env)
        status=process.wait(timeout=timeout)
        return subprocess.CompletedProcess(args,status,b"",b"")
    except subprocess.TimeoutExpired:
        raise
    finally:
        if process is not None:
            _terminate_group(process.pid)
            if process.poll() is None:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
