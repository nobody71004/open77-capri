Capri for every player (XyberRP and XyberRP Staging): her brain, her own voice, Mass Override for everyone
==========================================================================================================

Why other PCs heard a Windows voice (2026-11-12)
  Capri speaks with her real voice only on a PC that installed her local engine ("Install local
  voice": Pocket TTS and her voice files, about 900 MB) -- the laptop.  Every other PC's Capri Voz
  fell back to a borrowed Windows voice (on Linux: no voice at all), and the launcher package no
  longer ships the F1 window where that install button lives.
  Now her same engine and voice files (Pocket TTS 4.0.1, the laptop's exact version and model
  revisions) run once on the game servers' machine (/opt/capri-voice, the capri-voice service,
  its own private address behind nginx with a limit per address).  The package carries
  CapriVoz\servidor.json, and Capri Voz (Windows and Linux) uses it on launch: "auto" -- the
  default -- is her local engine when installed, else her voice from the server, else Windows'.
  A player's own voice choice (ElevenLabs, OpenAI...) is left alone.  Capri Voz logs every line to
  red4ext\plugins\CapriPersonalityConstruct\CapriVoz\cache\capri_voz.log.

Why "mass over ride" did nothing, and a cast showed on one PC only (2026-11-12, later)
  1. Mass Override is cast when Capri's brain answers with it.  The brain answers an explicit
     request at once, by itself -- but it only knew "mass override" as one word or two.  Typed as
     "mass over ride", the request went to the model, which answered with banter and no cast: on
     the desktop nothing happened.  The brain now hears it however it is typed (mass over ride,
     massoverride, mass-override, mass overide, mas override...), never "massive" or "the mass of".
     The kit's "brain" step puts the new program on the machine: the brain's journal shows, for
     each request, whether the shortcut answered it or the model did (mo=model / mo=no).
  2. A cast travels to the gate in one request.  From a PC whose connection to the machine drops
     now and then (the laptop that night: "Failed to connect ... after 21025 ms", "Recv failure:
     Connection was reset"), that one request was lost: the cast ran on that screen only.  Now
     the game sends it again until the gate answers (every 3 to 5 s, for up to 26 s), the gate
     answers a cast it already has (the same token) with that cast -- never run or charged twice --
     and every report a game sends names its own session.
  The "brain" step also shows (read only) the brain's last requests, both gates' last casts, and
  what on the machine could drop a player's connection (firewall limits, the kernel's dropped
  connection attempts, the connection table, nginx's limits hit).

Why a Mass Override showed on the caster's screen only (2026-11-12)
  The gate's feed only started on a PC after that PC cast once, it only carried the mode for that
  PC's NEXT cast, and every PC registered with the gate under its V's entity id -- the same on
  every PC, so one player's recharge blocked everyone's cast at the gate.  Now every game polls its
  gate from the start of its session under an id of its own; a cast carries where the caster stood
  and the mode the caster's game runs; and every other game runs it: the street around the cast
  (machines, lights, cars, the crowd) within 150 m, the city's lights and billboards for everyone.
  Nobody is turned on a V who did not cast, nothing is charged.  One run is on screen at a time:
  the next cast first puts the street back as it was.

Why she said "I'm here, V, but disconnected"
  The brain on the game servers' machine works: the web server hands it out at a private address
  (https://xyberrp.duckdns.org/capri-brain-.../v1, behind nginx), and it answers.  But the Capri
  package the Open77 launcher gives players never said where it is: the launcher may not ship
  r6\storages (her settings.json), so every PC but one set up by hand started her on her default,
  the Player2 app -- and without that app she greets you with "I'm here, V, but disconnected".

Why a "REDscript migration" window comes up at every game start
  The REDscript the launcher installs (1.0) no longer compiles 12 of Capri's script files as they
  are in the package (1554 errors: "inkMargin cannot be constructed with the new operator"...).
  So at every start it asks to rewrite them, rewrites them in the game folder, and compiles again;
  the launcher puts the original files back at the next connect, and the window comes back.  A
  player who clicks Cancel gets no Capri scripts at all.

What changes
  1. One script more in each server's Capri package: Capri.ServerBrain.reds.  When the game starts
     and Capri reads her settings, it points her at the server's brain -- unless the player has a
     service of their own with its own key (OpenRouter, Gemini, OpenAI, a custom one, or a local
     AI of their own), which stays.  It writes what it decided to
     r6\storages\CapriConstruct\server_brain.json on the player's PC (never an address or a key).
     Capri.Storage.reds gets the one line that calls it, where her settings are read.
  2. The 12 scripts ship already migrated, exactly as your game's REDscript rewrote them (the kit
     takes them from this PC's game folder only when they differ from the package by nothing but
     those rewrites -- the edit counts match the game's own log).  No window, nothing rewritten.
  3. The brain's nginx location gets per-address limits (a dozen questions at once, then one
     every five seconds; four at a time), because its private address now travels to every
     player: nobody can tie up the processors the game servers share with it.
  Players get the new build from the launcher the next time they join: it names Capri and asks
  once before installing it, because it carries a DLL -- as it did for 1.16.15.

The bats (run them in this order)
  C1-Check-Capri-and-the-brain-read-only.bat      READ ONLY, any time.  Both servers' Capri package
      (is the brain wired in?), who is on, what the launcher hands out; the brain: where nginx
      serves it, the unit behind it, Ollama and its models, its last requests; from this PC, the
      brain asked the way a player's game asks it (one short question, timed); this PC's Capri.
  C2-Capri-brain-voice-and-Mass-Override-on-Staging.bat   LEAVE STAGING FIRST.  1. her voice on
      the machine (once for the machine: venv, Pocket TTS, her voice files from Staging's package,
      a test line in English and Spanish, its service, its nginx location with a limit; the web
      server put back by itself on any failure), asked from this PC; 2. the brain hears Mass
      Override however it is typed (its program updated, kept first, checked by node, restarted,
      asked; put back by itself on any failure; once for the machine); 3. Staging's Mass Override
      gate updated and asked; 4. the new package: the live one with the brain wired in, Mass
      Override for everyone and Capri Voz using her server voice, compiled with YOUR GAME'S OWN
      Redscript and CapriVoz.ps1 checked by PowerShell's own parser -- nothing is sent unless both
      pass -- into Staging's mod store and server.jsonc (kept first, --check-config run); 5. the
      brain's limits; 6. Staging restarted; 7. what Staging hands out, checked, her voice asked.
  C3-Capri-brain-voice-and-Mass-Override-on-XyberRP.bat   The same for live XyberRP -- after
      Staging was fine in game.  Nobody may be on XyberRP.
  C2b-Put-Staging-Capri-back.bat / C3b-Put-XyberRP-Capri-back.bat   The server's Capri back to the
      build before (still in its mod store), and a restart.
  C2c-Take-the-brain-limits-back-out.bat           The brain's nginx site as it was before the limits.
  C4-This-PCs-Capri-read-only.bat                 READ ONLY, no server: this PC's Capri after a game
      with her -- what she thinks with, what the wiring decided, her requests to the brain.

What it needs
  - the fivem2open77 Studio (its Python and its SSH settings: it signs in to the machine the way
    the Studio does) and the AV kit next to this folder (Downloads\open77-av-kit);
  - on this PC, Cyberpunk 2077 with Redscript, and XyberRP's launcher layer installed (join
    XyberRP or Staging once): the compile check uses this PC's scripts the way a player's game does.

Logs (tell Claude "done": it reads them)
  kit\capri-<command>-<time>.log -- every step, what the machine said, what the compiler said.
  kit\_scc\<build>-<time>\r6\logs\ -- the compiler's own log for each check.
  kit\work\<server>-<time>\ -- the package as it was live, and the builds made from it.
  ..\open77-av-kit\avkit-restart-*.log -- the restarts.
  No log holds the brain's private address, a server address or a key.

Two bats at once
  Each step that changes the machine takes its turn (/root/capri-kit/kit.lock): a second bat's
  step waits for the first one's, and says what it waits for.  (C2 and C3 started together on
  2026-11-12 both downloaded her voice's Python into the same file at the same moment; one of
  them failed.)

On the machine
  /root/capri-kit/brain/: the brain's program before each update (0600).
  /opt/capri-voice: her voice (venv, capri_voice_server.py, voces\, hf\ her models, selftest\);
  capri-voice.service (user capri-voice, 127.0.0.1:8891, journalctl -u capri-voice: one line per
  line she said -- never the text); /root/capri-kit/voice.json (0600, her voice's private path);
  /root/capri-kit/gate/<role>-<time>/ the gate's files before the kit replaced them;
  /root/capri-kit/nginx/ the site file before every change.
  /opt/open77-xbuniverse-staging/server.jsonc.before-capri-kit-<version>-<time> (and the same for
  /opt/open77-xbuniverse): server.jsonc as it was.  /root/capri-kit/<staging|production>.json:
  what the kit changed, for the put-back.  The new builds sit next to the old ones in each
  server's .open77/mods store (content-addressed; nothing is removed).

About the brain's address
  It is a private path, and it now travels inside the Capri package to every player who joins --
  anybody who joins could find it.  That is why step 3 limits how often one address may ask it.
  If something ever stands in front of nginx (so every request comes from one address), step 3
  refuses rather than throttle every player together.

The compile check
  It never writes into the game folder: the compiler works on copies in kit\_scc\.  If the
  compiler ever opens its own window (an error, a migration), the check closes it at once with
  Cancel and fails, so nothing waits on your desktop.
