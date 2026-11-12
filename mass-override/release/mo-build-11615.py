import hashlib
import os
import zipfile

SRC = "CapriPersonalityConstruct-1.16.14-massoverride-hack.zip"
OUT = "CapriPersonalityConstruct-1.16.15-massoverride-street.zip"

SWAP = {
    "r6/scripts/CapriPersonalityConstruct/Capri.MassOverride.reds": "Capri.MassOverride.reds",
    "r6/scripts/Open77/Open77MassOverride.reds": "Open77MassOverride.reds",
}

os.chdir("/root/capri-publish")

with zipfile.ZipFile(SRC) as zin:
    entries = {i.filename.replace("\\", "/"): zin.read(i) for i in zin.infolist() if not i.is_dir()}

missing = [k for k in SWAP if k not in entries]
if missing:
    raise SystemExit("release is missing " + ", ".join(missing))

changed = []
for target, local in SWAP.items():
    data = open(local, "rb").read()
    if entries[target] != data:
        changed.append(target)
    entries[target] = data

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
    for name in sorted(entries):
        info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o644 << 16
        zout.writestr(info, entries[name])

raw = open(OUT, "rb").read()
print("entries", len(entries))
print("changed", changed)
print("sha256", hashlib.sha256(raw).hexdigest())
print("size", len(raw))

with zipfile.ZipFile(OUT) as z:
    open77 = z.read("r6/scripts/Open77/Open77MassOverride.reds").decode("utf-8")
    capri = z.read("r6/scripts/CapriPersonalityConstruct/Capri.MassOverride.reds").decode("utf-8")
    checks = {
        "build 1.16.15": 'Version() -> String { return "1.16.15"; }' in open77,
        "billboards + screens (ink layers, world widgets)": "GetWorldWidgets()" in open77 and "GetVirtualWindow()" in open77 and "MassOverrideInk.Collect(run, stats)" in capri,
        "light components pulse in hack colours": "light.SetParameters(settings, 0.05)" in open77 and "MassOverrideLights.Collect(run, object)" in capri,
        "V's screen glitch": "transition_glitch_loop" in open77 and "MassOverrideFx.Burst(game, player, 1.5)" in capri,
        "revert restores ink and lights": "MassOverrideInk.Restore(this.run)" in open77 and "MassOverrideLights.Restore(this.run)" in open77,
        "first cast is blink": "private let m_next: Int32 = 0;" in open77,
        "storage never reopened (RedFileSystem revokes it)": not any("GetStorage(" in l and not l.strip().startswith("//") for l in (open77 + "\n" + capri).splitlines()),
        "step log sent to the gate": '\\"phase\\":\\"log\\"' in open77 and 'MassOverrideLog.Flush(game, playerId, "cast")' in capri,
        "device glitch (QuestStartGlitch)": "ActionQuestStartGlitch" in open77 and "CapriMassOverrideGlitch" in open77 and "MassOverrideHack.Glitch(targets[i], object)" in capri,
        "EMP sparks": "EMPHitEvent" in open77 and "MassOverrideHack.Emp(targets[i], object" in capri,
        "light strobe (SetDeviceON/OFF)": "ActionSetDeviceON" in open77 and "ActionSetDeviceOFF" in open77 and "MassOverrideHack.StrobeStart(targets[i], object, !blackout)" in capri,
        "cars: Accelerate quickhack": "VehicleNetrunnerQuickhackType.Accelerate" in open77 and "EnableHighPriorityPanicDriving" in open77 and "MassOverrideCars.Hack(game" in capri,
        "car alarm": "CapriMassOverrideCarAlarm" in open77,
        "crowd panic": "gamedataStimType.Terror" in open77 and "MassOverridePeople.Panic(player)" in capri,
        "city lights strobe": "ForceCLSStateRequest" in open77 and "MassOverrideCity.Lit(game)" in capri,
        "beat stops before the revert": "class MassOverrideRun" in open77 and "this.run.ended = true" in open77,
        "revert undoes the hack": "MassOverrideHack.Unglitch(target, this.game)" in open77 and "MassOverrideHack.StrobeRestore(target, this.game)" in open77,
        "verify/settled/final reports": '"verify"' in capri and '"settled"' in capri and '"final"' in capri,
        "on-screen alerts == 3": capri.count("system.Alert(") == 3,
        "shots kept as .txt": 'tag + ".txt"' in capri and "vista_pedido.json" in capri,
        "cooldown 40 s": "Cooldown() -> Float { return 40.0; }" in capri,
        "attach registry": 'n"Entity/Attach"' in open77 and "WithRegistered" in open77,
        "cb handlers == 2": open77.count("cb func OnReply") == 2,
        "self re-arms == 2": open77.count("DelayCallback(this,") == 2,
    }
    for k, v in checks.items():
        print(("ok      " if v else "MISSING ") + k)
    if not all(checks.values()):
        raise SystemExit("content check failed")
print("BUILT")
