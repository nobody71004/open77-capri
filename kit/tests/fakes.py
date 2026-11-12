"""A stand-in for the game servers' machine, for the kit's tests: two Open77 server folders (staging, production)
with their server.jsonc, hosted mod store, server.log and package-manifest.json; the commands capri_server.py
calls (nginx, curl, systemctl, ss, journalctl, ollama) as small scripts on PATH; and each server's HTTP side (the
mod manifest players get, the blobs, the query status) served from 127.0.0.1 as the server would after its last
start (restart() re-reads server.jsonc, as a real restart does)."""
from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import stat
import tempfile
import textwrap
import threading
import zipfile

SECRET = "capri-brain-" + "0123456789abcdef" * 3
HOST = "xyberrp.duckdns.org"
URL = f"https://{HOST}/{SECRET}/v1"
CAPRI_ID = "capri-personality-construct"

STORAGE_REDS = textwrap.dedent('''\
    // Capri: Personality Construct - settings and conversation memory on disk.
    module Capri

    import Codeware.*
    import RedData.Json.*
    import RedFileSystem.*

    public class CapriSettingsDTO {
        public let player2Key: String;
        public let provider: String;       // who thinks for her
        public let openrouterKey: String;
        public let openrouterModel: String;
        public let geminiKey: String;
        public let geminiModel: String;
        public let openaiKey: String;
        public let openaiModel: String;
        public let localUrl: String;       // Ollama, LM Studio...: no key
        public let localModel: String;     // "" until the player picks one
        public let customUrl: String;
        public let customKey: String;
        public let customModel: String;
    }

    public class CapriStorage extends ScriptableService {
        private let m_storage: ref<FileSystemStorage>;
        public let settings: ref<CapriSettingsDTO>;

        private cb func OnInitialize() {
            this.m_storage = FileSystem.GetStorage("CapriConstruct");
            this.settings = this.LoadSettings();
        }

        public func WriteFile(fileName: String, text: String) -> Bool {
            if !IsDefined(this.m_storage) {
                return false;
            }
            let file = this.m_storage.GetFile(fileName);
            return IsDefined(file) && file.WriteText(text);
        }

        private func LoadSettings() -> ref<CapriSettingsDTO> {
            let s = new CapriSettingsDTO();
            s.provider = "player2";
            if StrLen(s.localUrl) == 0 {
                s.localUrl = "http://127.0.0.1:11434/v1";
            }
            return s;
        }

        public func SaveSettings() -> Void {
            FTLog("[Capri] saved");
        }
    }
    ''')


def package(storage=STORAGE_REDS, extra=None, crlf=False, gate="mass-override-staging") -> bytes:
    """A Capri launcher package like the live ones (deterministic)."""
    text = storage.replace("\n", "\r\n") if crlf else storage
    files = {
        "archive/pc/mod/CapriPersonalityConstruct.archive": b"ARCHIVE" * 1000,
        "red4ext/plugins/CapriPersonalityConstruct/CapriPersonalityConstruct.dll": b"MZ" + b"\0" * 500,
        "red4ext/plugins/CapriPersonalityConstruct/CapriVoz/CapriVoz.ps1": b"# voice\n",
        "bin/x64/plugins/cyber_engine_tweaks/mods/CapriVozReady/init.lua": b"-- heartbeat\n",
        "r6/scripts/CapriPersonalityConstruct/Capri.Storage.reds": text.encode("utf-8"),
        "r6/scripts/CapriPersonalityConstruct/Capri.System.reds": b"module Capri\npublic class CapriSystem {}\n",
        "r6/scripts/CapriPersonalityConstruct/Codeware/Codeware.reds": b"module Codeware\n",
        "r6/scripts/Open77/Open77MassOverride.reds": f"// gate https://{HOST}/{gate}/\n".encode(),
    }
    files.update(extra or {})
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[name])
    return out.getvalue()


SERVER_JSONC = '''{
  // XyberRP%(label)s
  "identity": { "name": "XyberRP%(label)s" },
  "network": { "port": %(port)d, "publicEndpoint": "example.invalid:%(port)d" },
  /* required mods: the launcher installs them */
  "requiredMods": {
    "enabled": true,
    "unsecured": true,
    "packages": [
      { "id": "codeware", "version": "1.21.0", "displayName": "Codeware", "sha256": "%(other)s", "sizeBytes": 10, "source": "hosted" },
      {
        "id": "capri-personality-construct",
        "version": "%(version)s",
        "displayName": "Capri - AI Companion with Voice (LLM)",
        "sha256": "%(sha)s",
        "sizeBytes": %(size)d,
        "source": "hosted"
      },
      { "id": "redhttpclient", "version": "0.5.0", "displayName": "RedHttpClient", "sha256": "%(other)s", "sizeBytes": 10, "source": "hosted" },
    ]
  },
  "resources": { "download": { "enabled": true } }
}
'''

NGINX_CONF = f'''# configuration file /etc/nginx/nginx.conf:
http {{
    access_log /var/log/nginx/access.log;
}}
# configuration file /etc/nginx/sites-enabled/xyberrp:
server {{
    listen 80;
    server_name {HOST};
    return 301 https://$host$request_uri;
}}
server {{
    listen 443 ssl;
    server_name {HOST};
    ssl_certificate /etc/letsencrypt/live/{HOST}/fullchain.pem;
    location /mass-override/ {{
        proxy_pass http://127.0.0.1:11901/;
    }}
    location /{SECRET}/ {{
        proxy_pass http://127.0.0.1:8890/;
        proxy_read_timeout 300s;
    }}
}}
'''


def _exe(path, body):
    with open(path, "w") as f:
        f.write("#!/usr/bin/env python3\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class Handler(http.server.BaseHTTPRequestHandler):
    machine = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        port = self.server.server_address[1]
        role = self.machine.by_port.get(port)
        st = self.machine.served.get(role)
        if st is None:
            self.send_error(404)
            return
        if self.path == "/mods/v1/manifest":
            body = json.dumps({"enabled": True, "unsecured": True, "digest": "x" * 64,
                               "mods": [{"id": CAPRI_ID, "version": st["version"], "sha256": st["sha"],
                                         "sizeBytes": st["size"]}]}).encode()
        elif self.path.startswith("/mods/v1/blobs/"):
            sha = self.path.rsplit("/", 1)[1]
            p = os.path.join(self.machine.root(role), ".open77", "mods", sha + ".blob")
            if not os.path.isfile(p):
                self.send_error(404)
                return
            body = open(p, "rb").read()
        elif self.path == "/query/v1/status":
            body = json.dumps({"status": "online", "numplayers": len(self.machine.online.get(role, [])),
                               "name": role}).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakeMachine:
    def __init__(self, ports=(23840, 23778), version="1.16.15"):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        self.servers_root = os.path.join(self.base, "opt")
        self.state = os.path.join(self.base, "state")
        self.bin = os.path.join(self.base, "bin")
        os.makedirs(self.bin)
        self.ports = {"staging": ports[0], "production": ports[1]}
        self.by_port = {ports[0] + 1: "staging", ports[1] + 1: "production"}
        self.online = {"staging": [], "production": []}
        self.served = {}
        self.check_config_exit = 0
        self.packages = {}
        for role, name, label, gate in (("staging", "open77-xbuniverse-staging", " Staging", "mass-override-staging"),
                                        ("production", "open77-xbuniverse", "", "mass-override")):
            root = os.path.join(self.servers_root, name)
            os.makedirs(os.path.join(root, ".open77", "mods"))
            data = package(gate=gate)
            self.packages[role] = data
            sha = hashlib.sha256(data).hexdigest()
            with open(os.path.join(root, ".open77", "mods", sha + ".blob"), "wb") as f:
                f.write(data)
            json.dump({"id": CAPRI_ID, "displayName": "Capri - AI Companion with Voice (LLM)", "capability": "executable"},
                      open(os.path.join(root, ".open77", "mods", sha + ".json"), "w"))
            with open(os.path.join(root, "server.jsonc"), "w") as f:
                f.write(SERVER_JSONC % {"label": label, "port": self.ports[role], "version": version, "sha": sha,
                                        "size": len(data), "other": "a" * 64})
            json.dump({"version": "2.50.0+op77.223"}, open(os.path.join(root, "package-manifest.json"), "w"))
            self.write_log(role)
            _exe(os.path.join(root, "Open77.Server"),
                 "import os, sys\nsys.exit(int(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "
                 "'check-config-exit')).read()) if '--check-config' in sys.argv else 0)\n")
            open(os.path.join(root, "check-config-exit"), "w").write("0")
            self.restart(role)
        os.makedirs(os.path.join(self.base, "log"))
        self.access_log = os.path.join(self.base, "log", "access.log")
        with open(self.access_log, "w") as f:
            f.write(f'203.0.113.7 - - [12/Nov/2026:04:30:00 +0000] "POST /{SECRET}/v1/chat/completions HTTP/1.1" 200 512 "-" "RedHttpClient"\n')
            f.write(f'198.51.100.9 - - [12/Nov/2026:04:31:00 +0000] "GET /{SECRET}/v1/models HTTP/1.1" 200 300 "-" "curl"\n')
            f.write('198.51.100.9 - - [12/Nov/2026:04:32:00 +0000] "GET / HTTP/1.1" 404 10 "-" "curl"\n')
        conf = NGINX_CONF.replace("/var/log/nginx/access.log", self.access_log)
        main, _, site = conf.partition("# configuration file /etc/nginx/sites-enabled/xyberrp:\n")
        etc = os.path.join(self.base, "etc", "nginx")
        os.makedirs(os.path.join(etc, "sites-available"))
        os.makedirs(os.path.join(etc, "sites-enabled"))
        self.site_real = os.path.join(etc, "sites-available", "xyberrp")
        self.site = os.path.join(etc, "sites-enabled", "xyberrp")
        open(self.site_real, "w").write(site)
        os.symlink(self.site_real, self.site)
        open(os.path.join(self.base, "nginx.conf"), "w").write(main.replace("# configuration file /etc/nginx/nginx.conf:\n", ""))
        self.brain_ok = True
        open(os.path.join(self.base, "brain-ok"), "w").write("1")
        self._fake_commands()
        self.servers = []
        for port in self.by_port:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), type("H", (Handler,), {"machine": self}))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.servers.append(srv)

    def root(self, role):
        return os.path.join(self.servers_root, {"staging": "open77-xbuniverse-staging",
                                                "production": "open77-xbuniverse"}[role])

    def write_log(self, role):
        lines = ["2026-11-12 03:34:44 [INF] Server configuration: x",
                 "2026-11-12 03:35:37 [INF] Required mods: 3 declared, digest=abc, enabled=True, unsecured=True.",
                 f"2026-11-12 03:35:37 [INF] XyberRP listening on UDP 0.0.0.0:{self.ports[role]} (players=1024)"]
        for i, c in enumerate(self.online[role]):
            lines.append(f"2026-11-12 03:40:0{i} [INF] Connection {c} opened from 203.0.113.{i + 1}:5000")
        lines.append("2026-11-12 03:41:00 [INF] Connection 99 opened from 203.0.113.50:5000")
        lines.append("2026-11-12 03:42:00 [INF] Connection 99 closed")
        open(os.path.join(self.root(role), "server.log"), "w").write("\n".join(lines) + "\n")

    def set_online(self, role, conns):
        self.online[role] = list(conns)
        self.write_log(role)

    def restart(self, role):
        """What the server hands out from its next start: server.jsonc's Capri entry."""
        import re
        text = open(os.path.join(self.root(role), "server.jsonc")).read()
        m = re.search(r'"id": "capri-personality-construct",\s*"version": "([^"]+)",.*?"sha256": "([0-9a-f]{64})",\s*'
                      r'"sizeBytes": (\d+)', text, re.S)
        self.served[role] = {"version": m.group(1), "sha": m.group(2), "size": int(m.group(3))}

    def entry(self, role):
        import re
        text = open(os.path.join(self.root(role), "server.jsonc")).read()
        m = re.search(r'"id": "capri-personality-construct",\s*"version": "([^"]+)",.*?"sha256": "([0-9a-f]{64})",\s*'
                      r'"sizeBytes": (\d+)', text, re.S)
        return {"version": m.group(1), "sha256": m.group(2), "sizeBytes": int(m.group(3))}

    def _fake_commands(self):
        b = self.base
        _exe(os.path.join(self.bin, "nginx"), f'''import os, sys
site = open({self.site!r}).read()
if sys.argv[1:] == ["-T"]:
    print("# configuration file /etc/nginx/nginx.conf:")
    print(open({os.path.join(b, 'nginx.conf')!r}).read())
    print("# configuration file {self.site}:")
    print(site)
    sys.exit(0)
if sys.argv[1:] == ["-t"]:
    bad = os.path.exists({os.path.join(b, 'nginx-t-fails')!r}) or site.count("{{") != site.count("}}")
    print("nginx: configuration file test " + ("failed" if bad else "is successful"))
    sys.exit(1 if bad else 0)
sys.exit(0)
''')
        _exe(os.path.join(self.bin, "curl"), f'''import json, sys
args = sys.argv[1:]
url = args[-1]
ok = open({os.path.join(b, 'brain-ok')!r}).read().strip() == "1"
served = "location /{SECRET}/" in open({self.site!r}).read()
if "--resolve" in args and url == "https://{HOST}/{SECRET}/v1/models" and ok and served:
    print(json.dumps({{"object": "list", "data": [{{"id": "capri-brain"}}, {{"id": "qwen2.5:7b"}}]}}))
    print("200", end="")
else:
    print("not found")
    print("404", end="")
''')
        _exe(os.path.join(self.bin, "systemctl"), '''import sys
a = sys.argv[1:]
if a and a[0] == "is-active":
    print("active")
elif a and a[0] == "show":
    props = [p for i, p in enumerate(a) if a[i - 1] == "-p"]
    if "--value" in a:
        print("")
    else:
        for p in ",".join(props).split(","):
            if p == "ActiveState":
                print("ActiveState=active")
            elif p == "Environment":
                print("Environment=CAPRI_BRAIN_MODEL=qwen2.5:7b CAPRI_BRAIN_API_KEY=supersecretvalue")
            else:
                print(p + "=")
sys.exit(0)
''')
        _exe(os.path.join(self.bin, "ss"), 'print("LISTEN 0 511 127.0.0.1:8890 0.0.0.0:* users:((\\"node\\",pid=1,fd=20))")\n')
        _exe(os.path.join(self.bin, "journalctl"), f'print("2026-11-12T04:30:00 node[1]: [capri-brain] chat messages=8/21 chars=6000 max_tokens=260 status=200 ms=33000")\nprint("2026-11-12T04:30:01 node[1]: path /{SECRET}/ from 203.0.113.7")\n')
        _exe(os.path.join(self.bin, "ollama"), '''import sys
if sys.argv[1:] == ["list"]:
    print("NAME ID SIZE MODIFIED")
    print("qwen2.5:7b abc 4.7 GB 2 days ago")
elif sys.argv[1:] == ["ps"]:
    print("NAME ID SIZE PROCESSOR CONTEXT UNTIL")
    print("qwen2.5:7b abc 5.0 GB 100% CPU 4096 29 minutes from now")
''')

    def env(self):
        e = dict(os.environ)
        e.update(SERVERS_ROOT=self.servers_root, CAPRI_KIT_STATE=self.state, PATH=self.bin + os.pathsep + e["PATH"])
        return e

    def close(self):
        for s in self.servers:
            s.shutdown()
            s.server_close()
        self.tmp.cleanup()
