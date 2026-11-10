const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { lintFile } = require("./reds-lint");

function tempReds(contents) {
  const file = path.join(os.tmpdir(), `reds-lint-angle-${Math.random().toString(36).slice(2)}.reds`);
  fs.writeFileSync(file, contents);
  return file;
}

test("a comparison inside an argument is not read as a bracket", () => {
  const file = tempReds(
    [
      "class B {",
      '  public static func Pick(player: Int32, target: String, kind: String) -> Int32 { return 0; }',
      "  public static func Use(target: String) -> Int32 {",
      '    return B.Pick(1, StrLen(target) > 0 ? target : "look", "npc");',
      "  }",
      "}",
    ].join("\n"),
  );
  const { findings } = lintFile(file);
  assert.deepEqual(findings, [], "the call has three arguments, not two");
});

test("an arrow in an argument is not read as a bracket either", () => {
  const file = tempReds(
    [
      "class C {",
      '  public static func Two(a: Int32, b: Int32) -> Int32 { return a + b; }',
      "  public static func Use(list: array<Int32>) -> Int32 {",
      "    return C.Two(ArraySize(list), ArraySize(list));",
      "  }",
      "}",
    ].join("\n"),
  );
  const { findings } = lintFile(file);
  assert.deepEqual(findings, [], "the generic array<Int32> is one argument, not a broken nest");
});
