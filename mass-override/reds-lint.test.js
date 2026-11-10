const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { lintFiles, lintFile } = require("./reds-lint");

const ROOT = path.join(__dirname, "..", "game", "r6", "scripts");
const OWNED = [
  path.join(ROOT, "Open77", "Open77MassOverride.reds"),
  path.join(ROOT, "CapriPersonalityConstruct", "Capri.MassOverride.reds"),
];

function tempReds(contents) {
  const file = path.join(os.tmpdir(), `reds-lint-${Math.random().toString(36).slice(2)}.reds`);
  fs.writeFileSync(file, contents);
  return file;
}

test("the two owned scripts are clean", () => {
  for (const file of OWNED) assert.ok(fs.existsSync(file), `${file} should exist`);
  const { findings } = lintFiles(OWNED);
  assert.deepEqual(findings, []);
});

test("every class the two files use is declared in one of them", () => {
  const { classes } = lintFiles(OWNED);
  for (const name of [
    "MassOverrideTarget",
    "MassOverrideMode",
    "MassOverrideKind",
    "MassOverrideLightSwitch",
    "MassOverrideStats",
    "MassOverrideArea",
    "MassOverrideCache",
    "MassOverridePrefs",
    "MassOverrideDiag",
    "MassOverrideProbe",
    "MassOverrideEffects",
    "MassOverridePulse",
    "MassOverrideHold",
    "MassOverrideRevert",
    "CapriMassOverride",
  ]) {
    assert.ok(classes.has(name), `${name} should be declared`);
  }
});

test("catches unbalanced braces", () => {
  const file = tempReds("class A {\n  public func B() -> Void {}\n");
  const { findings } = lintFile(file);
  assert.ok(findings.some((f) => f.includes("braces")));
});

test("catches a call whose arity no longer matches", () => {
  const file = tempReds(
    [
      "class A {",
      "  public static func Mode(game: GameInstance) -> Int32 { return 0; }",
      "  public static func Use() -> Int32 { return A.Mode(); }",
      "}",
    ].join("\n"),
  );
  const { findings } = lintFile(file);
  assert.ok(
    findings.some((f) => f.includes("A.Mode takes 1 but is called with 0")),
    findings.join("\n"),
  );
});

test("catches a call to a method that does not exist", () => {
  const file = tempReds(["class A {", "  public static func Use() -> Int32 { return A.Missing(); }", "}"].join("\n"));
  const { findings } = lintFile(file);
  assert.ok(findings.some((f) => f.includes("A.Missing is not defined")));
});

test("ignores comments and strings", () => {
  const file = tempReds(
    ["class A {", '  public func B() -> Void { let s: String = "}{ //"; }', "  // }", "}"].join("\n"),
  );
  const { findings } = lintFile(file);
  assert.deepEqual(findings, []);
});
