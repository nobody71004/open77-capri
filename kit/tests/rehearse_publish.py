"""A rehearsal of `capri_kit.py publish` on the owner's PC with everything real but the machine: the game's own
REDscript, this PC's game folder, the Studio's Python, the brain asked over HTTPS the way a player's game asks it --
and, in place of the SSH session, a folder standing in for the machine (it hands over LIVE.zip as the live package
and the brain's address this PC's own Capri settings use, and takes the import).  Nothing is sent anywhere.

    python rehearse_publish.py LIVE.zip [--role staging]

1.16.17: the stand-in machine also names her voice (a made-up private path: the build only writes it into
servidor.json, nothing asks it here) and the build carries Mass Override for everyone and Capri Voz edited -- the
compile check and PowerShell's own parser run on them for real.

Writes its log, the builds (work\\), the record and the compiler's sandboxes (_scc\\) next to this file.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
import capri_kit as ck  # noqa: E402


def main():
    live = os.path.abspath(sys.argv[1])
    role = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--role" else "staging"
    game = ck.find_game("")
    settings = json.load(open(os.path.join(game, "r6", "storages", "CapriConstruct", "settings.json"), encoding="utf-8-sig"))
    url = settings.get("localUrl") or ""
    if "capri-brain-" not in url or not url.startswith("https://"):
        print("this PC's Capri settings do not name the brain: no rehearsal")
        return 2
    server = os.path.join(HERE, "server-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(server)
    shutil.copyfile(live, os.path.join(server, "capri-current.zip"))
    with open(os.path.join(server, "brain.url"), "w", encoding="utf-8") as f:
        f.write(url + "\n")
    sha = hashlib.sha256(open(live, "rb").read()).hexdigest()
    # the machine's side of fetch and assemble: remote/capri_server.py's own code (pure Python), run here
    sys.path.insert(0, os.path.join(KIT, "remote"))
    import capri_server as cs  # noqa: E402
    import zipfile  # noqa: E402
    files = cs.read_entries(live)
    with zipfile.ZipFile(os.path.join(server, "scripts.zip"), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in sorted(files):
            if (n.startswith("r6/scripts/") and n.endswith(".reds")) or n in cs.EDITABLE_OTHER:
                info = zipfile.ZipInfo(n, cs.FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, files[n])
    with open(os.path.join(server, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"sha256": sha, "entries": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}, f)
    imported = {}
    voice_url = "https://" + url.split("/")[2] + "/capri-voice-" + "5eed" * 6 + "/v1"
    with open(os.path.join(server, "voice.url"), "w", encoding="utf-8") as f:
        f.write(voice_url + "\n")
    ck.ask_voice = lambda u, log: log("  (rehearsal: her voice is not asked -- the stand-in machine has none)") or True

    class Host:
        def get(self, remote, local):
            shutil.copyfile(os.path.join(server, os.path.basename(remote)), local)

        def put(self, local, remote, mode=0o644):
            shutil.copyfile(local, os.path.join(server, os.path.basename(remote)))

        def drop(self):
            pass

    class Stand:
        def __init__(self, a, log):
            self.log, self.h, self.work = log, Host(), server

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def call(self, *args, timeout=600):
            self.log(f"  (the stand-in machine: {args[0]})")
            if args[0] == "fetch":
                return 0, {"entry": {"version": "1.16.15", "sha256": sha, "sizeBytes": os.path.getsize(live),
                                     "displayName": "Capri - AI Companion with Voice (LLM)"},
                           "world": "XyberRP Staging" if role == "staging" else "XyberRP", "online": 0,
                           "wired": False, "wired_same": False, "host": url.split("/")[2],
                           "voice": {"languages": "en,es"}}
            if args[0] == "assemble":
                class Args:
                    pass
                x = Args()
                x.work, x.role = server, role
                x.delta = os.path.join(server, os.path.basename(args[args.index("--delta") + 1]))
                x.expect = os.path.join(server, os.path.basename(args[args.index("--expect") + 1]))
                x.expect_sha = args[args.index("--expect-sha") + 1]
                import io, contextlib  # noqa: E401,E402
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    try:
                        code = cs.cmd_assemble(x)
                    except cs.Failed as e:
                        print("CAPRI !! " + str(e))
                        code = 1
                res = {}
                for line in buf.getvalue().splitlines():
                    if line.startswith("CAPRI-RESULT "):
                        res = json.loads(line[len("CAPRI-RESULT "):])
                    elif line.startswith("CAPRI "):
                        self.log("  " + line[6:])
                return code, res
            if args[0] == "import":
                z = os.path.join(server, os.path.basename(args[args.index("--zip") + 1]))
                got = hashlib.sha256(open(z, "rb").read()).hexdigest()
                imported.update(zip=z, sha=got, version=args[args.index("--version") + 1])
                self.log(f"  (the stand-in machine took {os.path.basename(z)}, sha256 {got[:16]}...: nothing sent)")
                return 0, {"changed": True}
            return 1, {"failed": "not in the rehearsal"}

    ck.Machine = Stand
    ck.HERE = HERE          # the builds, the record and the compiler's sandboxes stay in this test folder

    class A:
        pass
    a = A()
    a.role, a.roles, a.hook, a.force, a.rebuild, a.sha, a.version, a.game = role, "", "auto", False, False, "", "", ""
    a.host, a.key_from = "rehearsal", "rehearsal"
    log = ck.Log(os.path.join(HERE, f"capri-publish-{role}-rehearsal-{time.strftime('%Y%m%d-%H%M%S')}.log"))
    log(f"REHEARSAL of publish --role {role}: the live package is {os.path.basename(live)}; the machine is a folder here")
    try:
        rc = ck.cmd_publish(a, log)
    except (ck.Failed, ck.W.BuildError) as e:
        log(f"!! {e}")
        rc = 1
    finally:
        # the stand-in machine's copy of the address: not kept
        for f in ("brain.url", "voice.url"):
            try:
                os.remove(os.path.join(server, f))
            except OSError:
                pass
    log(f"rehearsal exit {rc}; the build the stand-in machine took: {json.dumps({k: (os.path.basename(v) if k == 'zip' else v) for k, v in imported.items()})}")
    log(f"the full log: {log.path}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
