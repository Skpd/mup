# Bots

AI players: ordinary accounts and characters that start at level 1, play through the same rules as clients and grow
by a career plan. The milestones (B0..B3) are planned here, their status is in the table of `docs/roadmap.md`. As
there: one milestone per session, each ends with its tests passing, a look in the real client and its "Done" notes
here.

## Design

- In process, no socket: a `BotSession` is a connection the game can't tell from a client. `view.py` shows every
  non monster connection as a player, so real clients see bots with no extra packets. Chat, whispers and parties
  already go through `game.playing()`, so bots get them like clients do.
- Input: the bot builds client packets (`CMove`, `CAttack`, `CJoinGame`, ...) and dispatches them through the
  game's handlers like `protocol.py` does, as bytes through `factory`, so a bot's packet is parsed like one from the
  wire. Bots can do nothing a client can't, every server check applies to them.
- Output: `write()` hands the built server packets to the brain. `Packet` keeps its values as attributes, so they are
  typed events (`SDamage`, `SKill`, `SLevelUp`, later trade and party requests) without parsing.
- Perception: the bot's own `Player` (the client knows all of it), the objects in `c.view` (what a client standing
  there has been shown: positions, types, dead or not) and the static data files (game knowledge). Never a
  monster's life, target or path, nothing out of view, nobody else's inventory.
- Brain in three layers:
  - career: hunting grounds derived from data, not hand written. `Monster.txt` levels and `MonsterSetBase.txt`
    spawns grouped by map and area; pick the one near the bot's level. Map progression from the `Gate.bmd` graph
    (entrance -> target, minimum level, MG 2/3). Stat build per class as point ratios. Personality: risk, greed,
    chattiness, play schedule (log in and out in sessions, progress only while online).
  - activity: small state machines (travel, hunt, loot, rest, restock / sell, trade, idle in town) with timeouts,
    picked by priority every few seconds: survive > restock > sell / repair > upgrade > level.
  - motor: walks in segments at the client's pace, `path.find_path` for short paths, flow fields for long ones,
    attacks and casts at the pace the server checks, skill choice by mana and range.
- Driven by the game tick, each bot thinks every 0.5..1 s, staggered. No timers of its own.
- Storage: a migration with `bots (character_id, personality, career state as JSON, rng seed, schedule)`. Bot
  characters are ordinary `characters` rows saved by `GameServer.save`. `bin/account.py` creates bots.
- Bots get items and zen only from the drops, shops and kills players get, nothing out of thin air.
- Players can tell a bot when they ask or trade with it.

Where the code stood when this was planned (M6 done, M7 in progress):
- `GameServer.now` is `loop.time()`, the loop is used for nothing else but `start()`. With a fake clock and players
  standing outside Lorencia the data loads in 0.12 s and 10 game minutes take 0.08 s with 1 player (~7700 times real
  time), 0.5 s with 10 (~1200 times), 1.5 s with 40 (~400 times). The world needs no change to run faster than real
  time, the bots' thinking will be the cost.
- Not repeatable: `Monster`, `GroundItem` and the connections hash by `id()`, so the order of the sets in `ai.tick`,
  `Grid.near`, `find_target` and `dead_monsters` changes from run to run and the `random` draws land on different
  monsters. Measured, see [S0](#s0-fast-tests-and-replay).
- The game state of a connection (`window`, `trade`, `party`, `summon`, `area_casts`, `self_defense`, ...) is set in
  `BaseProtocol.__init__`; a connection without it breaks the tick. Handlers are registered in `bin/gs.py`, a
  simulation can't import them. `BaseProtocol.send_all`, `send_same_map` and `send_near` are unused.
- The server checks reach (3 tiles, bows 8), the attack pace (0.4 s / (1 + speed / 100), bursts of 4), skill mana,
  distance (+ 2) and pace, pick up within 3 tiles: mup's numbers, the client's own timing is a guess (M4). Walks are
  not paced: the position jumps to the walk's end, a walk may start up to 15 tiles from it.
- New characters have no items, wizards know energy ball, elves start in Noria. Gates: Lorencia -> Noria level 10,
  Devias 15, Dungeon 20; Noria -> Lorencia 10.

## Fast tests and replay

Bot behaviour is written and checked in game time, many times faster than real time; any run can be repeated, and a
bot's situation can be saved and played again as a test. S0 builds it without bots, B0 adds them, every B milestone
uses it.

- Clock: `GameServer` reads `now` (and a wall time for schedules) from a clock, `loop.time` by default. A
  simulation's clock moves only when it ticks.
- Same seed, same game: the simulation seeds `random`, each bot has its own `random.Random(seed)` so bot changes don't
  shift the world's draws, sets iterate in a repeatable order (hash by cid / id), no wall clock in game logic. A test
  runs the same seed twice and compares the trace digests.
- `mup/sim.py`: `Sim(seed, config overrides)` is the game with an in-memory database, the manual clock and the
  handlers, with `step()`, `run(seconds)`, `run_until(pred, limit)`; log lines carry the game time. `Puppet` is a
  session for test code: it sends client packets and waits for server packets like `tests/client.py`'s `Conn`, in
  game time. Tests are set up through the GM command functions (`command.level`, `item`, `move`).
- `tests/sim.py`: coded scenarios and the scenario files in `tests/scenarios/`, each running until its check holds or
  a game time limit. A plain script like `tests/client.py`, non zero exit on the first failure, seconds for all of
  it. Behaviour tests use small monster, spawn and drop files like `tests/client.py`; career tests use the real data.
- `bin/sim.py`: long runs and their report (`--bots dk,dw,elf,mg --hours 6 --seed 7 --exp-rate 1`); `--trace FILE`
  (JSONL: game time, bot, activity, event, position, life, target), `--packets BOT` (that bot's packets like
  `log_packets`), `--until T`, `--dump T BOT FILE`, `--grounds CLASS` (the hunting grounds the career picks by level).
- Scenario file (`--dump`): the bot's character (class, level, stats, life, mana, map, position, inventory, skills),
  its `bots` row, the monsters in its view (type, position, life), the seed and the game time. Loading one puts those
  monsters where they were instead of a random spawn spot. Activities aren't saved: the brain picks again by
  priority, as after a relog.
- Debugging loop: the report flags a stuck bot, `--trace` around that time shows why, `--dump` a minute earlier makes
  a scenario that fails, the fix makes it pass, the scenario stays as a test. A whole run is replayed by its seed:
  getting to the hour of the problem takes seconds.
- Fair play checker on what bots send, for what the server doesn't check: a walk starts on the bot's tile, has at
  most 15 steps, doesn't start before the last one ended at the client's pace; one `22` / `26` at a time, nothing
  while item use is locked. Every server refusal of a bot's request (`22` failed, `24` refused, a swing or cast out of
  pace or reach) is counted too: it means the bot's idea of the rules is wrong. Errors in `tests/sim.py`, counts in
  the report.

## S0 fast tests and replay

What B0 needs before the first bot: the game in process on a game clock, the same game from the same seed, clients in
process (puppets) for tests, a player's situation saved and loaded. None of it needs bots.

Done when: `tests/client.py` passes unchanged; `tests/sim.py` passes in a few seconds; the same seed gives the same
digest under different `PYTHONHASHSEED`s; `bin/sim.py` runs 8 hunters for 6 game hours in under a minute, and a
hunter dumped at a game time plays on from its file.

Spike (a scratch script, not kept; M7 in the working tree): `create_gs` from `bin/gs.py` with a fake clock and an
in-memory database, puppets (`BaseProtocol` on a fake transport) hunting outside the east exit of Lorencia through
the real handlers for 30 game minutes, a sha256 of every byte written to them:
- As the code is, the same seed is a different game every run: 5 runs, 5 digests, 3 different sets of levels.
  Monsters, ground items and connections hash by address, sets of them iterate in another order and the `random`
  draws go elsewhere.
- With `Monster` hashed by cid, `GroundItem` by id, the connections by cid and Devil Square's schedule on a wall clock
  derived from the game clock: 5 runs under `PYTHONHASHSEED` 1..5, one digest; another seed, another digest. Every
  draw already goes through `random` (functions take `rng=random`), seeding it is enough.
- Speed: 30 game minutes in 0.3 s with 1 puppet (~6300 times real time), 1.3 s with 8 (~1400 times), 74 s with 40 on
  one spot (24 times). In the profile the puppets' own A* (budget 400 every 0.4 s, mostly towards monsters they
  couldn't reach) took 17 of the 25 s, the monsters' AI 2.3 s. Pathing is what bots have to keep cheap.
- A new account costs 25 ms (`hash_password`, scrypt). `tests/client.py` takes 68 s, 2 s of it CPU: the rest is
  waiting for game time.

Steps (each leaves something that runs and is tested; after 4 is a stopping point if the session runs out):

1. Sessions and dispatch, no behaviour change:
   - `mup/server/session.py`: `Session` with what the game keeps on a connection (everything `BaseProtocol.__init__`
     sets but the buffer and the crypto), `write`, `disconnect`, `tag`, hash by cid. `BaseProtocol(Protocol,
     Session)` keeps framing, crypto and the packet log. The game never touches the transport (only the connect
     server's `server_info` handler disconnects).
   - `ServerBase.dispatch(c, packet)` out of `BaseProtocol.packet_received`: factory, handlers, the exception log.
   - Handler registration out of `bin/gs.py:create_gs` into `mup/server/handlers.py` (`register(gs)`).
   - The unused `send_all`, `send_same_map`, `send_near` go. Handler type hints to `Session` (mechanical, may wait).
2. Clock: `GameServer(loop, config, clock=None)`. A clock gives `now()` (game seconds, `loop.time` in the server) and
   `wall()` (epoch seconds, `time.time`). Devil Square's schedule and the trade log's time read the game's wall time;
   a simulation's is a fixed date plus the game time. The ping handler keeps the real time, puppets don't ping.
3. Repeatable order: `Monster` hashes by cid, `GroundItem` by `0x10000 + id` (ground ids 0..999 are monster cids
   too), `Session` by cid, `Party` by a number from a counter on the game, with a comment why. Nothing else the tick
   iterates hashes by address (`dead_monsters`, `affected`, `parties`, grid cells, `c.view`; the other sets hold
   ints).
4. Accounts without a password: `AccountRepository.create(name, None)` stores `!`, which `check_password` already
   refuses. No scrypt, nobody logs in with it. Puppets now, bots in B0.
5. `mup/sim.py`:
   - `Sim(seed=0, **config)`: seeds `random`, `Config(db_path=':memory:', ...)` with the overrides (test monster,
     spawn and drop files), the game with `handlers.register` and a manual clock. `step()` (one tick),
     `run(seconds)`, `run_until(pred, limit)` (game seconds; past the limit an `AssertionError` with the last
     packets, like `Conn.recv_until`). Log lines carry the game time (a logging filter).
   - `Puppet(Session)`: a client in process. `send(packet)` dispatches a built client packet as bytes through
     `factory`, like the wire; what the game writes lands in `inbox` as typed packets; `recv_until(pred, limit)` runs
     the game until one matches. Builders for what `tests/client.py` packs by hand (`CMove` from steps).
   - `Sim.enter(name, class, map, x, y, level=1)`: a character on an account without password, in game through
     `CJoinGame`. Level, items, zen and places through the GM command functions (`command.level`, `item`, `zen`,
     `move`, `heal`), so a test is set up the way a GM would.
   - `Hunter`: a puppet that hunts (the spike's: the nearest monster in view, a short A* towards it, a swing every
     0.4 s), the stand-in for bots until B0. `Sim.digest()`: sha256 of everything written to the puppets in order.
6. Scenarios: `Sim.dump(c, path)` writes JSON: the character as stored (row, items, skills), the monsters within view
   range (type, cid, position, home, life), the seed and the game time. `Sim.load(path)` makes a game with that
   seed, puts those monsters there (a `monster.place` next to `spawn`) and the character in game. AI targets and
   paths aren't kept, monsters look around again. B0 adds the bot's row.
7. `tests/sim.py`, a plain script like `tests/client.py` that stops at the first failure:
   - repeatable: hunters twice with one seed give one digest, another seed another;
   - game time instead of waiting, with test monsters: killed by the hound and back in town 3 s later, a spider back
     after its regen time, a drop only the killer's for 10 s and gone after 60 s, regeneration, a Devil Square round
     started through `command.devil_square_now` up to its ranking;
   - a dumped scenario loads and plays on.

   Checks read packet attributes, the raw offsets stay `tests/client.py`'s job.
8. `bin/sim.py`: `--players N --hours H --seed S --exp-rate R` with hunters and a report (levels, kills, deaths,
   packets, game minutes per second), `--until T --dump NAME FILE`, `--load FILE`, `--digest`, `--profile` (the
   slowest functions). B0 puts bots in the hunters' place and adds the trace, the fair play checker and the bot
   report.

Maybe later: `tests/client.py`'s server on a faster clock (a config factor) to cut its 66 s of waiting.

Done:
- `Session` (`mup/server/session.py`) holds what the game keeps on a connection; `BaseProtocol` is the network one,
  `Puppet` the in-process one. `ServerBase.dispatch`, `mup/server/handlers.py` (`bin/gs.py` calls `register`), the
  handlers take a `Session`. The unused send helpers are gone.
- `GameServer(loop, config, clock=None)`: `Clock` (the loop's time, `time.time()`), `now` and `wall_time`; Devil
  Square's schedule and the trade log read `wall_time`. `Monster`, `GroundItem`, `Session` and `Party` (numbered by
  `GameServer.party_numbers`) hash by number. `AccountRepository.create(name, None)` stores `!`.
- `mup/sim.py`: `Sim(seed, start, **config)` (tick counted, so no float drift; game errors logged during a run raise
  at the next `check`), `Sim.enter(name, class_type, at, level, cls)`, `Puppet` (`send`, `inbox`, `recv_until`,
  `of(cls, **values)` predicates), `Hunter`, `Sim.digest`, `Sim.dump` / `Sim.load` (character row, skills, items, the
  vault, the living monsters in view range; `monster.place` puts them back, the others in range die). `CMove.of`
  builds walks.
- Hunters taught something for B0's hunting grounds: monsters respawn anywhere in their spawn area (the east exit's 45
  spiders share x 180..227, y 90..245), so hunters that stay within 20 tiles of where they started had killed
  everything near after 30 game minutes and found nothing for hours. They roam now (within 64 tiles of home, out of
  town first after a death).
- `tests/sim.py` (tests/client.py's world, 2 s): repeatable (one digest twice, under another `PYTHONHASHSEED`, another
  for another seed), a walk seen by another puppet, the hound's kill and the respawn 3.0 s later, a spider back after
  its regen time, a drop the killer's for 10 s and gone after 60 s, regeneration, a Devil Square round from Charon to
  Noria, a scenario dumped and played on.
- `bin/sim.py`: 8 hunters for 6 game hours in about 30 s (~700 times real time), the profile led by the monsters' AI
  (`Grid.near`) and the paths; `--until 1:30 --dump Hunter3 FILE`, then `--load FILE` plays it on, the same digest
  each time.
- Left for B0: the trace, the fair play checker, `--packets` for one puppet. Guild membership isn't in scenarios.

## B0 bots: session, hunting, levelling

The session, hunting from data, levelling with the class build, on top of S0.

Done when: the test's client sees a bot appear, walk, attack and kill; the simulation takes bots of all four
classes a few levels up without getting stuck; the real client watches a bot hunt outside Lorencia.

Steps (each leaves something that runs and is tested; after 3 is a stopping point if the session runs out):

0. Capture, in the real client with `log_packets = yes`: walk long straight lines, hold the attack on a monster with a
   knight, cast energy ball over and over with a wizard, drink potions back to back, go through the Noria gate. From
   the log: ms per tile, the attack and cast intervals and the `0E` speeds, the potion interval, the time from `1C` to
   `F3 12`. Into `mup/bot/motor.py` and the doc, marked traffic; it also checks M4's pace guess. Until then the
   server's own pace and a placeholder walk speed.
1. Storage: a migration for `bots`, `mup/repository/bot.py`. `bin/account.py bot create NAME CLASS [--seed N]`,
   `bots`, `bot delete NAME`: an account without password (S0), its character through `character.new_character` at
   the class's start gate. `[bots] enabled = no` in `config.ini`.
2. `mup/bot/session.py` and `mup/bot/manager.py`: `BotSession`, a S0 puppet driven by a brain: its cid from
   `add_connection`, `acc` set, `CJoinGame` dispatched; its packets also in the packet log under its cid when
   `log_packets` is on. `BotManager`, called from the tick: the motor every tick, the brain every 0.5..1 s staggered,
   logins at start (the schedule later), bot state saved with the character. Test: a puppet gets `12` when a bot
   logs in, `14` when it logs out.
3. Motor (`mup/bot/motor.py`): `CMove` segments of at most 8 steps, the next when the last ended at the client's pace;
   `find_path` for short paths, per map flow fields for long ones (distance from a target area over the walkable
   tiles, about 65 000 per map, cached per map and target: gates, towns, hunting grounds; the bot walks downhill).
   Facing, swings at the server's pace, `19` casts with the client's mana and distance checks. Gates: walk into the
   entrance area, `1C`, `F3 12` after the answer. Test: from Lorencia to the Noria gate, refused at level 1, through
   at level 10, no checker errors.
4. Career (`mup/bot/career.py`): spawns laid on 16 x 16 tile cells per map (area spawns spread over their walkable
   tiles, single ones on their spot), counted by monster level. A cell's score for a bot: monsters in its level band
   and their density, minus danger (their damage against the bot's defense and life, `stats.py` values), travel (flow
   field distance) and the players already there; only maps the gate graph reaches at the bot's level. Class builds
   as point ratios spent with `F3 06` (mup's choice, e.g. knights strength / agility / vitality). `bin/sim.py
   --grounds` prints the picks. Tests: a level 1 knight hunts near Lorencia, a level 1 elf in Noria.
5. Brain (`mup/bot/brain.py`, `mup/bot/activity.py`): activities with timeouts, picked by priority (survive > spend
   points > level):
   - travel to a place, on the map or through gates;
   - hunt: a monster in view, in the band and reachable; approach, swing or cast until its `17`; a target it fails to
     reach a few times is left alone for a while;
   - rest: below the personality's life threshold, away from monsters or in the safe zone until regenerated;
   - dead: wait for `F3 04`, then travel back;
   - spend points.

   Trace events for every pick and its outcome, a stuck watchdog (no exp and no movement for N game minutes).
   Scenarios with the test monsters: kills a spider, rests at low life, dies to the hound and comes back, gives up on
   an unreachable monster, spends points on a level up, a wizard casting until out of mana.
6. `bin/sim.py` with bots instead of hunters, the report (level per hour per class, kills, deaths, time per
   activity, stuck count, checker errors and refusals), the trace, the bot row in dumps, the fair play checker. Tune
   until the four classes gain a few levels on several seeds without stuck flags.
7. Done check: the last server start of `tests/client.py` enables bots with one made by `bin/account.py bot create`;
   the client sees its `12`, a `10` walk, an `18` swing and the `17` of a monster it killed. Then the real client
   watches a bot hunt outside Lorencia.

Done:
- Step 0 from the real client's logs already in `logs/` (2026-10-08), no new capture: a knight holding the attack
  swings every 0.75..0.77 s at attack speed 32 (`0E`), the bots' swing is 1.0 s / (1 + speed / 100), the server's
  shape fitted to it; walks re-sent while walking put a tile at 0.25..0.3 s (rough), the bots walk 0.3 s a tile. In
  the doc, marked traffic. Casts, potions and gates aren't in the logs: casts take the swing's pace, `F3 12` goes 1 s
  after the `1C` answer, placeholders in `mup/bot/motor.py`. The server's attack pace (M4) allows 2.5 times the
  client's.
- Storage: migration 7 `bots (character_id, seed, personality, career, schedule)`, `mup/model/bot.py` (`Bot`,
  `Personality`: risk, rest below / until, drawn from the seed), `mup/repository/bot.py`. `bin/account.py bot create
  NAME CLASS [--seed N]`, `bots`, `bot delete NAME` (`mup/bot/account.py`: an account of its name without password,
  the character at the class's start gate). `bots_enabled = no` in `config.ini` (`[bots]`, the config is flat).
- Session: `LocalSession` (`mup/server/session.py`) is what `Puppet` and `BotSession` share: packets as bytes
  through `dispatch`, typed packets in the inbox, both in the packet log under the cid, a `tap` for the simulation's
  digest. `BotManager` (`game.bots`, made by `bin/gs.py` when bots are enabled and by every `Sim`) logs bots in with
  `CJoinGame`, runs them first in the game tick (the inbox to the brain, the brain when it is time, the motor),
  `Session.saved()` stores a bot's row with its character. `Sim.bot(name, class, at, level, seed, brain)`, dumps
  carry the bot row and load as a bot.
- Motor: walk segments of at most 8 steps (4 towards a target), the next one when the client would have walked the
  last; attack orders walk into reach (next to it, a skill's distance) on a path of at most 40 steps and swing or
  cast at the client's pace, the weapon when the mana runs out; a walk ending on an entrance gate sends `1C` when the
  level allows (the client's rule, at most every 3 s, one until the answer), `F3 12` after the map change. Flow
  fields (`mup/bot/flow.py`): a BFS over the tiles a bot walks on (entrance gates left out unless they are the
  target), 0.03 s for Lorencia, kept per map, target and blocked cells (64).
- Career: the spawns on 16 x 16 cells (1589 cells with monsters, 0.3 s once per game). A `Fight` per monster type
  from the client's formulas (hit chance, damage less defense, the client's pace, the damage of monsters that look
  for players, the regeneration). A ground's worth is the exp per second of its best band of monster types (the
  types added while they raise it, so slow kills don't drag the average), the cells around counting half, capped by
  the respawns, the walk there weighed over 300 s. Deadly cells (a monster around that would take 80% of its life
  in a fight) are left out and kept out of: travel, approaches, roaming and flights go around them. Builds:
  knights 5/2/3/0, wizards 1/2/2/5, elves 3/4/2/1, gladiators 4/2/2/2 (str/agi/vit/ene). `bin/sim.py --grounds
  CLASS`: without items every class hunts spiders up to level 10, budge dragons join around 15, knights and
  gladiators move to bull fighters around 40. Only the bot's own map: the gate graph is there
  (`career.reachable_maps`), travelling it is B1's.
- Brain: priorities dead > escape > rest > points > level (travel, hunt, idle). Escape was added: a monster hitting
  it that it can't afford, or one that would kill it about to notice it, makes it run to town when near, else out
  of the monster's chase (twice its view range); rest flees the same way, then stands. It picks only fights it has
  the life for, never a target near a monster that would kill it. Perception: its character, `c.view`, its packets
  and the data; a monster's attack is a `18` swing next to it (the client doesn't read the `18` target). A ground is
  given up after 180 s without a kill, 2 deaths or 5 escapes there; a target after 90 s, after 3 failed paths for
  120 s. Watchdog: 300 s without exp or a step while travelling or hunting. The ground it hunted on is kept across
  logins while it is worth 90% of the best.
- Checker (`mup/bot/checker.py`): errors for a walk not from its tile, over 15 steps or before the last one ended,
  a swing or cast while walking; refusals for a walk the server stopped, a swing or cast the server didn't pace
  (its attack clock didn't move), a `1C` that moved nothing, a point not taken.
- `bin/sim.py`: bots instead of hunters, the report (level per hour, kills, deaths, stuck, errors, refused, time per
  activity), `--trace FILE` (JSON lines: time, bot, activity, event, map, position, life, target and the event's
  values), `--packets BOT`, `--until T --dump BOT FILE`, `--load FILE`, `--grounds CLASS`, `--digest`, `--profile`.
  4 hours at exp rate 1 on seeds 1, 2, 3: knights 6..8, wizards 8..9, elves 10, gladiators 7..8, none stuck, no
  errors, nothing refused, 1..10 deaths per bot, about 650 times real time. 8 bots for 6 hours: 60 s.
- `tests/sim.py` (9 s): the bots' digest is repeatable, a puppet sees a bot's `12` and `14`, the motor to the Noria
  gate (127 steps in 38 s), no `1C` at level 1, through at 10 with `F3 12`; on the real data a knight hunts near
  Lorencia, an elf in Noria; the test world: kills the spider and rests, dies to the hound and goes back to a ground
  away from it, leaves alone a spider behind a wall, spends points by its build, a wizard casts until out of mana;
  four classes level for 10 minutes at exp rate 10; a bot's scenario plays on. None breaks the client's rules.
- `tests/client.py` ends with a bot: `bin/account.py bot create`, the game server restarted with bots enabled, a
  client sees its `12`, a `10` walk, an `18` swing and the `17` of the monster it killed, its `15` in the packet
  log under its cid.
- Left: the real client watching a bot hunt outside Lorencia. Without potions bots rest 10..45% of the time and
  wizards and gladiators die most (B1). The pace of casts, potions and gates still to capture.

## B1 bots: items, skills, map progression

Without town trips: selling, buying and repair come in B1b.

Done when: a bot left alone (a knight, wizard or gladiator; elves start in Noria) goes from Lorencia to the next map's
hunting ground with better gear than it started with: same seeds in the simulation, then once in the real client.

Steps:

1. Gear (`mup/bot/gear.py`): the inventory is the bot's own `Player.inventory`, kept in step by the answers (`22`,
   `24`, `28`, `2A`). Wearable by `inventory.can_wear` and the requirements (what the client shows red). A piece's
   worth: the damage, defense and speeds `stats.py` gives with it worn against without it (the client's formulas,
   what its character window shows); an item at 0 durability gives nothing.
2. Loot: after a kill, the drops in view (`20`): zen, potions, upgrades, items the build will soon wear, scrolls and
   orbs the class can learn, jewels. Walk within 1.5 tiles, one `22` at a time until its answer; an item refused in
   its owner time is tried once more after it. Nothing to sell yet: with the grid full the least worth is dropped,
   never what is worn. Test: a spider with fixed drops (sword, potion, zen) is picked clean.
3. Potions: `26` below the personality's life threshold, then wait for the unlock and the potion interval (step 0 of
   B0); mana potions for wizards. Potions don't stack yet (M5), each takes a slot; keep a few, they move the rest
   threshold. Test: hit by the dragon, drinks, `28` after the last one.
4. Equipping: `24` into a free slot, or the worn piece to the grid first; two-handed weapons, shields and ammunition
   by the server's rules; the old piece kept only if it is still worth something. Weapon skills follow the server's
   `F3 11`. Test: picks up the sword, wears it, a puppet gets `25`.
5. Requirements steer the build: an upgrade in the inventory whose missing points fit in the next few levels gets
   them first.
6. Skills: learn looted scrolls and orbs (`26`); pick by mana, distance and targets: single (`19`), area (`1E` with
   the `1D` report of what its effect hits, at most 5 targets per effect, like the client), the elf's heal and buffs
   on herself, her summon, knights' weapon skills. Elves fight bare handed until a bow and arrows drop and while the
   arrows last; buying them is a town trip. Test: a wizard learns a scroll from a fixed drop and uses it.
7. Map progression: when the best ground is on another map, travel along the gate route (a search over the
   entrances and their levels); respawn town by map; back to the previous map after repeated deaths. Test: a level
   10 bot whose only ground in the test data is in Noria gets there.
8. Optional: jewels of bless on the best worn piece up to +6, soul by the personality's risk; jewels are kept for
   trading in B2 otherwise.

Done:
- Gear (`mup/bot/gear.py`): a piece's worth is the share of exp per second it adds in the career's fights against
  the bot's band (its values with the piece worn against without, `gear.trial` with the weapon skills the server
  would grant); the raw values (the damage of the hands it hits with, wizardry, defense, a quarter of the defense
  rate, half the speeds) break exact ties only. That makes it an order: a first mix of both, relative to the outfit
  it started from, went round in circles (an empty left hand prefers the axe, the axe the shield, taking the axe off
  for the shield empties the hand). A bow without arrows gives nothing, one with its arrows in the grid is worn with
  them. Keeping values: an upgrade its share (at least 0.01), one it can wear within 3 levels half of that, potions
  0.2 while it has fewer than 4 of the kind (mana potions once a skill takes mana), a scroll or orb it can learn
  within 3 levels 1, jewels 0.5, arrows and bolts 0.2 for the classes that wear bows, zen 0.05; the rest is junk.
- Activities (priority items, between points and level, only with no monster at it): loot, the nearest item worth
  something within 12 tiles and not where a deadly monster would notice it, one `22` at a time, a full grid drops its
  least worth item first when that is worth less, a refused one is tried once more after the owner time; equip,
  scrolls and orbs it can learn (`26`), then the best change of its grid one `24` at a time, what leaves a slot goes
  to the grid when it is still worth something and there is room, else on the ground (`23`). The motor holds the
  item requests: the pick up order walks next to the item (the client's 1.5 tiles), one `22` / `24` until its
  answer, no `26` or `24` while item use is locked, 0.5 s from the unlock to the next `26` (a placeholder).
- Potions: a reflex at every think, in a fight below the personality's `potion_below` (0.3..0.5, drawn after the
  older values so a seed keeps them): the healing potion that gives most without going over, the elf's heal instead
  when she has it and the mana; a mana potion when its skill lacks the mana in a fight (what the client does on its
  own). Healing potions lower the rest threshold, by half with 4.
- Build: `gear.goal`, the stats the most worth piece, scroll or orb of its grid asks for that it can use within 3
  levels, gets the level up points first (`career.next_point(p, goal)`).
- Skills: the career counts weapon skills (the weapon's damage times 200 + energy / 10 % for knights, / 30 for
  gladiators, paced as swings) and the mana: over a hunt only the casts its regeneration allows, the weapon in
  between; one fight starts with half its mana. "ok", "deadly" and "fit" are about one fight, the exp per second
  about the hunt (the long run alone made a level 1 wizard's fight with a budge dragon deadly: 26 s). `Brain.skill`
  picks per target the most damage per second it has the mana for now, an area skill counting the monsters within
  3 tiles of the target (5 at most). Area: `1E` at the target, the `1D` report 0.4 s later with the monsters in view
  within 3 tiles of the point (both placeholders within the client's 0.8..3 tiles). Weapon skills send the client's
  `10` turn first. The elf, while she hunts: her best summon when she has none, greater defense and damage when they
  ran out, on herself (`19`).
- Map progression: `Flows.routes` searches the entrances its level allows (Dijkstra, a gate counts 13 steps for its
  `1C` and loading), around the cells it keeps out of on its own map. The pick ranks the grounds of every map the
  gates reach: on another map the walk is the route and the steps from the arrival area around that map's deadly
  cells (but the arrival area's own), weighed against 1800 s of hunting (300 on its map), and the ground has to be
  worth 1.1 times the best of its own map. On a map it came to it stays 20 minutes while it finds a ground there; 3
  deaths there send it back where it came from, the map left out for 30 minutes and 2 levels. Travel walks down the
  field to the first gate of the route, the motor goes through, on the next map it walks on from where it arrived.
  The respawn town is the server's by map, the bot picks from where it comes back.
- Found on the way, B0's model: `career.fight` divided by zero at an attack rate equal to the defense rate (no hits
  by the server's rule); the hunt's give up never fired when the hunt ended by roaming off its ground and started
  again (the last kill is kept per ground now, 90 s); a ground is a 16 x 16 cell but a monster killed there respawns
  anywhere in its spawn area, mostly away: the bot's own kills on a ground in the last 10 minutes count against it
  like other hunters sharing the respawns (with gear the elf emptied its cell and roamed); every real monster looks
  for players, those it can't fight dilute a ground's worth (excluding the ground left level 1 characters nothing,
  budge dragons are near every spider); targets out of reach of the tiles it walks on are skipped; after looting it
  hunts on where it stands when that is near its ground.
- Arrows and bolts, the first piece of B1b's town trips: a bow or crossbow is weighed with a stack of its
  ammunition (`gear.armed`, it can be bought), so an elf picks one up when it would shoot better with it; without a
  bow arrows are junk. Restock (priority items): with a bow it may wear and would use, fewer than 60 shots and the zen
  for a stack, it walks to the nearest shop that sells them (the shops' goods and the NPCs' spots are the game's
  data: Amy in Lorencia, Elf Lala in Noria, Isabel in Devias; another map's through the gates), talks to the NPC
  from next to it (`30`), buys from the list the shop showed it (`31`) up to 4 stacks (`32` one at a time), of the
  best level of which 4 cost at most half its zen (70 / 1200 / 2000 zen a stack of arrows +0 / +1 / +2), and walks
  off (the client sends nothing when a shop closes, the server closes it 5 tiles away). Equip wears the arrows and
  the bow; a spare stack goes into the empty hand when the worn one runs out (the client does that itself). A trip
  that failed waits 5 minutes. The checker: a `30` from more than a tile, a `32` without a shop open or before the
  last one's answer are errors, a buy that bought nothing is refused. The motor shoots from the client's reach now
  (`0x4650a0`, in the doc): 1.8 tiles, 2.2 with a spear, 6 with a bow or crossbow. On the real data the elf's build
  (strength 3 : agility 4) makes the short bows of Noria's spiders and goblins worth less than a small axe: it
  picks up the first bow that is better (seed 3, 4 hours: a short bow before any axe, arrows bought twice, then a
  short sword and the bow dropped). Test: an elf with a short bow and 1000 zen buys 4 stacks of arrows from Amy,
  wears both and shoots the spider.
- Stuck for good, found by an elf left alone for 24 hours (seed 1, from 17:45): a Hunter (attack range 4) stood on
  the tiles of Noria's gate to Lorencia and shot the elf on the arrival area. Bots don't step on a gate they don't
  take, so no path reached it; it was left alone after 3 tries, but an attacker came first whatever was left alone:
  a failed path every think, no step, no exp (the watchdog's new ground put it back on the same attacker). An
  attacker is chosen now only when it isn't left alone and a tile the bot walks on is next to it; one hitting it
  that it can't get at is a danger, it runs out of range. 24 hours of that elf: level 28, never stuck. Test: an
  archer on the gate's tiles, the bot runs.
- `tests/sim.py` (10 s): the spider's sword, potion and zen picked clean and the sword worn, a puppet gets the `25`;
  with a grid full of junk it drops some for the sword;
  two drinks hit by the dragon, `2A` then `28`; a wizard learns fire ball from the spider's scroll and casts it; a
  knight with a leather helm puts its points into strength and wears the helm at level 3; a wizard with flame casts
  it at the goblins and reports them in `1D`; a level 10 bot whose only ground is in Noria goes through the gate and
  hunts there; shot by an archer on a gate's tiles, it runs. None breaks the client's rules. In `tests/client.py`
  the bot hunts the test dragons, which drop nothing: a GM drops a short sword there, the client sees the bot wear
  it (`25`), its `22` and `24` are in the packet log under its cid. On the real clock the checker found a walk
  "0.00 s before the last one ended": the motor works with the tick's time, the session read the clock again when
  it sent; a bot's packets carry the tick's time now.
- `bin/sim.py`: the report has the items, zen, potions, skills learned, pieces worn, refused pick ups of others'
  drops ("owned"), what it wears and the maps it went to with the game time; `--grounds` the best ground of each map
  the gates reach. 4 hours at exp rate 1, seeds 1..6, the class averages from B0 to B1: knights 7.2 -> 13.0,
  wizards 8.2 -> 11.7, elves 9.0 -> 10.8, gladiators 7.0 -> 15.2; no errors, nothing refused, 1..7 deaths per bot.
  Done check: a gladiator alone (seeds 1, 2, 3, 6 hours) goes from Lorencia to Noria at 3:35..4:08, at level 15 or
  so, wearing a kris or two axes, a helm, gloves and boots it looted. Knights and wizards alone stay in Lorencia up
  to level 15..17 in 6 hours: for them Noria is at most about 10% better, under the margin (8 bots on seed 1, 6
  hours: a knight goes too, at 3:18, sharing its grounds with another). About 470 times real time with 4
  bots (B0 650), 8 bots for 6 hours in 88 s (B0 60 s): the flow fields per set of deadly cells and the loot.
- Left: the real client watching a bot loot and wear, and a gladiator through the Noria gate. Step 8 (jewels) isn't
  done, jewels are kept. Arrows don't drop in this data (`Item.txt`), so elves never get to use a bow. Gladiators
  still die in Noria's north where two or three hunters come at once (a try counting all the attackers against the
  life left looped at the edge of town and was taken out). The pace of casts, potions, gates and area effects is
  still to capture.

## B1b bots: town trips

After B1, shops are there since M5.

- Sell what is worth less than its slot, buy potions and arrows / bolts (arrows and bolts are done, B1), repair below
  a durability share (M5 wear), the vault for what the bot keeps but doesn't carry.
- Restock as an activity between survive and level: low on potions, arrows or durability, or a full grid, walks to
  the nearest town's NPC, talks (`30`), buys / sells / repairs, walks off (the client sends nothing when a shop
  closes), goes back to its ground. B1's `Restock` (arrows and bolts) is the start: the walk to an NPC, the talk,
  the list the shop shows (`31`), one `32` at a time.
- Upgrades from the shops: what each NPC sells is the game's data (the shop files, as players know it), priced by
  the client's formula (`shop.value`). Each piece weighed by `gear.value` against its price; a budget keeps zen for
  potions and repair; a trip for the best affordable upgrade when it adds enough, or on the way of a restock.
- Elves as archers: Eo the Craftsman (Noria's town) sells bows and crossbows with their skill, luck and + 4 damage
  (Short Bow 600, Crossbow + 1 1900, Bow 2400, Golden Crossbow + 3 17 300, Elven Bow + 2 19 200, Arcubus + 3 36 700,
  Battle Bow + 3 57 900), Elf Lala the vine, silk and wind sets + 0..+ 3 with luck and an option. Three changes to
  the career and gear so a bow is worth what it is:
  - the build agility first, e.g. 1 : 6 : 2 : 1 (measured in B1: better with melee weapons too, agility counts for
    an elf's damage either way and gives speed and defense; 13.0 against 10.1 exp/s with a hand axe at level 10);
  - the bow's skill: multiple arrow (24, an area skill, radius 6, 5 mana) counted in the fight model with the
    targets it would hit by the ground's density (the model counts single target skills only, the brain already
    uses area skills in fights), or count how many arrows hit a single target (increasing damage);
  - the reach: shooting from 6 tiles, less walking to the next monster and fewer hits while one comes.

Done when: a bot that runs out of potions walks to town, sells its junk, buys potions, repairs and goes back to its
hunting ground; an elf with the zen buys a bow with its skill from Eo and hunts with it.

Where B1 left it (seed 1, 4 bots, 6 hours at exp rate 1): the bots carry 2 600..11 500 zen and nothing to spend it on,
their weapons are at 3..8 of 18 durability (the values drop from half), they drink 6..19 potions in 6 hours (what
they loot), the elf carries two short bows she never shoots. A wizard died 41 times, 25 of them at the east exit of
Lorencia where a lich (level 14, reach 4) chased it to the town's edge and stayed: each walk out ran into it.

Steps:

1. Gear (`mup/bot/gear.py`): a sale worth for what it doesn't use, the client's sell price per tile of the grid
   (under any use, from 50 zen), so it picks up junk worth selling and keeps old pieces to sell; potions while it has
   fewer than a stock of 9 (3 stacks of 3), the rest threshold as before with 4. The item bytes of a list (`31`)
   read back into items.
2. Motor and checker: `33` one at a time until its answer, `34` (all, or one piece), `24` into the vault's window
   until its answer and `82` to close it. Checker errors: a `33` or `34` without a shop open (a repair at a smith's),
   a `24` into a vault that isn't open; refusals: a sale or repair that changed nothing.
3. Town (`mup/bot/town.py`): errands from what it carries and the game's data (the shops' goods, the smiths, the vault
   keepers, their spots): sell (any shop), repair (Hanzo, Zienna, Eo), potions (the shops that sell them: the
   healing potion that gives the most life per zen of what it lacks when it drinks, but at least a fifth of its
   life; mana potions for skills that take mana), arrows and bolts (B1's), an upgrade (step 4), the vault (jewels,
   kept for B2). A trip is due for: no or one healing potion left with the zen for a stack, a worn piece at half its
   durability with the zen to repair it, a grid nearly full of what it sells or stores, its ammunition (B1), an
   upgrade worth a trip. On a trip it does every errand of the town it goes to: tops up its potions, repairs what is
   worn a tenth, sells all its junk, buys the best upgrade it can afford, stores its jewels. Budget: repair, then
   potions, then ammunition, then upgrades.
4. Upgrades from the shops of its map: each piece it may wear now or within 3 levels weighed by `gear.value` (a bow
   with its arrows) against what is left of its zen after the budget; a trip for one that adds 5%, any along with
   another errand. Kept until its items, values or level change, or a minute.
5. `Trip` (replaces B1's `Restock`): the stops in order, nearest first; at each it walks next to the NPC, talks (`30`),
   sells, repairs, buys (one request at a time), stores and closes the vault (`82`), then the next. Done, it hunts
   again (wears what it bought first). A trip that failed or left an errand undone waits 5 minutes. Tests: a knight
   out of potions with junk, a worn sword and a jewel sells, repairs, buys potions, stores the jewel and kills the
   spider again; a knight with zen buys a weapon from Hanzo and wears it.
6. Elves as archers: the build agility first (1 : 6 : 2 : 1); the reach in the career's fights: the monsters that come
   at it walk the reach less their own while it shoots (fewer hits), the walk to the next monster is shorter. Test:
   an elf with the zen buys a bow from Eo and arrows from Elf Lala, wears them and shoots.
7. `bin/sim.py`: trips, sold, bought, repairs, zen spent in the report; runs on several seeds without errors or
   refusals, the elf with a bow from Eo. `tests/client.py`: the bot made with `bin/account.py` gets zen (in the
   database) and buys potions from Amy (its `30` and `32` in the packet log under its cid).
8. If the session allows: the wizard's deaths at the east exit (travel around a monster that would kill it in view).

Done:
- Gear: what a bot doesn't use is worth its sell price per tile (`gear.sale`, under any use, from 50 zen), so it picks
  up what sells and keeps a piece it takes off to sell it; potions up to a stock of 9, the rest threshold as before.
  `gear.decoded` reads the item bytes of `31`. `best_change` ranks its candidates by the order `gain` makes (the exp
  per second, then the raw values): an elf with two round shields, one with an option, took one off and put the
  other on 6 400 times (with the hand empty both add the same exp per second and the first by slot won, the plain
  one). `gear.power` counts the walk to the next monster (8 tiles, less what a bow's reach adds), the career's
  fights the reach (a monster that comes at a bow walks the reach less its own first, shot all the way). A level 15
  elf with a short bow and its option: 10.2 exp/s, 7.6 with a hand axe (before: 17.9 and 22.2). Elves 1 : 6 : 2 : 1.
- Motor and checker as planned: `33` and `24` into the vault's window one at a time until the answer, `34` (the
  server answers only what it did), `82`; errors for a sale or repair without the shop (a smith's) open, a move into
  a vault that isn't; refusals for a sale or repair that changed nothing. The motor keeps what a buy, sale or repair
  cost, for the report.
- Town (`mup/bot/town.py`) as planned, with: upgrades only of the shops of its map and that it can wear now (an elf
  bought a crossbow +1 it could wear in 3 levels and carried it); ammunition is due only when the zen left after
  the repair and the potions pays for a stack (trips for arrows bought potions and ended undone); healing potions
  are never sold, nor what the trip buys (an elf bought arrows for the bow she was about to buy and sold them right
  back, 67 times). Potions: apples to about level 15 (the most life per zen of those that give a fifth of its life),
  small healing potions after; mana potions along for the skills.
- Trip (`mup/bot/activity.py`, replaces `Restock`) as planned. The walk to an NPC ignores the deadly cells around it:
  Amy stands outside Lorencia's north wall, the cell of the passage gets bull fighters, deadly under level 10, and
  every trip to her failed ("no way there"); it also counts them from where it stands (after Amy the walk to Hanzo
  started inside one). Two escapes on the way make the trip wait like a failed one (a bull fighter near Amy: 940
  trips picked and dropped in a row).
- Found on the way: the hunt's 90 s without a kill counted from the last kill, so the walk back from town and the
  rests used them up and fresh grounds were given up at once; it counts hunting time only now (`Brain.hunted`). A
  knight that fled into a pocket closed in by deadly cells found no ground and stood idle 49% of 6 hours: `Idle`
  walks to the safe zone through them. A bow without arrows left an elf unable to hit back while spiders hit her,
  equip waited for no monster at her and her flight never moved (the hunt's attack order kept the motor busy): 2
  hours of escapes in place. The bow comes off at once now (or a stack goes in the hand), a flight drops the attack
  order. The wizard's deaths at the east exit (step 8) didn't come back: in that run (seed 1, the bots named Botdk,
  Botdw, ...) it dies 4 times instead of 41, at level 17 instead of 9.
- `tests/sim.py` (12 s): the arrows test buys potions along now; a knight out of potions with two pad gloves, a sword
  at 5 of 22 and a jewel walks to the vault keeper, Hanzo and Amy, stores the jewel and closes the vault (`24` to
  window 2, `82`), sells the gloves (`33`), repairs all (`34 FF 00`), buys apples with the rest (`32`), the zen adds
  up, and kills the spider again; a knight with 3 000 zen goes to Hanzo for an upgrade and wears it; an elf of level 8
  with 3 000 zen buys a short bow from Eo and 4 stacks of arrows from Elf Lala and shoots the spider; an elf whose
  arrows ran out, hit by the dragon, takes her bow off and kills it. None breaks the client's rules.
  `tests/client.py`: the bot gets 300 zen in the database, its first trip is to Amy: its `30` to her and `32` in the
  packet log, the server's "Botty buys" apples.
- `bin/sim.py`: the report has the trips, sales, buys, repairs and their zen. 6 hours at exp rate 1, seeds 1..6: at 4
  hours the class averages from B1 to B1b: knights 13.0 -> 15.0, wizards 11.7 -> 13.2, elves 10.8 -> 13.0,
  gladiators 15.2 -> 16.0; at 6 hours 18.0, 16.2, 16.5, 19.0. 12..52 trips per bot (1..4% of the time), selling
  16..67 items for 1 200..6 200 zen, buying potions, arrows, weapons and armor (Hanzo, Harold, Elf Lala, Eo), 0..7
  repairs; 5 000..33 000 zen left. Five elves of six shoot a looted short bow from minute 9..18, every one buys a bow
  with its skill from Eo at 0:47..4:53 (a short bow, a crossbow +1, a bow) and hunts with it. No errors, nothing
  refused, none stuck. 250..340 times real time with 4 bots (B1 470): more kills, looting and walking, the profile
  is the monsters' AI and the paths as before.
- Left: the real client watching a bot's town trip and an elf with Eo's bow. The vault stores jewels only, none
  dropped on these seeds. 6 of the 79 deaths of the six runs are on the way to Amy (bull fighters). Bots carry most
  of their zen: the shops of their map have little more for them (Lumen's wings at 1 000 000).

## B2 bots: party, whisper, trade

- Party: accept invites from players near the bot's level, follow the leader, share exp.
- Whisper and chat: canned lines per situation, a tiny command grammar (`price X`, `buy X`, `sell X`), wts / wtb
  ads in town chat. A language model for chat lines only, optional: async, with a timeout, never in the tick, no
  decisions.
- Item value: base price from the client's prices (`shop.py`), use to the bot (upgrade for its class and stats,
  jewels it needs), market memory: the `trades` / `trade_items` log (M6), median price per item, level and options.
- Bot to bot: a server side order book matches wants and offers, bots meet in town and trade through the real
  `36`..`3D` flow so players see it.
- Bot to player: trade requests arrive as events, the bot checks every change of the window against its reserve
  price, accepts only after the other side has been unchanged for ~2 s, never takes unknown items, daily spend cap
  per bot.

Done when: a player buys an item from a bot and sells one to it in the real client; two bots trade with each other
in Lorencia.

## B3 bots: guilds, quests, events

- Join and create guilds, second class quest when the career reaches it, Devil Square entry.
