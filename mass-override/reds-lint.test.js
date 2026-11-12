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

// RedHttpClient only invokes a reply method declared `cb`; without it the response is
// dropped silently. That is what made every Mass Override cast stop after the
// register call: the cast that follows the reply was never sent, and the feed
// poller never re-armed. Pin the keyword so it cannot be lost again.
test("both HTTP reply handlers are declared cb", () => {
  const text = fs.readFileSync(path.join(ROOT, "Open77", "Open77MassOverride.reds"), "utf8");
  assert.equal((text.match(/func OnReply\(/g) || []).length, 2, "both OnReply handlers present");
  assert.equal(
    (text.match(/cb func OnReply\(/g) || []).length,
    2,
    "RedHttpClient only invokes cb methods, so both reply handlers need it",
  );
});

// HttpCallback keeps only a weak reference to its target. A one-shot delay callback
// is released the moment Call() returns, so the reply arrived with nothing to
// invoke. Both HTTP objects must keep themselves scheduled, which is what leaves the
// delay system holding them across the request.
test("both HTTP objects keep themselves alive while a request is in flight", () => {
  const text = fs.readFileSync(path.join(ROOT, "Open77", "Open77MassOverride.reds"), "utf8");
  const rearm = text.match(/DelayCallback\(this,/g) || [];
  assert.equal(rearm.length, 3, "the feed poll, the cast post and the cast's sender must each re-arm themselves");
  // the poll re-arms at the top of every Call, before any early return and before its request
  const poll = text.slice(text.indexOf("public class MassOverrideFeedPoll"), text.indexOf("public class MassOverrideRemote"));
  const call = poll.slice(poll.indexOf("public func Call()"), poll.indexOf("private cb func OnReply"));
  assert.ok(call.indexOf("DelayCallback(this,") > 0, "the poll re-arms itself");
  assert.ok(call.indexOf("DelayCallback(this,") < call.indexOf("AsyncHttpClient.Get"), "the poll must be armed before its request");
  assert.ok(call.indexOf("DelayCallback(this,") < call.indexOf("if this.inFlight"), "armed before the in-flight guard returns");
  assert.ok(/if now - this\.sentAt < MassOverrideFeed\.StuckSeconds\(\) \{ return; \}/.test(call), "a request still out is not doubled");
  assert.ok(/private cb func OnReply/.test(poll), "the poll's reply handler is a cb");
  assert.ok(/if this\.keepAlive \{/.test(text), "the cast keep-alive firing must not re-arm");
});

// 2026-11-12: a cast whose one request was lost (a dropped connection) ran on the caster's screen only.
// The cast is now sent again until the gate answers; the sender stays scheduled (so the replies of its
// tries have a live object to land on) and goes no further once answered or out of tries.
test("a cast is sent again until the gate answers, and never forever", () => {
  const text = fs.readFileSync(path.join(ROOT, "Open77", "Open77MassOverride.reds"), "utf8");
  const send = text.slice(text.indexOf("public class MassOverrideCastSend"), text.indexOf("public class MassOverrideDiag"));
  assert.ok(send.length > 500, "MassOverrideCastSend is declared before MassOverrideDiag");
  const call = send.slice(send.indexOf("public func Call()"), send.indexOf("private func Post("));
  assert.ok(call.indexOf("if this.answered { return; }") >= 0, "nothing once answered");
  assert.ok(call.indexOf("MaxAttempts()") > 0 && call.indexOf("GiveUpSeconds()") > 0, "it gives up");
  assert.ok(call.indexOf("DelayCallback(this,") > 0 && call.indexOf("DelayCallback(this,") < call.indexOf("this.Post("),
    "re-armed before its try goes out");
  assert.ok(/post\.send = this;/.test(send), "each try reports back to its sender");
  const answered = send.slice(send.indexOf("public func Answered("));
  assert.ok(/status == 200[\s\S]*this\.answered = true;/.test(answered), "a 200 ends it");
  assert.ok(/status == 409[\s\S]*this\.answered = true;/.test(answered), "a refusal ends it");
  const post = text.slice(text.indexOf("public class MassOverrideCastPost"), text.indexOf("public class MassOverrideCastSend"));
  assert.ok(/if IsDefined\(this\.send\) \{\s*this\.send\.Answered\(this\.attempt, response, this\.isRegister\);/.test(post),
    "a try's reply goes to its sender");
  const capri = fs.readFileSync(path.join(ROOT, "CapriPersonalityConstruct", "Capri.MassOverride.reds"), "utf8");
  assert.ok(/MassOverrideCastSend\.Start\(game, MassOverrideCastPost\.Body\(/.test(capri), "Capri's cast uses the sender");
  assert.ok(!/MassOverrideCastPost\.Register\(/.test(capri), "no one-shot register-then-cast any more");
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
    "MassOverrideCastSend",
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
