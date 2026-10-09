# mup: MU Online 0.97 server in Python

Hobby / learning project: a private server for the old MU Online 0.97 client (0.97b Chs, version `09704`).
Python 3.10 venv, asyncio, no framework. Work is planned in `docs/roadmap.md`, one milestone per session.

## Layout

- `bin/cs.py` connect server (port 44405), `bin/gs.py` game server (55901). Run from the repo root, `data/`
  (crypto keys, the client's terrains, `Gate.bmd`, `item.bmd`, `skill.bmd` and `Quest.bmd`, the server's `Monster.txt` /
  `MonsterSetBase.txt` / `Item.txt` / `Skill.txt` and `shop/`, mup's `ChaosMix.txt`), `config.ini` and the database
  are opened with relative paths.
  `bin/account.py`: accounts (create, password, personal code, ban, GM) and bots (`bot create NAME CLASS`, `bots`,
  `bot delete`). `bin/sim.py`: the game on a fast clock with bots, their report and trace, scenario dump / load,
  `--grounds CLASS` (`docs/bots.md`, S0, B0, B1).
- `config.ini` (or the file in `MU_CONFIG`), read by `mup/config.py`: ports, advertised GS host, exp / drop rates,
  database file and autosave, monster, item, skill, shop and mix data files, fixed drops, Devil Square times, account
  auto creation, bots, log level, packet logging.
- `mup/packet/`: `base.py` has `Base(bytearray)` (type, size, head, sub) and the declarative `Packet`: `code`, `size`,
  `fields` as `(offset, name, type[, default])`, `entry` for lists. Field types carry the byte order (`u16` LE,
  `u16be`, `cid` BE). `Packet(name=value)` builds, `Packet(data)` parses into attributes; list packets have an
  `of(...)` builder from models. `client_packet/*` mapped by their `code` in `client.py`, `server_packet/*` aliased
  in `server.py` (`S...` names).
- `mup/server/`: `session.py` (`Session`: what the game keeps on a connection, base of `protocol.py`'s network client;
  `LocalSession`: one in process, packets as bytes through `dispatch`, typed packets in its inbox), `protocol.py`
  (framing, crypto, packet log), `base.py` (`dispatch` to the handlers),
  `game.py` (`GameServer`: connections by cid, maps, its clock, the 100 ms game tick, entering, walking, relocating),
  `world.py` (maps, grids of who is where),
  `terrain.py`, `view.py` (what each client has in view, `12` / `13` / `14`, ground items `20` / `21`), `gate.py`,
  `monster.py` (monster data, spawns), `ai.py` (monster and summon behaviour), `path.py`, `combat.py` (hits, miss,
  ammunition, pace, death, respawn, regen), `stats.py` (what class, stats and items give, the client's formulas,
  `F3 06`), `experience.py` (kill exp, level up, death loss), `skill.py` (skill data, the list, learning, weapon
  skills), `casting.py` (skills on targets and areas, `1D` hits, buffs, teleport), `effect.py` (poison, ice, buffs,
  `1B`), `summon.py`, `item.py` (item data, wear slots, requirements, durability, wear), `inventory.py` (grids,
  what may be worn, moves between windows, potions, scrolls), `ground.py` (items on the ground, drop, pick up),
  `loot.py` (monster drops), `npc.py` (NPC windows, talking), `shop.py` (shops, the client's prices, buy, sell,
  repair), `warehouse.py`, `chaos.py` (chaos machine mixes), `jewel.py`, `command.py` (GM commands in chat),
  `chat.py` (chat, whispers), `party.py`, `trade.py`, `pk.py` (player kills, pk levels, murderers), `quest.py`
  (Sevina's quests), `guild.py`, `devil_square.py`, `connect.py`,
  `handler/*` (one per packet, registered in `handlers.py` / `bin/cs.py`), `character.py` (creation rules, start
  and respawn gates). Game time is `GameServer.now`, the tick passes it on; `GameServer.wall_time` for schedules.
- `mup/sim.py`: the game in process on its own clock: `Sim` (seeded, in-memory database, `run` / `run_until`,
  `digest`, `dump` / `load` of scenarios, `bot`), `Puppet` (a client in process for tests: `send` client packets,
  typed server packets in `inbox`, `recv_until`), `Hunter` (a puppet that hunts, a cheap policy for tests).
- `mup/bot/` (`docs/bots.md`): `session.py` (`BotSession`, a `LocalSession` with a brain), `manager.py`
  (`BotManager`: logs bots in, drives them from the game tick, the trace), `motor.py` (the client's pace: walk
  segments, attack orders and casts at the client's reach, area reports, gates, item requests, shops, the vault),
  `flow.py` (flow fields per map and target, walk masks, routes over the gates), `career.py` (hunting grounds from
  the spawns, fights from the client's formulas with skills, mana and a bow's reach, class builds), `gear.py` (what
  items are worth to a bot to use or to sell, the best change of its equipment, the stats a piece it will soon wear
  asks for), `town.py` (town trips: the errands due and along, the shops' goods and prices, potions, upgrades, the
  stops), `brain.py` (perception, priorities, reflexes: potions, buffs; the ground on its map or another, watchdog),
  `activity.py` (dead, escape, rest, points, loot, equip, trip: sell, repair, buy, the vault; travel, hunt, idle),
  `checker.py` (fair play: errors and refusals), `account.py` (making and removing bots).
- `mup/model/` dataclasses. `mup/repository/`: SQLite storage (`database.py` schema migrations, account, character,
  guild and bot repositories). Characters in game live in memory and are saved by `GameServer.save`.
- `mup/common/crypt.py`: C3/C4 SimpleModulus, C1/C2 xor chain (`extract` / `pack`), login field xor.
- `docs/protocol-097.md`: the protocol as the client implements it. `docs/roadmap.md`: milestones. `docs/bots.md`:
  bots and the simulation (S0, B0..B3).
- `tools/`: protocol extraction from the client with Ghidra. `tests/client.py`: scripted client test.
  `tests/sim.py`: fast tests in game time.

## Running

- Python: `./venv/bin/python` (`mu.pth` in its site-packages puts the repo on the path).
- `./run-gs.sh`: starts CS + GS, then a client. `./run-client.sh [client dir] [WxH] [desktop name]`: one client in a
  wine virtual desktop (native wine 9, `WINEPREFIX=~/projects/client`). Run it again for a second client.
- Client: `~/projects/client/mu/main.exe`, patched to connect to `mu.skpd.dev:44405` (resolves to 127.0.0.1) and
  serial `muonlineonpython`. `main.exe.orig` is the original. `tools/fix_client.py` fixed its `Data/Local` files
  (`*.orig` the originals): two texts that crashed the trade and guild questions, the font (Verdana), the names left
  in Korean. The wine prefix has `FontSmoothing` 0 (the client thresholds text to 1 bit). The other folders in
  `~/projects/client` are other versions with other protocols.
- Servers log at INFO. `log_packets = yes` in `config.ini` logs every packet in and out, tagged with the cid. For
  problems in the real client, ask the user to turn it on and paste the server log.

## Testing

- `./venv/bin/python tests/client.py`: starts its own CS and GS with a test config (ports 44415 / 55911, packet
  logging on, its own monster and drop files), plays two clients through login, character creation, walking, chat,
  combat, magic, drops, picking up, wearing and dropping items, a potion, disconnect, relog, GM commands, level up
  points, skills (scrolls, area hits, poison, teleport, weapon skills, an elf's buff, arrows, summons), monsters
  chasing and killing, respawn and a gate, NPCs (shops, wear and repair, the vault across a restart, a jewel, a
  mix, a trap), whispers, a party sharing a kill and trades, player kills, the quests, a guild and a Devil Square
  round, and last a bot made with `bin/account.py` buying potions from Amy with its zen, hunting and wearing a drop
  after a restart with bots enabled, one function per area. Run it after every change and extend it with every
  feature. It checks raw offsets from the doc, never the packet definitions, so a wrong definition fails it.
- `./venv/bin/python tests/sim.py`: the game in process (`mup/sim.py`) on tests/client.py's test world, about 10 s:
  the same seed gives the same game (also under another `PYTHONHASHSEED`), what tests/client.py would wait for in
  game time (respawns, drop owner time and lifetime, regeneration, a Devil Square round, a scenario played on), and
  the bots (session, motor through a gate, career picks on the real data, brain scenarios, loot and wear, potions,
  a scroll learned and cast, points for a piece, an area skill, a map change, a monster out of reach, arrows bought
  from Amy, a town trip that sells, repairs, buys potions and stores a jewel, a weapon from Hanzo, a bow from Eo,
  four classes levelling, a bot's scenario), none breaking the client's rules. Run it after every change
  too; a game error logged during a simulation fails it.
- The real client is the final check: ask the user to try it and paste the log.

## Protocol rules

- **The client binary is the source of truth.** Check `docs/protocol-097.md` first. For anything not in it, read the
  client's handler or sender (`tools/extract.sh`, addresses in the doc) before implementing, and add what you
  confirm to the doc. Don't copy OpenMU layouts blindly: character info, server list and area skill hits differ
  for this client.
- Values are little endian, except object ids (cid): 2 bytes big endian, high bit is a flag.
- After login, client C1/C2 packets are xor chained from the byte after the header (`protocol.py`, `joined`).
  Connect server packets are plain.
- Some server packets are only accepted encrypted (C3/C4): list in the doc. Sent as C1 they are dropped and the
  client answers `C1 F1 03 00`.
- Character class: the create request sends class number << 2 (0, 16, 32, 48), everything else uses
  class number << 3 (`CharacterClass` values).
- Skills: the client sends the skill list index, server packets carry the skill number (`Player.skill()`).
- List packets: check the entry size in the doc (players in view are 32 bytes per entry).

## Reverse engineering

- `tools/extract.sh ~/projects/client/mu/main.exe /tmp/mu-extract`: about 2 minutes. Ghidra 12.1.4 in
  `/opt/ghidra_12.1.4_PUBLIC`, JDK 21 in `/usr/lib/jvm/java-21-openjdk-amd64` (the default java is 17, too old).
- Output: dispatch map, offsets read per handler, decompiled handlers and senders. Find a packet by the handler or
  sender address listed in the doc, then read the decompiled code.
- Mark everything added to the doc with how it was confirmed: code, traffic, or index only.

## Conventions

- Follow the existing style: one packet class per packet, one small handler per packet, game logic in `mup/server`
  modules rather than in handlers.
- Packet fields are copied from the doc table with their offsets; a layout mistake (overlap, past the size) fails
  at import. Logging: `logging.getLogger(__name__)`, no `print`.
- Schema changes: append a migration to `MIGRATIONS` in `mup/repository/database.py`, never edit a shipped one.
- Keep the game repeatable (`tests/sim.py` checks it): time from `game.now` / `game.wall_time`, never `time.time()`;
  randomness through `random` (functions take `rng=random`), a bot's through its own `rng`; objects that go into
  sets the game iterates hash by a number (`Monster` and `Session` by cid, `GroundItem` by id, `Party` by number),
  never by address.
- Bots perceive only what a client knows (their own character, `c.view`, the packets they get, the data files): never
  a monster's life, target or path. They send only what a client would, the checker counts what breaks that.
- Commit only when asked.
