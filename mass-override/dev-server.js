// Local-only dev server for the Mass Override gate. Binds to 127.0.0.1 only.
// Serves the gate over HTTP so it can be exercised without the game or Staging.
// Routes:
//   POST /players           { id, ownsCapri, capriSummoned, balance }
//   POST /cast              { playerId, candidates: [{ id, type }] }
//   POST /expire            { castId }  (uses the server clock, or `now` for tests)
//   POST /mode              { mode: "blink" | "blackout" | "alternate" }
//   GET  /state             current cooldowns, claims and mode (debug)

const http = require("node:http");
const { createMassOverride } = require("./gate");

function createDevServer(options = {}) {
  const mo = createMassOverride(options);
  const players = new Map();
  const now = options.now ?? (() => Date.now());

  function readBody(req) {
    return new Promise((resolve, reject) => {
      let data = "";
      req.on("data", (c) => {
        data += c;
        if (data.length > 1e6) reject(new Error("body too large"));
      });
      req.on("end", () => {
        try {
          resolve(data ? JSON.parse(data) : {});
        } catch (e) {
          reject(e);
        }
      });
      req.on("error", reject);
    });
  }

  function send(res, status, body) {
    res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
    res.end(JSON.stringify(body));
  }

  const server = http.createServer(async (req, res) => {
    try {
      if (req.method === "POST" && req.url === "/players") {
        const p = await readBody(req);
        if (!p.id) return send(res, 400, { error: "id required" });
        players.set(p.id, p);
        mo.setBalance(p.id, p.balance ?? 0);
        return send(res, 200, { ok: true });
      }
      if (req.method === "POST" && req.url === "/cast") {
        const { playerId, candidates = [] } = await readBody(req);
        const player = players.get(playerId);
        if (!player) return send(res, 404, { ok: false, reason: "unknown_player" });
        const result = mo.cast(player, candidates, now());
        return send(res, result.ok ? 200 : 409, result);
      }
      if (req.method === "POST" && req.url === "/expire") {
        const { castId } = await readBody(req);
        const result = mo.expire(castId, now());
        return result ? send(res, 200, result) : send(res, 404, { error: "not_expired_or_unknown" });
      }
      if (req.method === "POST" && req.url === "/mode") {
        const { mode } = await readBody(req);
        if (mode !== "blink" && mode !== "blackout" && mode !== "alternate") {
          return send(res, 400, {
            error: "mode must be blink, blackout or alternate",
            mode: mo.cfg.mode,
          });
        }
        mo.setMode(mode);
        return send(res, 200, { ok: true, mode: mo.cfg.mode });
      }
      if (req.method === "GET" && req.url === "/state") {
        const s = mo._state;
        return send(res, 200, {
          cooldownUntil: Object.fromEntries(s.cooldownUntil),
          balances: Object.fromEntries(s.balances),
          claims: Object.fromEntries(s.claims),
          active: Object.fromEntries(s.active),
          nextMode: s.nextMode,
          mode: mo.cfg.mode,
        });
      }
      send(res, 404, { error: "not_found" });
    } catch (e) {
      send(res, 400, { error: e.message });
    }
  });

  return server;
}

if (require.main === module) {
  const port = Number(process.env.MASS_OVERRIDE_PORT) || 11900;
  createDevServer().listen(port, "127.0.0.1", () => {
    console.log(`mass-override dev server on http://127.0.0.1:${port}`);
  });
}

module.exports = { createDevServer };
