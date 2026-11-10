// Static checks for the Mass Override .reds files.
//
// Purely a stand-in for a compiler that cannot run here (redscript compiles at game
// start, scc.exe only takes .script). It catches the classes of error this project
// has actually hit: an unresolved member, a call whose arity no longer matches its
// definition after a signature change, and a broken brace.
//
// It is deliberately conservative: it only judges symbols and calls the two files
// declare themselves, so vanilla APIs are never guessed at.

const fs = require("node:fs");

// Blanks out strings and comments while keeping line numbers intact.
function strip(src) {
  let out = "";
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    const n = src[i + 1];
    if (c === "/" && n === "/") {
      while (i < src.length && src[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && n === "*") {
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) {
        if (src[i] === "\n") out += "\n";
        i += 1;
      }
      i += 2;
      continue;
    }
    if (c === '"') {
      i += 1;
      while (i < src.length && src[i] !== '"') {
        if (src[i] === "\\") i += 1;
        i += 1;
      }
      i += 1;
      out += '""';
      continue;
    }
    out += c;
    i += 1;
  }
  return out;
}

const lineOf = (text, index) => text.slice(0, index).split("\n").length;

// Splits an argument list on top-level commas, respecting nesting. Angle brackets
// track generics (ref<X>, array<ref<Y>>) in their own counter: a comparison such as
// `StrLen(target) > 0 ? a : b` inside an argument is not a closing bracket, and
// neither is the arrow in `->`. Counting them with the round brackets made a
// three-argument call read as two.
function splitArgs(raw) {
  const args = [];
  let depth = 0;
  let angle = 0;
  let current = "";
  for (const ch of raw) {
    if ("([{".includes(ch)) depth += 1;
    else if (")]}".includes(ch)) depth -= 1;
    else if (ch === "<") angle += 1;
    else if (ch === ">" && angle > 0) angle -= 1;
    if (ch === "," && depth === 0 && angle === 0) {
      args.push(current);
      current = "";
      continue;
    }
    current += ch;
  }
  if (current.trim()) args.push(current);
  return args.filter((a) => a.trim().length > 0);
}

function matchingBrace(text, openIndex) {
  let depth = 0;
  for (let i = openIndex; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function lintFile(path, known = new Set()) {
  const findings = [];
  const src = fs.readFileSync(path, "utf8");
  const text = strip(src);

  const open = (text.match(/\{/g) || []).length;
  const close = (text.match(/\}/g) || []).length;
  if (open !== close) findings.push(`${path}: braces { ${open} vs } ${close}`);

  const parens = (text.match(/\(/g) || []).length - (text.match(/\)/g) || []).length;
  if (parens !== 0) findings.push(`${path}: parentheses unbalanced by ${parens}`);

  // Classes and the funcs they declare.
  const classes = new Map(); // name -> { fields:Set, funcs:Map<name, arity> }
  const classRe = /\bclass\s+(\w+)\s*(?:extends\s+[\w.<>]+)?\s*\{/g;
  let m;
  while ((m = classRe.exec(text)) !== null) {
    const name = m[1];
    const startFn = text.indexOf("{", m.index);
    const end = matchingBrace(text, startFn);
    if (end < 0) {
      findings.push(`${path}:${lineOf(text, m.index)}: class ${name} has no closing brace`);
      continue;
    }
    const body = text.slice(startFn + 1, end);
    const info = { fields: new Set(), funcs: new Map() };
    for (const f of body.matchAll(/\blet\s+(\w+)\s*:/g)) info.fields.add(f[1]);
    for (const f of body.matchAll(/\bfunc\s+(\w+)\s*\(([^)]*)\)/g)) {
      info.funcs.set(f[1], splitArgs(f[2]).length);
    }
    classes.set(name, info);
  }

  // Field and class symbols referenced anywhere in the file.
  const declared = new Set([...classes.keys()]);
  for (const info of classes.values()) for (const f of info.fields) declared.add(f);

  for (const ref of text.matchAll(/\b(MassOverride\w+|CapriMassOverride)\b/g)) {
    if (!declared.has(ref[1]) && !known.has(ref[1])) {
      // A bare word that is not a class, field or local is only reported when it
      // looks like one of ours and is never assigned.
      const assigned = new RegExp(`\\blet\\s+${ref[1]}\\b`).test(text);
      if (!assigned) {
        findings.push(`${path}:${lineOf(text, ref.index)}: ${ref[1]} is not declared here`);
      }
    }
  }

  // Call sites into classes these files declare: arity must match.
  for (const call of text.matchAll(/\b(\w+)\.(\w+)\s*\(/g)) {
    const [, cls, fn] = call;
    const info = classes.get(cls);
    if (!info) continue;
    const arity = info.funcs.get(fn);
    if (arity === undefined) {
      findings.push(`${path}:${lineOf(text, call.index)}: ${cls}.${fn} is not defined`);
      continue;
    }
    const openParen = text.indexOf("(", call.index);
    let depth = 0;
    let end = -1;
    for (let i = openParen; i < text.length; i += 1) {
      if (text[i] === "(") depth += 1;
      else if (text[i] === ")") {
        depth -= 1;
        if (depth === 0) {
          end = i;
          break;
        }
      }
    }
    if (end < 0) continue;
    const args = splitArgs(text.slice(openParen + 1, end));
    if (args.length !== arity) {
      findings.push(
        `${path}:${lineOf(text, call.index)}: ${cls}.${fn} takes ${arity} but is called with ${args.length}`,
      );
    }
  }

  return { findings, classes };
}

function lintFiles(paths) {
  // Two passes: collect every class the set declares, then lint each file against
  // that union, because one file legitimately uses classes declared in the other
  // (Capri's file calls into the Open77 one). Linting in isolation reported every
  // one of those as undeclared.
  const declared = new Set();
  for (const p of paths) {
    for (const name of lintFile(p, new Set()).classes.keys()) declared.add(name);
  }
  const findings = [];
  for (const p of paths) findings.push(...lintFile(p, declared).findings);
  return { findings: [...new Set(findings)], classes: declared };
}

module.exports = { lintFiles, lintFile, strip, splitArgs };

if (require.main === module) {
  const paths = process.argv.slice(2);
  if (paths.length === 0) {
    console.error("usage: node reds-lint.js <file.reds> [more.reds]");
    process.exit(2);
  }
  const { findings } = lintFiles(paths);
  for (const f of findings) console.error(f);
  console.log(findings.length === 0 ? "clean" : `${findings.length} finding(s)`);
  process.exit(findings.length === 0 ? 0 : 1);
}
