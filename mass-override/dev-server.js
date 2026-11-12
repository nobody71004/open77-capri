// The Mass Override gate over HTTP. Binds to 127.0.0.1 only; nginx publishes it
// (/mass-override/ for XyberRP, /mass-override-staging/ for XyberRP Staging).
// Routes:
//   POST /players           { id, ownsCapri, capriSummoned, balance }
//   POST /cast              { playerId, session?, token?, mode?, x?, y?, z?, candidates: [{ id, type }] }
//                           session: the game's own id for this gate (one per running game; older builds sent
//                           only playerId, which is the same on every PC); an unknown session is registered
//                           as Capri's owner with her summoned, which is what every game build sends anyway.
//                           x, y, z / mode / token: where the caster stood, the mode the caster's game runs and
//                           the caster's token for this cast -- what every other client needs (GET /casts).
//   POST /report            a cast's own counts (and the step log), as the client measured them: logged
//   POST /expire            { castId }  (uses the server clock, or `now` for tests)
//   POST /mode              { mode: "blink" | "blackout" | "alternate" }
//   GET  /casts?since=N&session=S
//                           every cast after seq N that is still on, one per line, for the game scripts (no JSON
//                           parser in reach): first line "<next>", then "<seq> <mode> <xcm> <ycm> <zcm> <ageMs>
//                           <remainingMs> <token>" (positions in whole centimetres: the game reads integers).
//                           session only names the poller in the log and in /state.
//   GET  /events?since=N    accepted casts after seq N, as JSON
//   GET  /feed?since=N      the newest unseen cast as "<seq> <mode>", or "<seq> none" (builds up to 1.16.16)
//   GET  /state             current cooldowns, claims, mode, the clients polling (debug)

const http = require("node:http");
const { createMassOverride, isPoint } = require("./gate");

// A poller counts as "polling" for this long after its last request.
const POLLING_MS = 30_000;
const ID_RX = /^[A-Za-z0-9_.:()\- ]{1,80}$/;
const TOKEN_RX = /^[A-Za-z0-9_\-]{1,64}$/;

function createDevServer(options = {}) {
  const mo = createMassOverride(options);
  const players = new Map();
  const pollers = new Map(); // session -> { first, last, polls }
  const now = options.now ?? (() => Date.now());
  const say = options.log ?? ((line) => console.log(line));
  const stats = { casts: 0, refused: 0, polls: 0, reports: 0 };

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

  function text(res, body) {
    res.writeHead(200, { "content-type": "text/plain", "cache-control": "no-store" });
    res.end(body);
  }

  function polling(t) {
    let n = 0;
    for (const p of pollers.values()) if (t - p.last <= POLLING_MS) n += 1;
    return n;
  }

  function notePoller(session, t) {
    if (!session || !ID_RX.test(session)) return;
    const seen = pollers.get(session);
    if (seen) {
      if (t - seen.last > POLLING_MS) say(`[feed] ${session} polling again after ${Math.round((t - seen.last) / 1000)} s (${polling(t) + 1} polling)`);
      seen.last = t;
      seen.polls += 1;
      return;
    }
    pollers.set(session, { first: t, last: t, polls: 1 });
    say(`[feed] new client ${session} polling (${polling(t)} polling)`);
    // a session that has not polled for a day is forgotten
    for (const [k, p] of pollers) if (t - p.last > 86_400_000) pollers.delete(k);
  }

  const cm = (v) => Math.round(v * 100);

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://127.0.0.1");
      if (req.method === "POST" && url.pathname === "/players") {
        const p = await readBody(req);
        const id = p.session || p.id;
        if (!id) return send(res, 400, { error: "id required" });
        players.set(id, { ...p, id });
        mo.setBalance(id, p.balance ?? 0);
        return send(res, 200, { ok: true });
      }
      // A cast's own counts, sent by the client after its effects ran. The in-game
      // file log can refuse writes, so this is the reliable channel: no report, no
      // completed cast.
      if (req.method === "POST" && url.pathname === "/report") {
        const r = await readBody(req);
        mo.setReport(r);
        stats.reports += 1;
        say(`[report] ${JSON.stringify(r)}`);
        return send(res, 200, { ok: true });
      }
      if (req.method === "POST" && url.pathname === "/cast") {
        const body = await readBody(req);
        const { playerId, session, candidates = [] } = body;
        const key = session || playerId;
        let player = players.get(key);
        if (!player && session && ID_RX.test(session)) {
          // what every game build registers with (MassOverrideCastPost.Register)
          player = { id: session, ownsCapri: true, capriSummoned: true, balance: 100 };
          players.set(session, player);
          mo.setBalance(session, 100);
        }
        if (!player) return send(res, 404, { ok: false, reason: "unknown_player" });
        if (session && (mo._state.balances.get(key) ?? 0) < mo.cfg.cost) mo.setBalance(key, 100);
        const origin = {
          x: Number(body.x),
          y: Number(body.y),
          z: Number(body.z),
          mode: body.mode,
          token: typeof body.token === "string" && TOKEN_RX.test(body.token) ? body.token : "",
        };
        const result = mo.cast(player, Array.isArray(candidates) ? candidates : [], now(), origin);
        if (result.ok) {
          stats.casts += 1;
          const e = result.event;
          const where = e.at ? `${e.at.x.toFixed(1)},${e.at.y.toFixed(1)},${e.at.z.toFixed(1)}` : "unknown (an older build)";
          const seq = mo._state.events.length ? mo._state.events[mo._state.events.length - 1].seq : 0;
          say(`[cast] seq=${seq} by ${key} mode=${e.mode} at ${where} token=${e.token || "-"} targets=${e.targets.length} ` +
            `(${polling(now())} client(s) polling)`);
        } else {
          stats.refused += 1;
          say(`[cast] refused for ${key}: ${result.reason}`);
        }
        return send(res, result.ok ? 200 : 409, result);
      }
      if (req.method === "POST" && url.pathname === "/expire") {
        const { castId } = await readBody(req);
        const result = mo.expire(castId, now());
        return result ? send(res, 200, result) : send(res, 404, { error: "not_expired_or_unknown" });
      }
      if (req.method === "POST" && url.pathname === "/mode") {
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
      if (req.method === "GET" && url.pathname === "/casts") {
        const t = now();
        stats.polls += 1;
        notePoller(url.searchParams.get("session"), t);
        const feed = mo.castsSince(url.searchParams.get("since"), t);
        const lines = [String(feed.next)];
        for (const e of feed.events) {
          // a cast from an older build has no position: the clients can only run its city part
          const at = e.at && isPoint(e.at) ? e.at : null;
          lines.push([e.seq, e.mode, at ? cm(at.x) : 0, at ? cm(at.y) : 0, at ? cm(at.z) : 0, Math.round(e.ageMs),
            Math.round(e.remainingMs), e.token || (at ? "-" : "nopos")].join(" "));
        }
        return text(res, lines.join("\n"));
      }
      if (req.method === "GET" && (url.pathname === "/events" || url.pathname === "/feed")) {
        const feed = mo.feedSince(url.searchParams.get("since"));
        if (url.pathname === "/feed") {
          // Plain text for the game scripts up to 1.16.16, which only need the newest mode
          // plus a cursor: "<seq> <mode>". A caught-up poller gets its own cursor back with
          // "none", so it never rewinds and re-applies a cast it has already run.
          const newest = feed.events[feed.events.length - 1];
          return text(res, newest ? `${newest.seq} ${newest.mode}` : `${feed.next} none`);
        }
        return send(res, 200, { ok: true, next: feed.next, events: feed.events });
      }
      if (req.method === "GET" && url.pathname === "/state") {
        const s = mo._state;
        const t = now();
        return send(res, 200, {
          report: s.report ?? null,
          cooldownUntil: Object.fromEntries(s.cooldownUntil),
          balances: Object.fromEntries(s.balances),
          claims: s.claims.size,
          active: Object.fromEntries(s.active),
          nextMode: s.nextMode,
          mode: mo.cfg.mode,
          polling: polling(t),
          pollers: Object.fromEntries([...pollers].map(([k, p]) => [k, { polls: p.polls, lastS: Math.round((t - p.last) / 1000) }])),
          recent: s.events.slice(-8).map((e) => ({ seq: e.seq, mode: e.mode, by: e.casterId, ageS: Math.round((t - e.castAt) / 1000),
            at: e.at ? [e.at.x, e.at.y, e.at.z].map((v) => Math.round(v)) : null })),
          stats,
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
    console.log(`mass-override gate on http://127.0.0.1:${port} (casts with positions: GET /casts)`);
  });
}

module.exports = { createDevServer };
