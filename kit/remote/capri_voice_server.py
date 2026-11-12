#!/usr/bin/env python3
"""Capri's own voice for every XyberRP player, served from the game servers' machine.

A player's Capri Voz speaks with her own voice only when that PC installed her local engine (capri_motor.py:
Pocket TTS on the CPU with her voice states, about 900 MB); every other PC fell back to a Windows voice.  This
is the same engine and the same voice states (voces/capri_<language>.safetensors from the Capri package, Pocket
TTS 4.0.1: the model revisions a player's local engine loads), run once on the server as a small HTTP service
behind nginx.  A player's Capri Voz without the local engine sends each line here and plays what comes back.

    capri_voice_server.py --voices DIR [--host 127.0.0.1] [--port 8891] [--threads N] [--preload en,es]
    capri_voice_server.py --selftest OUTDIR --voices DIR [--languages en,es] [--threads N]

Routes (nginx puts them under the voice's private path):
    GET  /health            {"ok", "version", "pocket_tts", "languages": {"en": {"voice": "capri"}}, counters...}
    GET  /v1/models         {"data": [{"id": "capri-voice"}]}
    POST /v1/audio/speech   {"input": TEXT, "language": "en"|"es"|..., "voice": "capri", "response_format": "wav"}
                            -> audio/wav, 24 kHz mono 16-bit; headers X-Capri-Voice (capri, or the catalog voice
                            used instead), X-Capri-Language, X-Capri-Seconds, X-Capri-Generated-Ms

One line is generated at a time (Pocket TTS is not thread-safe), on --threads cores; up to --queue lines wait,
each at most --wait seconds -- past that the answer is 503 at once, so the player's Capri Voz says the line with
its own fallback instead of hanging.  Every request is logged on one line (status, language, length, wait, time to
generate, seconds of audio, which voice) -- never the text, and the player's address only as a short hash.

The self-test loads every language there is a voice state for, says one line in each, writes the WAVs to OUTDIR
and prints one JSON line (exit 0 only when every language spoke with Capri's own voice).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import math
import os
import queue
import re
import signal
import struct
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0.0"
MODEL_ID = "capri-voice"
# Pocket's languages, by the two letters the game sends (capri_motor.py's own table).
LANGUAGES = {"en": "english", "es": "spanish", "fr": "french", "de": "german", "it": "italian",
             "pt": "portuguese", "nl": "dutch"}
# Without a voice state of hers for a language: a woman's voice from Pocket's catalog (capri_motor.py's own).
CATALOG = {"english": ["eve", "alba", "jane"], "spanish": ["lola", "eve"], "french": ["estelle", "eve"]}
SELFTEST_LINES = {
    "en": "Hello V. This is Capri, speaking from the server.",
    "es": "Hola V. Soy Capri, hablando desde el servidor.",
    "fr": "Bonjour V. C'est Capri, depuis le serveur.",
    "de": "Hallo V. Hier ist Capri, vom Server aus.",
    "it": "Ciao V. Sono Capri, dal server.",
    "pt": "Ola V. Sou a Capri, falando do servidor.",
    "nl": "Hallo V. Dit is Capri, vanaf de server.",
}

log = logging.getLogger("capri-voice")


def peer_tag(address: str) -> str:
    """A player's address as a short hash: enough to tell players apart in the log, nothing more."""
    return hashlib.sha256(("capri-voice:" + (address or "?")).encode("utf-8")).hexdigest()[:8]


def wav_bytes(pcm: bytes, rate: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def pcm_stats(pcm: bytes) -> tuple[float, int]:
    """(RMS, peak) of 16-bit mono PCM: a voice that came out silent shows here."""
    n = len(pcm) // 2
    if n == 0:
        return 0.0, 0
    samples = struct.unpack("<%dh" % n, pcm[: n * 2])
    peak = max(abs(s) for s in samples)
    return math.sqrt(sum(s * s for s in samples) / n), peak


def language_of(value) -> str:
    code = str(value or "en").strip().lower()[:2]
    return code if code in LANGUAGES else "en"


# ------------------------------------------------------------------------------------------------ the engine
class Engine:
    """Pocket TTS with her voice states, loaded once per language. Used from ONE thread only (the worker)."""

    def __init__(self, voices_dir: str, threads: int, quantize: bool = False):
        self.voices_dir = voices_dir
        self.threads = threads
        self.quantize = quantize
        self.models = {}
        self.voices = {}
        self.loaded = {}       # code -> {"voice", "warning", "load_s", "model"}
        self._torch = None
        self._np = None

    def _imports(self):
        if self._torch is None:
            import numpy as np  # noqa: PLC0415
            import torch  # noqa: PLC0415
            torch.set_num_threads(self.threads)
            try:
                torch.set_num_interop_threads(1)
            except RuntimeError:
                pass        # already set once in this process
            self._torch, self._np = torch, np
        return self._torch, self._np

    def has_state(self, code: str) -> bool:
        return os.path.isfile(os.path.join(self.voices_dir, f"capri_{LANGUAGES[code]}.safetensors"))

    def languages_with_state(self) -> list[str]:
        return [c for c in LANGUAGES if self.has_state(c)]

    def model_for(self, code: str):
        name = LANGUAGES[code]
        if name not in self.models:
            self._imports()
            from pocket_tts import TTSModel  # noqa: PLC0415
            t0 = time.time()
            self.models[name] = TTSModel.load_model(language=name, quantize=self.quantize) if self.quantize \
                else TTSModel.load_model(language=name)
            log.info("model %s loaded in %.1f s (sample rate %s)", name, time.time() - t0,
                     self.models[name].sample_rate)
        return name, self.models[name]

    def voice_for(self, code: str):
        """Her voice state for the language (the package's capri_<language>.safetensors), else a catalog voice."""
        name, model = self.model_for(code)
        if name in self.voices:
            return self.voices[name]
        saved = os.path.join(self.voices_dir, f"capri_{name}.safetensors")
        state, used, warning = None, "", ""
        if os.path.isfile(saved):
            try:
                state, used = model.get_state_for_audio_prompt(saved), "capri"
            except Exception as e:  # noqa: BLE001 -- said in the log and on /health, then a catalog voice
                warning = f"her voice state for {name} did not load: {e.__class__.__name__}: {e}"
        else:
            warning = f"no voice state of hers for {name}"
        if state is None:
            for pick in CATALOG.get(name, ["eve"]):
                try:
                    state, used = model.get_state_for_audio_prompt(pick), pick
                    break
                except Exception:  # noqa: BLE001
                    continue
        if state is None:
            raise RuntimeError(f"Pocket has no voice for {name}")
        if warning:
            log.warning("%s: %s; speaking with %r", code, warning, used)
        self.voices[name] = (state, used, warning)
        return self.voices[name]

    def load(self, code: str) -> dict:
        t0 = time.time()
        _, used, warning = self.voice_for(code)
        name = LANGUAGES[code]
        self.loaded[code] = {"voice": used, "warning": warning, "load_s": round(time.time() - t0, 1),
                             "model": name}
        return self.loaded[code]

    def speak(self, text: str, code: str) -> tuple[bytes, int, str, str]:
        """(16-bit mono PCM, sample rate, the voice used, a warning or '')."""
        torch, np = self._imports()
        name, model = self.model_for(code)
        state, used, warning = self.voice_for(code)
        if code not in self.loaded:
            self.loaded[code] = {"voice": used, "warning": warning, "load_s": None, "model": name}
        audio = model.generate_audio(state, text)
        samples = audio.detach().cpu().numpy().reshape(-1)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        return pcm, int(model.sample_rate), used, warning


# ------------------------------------------------------------------------------------------------ one at a time
class Job:
    def __init__(self, kind: str, text: str = "", code: str = "en"):
        self.kind, self.text, self.code = kind, text, code
        self.queued_at = time.time()
        self.started_at = None
        self.finished_at = None
        self.done = threading.Event()
        self.cancelled = False
        self.result = None
        self.error = None


class Worker(threading.Thread):
    def __init__(self, engine: Engine, depth: int):
        super().__init__(name="capri-voice-worker", daemon=True)
        self.engine = engine
        self.jobs: queue.Queue = queue.Queue(maxsize=depth)
        self.busy = False

    def submit(self, job: Job) -> bool:
        try:
            self.jobs.put_nowait(job)
            return True
        except queue.Full:
            return False

    def waiting(self) -> int:
        return self.jobs.qsize()

    def run(self):
        while True:
            job = self.jobs.get()
            if job.cancelled:
                job.done.set()
                continue
            job.started_at = time.time()
            self.busy = True
            try:
                if job.kind == "load":
                    job.result = self.engine.load(job.code)
                else:
                    job.result = self.engine.speak(job.text, job.code)
            except Exception as e:  # noqa: BLE001 -- handed to the request, logged there
                job.error = e
            finally:
                self.busy = False
                job.finished_at = time.time()
                job.done.set()


# ------------------------------------------------------------------------------------------------ HTTP
class Service:
    def __init__(self, args):
        self.args = args
        self.engine = Engine(args.voices, args.threads, args.quantize)
        self.worker = Worker(self.engine, args.queue)
        self.started = time.time()
        self.counters = {"spoken": 0, "errors": 0, "busy": 0, "refused": 0, "audio_s": 0.0, "gen_ms": 0}
        self.lock = threading.Lock()
        self.preload_errors = {}

    def count(self, **kw):
        with self.lock:
            for k, v in kw.items():
                self.counters[k] = self.counters.get(k, 0) + v

    def preload(self, codes: list[str]):
        for code in codes:
            job = Job("load", code=code)
            if not self.worker.submit(job):
                break
            job.done.wait()
            if job.error:
                self.preload_errors[code] = f"{job.error.__class__.__name__}: {job.error}"
                log.error("preload %s failed: %s", code, self.preload_errors[code])
            else:
                log.info("preload %s: voice %s (%s s)%s", code, job.result["voice"], job.result["load_s"],
                         f" -- {job.result['warning']}" if job.result.get("warning") else "")

    def health(self) -> dict:
        try:
            from importlib.metadata import version  # noqa: PLC0415
            pocket = version("pocket-tts")
        except Exception:  # noqa: BLE001
            pocket = None
        with self.lock:
            c = dict(self.counters)
        spoken = c.get("spoken") or 0
        return {"ok": True, "service": "capri-voice", "version": VERSION, "pocket_tts": pocket,
                "threads": self.args.threads, "languages": dict(self.engine.loaded),
                "voice_states": self.engine.languages_with_state(), "preload_errors": self.preload_errors,
                "queue": self.worker.waiting(), "generating": self.worker.busy, "queue_limit": self.args.queue,
                "uptime_s": round(time.time() - self.started), "spoken": spoken, "errors": c.get("errors", 0),
                "busy_refused": c.get("busy", 0), "refused": c.get("refused", 0),
                "audio_s": round(c.get("audio_s", 0.0), 1),
                "avg_gen_ms": round((c.get("gen_ms", 0) / spoken) if spoken else 0)}


def make_handler(service: Service):
    args = service.args

    class Handler(BaseHTTPRequestHandler):
        server_version = "capri-voice/" + VERSION
        sys_version = ""
        timeout = 30            # a client that stops sending is dropped

        def log_message(self, fmt, *a):      # the default access line is replaced by the one per request below
            return

        def peer(self) -> str:
            return peer_tag(self.headers.get("X-Real-IP") or self.client_address[0])

        def send_json(self, status: int, body: dict, extra: dict | None = None):
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path in ("/health", "/v1/health"):
                return self.send_json(200, service.health())
            if path == "/v1/models":
                return self.send_json(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model",
                                                                         "owned_by": "xyberrp"}]})
            if path == "/v1/audio/voices":
                return self.send_json(200, {"voices": ["capri"], "languages": service.engine.languages_with_state()})
            self.send_json(404, {"error": "not_found"})

        def do_POST(self):  # noqa: N802
            path = self.path.split("?", 1)[0].rstrip("/")
            if path not in ("/v1/audio/speech", "/audio/speech"):
                return self.send_json(404, {"error": "not_found"})
            t0 = time.time()
            peer = self.peer()
            try:
                size = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                size = -1
            if size <= 0 or size > args.max_body:
                service.count(refused=1)
                log.info("speak 413 peer=%s body=%s", peer, size)
                return self.send_json(413 if size > 0 else 400, {"error": "a JSON body of up to %d bytes" % args.max_body})
            try:
                body = json.loads(self.rfile.read(size).decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("not an object")
            except (ValueError, UnicodeDecodeError) as e:
                service.count(refused=1)
                log.info("speak 400 peer=%s bad json (%s)", peer, e.__class__.__name__)
                return self.send_json(400, {"error": "the body is not JSON"})
            text = re.sub(r"\s+", " ", str(body.get("input") or body.get("text") or "")).strip()
            code = language_of(body.get("language") or body.get("idioma"))
            fmt = str(body.get("response_format") or "wav").lower()
            if not text:
                service.count(refused=1)
                log.info("speak 400 peer=%s lang=%s empty", peer, code)
                return self.send_json(400, {"error": "nothing to say"})
            if len(text) > args.max_chars:
                service.count(refused=1)
                log.info("speak 413 peer=%s lang=%s chars=%d (limit %d)", peer, code, len(text), args.max_chars)
                return self.send_json(413, {"error": "the line is longer than %d characters" % args.max_chars})
            if fmt not in ("wav", "pcm"):
                service.count(refused=1)
                return self.send_json(400, {"error": "response_format: wav or pcm"})
            job = Job("speak", text, code)
            if not service.worker.submit(job):
                service.count(busy=1)
                log.info("speak 503 peer=%s lang=%s chars=%d busy (%d waiting)", peer, code, len(text),
                         service.worker.waiting())
                return self.send_json(503, {"error": "busy"}, {"Retry-After": "2"})
            if not job.done.wait(args.wait):
                job.cancelled = True
                service.count(busy=1)
                log.info("speak 503 peer=%s lang=%s chars=%d waited %.1f s", peer, code, len(text), time.time() - t0)
                return self.send_json(503, {"error": "busy"}, {"Retry-After": "2"})
            if job.error:
                service.count(errors=1)
                log.error("speak 500 peer=%s lang=%s chars=%d %s: %s", peer, code, len(text),
                          job.error.__class__.__name__, job.error)
                return self.send_json(500, {"error": f"{job.error.__class__.__name__}: {job.error}"})
            pcm, rate, used, warning = job.result
            seconds = len(pcm) / 2 / rate
            gen_ms = int(((job.finished_at or time.time()) - (job.started_at or t0)) * 1000)
            wait_ms = int(((job.started_at or t0) - job.queued_at) * 1000)
            data = wav_bytes(pcm, rate) if fmt == "wav" else pcm
            service.count(spoken=1, audio_s=seconds, gen_ms=gen_ms)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav" if fmt == "wav" else "audio/pcm")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Capri-Voice", used)
                self.send_header("X-Capri-Language", code)
                self.send_header("X-Capri-Seconds", f"{seconds:.2f}")
                self.send_header("X-Capri-Generated-Ms", str(gen_ms))
                self.send_header("X-Capri-Sample-Rate", str(rate))
                if warning:
                    self.send_header("X-Capri-Warning", re.sub(r"[^\x20-\x7e]", "?", warning)[:200])
                self.end_headers()
                self.wfile.write(data)
                sent = "200"
            except (BrokenPipeError, ConnectionResetError):
                sent = "200-gone"   # the player's Capri Voz gave up waiting
            log.info("speak %s peer=%s lang=%s chars=%d wait=%dms gen=%dms audio=%.2fs voice=%s bytes=%d total=%dms",
                     sent, peer, code, len(text), wait_ms, gen_ms, seconds, used, len(data),
                     int((time.time() - t0) * 1000))

    return Handler


def serve(args) -> int:
    service = Service(args)
    service.worker.start()
    codes = [c.strip() for c in (args.preload or ",".join(service.engine.languages_with_state()) or "en").split(",")
             if c.strip() in LANGUAGES]
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(service))
    httpd.daemon_threads = True
    log.info("capri-voice %s on http://%s:%d: voices %s (states for %s), %d thread(s), queue %d, wait %d s, "
             "up to %d characters", VERSION, args.host, args.port, args.voices,
             ",".join(service.engine.languages_with_state()) or "none", args.threads, args.queue, args.wait,
             args.max_chars)
    threading.Thread(target=service.preload, args=(codes,), name="capri-voice-preload", daemon=True).start()
    if args.exit_after > 0:
        # tests: the service ends by itself
        def later():
            time.sleep(args.exit_after)
            log.info("--exit-after %d s: stopping", args.exit_after)
            httpd.shutdown()
        threading.Thread(target=later, name="capri-voice-exit-after", daemon=True).start()

    def stop(signum, _frame):
        log.info("signal %d: stopping", signum)
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        httpd.server_close()
    log.info("stopped after %d s: %s", int(time.time() - service.started), json.dumps(service.counters))
    return 0


def selftest(args) -> int:
    """Every language with a voice state of hers (or --languages): loaded, one line said, written to OUTDIR."""
    os.makedirs(args.selftest, exist_ok=True)
    engine = Engine(args.voices, args.threads, args.quantize)
    codes = [c.strip() for c in (args.languages or ",".join(engine.languages_with_state()) or "en").split(",")
             if c.strip() in LANGUAGES]
    out = {"ok": True, "version": VERSION, "threads": args.threads, "languages": {}}
    try:
        from importlib.metadata import version  # noqa: PLC0415
        out["pocket_tts"] = version("pocket-tts")
        out["torch"] = version("torch")
    except Exception as e:  # noqa: BLE001
        out["ok"] = False
        out["error"] = f"pocket-tts is not installed: {e.__class__.__name__}: {e}"
        print(json.dumps(out), flush=True)
        return 1
    for code in codes:
        r = {}
        try:
            t0 = time.time()
            info = engine.load(code)
            r.update(voice=info["voice"], warning=info["warning"], load_s=round(time.time() - t0, 1))
            t1 = time.time()
            pcm, rate, used, warning = engine.speak(SELFTEST_LINES[code], code)
            r["gen_s"] = round(time.time() - t1, 2)
            r["seconds"] = round(len(pcm) / 2 / rate, 2)
            r["rate"] = rate
            rms, peak = pcm_stats(pcm)
            r["rms"], r["peak"] = round(rms), peak
            r["rtf"] = round(r["gen_s"] / r["seconds"], 2) if r["seconds"] else None
            path = os.path.join(args.selftest, f"capri-voice-selftest-{code}.wav")
            with open(path, "wb") as f:
                f.write(wav_bytes(pcm, rate))
            r["wav"] = path
            r["ok"] = used == "capri" and r["seconds"] >= 1.0 and rms >= 300
            if not r["ok"]:
                r["why"] = ("not her own voice (%s)" % used) if used != "capri" else "too short or silent"
        except Exception as e:  # noqa: BLE001
            r.update(ok=False, why=f"{e.__class__.__name__}: {e}")
        out["languages"][code] = r
        out["ok"] = out["ok"] and r.get("ok", False)
        log.info("selftest %s: %s", code, json.dumps(r))
    if not codes:
        out["ok"] = False
        out["error"] = "no voice state of hers in " + args.voices
    print(json.dumps(out), flush=True)
    return 0 if out["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voices", required=True, help="the folder with capri_<language>.safetensors")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8891)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--queue", type=int, default=12, help="lines that may wait for the one being generated")
    ap.add_argument("--wait", type=int, default=25, help="seconds a line may wait before 503")
    ap.add_argument("--max-chars", type=int, default=1200)
    ap.add_argument("--max-body", type=int, default=32768)
    ap.add_argument("--preload", default="", help="languages loaded at the start (default: every one with a state)")
    ap.add_argument("--quantize", action="store_true", help="int8 (faster, less memory; not what players' PCs run)")
    ap.add_argument("--selftest", default="", metavar="OUTDIR")
    ap.add_argument("--languages", default="", help="--selftest: which languages")
    ap.add_argument("--exit-after", type=int, default=0, help=argparse.SUPPRESS)   # tests: stop after N seconds
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")
    # the download library's request lines carry signed URLs, and Pocket's own lines come five per sentence: the
    # journal keeps this service's one line per request (and their warnings)
    for name in ("httpx", "httpcore", "huggingface_hub", "urllib3", "filelock"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if not a.selftest:
        logging.getLogger("pocket_tts").setLevel(logging.WARNING)
        for name in list(logging.root.manager.loggerDict):
            if name.startswith("pocket_tts"):
                logging.getLogger(name).setLevel(logging.WARNING)
    # Hugging Face's newer downloader (Xet) breaks halfway for some (capri_motor.py does the same)
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    a.threads = max(1, min(16, a.threads))
    if a.selftest:
        return selftest(a)
    return serve(a)


if __name__ == "__main__":
    sys.exit(main())
