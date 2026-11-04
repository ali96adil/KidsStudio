"""Owner Mac read-only initial hardware/asset inventory for final acceptance.

NO installs, network, model inference, media generation, file modifications,
API key reads, unsafe shell commands or publishing. This is a discovery probe,
not a final engine/model/rights qualification.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import platform
import shutil
import sys


ASSETS = {
    "kidsstudio_workspace":("KidsStudio", "dir"),
    "ltx_mlx_engine":("KidsStudio/engines/ltx-2-mlx", "dir"),
    "chatterbox_python":("KidsStudio/engines/tts-chatterbox/.venv/bin/python", "file"),
    "voice_runner":("KidsStudio/agents/voice_studio_v2.py", "file"),
    "bunny_reference":("ComfyUI-Shared/input/KidsStudio_Bunny_reference.png", "file"),
    "character_voices_registry":("KidsStudio/production/voices/characters.json", "file"),
    "bunny_red_ball_pilot":(
        "KidsStudio/output/pilots/RedBall_v03/RedBall_dialogue_v03.mp4", "file"),
}
TOOLS = ("ffmpeg","ffprobe","git","python3")


def inspect_owner_mac(home: Path | str | None = None, *, system: str | None = None,
                      machine: str | None = None,
                      tool_lookup=None) -> dict:
    system = system if system is not None else platform.system()
    machine = machine if machine is not None else platform.machine()
    home_path = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()
    if tool_lookup is None:
        tool_lookup=shutil.which
    files={}
    for name,(relative,kind) in ASSETS.items():
        candidate=home_path/relative
        exists=(candidate.is_dir() if kind=="dir" else
                candidate.is_file() and candidate.stat().st_size>0)
        files[name]={"state":"FOUND" if exists else "MISSING",
                     "checked":True,"contents_read":False}
    tools={}
    for name in TOOLS:
        found=tool_lookup(name)
        tools[name]={"state":"FOUND" if found else "MISSING",
                     "executed":False}
    mac_qualified=system=="Darwin" and machine in ("arm64","aarch64")
    missing=[name for name,value in files.items()
             if value["state"]=="MISSING"]
    if not mac_qualified:
        status="NOT_APPLE_SILICON_MAC"
    elif missing or any(value["state"]=="MISSING" for value in tools.values()):
        status="MAC_DISCOVERY_INCOMPLETE_NO_CHANGES"
    else:
        status="MAC_PATHS_FOUND_ENGINE_API_NOT_QUALIFIED"
    return {
        "schema_version":1,"status":status,
        "operating_system":system,"cpu_architecture":machine,
        "apple_silicon_mac":mac_qualified,
        "assets":files,"local_tools":tools,
        "missing_asset_roles":missing,
        "filesystem_paths_disclosed":False,
        "api_keys_read":False,"files_modified":False,
        "network_requests":False,"model_execution_performed":False,
        "voice_and_model_license_verified":False,
        "youtube_upload_performed":False,"public_release_authorized":False,
        "next_action":("Review missing engine/assets before real Mac pilot."
                       if missing else
                       "Pin exact engine versions, weights and tested wrappers "
                       "before any real model execution.")
    }


def main(argv=None)->int:
    p=argparse.ArgumentParser(prog="studio-mac-quick-probe")
    p.add_argument("--home",type=Path,help="Test-only alternate home root")
    args=p.parse_args(argv)
    import json
    print(json.dumps(inspect_owner_mac(args.home),ensure_ascii=False,indent=2))
    # Discovery, not production approval. Return success even when a role is
    # missing so the user can share the complete diagnostic output.
    return 0


if __name__=="__main__":
    raise SystemExit(main())
