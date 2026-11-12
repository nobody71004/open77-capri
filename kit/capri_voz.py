"""Capri Voz (the helper that speaks for Capri on a player's PC) speaking with her voice from the game server.

A player's Capri Voz says her lines with her own voice only when that PC installed her local engine ("Install
local voice": Pocket TTS and her voice states, about 900 MB, run on the PC's processor); every other PC fell back
to a borrowed Windows voice (Linux: no voice at all).  The XyberRP server now runs the same engine with the same
voice states (remote/capri_voice_server.py), and this module puts three things into the Capri package a server
hands out:

  red4ext/plugins/CapriPersonalityConstruct/CapriVoz/servidor.json        where that server's voice answers
  red4ext/plugins/CapriPersonalityConstruct/CapriVoz/CapriVoz.ps1         Windows: "auto" = her local engine when
                                                                          installed, else the server's voice
                                                                          (servidor.json), else Windows'
  red4ext/plugins/CapriPersonalityConstruct/CapriVoz/linux/capri_voz_linux.py   the same for Linux (Proton)

The two programs are Capri's own, changed by exact, anchored edits (each anchor must be there exactly once, or
nothing is built) that undo exactly: a package that already carries them (the server's package after the first
publish) is taken back to Capri's own file first and edited again, so a build is the same bytes whichever it
started from.  A player's own choice of voice (ElevenLabs, OpenAI, Windows...) is left alone: only "auto" -- the
default -- changes, and only on a PC without her local engine.

Pure Python, no I/O.
"""
from __future__ import annotations

import hashlib
import json
import re

VOZ_DIR = "red4ext/plugins/CapriPersonalityConstruct/CapriVoz"
PS1 = VOZ_DIR + "/CapriVoz.ps1"
LINUX = VOZ_DIR + "/linux/capri_voz_linux.py"
SERVIDOR = VOZ_DIR + "/servidor.json"
VOICES_DIR = VOZ_DIR + "/voces"
MARK = "XyberRP server voice"
VOICE_URL_RX = re.compile(r"^https://([a-z0-9.-]{3,253})/capri-voice-[0-9a-f]{12,64}/v1$")
SECRET_RX = re.compile(r"capri-voice-[0-9a-fA-F]{12,}")   # its path: capri-voice-<24 hex>


class VozError(Exception):
    pass


def mask(text: str) -> str:
    return SECRET_RX.sub("capri-voice-<secret>", str(text))


# ------------------------------------------------------------------------------------------------ CapriVoz.ps1
PS1_FUNCTIONS = r'''# XyberRP server voice ----------------------------------------------------------------------------------------
# servidor.json, next to this file, comes in the Capri package of a server that runs her voice: the same engine
# and voice files as "Install local voice" (Pocket TTS, voces\capri_<language>.safetensors), run on the server.
# With "auto" (the default), a PC without her local engine speaks with it instead of a borrowed Windows voice;
# her local engine still comes first when it's installed, and Windows' voice is what's left when neither answers.
$script:ServerVoiceFile = Join-Path $PSScriptRoot "servidor.json"
$script:ServerVoice = $null
$script:ServerVoiceStamp = [DateTime]::MinValue
$script:ServerVoiceDownUntil = [DateTime]::MinValue
$script:ServerVoiceLines = 0
$script:LastProvider = ""

# servidor.json read again whenever it changes: {"url", "mundo", ...}, or $null.
function Server-Voice {
    if (-not (Test-Path -LiteralPath $script:ServerVoiceFile)) {
        if ($script:ServerVoice) { Say-Info "servidor.json is gone: her server voice is off" "Yellow" }
        $script:ServerVoice = $null
        $script:ServerVoiceStamp = [DateTime]::MinValue
        return $null
    }
    try {
        $stamp = (Get-Item -LiteralPath $script:ServerVoiceFile).LastWriteTimeUtc
        if ($stamp -ne $script:ServerVoiceStamp) {
            $script:ServerVoiceStamp = $stamp
            $s = [IO.File]::ReadAllText($script:ServerVoiceFile, [Text.Encoding]::UTF8) | ConvertFrom-Json
            $url = "$($s.url)"
            if ($url -match '^https://[A-Za-z0-9.-]+(:\d+)?/' -or $url -match '^http://(127\.0\.0\.1|localhost)(:\d+)?/') {
                $script:ServerVoice = $s
                Say-Info (L "Her voice from the server: $(([Uri]$url).Host) ($($s.mundo), package $($s.paquete))" "Su voz desde el servidor: $(([Uri]$url).Host) ($($s.mundo), paquete $($s.paquete))") "Cyan"
            } else {
                $script:ServerVoice = $null
                Say-Info "servidor.json: not an https address, her server voice is off" "Yellow"
            }
        }
    } catch {
        $script:ServerVoice = $null
        Say-Info "servidor.json can't be read: $($_.Exception.Message)" "Yellow"
    }
    return $script:ServerVoice
}

# What "auto" means right now: her local engine, else the server's voice (unless it just failed), else Windows.
function Auto-Provider {
    if (Motor-Python) { return "pocket" }
    if ((Server-Voice) -and (Get-Date) -ge $script:ServerVoiceDownUntil) { return "server" }
    return "windows"
}

# The voice chosen in config.json, "auto" resolved ("servidor" is "server").
function Chosen-Provider {
    $p = "$($script:Cfg.proveedor)".ToLower()
    if ($p -eq "auto" -or -not $p) { return (Auto-Provider) }
    if ($p -eq "servidor") { return "server" }
    return $p
}

# What the game is told (heartbeat): "server" while her server voice speaks for "auto" -- the game then
# doesn't ask the player to install a local voice.
function Shown-Provider {
    $p = "$($script:Cfg.proveedor)".ToLower()
    if (($p -eq "auto" -or -not $p) -and (Chosen-Provider) -eq "server") { return "server" }
    return "$($script:Cfg.proveedor)"
}

# The voice that said the last line, for its answer to the game.
function Said-Provider {
    $p = "$($script:Cfg.proveedor)".ToLower()
    if (($p -eq "auto" -or -not $p) -and $script:LastProvider) { return $script:LastProvider }
    return "$($script:Cfg.proveedor)"
}

# Her voice from the server: the line goes up (HTTPS), a WAV comes back.
function Speak-Server([string]$text, [string]$file, [string]$language) {
    $ProgressPreference = "SilentlyContinue"
    $s = Server-Voice
    if (-not $s) { throw (L "this server's Capri package has no voice server" "el paquete de Capri de este servidor no trae servidor de voz") }
    $url = ("$($s.url)".TrimEnd("/")) + "/audio/speech"
    $hostName = ([Uri]$url).Host
    $body = @{ model = "capri-voice"; input = $text; voice = "capri"; language = $language; response_format = "wav" }
    $limit = (Voice-Limit $text) + 10
    $t0 = Get-Date
    try {
        $r = Invoke-WebRequest -Uri $url -Method Post -UseBasicParsing -OutFile $file -PassThru -TimeoutSec $limit `
            -Headers @{ "Accept" = "audio/wav" } -ContentType "application/json; charset=utf-8" -Body (Json-Bytes $body)
    } catch {
        $message = Web-Error $_
        if ($message -match "timed out|tiempo de espera|operation has timed out") { $message = (L "took longer than $limit s" "tardo mas de $limit s") }
        $script:ServerVoiceDownUntil = (Get-Date).AddSeconds(60)
        throw ((L "Server voice" "Voz del servidor") + " ($hostName): $message")
    }
    $bytes = [IO.File]::ReadAllBytes($file)
    if ($bytes.Length -lt 64 -or [Text.Encoding]::ASCII.GetString($bytes, 0, 4) -ne "RIFF") {
        $script:ServerVoiceDownUntil = (Get-Date).AddSeconds(60)
        throw ((L "Server voice" "Voz del servidor") + " ($hostName): " + (L "the answer is not audio" "la respuesta no es audio"))
    }
    $script:ServerVoiceDownUntil = [DateTime]::MinValue
    $script:ServerVoiceLines += 1
    $voice = "$($r.Headers['X-Capri-Voice'])"
    $took = ((Get-Date) - $t0).TotalSeconds
    if ($script:ServerVoiceLines -eq 1 -or $voice -ne "capri") {
        Say-Info ((L "Server voice ({0}): {1} s of audio in {2:N1} s, voice {3}, {4}" "Voz del servidor ({0}): {1} s de audio en {2:N1} s, voz {3}, {4}") -f $hostName, "$($r.Headers['X-Capri-Seconds'])", $took, $voice, $language) "Cyan"
    }
    return "wav"
}

'''

PS1_EDITS = [
    # (what, old, new) -- new contains old, so the edit undoes exactly
    ("version", "$Version = 17\n",
     "$Version = 18\n# XyberRP server voice: 18 = Capri Voz 17 with her voice from the game server (servidor.json)\n"),
    ("file log", '''function Say-Info([string]$text, [string]$color = "Gray") {
    $script:Log.Add(("{0:HH:mm:ss}  {1}" -f (Get-Date), $text))
''', '''function Say-Info([string]$text, [string]$color = "Gray") {
    $script:Log.Add(("{0:HH:mm:ss}  {1}" -f (Get-Date), $text))
    # XyberRP server voice: every line also in cache\\capri_voz.log (kept under 1 MB), to look at afterwards
    try {
        $logFile = Join-Path $Cache "capri_voz.log"
        if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -gt 1MB) { Move-Item -LiteralPath $logFile -Destination "$logFile.1" -Force }
        [IO.File]::AppendAllText($logFile, ("{0:yyyy-MM-dd HH:mm:ss}  {1}`r`n" -f (Get-Date), $text), (New-Object Text.UTF8Encoding $false))
    } catch {}
'''),
    ("functions", "# Her ears: V's microphone through Windows' MCI, to text with whoever V chose ----------------------\n",
     PS1_FUNCTIONS + "# Her ears: V's microphone through Windows' MCI, to text with whoever V chose ----------------------\n"),
    ("speak provider", '''    if (-not $language) { $language = "es" }
    $provider = "$($script:Cfg.proveedor)".ToLower()
    if ($provider -eq "auto" -or -not $provider) { $provider = if (Motor-Python) { "pocket" } else { "windows" } }
''', '''    if (-not $language) { $language = "es" }
    # XyberRP server voice: "auto" is her local engine, else her voice from the server, else Windows'
    $provider = Chosen-Provider
    $script:LastProvider = $provider
'''),
    ("speak switch", '''            "pocket" { $kind = Speak-Pocket $plain $file $language }
''', '''            "pocket" { $kind = Speak-Pocket $plain $file $language }
            "server" { $kind = Speak-Server $plain $file $language }
'''),
    ("fallback pocket", '''                $kind = Speak-Pocket $plain $file $language
                if ($plain -ne $text) { $script:LastLaugh = "1" }
                Say-Info (L "Voice failed ($($script:LastError)): saying it with her local voice."''',
     '''                $kind = Speak-Pocket $plain $file $language
                $script:LastProvider = "pocket"
                if ($plain -ne $text) { $script:LastLaugh = "1" }
                Say-Info (L "Voice failed ($($script:LastError)): saying it with her local voice."'''),
    ("fallback server", '''        if (-not $kind) {
            Say-Info (L "Voice failed ($($script:LastError)): saying it with the Windows voice."''',
     '''        # XyberRP server voice: before Windows', her voice from the server
        if (-not $kind -and $provider -ne "server" -and (Server-Voice) -and (Get-Date) -ge $script:ServerVoiceDownUntil) {
            try {
                $kind = Speak-Server $plain $file $language
                $script:LastProvider = "server"
                if ($plain -ne $text) { $script:LastLaugh = "1" }
                Say-Info (L "Voice failed ($($script:LastError)): saying it with her voice from the server." "Fallo la voz ($($script:LastError)): la digo con su voz del servidor.") "Yellow"
            } catch { $kind = $null }
        }
        if (-not $kind) {
            $script:LastProvider = "windows"
            Say-Info (L "Voice failed ($($script:LastError)): saying it with the Windows voice."'''),
    ("languages", '''function Voice-Languages {
    $provider = "$($script:Cfg.proveedor)".ToLower()
    if ($provider -eq "auto" -or -not $provider) { $provider = if (Motor-Python) { "pocket" } else { "windows" } }
''', '''function Voice-Languages {
    # XyberRP server voice: her voice from the server speaks the languages her voice files do, like her local one
    $provider = Chosen-Provider
    if ($provider -eq "server") { $provider = "pocket" }
'''),
    ("beat", '''        $script:BeatState.proveedor = "$($script:Cfg.proveedor)"
''', '''        $script:BeatState.proveedor = (Shown-Provider)
'''),
    ("answer", '''seconds = (Seconds-Json $seconds); proveedor = "$($script:Cfg.proveedor)"; risa''',
     '''seconds = (Seconds-Json $seconds); proveedor = (Said-Provider); risa'''),
    ("beat start", '''    proveedor = "$($script:Cfg.proveedor)"; motor = (Motor-State); idiomas = (Voice-Languages) })
''', '''    proveedor = (Shown-Provider); motor = (Motor-State); idiomas = (Voice-Languages) })
if (Server-Voice) { Say-Info (L "Her voice: her local engine when installed, else this server's voice, else Windows'." "Su voz: su motor local si esta instalado, si no la voz de este servidor, si no la de Windows.") "Cyan" }
'''),
]

# ------------------------------------------------------------------------------------------------ capri_voz_linux.py
LINUX_METHODS = '''    # XyberRP server voice ---------------------------------------------------------------------
    # servidor.json, next to Capri Voz, comes in the Capri package of a server that runs her voice: the
    # same engine and voice files as "Install local voice", run on the server. With "auto", a PC without
    # her local engine speaks with it (Linux has no Windows voice to borrow).
    def server_voice(self):
        path = os.path.join(VOZ, "servidor.json")
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            if self.server_voice_cache[1]:
                self.say("servidor.json is gone: her server voice is off")
            self.server_voice_cache = (None, None)
            return None
        if self.server_voice_cache[0] != stamp:
            s = None
            try:
                with open(path, encoding="utf-8-sig") as f:
                    s = json.load(f)
                url = str(s.get("url") or "")
                if re.match(r"^https://[A-Za-z0-9.-]+(:\\d+)?/", url) or re.match(r"^http://(127\\.0\\.0\\.1|localhost)(:\\d+)?/", url):
                    host = urllib.parse.urlparse(url).hostname
                    self.say(self.L("Her voice from the server: %s (%s, package %s)" % (host, s.get("mundo"), s.get("paquete")),
                                    "Su voz desde el servidor: %s (%s, paquete %s)" % (host, s.get("mundo"), s.get("paquete"))))
                else:
                    self.say("servidor.json: not an https address, her server voice is off")
                    s = None
            except (OSError, ValueError, AttributeError) as e:
                self.say("servidor.json can't be read: %s" % e)
                s = None
            self.server_voice_cache = (stamp, s)
        return self.server_voice_cache[1]

    def speak_server(self, text, path, language):
        s = self.server_voice()
        if not s:
            raise RuntimeError(self.L("this server's Capri package has no voice server",
                                      "el paquete de Capri de este servidor no trae servidor de voz"))
        url = str(s["url"]).rstrip("/") + "/audio/speech"
        host = urllib.parse.urlparse(url).hostname
        limit = self.voice_limit(text) + 10
        t0 = time.time()
        try:
            _, data = http(url, "POST", {"model": "capri-voice", "input": text, "voice": "capri", "language": language,
                                         "response_format": "wav"}, {"Accept": "audio/wav"}, limit)
        except HttpError as e:
            self.server_voice_down_until = time.time() + 60
            message = str(e)
            if "timed out" in message:
                message = self.L("took longer than %d s" % limit, "tardo mas de %d s" % limit)
            raise RuntimeError(self.L("Server voice", "Voz del servidor") + " (%s): %s" % (host, message))
        if len(data) < 64 or data[:4] != b"RIFF":
            self.server_voice_down_until = time.time() + 60
            raise RuntimeError(self.L("Server voice", "Voz del servidor") + " (%s): %s" % (
                host, self.L("the answer is not audio", "la respuesta no es audio")))
        with open(path, "wb") as f:
            f.write(data)
        self.server_voice_down_until = 0.0
        self.server_voice_lines += 1
        if self.server_voice_lines == 1:
            self.say(self.L("Server voice (%s): first line in %.1f s, %s" % (host, time.time() - t0, language),
                            "Voz del servidor (%s): primera frase en %.1f s, %s" % (host, time.time() - t0, language)))
        return "wav"

'''

LINUX_EDITS = [
    ("version", "VERSION = 17\n", "VERSION = 18  # XyberRP server voice: Capri Voz 17 with her voice from the game server\n"),
    ("init", '''        self.beat = {"proveedor": "pocket", "motor": "no instalada", "idiomas": "en,es"}
''', '''        self.beat = {"proveedor": "pocket", "motor": "no instalada", "idiomas": "en,es"}
        # XyberRP server voice
        self.server_voice_cache = (None, None)
        self.server_voice_down_until = 0.0
        self.server_voice_lines = 0
'''),
    ("provider", '''    def provider(self):
        """The voice in use. On Linux there are no Windows voices: "auto" (and "windows") is her own."""
        p = str(self.cfg.get("proveedor") or "").lower()
        return "pocket" if p in ("", "auto", "windows") else p
''', '''    def provider(self):
        """The voice in use. On Linux there are no Windows voices: "auto" (and "windows") is her own."""
        p = str(self.cfg.get("proveedor") or "").lower()
        # XyberRP server voice: without her local engine, "auto" is her voice from the server
        if p == "servidor":
            return "server"
        if p in ("", "auto", "windows") and not self.motor_ready() and self.server_voice() \\
                and time.time() >= self.server_voice_down_until:
            return "server"
        return "pocket" if p in ("", "auto", "windows") else p
'''),
    ("methods", "    def speak_elevenlabs(self, text, mood, path):\n", LINUX_METHODS + "    def speak_elevenlabs(self, text, mood, path):\n"),
    ("speak switch", '''            elif provider == "pocket":
                kind = self.speak_pocket(plain, path, language)
''', '''            elif provider == "pocket":
                kind = self.speak_pocket(plain, path, language)
            elif provider == "server":
                kind = self.speak_server(plain, path, language)
'''),
    ("fallback", '''            if provider == "pocket" or self.cfg.get("respaldo") is False or not self.motor_ready():
                raise
            self.last_error = str(e)
            if re.search("no contesto en|didn't answer in", self.last_error):
                self.slow_until = time.time() + 600
                self.slow_voice = provider
            kind = self.speak_pocket(plain, path, language)
            if plain != text:
                self.last_laugh = "1"
            self.say(self.L("Voice failed (%s): saying it with her local voice." % self.last_error,
                            "Fallo la voz (%s): la digo con su voz local." % self.last_error))
''', '''            # XyberRP server voice: her voice from the server when her local one can't
            server_ok = provider != "server" and self.server_voice() and time.time() >= self.server_voice_down_until
            if self.cfg.get("respaldo") is False or ((provider == "pocket" or not self.motor_ready()) and not server_ok):
                raise
            self.last_error = str(e)
            if re.search("no contesto en|didn't answer in", self.last_error):
                self.slow_until = time.time() + 600
                self.slow_voice = provider
            if provider != "pocket" and self.motor_ready():
                kind = self.speak_pocket(plain, path, language)
                said = self.L("her local voice", "su voz local")
            else:
                kind = self.speak_server(plain, path, language)
                said = self.L("her voice from the server", "su voz del servidor")
            if plain != text:
                self.last_laugh = "1"
            self.say(self.L("Voice failed (%s): saying it with %s." % (self.last_error, said),
                            "Fallo la voz (%s): la digo con %s." % (self.last_error, said)))
'''),
    ("languages", '''        langs = "*"
        if provider == "pocket":
''', '''        langs = "*"
        if provider in ("pocket", "server"):  # XyberRP server voice: the same voice files
'''),
]


def _apply(text: str, edits, label: str) -> str:
    for what, old, new in edits:
        n = text.count(old)
        if n != 1:
            raise VozError(f"{label}: the place for '{what}' is there {n} times (once expected): Capri Voz changed -- "
                           f"nothing built")
        text = text.replace(old, new)
    return text


def _undo(text: str, edits, label: str) -> str:
    for what, old, new in reversed(edits):
        if text.count(new) != 1:
            raise VozError(f"{label}: it carries the XyberRP server voice, but '{what}' is not as this kit writes it "
                           f"-- nothing built")
        text = text.replace(new, old)
    if MARK in text:
        raise VozError(f"{label}: XyberRP server voice edits this kit did not write -- nothing built")
    return text


def _patch(data: bytes, edits, label: str) -> tuple[bytes, bool]:
    """Capri's file with the edits (the BOM, if any, kept; line ends as they were). (bytes, was it patched)."""
    bom = data.startswith(b"\xef\xbb\xbf")
    try:
        text = data[3 if bom else 0:].decode("utf-8")
    except UnicodeDecodeError as e:
        raise VozError(f"{label} is not UTF-8: {e}") from e
    crlf = "\r\n" in text
    plain = text.replace("\r\n", "\n")
    had = MARK in plain
    if had:
        plain = _undo(plain, edits, label)
    out = _apply(plain, edits, label)
    if _undo(out, edits, label) != plain:
        raise VozError(f"{label}: the edits do not undo exactly -- nothing built")
    if crlf:
        out = out.replace("\n", "\r\n")
    return (b"\xef\xbb\xbf" if bom else b"") + out.encode("utf-8"), had


def patch_ps1(data: bytes) -> tuple[bytes, bool]:
    return _patch(data, PS1_EDITS, "CapriVoz.ps1")


def patch_linux(data: bytes) -> tuple[bytes, bool]:
    return _patch(data, LINUX_EDITS, "capri_voz_linux.py")


def original(data: bytes, which: str) -> bytes:
    """Capri's own file again from one this module edited (or the file itself if it is not edited)."""
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data[3 if bom else 0:].decode("utf-8")
    crlf = "\r\n" in text
    plain = text.replace("\r\n", "\n")
    if MARK in plain:
        plain = _undo(plain, PS1_EDITS if which == "ps1" else LINUX_EDITS, which)
    if crlf:
        plain = plain.replace("\n", "\r\n")
    return (b"\xef\xbb\xbf" if bom else b"") + plain.encode("utf-8")


def languages(entries: dict) -> str:
    """The languages her voice files in the package speak ("en,es"), as Capri Voz names them."""
    names = {"english": "en", "spanish": "es", "french": "fr", "german": "de", "italian": "it", "portuguese": "pt",
             "dutch": "nl"}
    have = sorted({names[m.group(1)] for n in entries
                   for m in [re.match(re.escape(VOICES_DIR) + r"/capri_(\w+)\.safetensors$", n)] if m and m.group(1) in names})
    return ",".join(have)


def servidor_json(url: str, world: str, version: str, langs: str) -> bytes:
    """What servidor.json says: where this server's voice answers (its address is a capability, like the
    brain's: it travels to every player in the package and is never printed)."""
    if not VOICE_URL_RX.match(url or ""):
        raise VozError("the server voice's address is not https://HOST/capri-voice-<secret>/v1")
    doc = {
        "_ayuda": ("Put in by the XyberRP server's Capri package: with the voice on \"auto\", Capri Voz speaks with "
                   "her voice from this server when her local voice is not installed. / Lo pone el paquete de Capri "
                   "del servidor XyberRP: con la voz en \"auto\", Capri Voz habla con su voz de este servidor cuando "
                   "su voz local no esta instalada."),
        "url": url,
        "voz": "capri",
        "modelo": "capri-voice",
        "mundo": world,
        "paquete": version,
        "idiomas": langs,
    }
    return (json.dumps(doc, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def servidor_values(data: bytes) -> dict:
    try:
        doc = json.loads(data.decode("utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (UnicodeDecodeError, ValueError):
        return {}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
