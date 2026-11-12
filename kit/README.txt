Capri thinks with the server's brain, for every player (XyberRP and XyberRP Staging)
=====================================================================================

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
  C2-Capri-thinks-with-the-server-on-Staging.bat   LEAVE STAGING FIRST.  Takes the package Staging
      hands out now, adds the script with the brain's address as nginx serves it (checked from this
      PC first) and the migrated scripts, compiles it with YOUR GAME'S OWN Redscript compiler on
      this PC -- the live package first, then the new one; nothing is sent unless it compiles with
      nothing left to migrate -- puts it into Staging's mod store, names it in server.jsonc (kept
      first, the server's own --check-config run), adds the brain's limits, restarts Staging and
      checks what Staging hands out.  Then join Staging from the PC you play on.
  C3-Capri-thinks-with-the-server-on-XyberRP.bat   The same for live XyberRP -- after Staging was
      fine in game.  Nobody may be on XyberRP.
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

On the machine
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
