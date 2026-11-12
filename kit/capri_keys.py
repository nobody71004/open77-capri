"""Her keys as Open77 key mappings: the edit to Capri.System.reds that lets a server's resource drive them.

XyberRP, 2026-11-12.  The owner: "give capri real configurable keybinds to set in the open77 esc settings keybinds
tab".  Capri read her five keys -- type to her, mark a target, talk to her, summon her, switch seats while she
drives -- straight off the game's key events (CapriSystem.OnKeyInput, the keys from her own Settings > Mods page):
nothing in Open77's KEY BINDINGS, two of them already keys of XyberRP's own resource (F7 its appearance panel, Caps
Lock its radio), and Enter on a row of a staff menu opened her text box under it.

Now opx_infinity (core/client/caprikeys.lua) declares the five as Open77 key mappings -- ESC > Settings > KEY
BINDINGS lists them, a player sets them there -- and hands every press to her through Open77.rtti:

    CapriSystem.KeyFromHost(game, action, down) -> String      (put in here)

    action  type | mark | summon        a press (down) does what her own key did; a release answers "up"
            talk                        down starts her listening, up sends what she heard
            seats                       a quick tap (down, then up within 0.5 s) switches seats
            lease                       her own reading of the game's keys rests for 6 s ("taken" / "held")
            release                     her own keys again at once ("released" / "free")
            keys                        the keys her settings name: "type=IK_Enter mark=IK_MiddleMouse ..."
            typing                      her text box: "typing", "closing" (0.5 s after) or "free"
    answer  what happened, one word, for the resource's log: "opened", "offline", "busy", "menu", "typing",
            "listening", "heard", "armed", "seats", "marked", "summoned", "no-session", "no-capri"...

While the resource keeps asking for the lease (every 2 s) her own reading of the game's keys rests, so the key a
player set in KEY BINDINGS is the only one.  The lease counts only while it has between 0 and 10 s left (a clock
that went back -- a save loaded -- cannot keep her own keys off), and a game nobody asks for (single player,
another server) has her own keys back within 6 s.  Everything else she does with a key is her own code, called the
way her key called it: OpenInput, Mark, Summon, StartListening / StopListening, her drive's SeatKey.

One anchored edit, as the brain's in Capri.Storage.reds: the field before OnKeyInput and OnKeyInput's first lines
must be exactly Capri 1.16's or nothing is built.  The edit sits between marks; applying it again first takes the
earlier one out (whatever its version), so a package built from a built one carries it once.
Pure Python, no I/O: capri_wire.build calls it.
"""
from __future__ import annotations

import re

SYSTEM = "r6/scripts/CapriPersonalityConstruct/Capri.System.reds"
CONFIG = "r6/scripts/CapriPersonalityConstruct/Capri.Config.reds"

# Capri 1.16: the field before her key callback, and the callback's first lines.
ANCHOR = ("    private let m_seatKeyAt: Float;\n"
          "\n"
          "    private cb func OnKeyInput(event: ref<KeyInputEvent>) {\n"
          "        if !this.m_inSession {\n"
          "            return;\n"
          "        }\n")

BEGIN = "    // >>> XyberRP host keys (capri_keys.py)"
END = "    // <<< XyberRP host keys"
GATE_BEGIN = "        // >>> XyberRP host keys:"
GATE_END = "        // <<< XyberRP host keys"
MARK = "XyberRP host keys"

BLOCK = BEGIN + """: her keys as Open77 key mappings, put in by the XyberRP Capri kit.
    // On XyberRP a resource of the server (opx_infinity, core/client/caprikeys.lua) declares type, mark, talk,
    // summon and seats under ESC > Settings > KEY BINDINGS, where a player sets them, and hands each one here
    // through Open77.rtti. While it keeps the lease (asked every 2 s, good for 6 s) her own reading of the game's
    // keys below rests, so the key set there is the only one. Nobody asking (single player, another server): her
    // own keys within 6 s.
    private let m_hostKeysUntil: Float;
    private let m_hostSeatAt: Float;

    public static func KeyFromHost(game: GameInstance, action: String, down: Bool) -> String {
        let system = CapriSystem.Get(game);
        if !IsDefined(system) {
            return "no-capri";
        }
        return system.OnHostKey(action, down);
    }

    public func OnHostKey(action: String, down: Bool) -> String {
        if Equals(action, "lease") {
            let fresh = !this.HostHasKeys();
            this.m_hostKeysUntil = this.Now() + 6.0;
            if fresh {
                FTLog("[Capri] keys: Open77's key mappings have her keys (her own keys rest)");
                return "taken";
            }
            return "held";
        }
        if Equals(action, "release") {
            let had = this.HostHasKeys();
            this.m_hostKeysUntil = 0.0;
            if had {
                FTLog("[Capri] keys: her own keys again");
                return "released";
            }
            return "free";
        }
        if Equals(action, "keys") {
            let config = CapriConfig.Get(this.GetGameInstance());
            if !IsDefined(config) {
                return "none";
            }
            return "type=" + CapriSystem.HostKeyName(config.keyType)
                + " mark=" + CapriSystem.HostKeyName(config.keyMark)
                + " talk=" + CapriSystem.HostKeyName(config.keyTalk)
                + " summon=" + CapriSystem.HostKeyName(config.keySummon)
                + " seats=" + CapriSystem.HostKeyName(config.keySeats);
        }
        if Equals(action, "typing") {
            if this.m_typing {
                return "typing";
            }
            return (this.Now() - this.m_typingClosedAt < 0.5) ? "closing" : "free";
        }
        if !this.m_inSession {
            return "no-session";
        }
        if Equals(action, "talk") {
            if down {
                if this.InMenu() {
                    return "menu";
                }
                this.StartListening();
                return "listening";
            }
            if this.IsListening() {
                this.StopListening();
                return "heard";
            }
            return "idle";
        }
        // while the text box is open every key belongs to it; the Enter that confirms it must not open it again
        if this.m_typing || this.Now() - this.m_typingClosedAt < 0.5 {
            return "typing";
        }
        if Equals(action, "seats") {
            // a quick tap, as with her own key (the game's lights share it)
            if down {
                this.m_hostSeatAt = this.Now();
                return "armed";
            }
            if this.Now() - this.m_hostSeatAt >= 0.5 {
                return "held";
            }
            if this.InMenu() {
                return "menu";
            }
            this.m_hostSeatAt = 0.0;
            this.m_drive.SeatKey(this.Player());
            return "seats";
        }
        if !down {
            return "up";
        }
        if this.InMenu() {
            return "menu";
        }
        if Equals(action, "type") {
            let online = this.m_player2.IsConnected();
            let busy = this.m_busy;
            this.OpenInput();
            if this.m_typing {
                return "opened";
            }
            if !online {
                return "offline";
            }
            return busy ? "busy" : "not-opened";
        }
        if Equals(action, "mark") {
            this.Mark();
            return "marked";
        }
        if Equals(action, "summon") {
            this.Summon();
            return "summoned";
        }
        return "unknown";
    }

    // The lease counts while it has between 0 and 10 s left: a clock that went back (a save loaded) cannot keep
    // her own keys off.
    private func HostHasKeys() -> Bool {
        let left = this.m_hostKeysUntil - this.Now();
        return left > 0.0 && left <= 10.0;
    }

    private static func HostKeyName(key: EInputKey) -> String {
        return EnumValueToString("EInputKey", Cast<Int64>(EnumInt(key)));
    }
""" + END + "\n"

GATE = (GATE_BEGIN + " Open77's key mappings have her keys (KeyFromHost above)\n"
        "        if this.HostHasKeys() {\n"
        "            return;\n"
        "        }\n"
        + GATE_END + "\n")

REPLACEMENT = ("    private let m_seatKeyAt: Float;\n"
               "\n"
               + BLOCK +
               "\n"
               "    private cb func OnKeyInput(event: ref<KeyInputEvent>) {\n"
               "        if !this.m_inSession {\n"
               "            return;\n"
               "        }\n"
               + GATE)

# What the edit calls in Capri's own files: a package where any of this changed is not built.
REQUIRED_IN_SYSTEM = (
    "module Capri",
    "public class CapriSystem extends ScriptableSystem {",
    "public static func Get(game: GameInstance) -> ref<CapriSystem> {",
    "private let m_inSession: Bool;",
    "private let m_busy: Bool;",
    "private let m_typing: Bool;",
    "private let m_typingClosedAt: Float;",
    "public func Now() -> Float {",
    "private func Player() -> ref<PlayerPuppet> {",
    "private func InMenu() -> Bool {",
    "public func OpenInput() -> Void {",
    "public func Mark() -> Void {",
    "public func Summon() -> Void {",
    "public func IsListening() -> Bool {",
    "public func StartListening() -> Void {",
    "public func StopListening() -> Void {",
    "this.m_drive.SeatKey(this.Player());",
    "this.m_player2.IsConnected()",
)
REQUIRED_IN_CONFIG = (
    "public class CapriConfig extends ScriptableSystem {",
    "public let keyType: EInputKey",
    "public let keyMark: EInputKey",
    "public let keyTalk: EInputKey",
    "public let keySummon: EInputKey",
    "public let keySeats: EInputKey",
    "public static func Get(game: GameInstance) -> ref<CapriConfig> {",
)

_BLOCK_RX = re.compile(r"\n" + re.escape(BEGIN) + r".*?\n" + re.escape(END) + r"\n", re.S)
_GATE_RX = re.compile(re.escape(GATE_BEGIN) + r".*?\n" + re.escape(GATE_END) + r"\n", re.S)


class KeysError(Exception):
    pass


def has(text: str) -> bool:
    """The edit (any version of it) is in this Capri.System.reds."""
    return MARK in text


def unapply(text: str) -> str:
    """Capri's own file again (LF text in, LF text out): both marked parts taken out, whatever their version."""
    if not has(text):
        return text
    plain, blocks = _BLOCK_RX.subn("", text)
    plain, gates = _GATE_RX.subn("", plain)
    if blocks != 1 or gates != 1 or has(plain):
        raise KeysError(f"{SYSTEM} carries the host keys in a way this kit did not write "
                        f"({blocks} block(s), {gates} gate(s))")
    if plain.count(ANCHOR) != 1:
        raise KeysError(f"{SYSTEM}: taking the host keys out did not give Capri's own lines back")
    return plain


def apply(text: str) -> str:
    """The edit in (LF text in, LF text out); an earlier one is taken out first."""
    plain = unapply(text)
    if plain.count(ANCHOR) != 1:
        raise KeysError(f"{SYSTEM}: OnKeyInput's first lines are not exactly as expected (host keys refused)")
    out = plain.replace(ANCHOR, REPLACEMENT)
    if out.count(BEGIN) != 1 or out.count(GATE_BEGIN) != 1 or unapply(out) != plain:
        raise KeysError(f"{SYSTEM}: the host keys did not go in cleanly")
    return out


def problems(entries: dict[str, bytes]) -> list[str]:
    """What the edit needs from Capri's own files that this package does not have."""
    out = []
    for path, needs in ((SYSTEM, REQUIRED_IN_SYSTEM), (CONFIG, REQUIRED_IN_CONFIG)):
        blob = entries.get(path)
        if blob is None:
            out.append(f"{path} is not in the package")
            continue
        text = blob.decode("utf-8", errors="replace").replace("\r\n", "\n")
        if path == SYSTEM:
            try:
                text = unapply(text)
            except KeysError as e:
                out.append(str(e))
                continue
            if text.count(ANCHOR) != 1:
                out.append(f"{SYSTEM}: OnKeyInput's first lines are not exactly as expected")
        out += [f"{path} no longer has: {need}" for need in needs if need not in text]
    return out


def edit(blob: bytes, on: bool) -> bytes:
    """Capri.System.reds with the edit in (on) or out, its line ends kept."""
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as e:
        raise KeysError(f"{SYSTEM} is not UTF-8: {e}") from e
    crlf = "\r\n" in text
    plain = text.replace("\r\n", "\n")
    plain = apply(plain) if on else unapply(plain)
    return (plain.replace("\n", "\r\n") if crlf else plain).encode("utf-8")


def carries(blob: bytes) -> bool:
    """This Capri.System.reds has exactly this kit's current edit."""
    try:
        text = blob.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return False
    return text.count(BEGIN) == 1 and REPLACEMENT in text
