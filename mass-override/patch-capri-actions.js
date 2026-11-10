// Applies the Mass Override integration to Capri's action switch
// (r6/scripts/CapriPersonalityConstruct/Capri.Actions.reds): the two dispatch cases
// and the two prompt lines that let her choose them.
//
// That file belongs to Capri, not to this repo, and an update or a mod manager can
// replace it at any time. This script is how the integration is re-applied; it is
// idempotent, and sync-scripts.sh verifies the result.
//
// Usage: node mass-override/patch-capri-actions.js "/path/to/Cyberpunk 2077"
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const GAME = process.argv[2];
if (!GAME) {
  console.error('usage: node patch-capri-actions.js "/path/to/Cyberpunk 2077"');
  process.exit(2);
}

const FILE = path.join(GAME, "r6", "scripts", "CapriPersonalityConstruct", "Capri.Actions.reds");
if (!fs.existsSync(FILE)) {
  console.error(`not a Cyberpunk 2077 install: ${FILE} is missing`);
  process.exit(2);
}

const BS = "\u005c"; // a backslash, without escaping games
const DQ = BS + '"';
const NL = BS + "n";

const text = fs.readFileSync(FILE, "utf8");
const crlf = text.includes("\r\n");
const eol = crlf ? "\r" : "";
const lines = text.split("\n");

const hasCase = lines.some((l) => l.includes('case "mass_override_mode"'));
const hasPrompt = lines.some((l) => l.includes("mass_override_mode") && l.includes("do"));
if (hasCase && hasPrompt) {
  console.log("already patched");
  process.exit(0);
}

// 1. The dispatch cases, just before the switch's "none" arm.
if (!hasCase) {
  const noneAt = lines.findIndex((l) => l.trim() === 'case "none": return "";');
  if (noneAt < 0) {
    console.error("no 'none' arm in the action switch: Capri's file changed shape");
    process.exit(1);
  }
  lines.splice(
    noneAt,
    0,
    '            case "mass_override": return CapriMassOverride.Run(player, CapriSystem.Get(player.GetGame()));' + eol,
    '            case "mass_override_mode": return CapriMassOverride.SetModeFromAction(target);' + eol,
  );
}

// 2. The prompt lines, after the device switches she already knows.
if (!hasPrompt) {
  const promptAt = lines.findIndex((l) => l.includes("device_on") && l.includes("switch devices"));
  if (promptAt < 0) {
    console.error("no device_on prompt line: Capri's prompt changed shape");
    process.exit(1);
  }
  const cast = `            + " {${DQ}do${DQ}:${DQ}mass_override${DQ},${DQ}target${DQ}:...} change everything around V at once: lights, screens, billboards and cars go out, people turn hostile. Costs battery charge, once every two minutes; with nothing around V she says so${NL}"${eol}`;
  const mode = `            + " {${DQ}do${DQ}:${DQ}mass_override_mode${DQ},${DQ}target${DQ}:${DQ}blink${DQ}|${DQ}blackout${DQ}|${DQ}auto${DQ}} the mode the next Mass Override casts use: blink pulses, blackout holds the block dark, auto alternates one per cast. V asks to pin one or to go back to auto${NL}"${eol}`;
  lines.splice(promptAt + 1, 0, cast, mode);
}

fs.writeFileSync(FILE, lines.join("\n"));
console.log(`patched ${FILE} (${crlf ? "CRLF" : "LF"})`);
