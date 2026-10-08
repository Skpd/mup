# Roadmap

One milestone per session. Each starts from `CLAUDE.md` and the spec below, ends with `tests/client.py` extended and
passing, a manual test with the real client, and the status updated here.

Packet codes are hex, details in `docs/protocol-097.md`. Where a code's meaning is marked "usual", it is the common
0.97 meaning and still has to be confirmed by reading the client's handler.

| milestone | status |
|---|---|
| M0 protocol fixes, housekeeping | done |
| M1 persistence, character select flow | done |
| M2 world: maps, gates, monsters | done |
| M3 items | done |
| M4 combat and progression | done |
| M5 NPCs, shops, warehouse, chaos machine | done |
| M6 social: whisper, party, trade | done, real client check pending |
| M7 guilds, quests, events, PK | todo |
| B0 bots: session, hunting, levelling (after M2) | todo |
| B1 bots: items, shops, map progression (after M3..M5) | todo |
| B2 bots: party, whisper, trade (after M6) | todo |
| B3 bots: guilds, quests, events (after M7) | todo |

## M0 protocol fixes, housekeeping

Fix what `docs/protocol-097.md` ("Differences with mup") found:

- `F3 03` character info: 42 byte client layout (money at 36, pk level 40, ctl 41), see the 2019 version.
- `15` damage: 13 bit value, colour flags in bits 5..7 of `[5]` (blue critical, green excellent, magenta).
- `12` players in view: 32 byte entries, effects at entry + 16 / + 17.
- `0E` ping: attack and magic speed are 2 bytes at 8 and 10. `F1 01` login tick is little endian.
- `F4 03` request: server code is 2 bytes. Weather `0F`: send a value the client understands or nothing.
- Drop the `F3 30` -> exit mapping. Fix the server list comment in `server_list.py`.

Housekeeping:
- Config file: ports, advertised GS host, exp / drop rates, log level. Default log level INFO with a packet
  DEBUG switch.
- Decide whether to move packets to declarative definitions (field list -> encode / decode) before the packet count
  grows. Most bugs so far were hand counted offsets and byte order.
  Decided: yes, all packets converted. `Packet` in `mup/packet/base.py`: fields as (offset, name, type) copied from
  the doc, types carry the byte order, layouts checked at import (order, overlaps, size). `tests/client.py` keeps
  checking raw offsets so it catches a wrong definition.

Done when: test checks money / pk level in character info and a damage above 255, real client shows the right zen.

## M1 persistence, character select flow

- SQLite with the stdlib `sqlite3`, a single file, no server. Starting point:
  ```
  accounts      (id, name UNIQUE, password_hash, ctl_code, active, created_at)
  characters    (id, account_id, slot, name UNIQUE, class, level, exp, level_up_points, str, agi, vit, ene,
                 life, mana, zen, map, x, y, dir, pk_level, pk_count, ctl_code, quest_state, created_at)
  items         (id, serial UNIQUE, owner 'inventory' | 'warehouse', character_id / account_id, slot,
                 item fields once M3 knows the format)
  skills        (character_id, slot, number)
  warehouses    (account_id, zen)
  guilds        (id, name UNIQUE, master_id, mark BLOB, score)
  guild_members (guild_id, character_id, status)
  ```
  Items get a unique serial (duplication checks later). Parties and trades stay in memory.
- Repositories replace `mup/mapper/`. Online state lives in memory, saved on logout, level up, item changes,
  every few minutes and on shutdown.
- Accounts: password hash, banned flag. Auto creating an account on first login stays as a config option.
- Characters: 5 slots, name rules, delete checks the personal code (`F3 02` `[14..23]`), class base stats from
  `~/projects/client/Data/Character/DefaultClassInfo.txt`, start map / position per class (Lorencia gate 17,
  elves Noria gate 27, from `Move/Gate.txt`).
- Logout `F1 02` (client sends the type: close, back to character select, back to server select; the result must be C3),
  remove the player from the world, then character list or disconnect.
- `F1 03` client reports: log reason (0 unencrypted packet, 6 decrypt failure).

Done when: create a character, go back to character select, restart the server, log in, the character is there
with its position and exp.

Done:
- `mup/repository/`: `database.py` (connect, schema as numbered migrations in `PRAGMA user_version`, WAL),
  `account.py`, `character.py`. All tables of the starting point exist; items, warehouses and guilds are empty
  until M3 / M5 / M7. Names are unique case insensitive.
- Accounts: scrypt password hash, `active` is the ban flag, `personal_code` column added (not in the starting
  point): auto created accounts get `personal_code` from the config. `bin/account.py` creates accounts, sets
  passwords and personal codes, bans.
- Characters: names of 3..10 letters / digits without `webzen` (the client hides those players), only first
  classes, 5 slots. Base stats from `DefaultClassInfo.txt` (`CLASS_INFO`), max life / mana are derived from it
  (`Player.max_life`), level up adds the class's points (MG 7). Start at a random spot of the gate area: the
  areas contain walls and a fountain, M2 has to pick a walkable tile.
- Saved on logout, disconnect, level up, every `autosave_interval` seconds and on SIGINT / SIGTERM. A second login
  of an account in game is refused with `F1 01` result 3.
- Logout `F1 02`: result handler read in the code, the request confirmed in traffic.
- Real client: created characters of three classes, character select, server select, exit, delete with a wrong
  and the right personal code, killed the exit monsters up to level 3, restarted the server twice: position,
  level, exp and level up points survived each restart.
- Found on the way: the client sends its key settings (`F3 30`) on every logout, mup doesn't store them yet.
- Placeholder monsters until M2: 3 budge dragons or spiders just outside each of the 4 Lorencia town exits
  (`LORENCIA_EXITS` in `game.py`), the client doesn't allow attacks in the safe zone. The test walks A and B to the
  east exit.

## M2 world: maps, gates, monsters

- Map registry for 0..10: Lorencia, Dungeon, Devias, Noria, Lost Tower, Exile, Arena, Atlans, Tarkan, Devil Square,
  Icarus. Terrain attributes (walls, safe zones) from `~/projects/client/Data/Terrain/TerrainN.att` (3 byte header,
  256 x 256 bytes, index `y * 256 + x`, `0x01` safe zone, `0x04` blocked, other bits not checked yet). Check them against the client's own `World*` files,
  some maps changed after 0.97.
- Walk validation against terrain. A spatial index for visibility (`map_view_wip.py` is a start).
- Gates and map change: `1C` both ways (server packet must be C3), gate data from the client's `Gate.bmd` or
  `Move/Gate.txt`.
- One game tick (100..250 ms) driving AI, respawn, regen, timers, autosave. Replaces the `Interval`s.
- Monsters: stats from `Monster/Monster.txt`, spawns from `Monster/MonsterSetBase.txt` (filter to maps 0..10), AI
  (idle, wander in spawn area, chase, attack, return), monster attacks on players (`15` to the player, life update
  `26`), player death (`17`) and respawn (`F3 04`) in the town, exp loss.
- Regen: life / mana (`26` / `27` usual meaning).

Done when: walk from Lorencia to Noria through a gate, monsters chase and hit, dying respawns in town.

Done:
- Client data in `data/`: the client's terrains (`World{n+1}/Terrain{n+1}.att`, 4 maps differ from the server's
  `Data/Terrain`), its `Gate.bmd`, the server's `Monster.txt` / `MonsterSetBase.txt` (`[world]` in `config.ini`).
  Terrain and gate formats, walkable bits (`0x04` wall, `0x08` no ground), the respawn, life, mana, map move and
  map loaded packets confirmed in the client's code, see the doc.
- `mup/server/world.py`: maps with an 8 x 8 cell grid each for players and monsters, `view.py` keeps what every
  client has in view (`c.view`) and sends `12` / `13` / `14` as players and monsters come and go, replacing the
  distance scans. `tools/map_view_wip.py` and the `move_strategy` modules are gone.
- Walks: the start must be walkable and within 15 tiles of the server's position, the walk stops before the first
  blocked step. New characters and respawns get a walkable tile of their gate area.
- Gates (`gate.py`): the request is accepted when the player's position or last walk is in the entrance area and
  the level is enough (MG two thirds), then `C3 1C` and everything in view again. The client's gate table has no
  gates to Lost Tower, Atlans, Tarkan and Icarus, their monsters wait for a warp command.
- One tick of 100 ms (`GameServer.run`) for monster AI (only monsters within 20 tiles of a player act), respawns,
  player respawn, regen and autosave. `mup/common/interval.py` is gone. 40 players among the real spawns: about 1 ms
  per tick.
- Monsters (`monster.py`, `ai.py`): the area and single spawns of maps 0..10 without Devil Square (event, M7), single
  spawns within 3 tiles of their spot (mup's choice). 2301 monsters, 87 of them on spots that are walls in this
  client's terrain (mostly Atlans) are left out, 2214 on the maps. AI: notice within view range, chase with an A* path
  (`path.py`) up to twice the view range and the spawn's range from home, attack (`18` animation `0x64`, `15` and
  `26` to the player) at attack speed, return home, wander within move range. Monsters don't enter the safe zone,
  don't stand on each other and don't attack players in it. Damage is the raw `Monster.txt` range, no defense or
  miss yet (M4).
- Death: `17` to the player and its viewers, `F3 04` after 3 s in the town of the map (Devias for Devias, Lost
  Tower, Icarus; Noria for Noria; Lorencia otherwise, usual rules), full life and mana. From level 10 a death costs
  2% of the level's exp (usual value; with mup's exp per level until M4's exp table). A character saved dead comes
  back in town.
- Regen every 3 s: 1% of max life, 3% of max mana (mup's own rates), `26` / `27` with `FF`.
- Test: own monster files (a spider that doesn't look, a dragon hitting for 1, a hound killing with one hit), a
  walk into a wall, chase and hit, regen, death and respawn, the gate to Noria at level 1 (refused) and level 10.
- Real client: looked fine.

## M3 items

- Reverse engineer the item format first: 4 bytes per item in `F3 10` (`[slot][4 bytes]`), 8 x 8 inventory grid,
  equipment slots. Inventory handler `0x414310`, item decode around `0x48d940`.
- Item definitions: client `Data/Local/item.bmd` (sizes, requirements, names; xor `FC CF AB` like `read_text.py`)
  plus `Item/Item.txt` for server side values.
- `F3 10` real inventory, `24` move / equip (result must be C3), equipment shown to others (`25` usual,
  appearance bytes in `12` and character list).
- Ground items: `20` in view, `21` gone, `22` pick up, `23` drop. Monster drops (`Item/ItemDrop.txt`) and zen.
- `26` use item: potions. Zen in character info.

Done when: kill a monster, pick up its drop, equip it, another client sees the new look, a potion heals.

Steps (each leaves something that runs and is tested):

0. Reverse engineering into the doc first (`tools/extract.sh`):
   - item bytes: `0x48d940` decodes an item (also called for `32`, `39`, `F3 14`): entry size, type / level / skill
     / luck / option / excellent / durability bits.
   - `F3 10` (`0x414310`, `[5]` count, entries from `[6]`): slot numbering, equipment slots, where the 8 x 8 grid
     starts.
   - server handlers `20` (`0x419f90`), `21` (inline), `22` (`0x41a0b0`), `23` (`0x41a3a0`), `24` (`0x41a680`),
     `25` (`0x416060`), `26` / `27` item counts, `28` (`0x48e0d0`). Do ground items share the 400 objects' cids?
   - client senders `22` (`0x4650a0`), `23` (`0x497760`), `24` (`0x422db0`, `0x474ac0`), the item use `26` sender
     (not in the sender index: inventory right click).
   - equipment look: the 10 bytes in `12` `[+5..14]` / `F3 00` `[+16..25]` (`0x4164b0`, `0x4124b0`), replacing the
     guesses in `appearance.py`.
   - requirements: the tooltip's formula (`0x487030`), so the server refuses what the client shows red. Potion
     stack limit if the client checks one.
   - `item.bmd`: 28676 bytes = 512 records of 56 bytes + 4, xor `FC CF AB`, 16 groups x 32 (type
     `group * 32 + index`, Horn of Uniria `0x1A2` = 13/2). Record field offsets.
1. Item data: `data/item.bmd` from the client, loader in `mup/server/item.py` (`ItemDef`). The server's `Item.txt`
   in `~/projects/client/Data/Item` is a later version (512 per group, DL), use it only for values the client
   doesn't have, where `index < 32` and the name matches. Potion heal values: small table, usual or mup's choice.
2. Model and storage: `ItemDef` (static) and `Item` (serial, type, level, durability, options) instead of
   `mup/model/item.py`'s mix. `Player.inventory` slot -> `Item` (equipment and grid). Migration rebuilding the empty
   `items` table with item columns, items saved with the character in one transaction, serials from a counter. One
   item codec (a `Packet` field type) for every packet carrying items.
3. Inventory rules, `mup/server/inventory.py`, no packets: grid occupancy by item size, free spot, equipment slot
   per item group, class flags, requirements (client formula), two-handed vs shield, bow / arrows, move validation.
4. Packets: real `F3 10` on join, `24` move / equip with the C3 result, `25` new look to viewers, real
   `appearance.equipment(p)` (fixes `12` and the character list).
5. Ground items: an item grid per map in `world.py`, `view.py` sends `20` / `21` as they come and go, expiry and
   owner priority (killer / dropper first for a few seconds, mup's choice) in the tick. `23` drop, `22` pick up
   (items and zen, zen into `Player.zen`).
6. Drops: on kill (`combat.hit_monster`) roll nothing / zen / item with `drop_rate`. Items from `item.bmd` by level
   near the monster's (usual 0.97 rule), potions by monster level, small option chances. `[world] item_drops` file
   for fixed drops per monster, the test config uses it. The later server's `ItemDrop.txt` is mostly post 0.97
   items, not used.
7. Potions: `26` use, heal, `26 FF` / `27 FF`, count down or delete, the potion delay the client's `FD` timer
   implies.
8. Test (raw offsets): empty `F3 10`, A kills a fixed drop monster, A and B see `20`, A picks up (`22`), both get
   `21`, A equips (C3 `24`), B gets `25`, refused moves (wrong slot, requirement, overlap), A drops and B picks up
   after the owner time, zen pickup, a potion heals, after relog `F3 10`, `F3 03` money and the look in the
   character list are kept. Then the real client.

Not in M3: durability loss (`2A`) and repair, jewels, shops and warehouse (M5), item stats in damage (M4), PK
item drop (M7).

Done:
- Doc: [Items](protocol-097.md#items) (item bytes, `item.bmd`, slots, slot classes, requirements, equipment look,
  item use lock) and the packets `F3 10`, `20`..`28`, `2A` both ways, all from code. 4 bytes per item, the client
  places a grid item by its top left slot. Zen on the ground has a 9 byte entry in `20`. `22` / `23` / `24` / `26`
  requests are C3.
- `data/item.bmd` (the client's) and `data/Item.txt` (the later server's: skill, options, drops) in
  `mup/server/item.py`, `ItemInfo` / `Item` / `GroundItem` in `mup/model/item.py`. `Player.inventory` is slot ->
  `Item`. Migration 2 rebuilds `items` with the item fields, items are saved with the character (`INSERT OR
  REPLACE` by serial, so an item that changed hands moves to its new owner), serials from the highest stored.
- `inventory.py`: grid fit, free slot (row by row), wear rules as the client checks them (slot class, rings both
  slots, one-handed weapons in the left hand for every class, class byte, magic gladiators as wizards or knights,
  no two-handed weapon sharing the hands but with arrows / bolts) plus the requirements the client doesn't check.
  Only the inventory window (0), trade / warehouse / chaos moves are refused. `25` to the viewers for slots 0..8.
- Ground items (`ground.py`): ids 0..999, an item grid per map in `world.py`, in `c.view` like players and monsters
  (`20` / `21`, `21` before a map change). 60 s on the ground, the killer alone may pick up for 10 s, player drops
  have no owner, pick up within 3 tiles, a drop farther than 3 tiles or on a wall lands on the player's tile. Zen
  goes into the money (`22 FE`, at most 2 000 000 000). All mup's choices.
- Drops (`loot.py`): an item when `rand(ItemRate) < 10 * drop_rate`, else zen when `rand(MoneyRate) < 10`
  (Monster.txt columns, the usual servers' shape with mup's numbers): 5..9% items, 35..46% zen on the real data.
  Items with the drop flag and a drop level up to 20 below the monster's, one item level per 10 monster levels
  up to `MaxItemLevel`, skill 15%, luck 10%, option 1 15% / 2 5%. Zen `level² / 2 + 5 level` +-25%. Fixed drops per
  monster type from `item_drops` (every line rolls on its own). Potions are as rare as any other item for now.
- Potions (`inventory.use`): healing `value * 10 - 2 * level` + 10 / 20 / 30 / 40% of max life, mana 20 / 30 / 40%
  (the later WebZen servers' formulas), then `2A` with the count or `28` for the last one, both unlock item use;
  other items only get the unlock (`26 FD`). No stacking on pick up yet.
- Test: drops seen by both players with the fall flag and the zen entry, the owner refusing A, pick up into slots
  12 / 13, zen, refused moves (overlap, a potion as helm, a wizard's strength), wearing the sword with `25` to the
  other player, a player drop picked up by the other, the look in the char list and in `12` after relog and
  restart, the inventory and money after relog and restart, a potion healing with `28` after it.
- Real client: looked fine.

## M4 combat and progression

- Damage formulas per class, stats and weapon, defense, miss, critical / excellent rolls, attack range and speed checks.
- Exp per monster level, experience table, stat points (`F3 06`), derived life / mana per class.
- Skills: data from `skill.bmd` / `Skill/Skill.txt` (mana, range, damage), learned from scrolls / orbs (`26`),
  area hits from the client's `1D` report instead of the server side guess, elf buffs, summons (`1F`), `1B` cancel,
  `F3 11` add / remove.
- GM commands through chat (moved from M6: the manual tests from here on need levels, items and places).

Done when: the character window shows the damage and defense the server uses, kills give exp by monster level and
the exp bar is right across level ups, points go into stats, a wizard learns a skill from a scroll and an area skill
hits what the client reported, an elf buffs another player.

Steps (each leaves something that runs and is tested; after 4 is a stopping point if the session runs out):

0. Reverse engineering into the doc (`DumpDecompiled.java` on the addresses, in the project `extract.sh` leaves):
   - what the client derives from stats and equipment: the character window `0x4a20e0` (damage, defense, speeds,
     magic damage, whatever it shows) and `0x45c9f0` (called by the `34` handler, reads 2 byte values at
     `+0x46..+0x58b` of its argument, presumably the hero's recalculation). The server's formulas give what the
     window shows; hit chance and the monster side stay the usual 0.97 ones, marked as such.
   - `skill.bmd` (`Data/Local`, 2436 bytes: 64 records of 38 bytes + 4, xor `FC CF AB`, name in 32 bytes, then 6
     bytes, mana 2 bytes at +34 going by Soldier Summon's 350, files): fields from its loader (`0x4c09b0`).
   - casting: what the client checks before `19` / `1E` (mana, distance, level / energy), which skills send `1D`
     (`0x442610` and its callers), reports per cast and what `[6]` counts. Effects: `19` `[6..7]` bit 15, `1B`
     (`0x418500`, code: `[3]` skill, `[4..5]` cid, clears object `+0x76` bit 1 for skill 1 poison, 2 for 7 ice, 4 for
     28 greater damage, 8 for 27 greater defense, `0x100` for 16 mana shield).
   - learning: the answer to `26` on a scroll / orb (`F3 11` `FE`, `28`?), which item teaches which skill. Weapon
     skills: does the client list an equipped weapon's skill itself or wait for `F3 11` `FE` / `FF`.
   - teleport (skill 6): the request (usual: `1C` gate 0 with x, y in `[4]` `[5]`), answered with `1C` `[3]` 0.
   - `1F` summons in view (`0x4172c0`, code: `[4]` count, entries from `[5]` start like `13`'s), the owner field.
   - `F3 30` key settings: the server packet (`0x41ff50`) and the 18 byte request M1 found on every logout.
   - excellent option texts (`Text.bmd` entries for ids `0x42..0x4f`, `0x45a270`), so options do what the tooltip
     says.
1. GM commands: chat lines starting with `/` from characters with the GM ctl code (`bin/account.py` sets it), in
   `mup/server/command.py`: `/level`, `/zen`, `/item group index [level options]`, `/move map x y`, `/skill`,
   answers as notices (`0D`). Housekeeping: split `play` in `tests/client.py` (400 lines) into one function per area
   sharing servers and clients, before M4..M7 double it.
2. Experience: total exp as the client keeps it (`16` adds to it, `F3 05` sets the next level's from
   `10 (L + 9) L²`) instead of mup's exp per level, a migration adds the levels below to stored characters. Exp per
   kill from monster and player level (usual 0.97 formula, times `exp_rate`), several level ups from one kill, `16`
   split above 65535, the death loss from the level's share.
3. Stats: `mup/server/stats.py` derives max life / mana, damage, magic damage, defense, attack / defense rate and
   attack speed from class, level, stats and worn items (+ 3 per item level, options, excellent options; nothing from
   items at durability 0 once M5 wears them), recomputed on stat, level and equipment changes. `F3 06` handler: one
   point, result with the new max life / mana for vit / ene, at most 65535 (mup's choice, the client checks nothing).
4. Hits: one hit function for every attacker / defender pair: hit chance from attack and defense rate (`15` with 0 is
   a miss), defense, critical (luck), excellent (option), colour flags, for player -> monster and monster -> player,
   replacing `10 + level` and the raw `Monster.txt` range. `15` requests: target in view and within the weapon's
   reach, not faster than the attack speed (a few in a row allowed for lag, mup's choice), `0E` speeds compared with
   the server's (logged). Bows / crossbows use an arrow / bolt per shot (`2A`, `28` for the last, no shot without).
   Hits on players stay refused until PK (M7).
5. Skills: `mup/server/skill.py` from `data/skill.bmd` (the client's) with `Skill.txt` for what it lacks (radius,
   effect, classes). New characters start with their class's usual skills (energy ball for wizards) instead of
   `DEFAULT_SKILLS`' test set, stored characters keep theirs. Scrolls (group 15) and orbs (12/7..14) through `26`:
   class, level and energy checks, `F3 11` `FE`, the item used up. Weapon skills on equip / unequip if step 0 says
   the server sends them.
6. Casting: `19` / `1E` cost mana (`27`) and check range, damage from the skill plus magic damage (wizards) or weapon
   damage (others, usual factors). Area skills hit what `1D` reports: targets in view within the skill's radius of
   the reported point, one report per cast, replacing the 5 tile guess ("Differences with mup" 1). Poison and ice:
   effect bits in `12` / `13`, poison damage over time, `1B` at the end. Teleport, defense (18), mana shield (16).
7. Elf buffs and summons: heal (26), greater defense (27) / damage (28) on herself or another player for a while
   (usual durations), effect bits in `12`, `1B` at the end, the bonus in `stats.py`. Summons (30..36): a monster
   owned by the elf, `1F` in view, follows her, attacks what she attacks, gone when it or she dies, she leaves the map
   or summons another.
8. Key settings: `F3 30` stored per character (migration), sent back on join.
9. Test (raw offsets): GM `/level` and `/item`, `F3 06` result, a kill's `16` against the formula and the total across
   a level up (`F3 05`), hit damage within the range for the worn sword, a miss against a dodging test monster, arrows
   counting down, a scroll from a fixed drop learned (`F3 11 FE`, `28`), mana spent (`27`), an area skill damaging
   the monsters of a `1D` report and nothing else, a buff on B and its `1B`, skills, points and key settings after
   relog. Then the real client: the window's numbers against the hits, each class's skills.

Not in M4: hits on players (M7), durability loss and repair (M5), second class skills from quests (M7).

Done:
- Doc: [Character values](protocol-097.md#character-values) (the client's damage, wizardry damage, attack rate,
  speeds, defense and defense rate, the wear factor, item values by level and excellent, option ids with their
  `Text.bmd` texts) and [Skills](protocol-097.md#skills) (`skill.bmd`, a skill's wizardry damage, mana, what scrolls
  and orbs teach), `16` bit 15, the `19` / `1D` / `1E` senders (the selected list index, `1D` at most 5 targets per
  effect, several per cast), `1B`, `1F`, the teleport `1C`, `F3 30` both ways. All from code.
- GM commands (`command.py`): `/level`, `/points`, `/zen`, `/item`, `/move`, `/skill`, `/heal` for accounts with
  ctl code `0x20` (`bin/account.py gm`), answered with notices.
- Exp (`experience.py`): the total exp the client keeps, migration 3 converts the stored characters. Kill exp by the
  usual 0.97 formula, shared by the life each player took, in `16` (bit 15 for skill kills and the other players,
  split above 65535), several level ups at once, death loss 2% of the level's span from level 10.
- Stats (`stats.py`): `Player.values` by the client's formulas, recomputed on join, equipment, level and points.
  `F3 06` with the client's result (stats up to 65535, mup's choice). What the client doesn't count, mup's way:
  life / mana + 4% (`26` / `27` FE), damage decrease, reflect, life / mana after a kill, zen + 40%, excellent damage
  10%, luck on weapons 5% critical, option `41` adds to the regeneration.
- Hits (`combat.py`): the usual miss check (5% below the defense rate), critical (max) and excellent (120%),
  defense, at least level / 10 (mup's), two weapons 55% each, the bow's hand, an arrow / bolt per shot (`2A`, `28`).
  Reach 3 / 8 tiles and the pace (0.4 s / (1 + speed / 100), bursts of 4) are mup's, `0E` speeds that differ from
  the server's are logged.
- Skills (`skill.py`, `casting.py`, `effect.py`, `summon.py`): wizards start with energy ball, scrolls / orbs with
  the item's requirements, weapon skills by the client's table while worn (`F3 11` FE / FF, free list slots stay
  free). `19` and `1E` take mana, check the distance (+ 2 tiles) and the pace; area skills hit only what `1D`
  reports within the radius (+ 2) of the cast, once per effect serial, for 3 s. Knights' weapon skills hit for the
  weapon times 200 + ene / 10 %. Poison (3% of life every 2 s for 10 s), ice (half speed for 10 s), `1B` at the end;
  heal 5 + ene / 5, greater defense 2 + ene / 8 and damage 3 + ene / 7 for 60 s (usual), the knight's defense
  halves the damage for 3 s (mup's). Teleport `1C 0 x y`, `11` to the players who see it. Summons 30..36 (the usual
  monster types) follow the elf and attack what she attacks, `1F` in view, gone with death, map change and logout;
  monsters ignore them and players can't hit them (mup's).
- Key settings `F3 30` stored with the character (also when they come after a logout to the server list), sent
  back after the skill list.
- Test: split into one function per area. GM commands, `F3 06`, exp shares in `16`, damage within the formulas'
  ranges, mana, a scroll read and one refused, flame hitting what `1D` reports and nothing else, poison ending with
  `1B`, a teleport the other player sees, a shield's skill on and off, skills and hotkeys after relog, an elf's
  buff on B, arrows counting down, misses against a dodging monster, a summon in `1F` attacking with the elf.
- Left: mana shield and the other second class skills (M7), the client's own attack / cast timing (the pace is a
  guess), the monsters' magic defense column, the wings' damage / absorb % (not in this client's values).

## M5 NPCs, shops, warehouse, chaos machine

- NPC spawns, talk `30` (result must be C3), shops `31`..`34` from `Shop/*.txt`, repair.
- Warehouse `81`..`83`. Chaos machine `86` / `87`, basic mixes.
- Durability loss (`2A`) and jewels (bless, soul, life), left out of M3.

Done when: in the real client, buy potions and a weapon, sell an item, repair a worn one, store an item and zen in the
warehouse and take them out with another character of the account, a jewel of bless, a +10 mix.

Steps:

0. Reverse engineering into the doc:
   - NPCs: the types this client knows (`NpcName(Eng).txt`: traps 100..103, 200, 235..255; models `0x4bc4d0`), only
     234 and up can be talked to. The later server's section 0 spawns 226, 229, 230, 233, 257, 375, 379, 450, 451 on
     maps 0..10, not in this client.
   - `30` talk result (`0x41abc0`, must be C3): `[3]` the window per NPC (shop, warehouse, chaos machine, guild
     master, Charon, ...), what the client sends or expects after it.
   - `31` lists (`0x414890`, code: `[4]` 3 the chaos machine's 8 x 4 grid, anything else the 120 slot (8 x 15) shop /
     warehouse grid via `0x48d3b0`, `[5]` count, 5 bytes per entry: slot, item). The `31` request closes (M1).
   - shop: the buy request (not in the sender index, the shop window's click code), `32` result (`0x48d940`), sell
     `33` (request from `0x497760`, an item dropped on the shop), repair `34` (request `0x4a19f0`). How the client's
     money changes after each, and **the prices the client shows** (buy, sell, repair), so the server charges them.
   - warehouse: `81` (`0x41d970`, request `0x4232c0`, usual: zen in / out), `82` (`0x41dbe0`, request `0x4aa5c0`,
     usual: close), `83` (`0x41dc30`); `24` with window 2.
   - chaos machine: `86` (`0x41f960`), `87` (`0x41fa20`, request `0x4aa3a0`), the mix request, what the client shows
     of a mix (rate, zen) before it sends.
   - jewels: how the client applies bless / soul / life (`26` with the target slot `[4]`, or `24`), the answer that
     unlocks item use. Durability: what the client does at 0, which `2A` it expects.
1. NPCs: `MonsterSetBase.txt` section 0 on maps 0..10, the client's types only, ids in the monster range, in view with
   `13`, at their spot and direction. Not attackable, no AI except traps 100..103 (hit who stands on them, usual);
   guards stand until M7.
2. Talk: `30` with the NPC in view and near (mup's choice), the window per NPC type, `C3 30`, the open window kept on
   the connection, closed by `31`, walking away, a map change, death and logout. One window at a time.
3. Shops: the later server's `Shop/*.txt` and `ShopManager.txt` copied to `data/shop/`, items this client has, placed
   by size in the 8 x 15 grid (file order unless step 0 finds a rule), `31` after `30`. Buy: price, money, a free
   slot, a new item with a serial and full durability. Sell: the client's price, the item gone, money capped.
4. Durability and repair: weapons wear on hits, armor and shields on hits taken (usual rates), `2A`, no stats at 0
   (`stats.py`). Repair at the blacksmith and in the inventory (usual: dearer), `34`.
5. Warehouse: per account, items with owner `warehouse` and `warehouses.zen` (M1 tables), loaded on first open, `31`
   with its items, `24` between windows 0 and 2 (grid fit as in the inventory), `81` zen in / out, saved with the
   character in one transaction on close, logout and autosave, so nothing is duplicated or lost.
6. Jewels: bless +1..+6, soul +7..+9 (50%, more with luck, a failure drops the level), life adds an option (usual 0.97
   rates), the way step 0 found.
7. Chaos machine: the chaos goblin's window, `24` with window 3 (8 x 4), items left in it go back on close and logout.
   Mix: the recipe from the items, zen, chance, the result or the items lost, then its `31`. Item +10 / +11, chaos
   weapons, Dinorant from ten Horns of Uniria, first wings (usual recipes and rates from a data file, so the test
   config can make them certain). The Devil Square invitation comes with M7.
8. Test (raw offsets): talk to the potion girl (C3 `30`, `31`), buy a potion (money, slot), refused buys (no money, no
   room), sell it, durability after hits (`2A`), repair (`34`, money), store an item and zen and take them with
   another character of the account, also after a restart, a jewel of bless (+1), a certain +10 mix. Then the real
   client.

Not in M5: shops refusing murderers (M7).

Done:
- Doc: [NPC windows](protocol-097.md#npc-windows) (the windows `30` opens, what each needs, how the client closes
  them, the repair NPCs 243 / 246 / 251 and the inventory's repair button from level 80),
  [Prices](protocol-097.md#prices) (buy, sell, repair cost, the full durability of `0x486fd0`, +3 arrows / bolts
  priced with garbage by the client),
  [Chaos machine](protocol-097.md#chaos-machine) (what the box takes, the five mixes the client recognises with their
  rates and zen, the mix state that needs the window opened again after a mix), [Jewels](protocol-097.md#jewels), and
  the packets `30`..`34`, `81`..`83`, `86`, `87`, `F3 14` both ways, `2A`, `26` with a jewel. All from code. The buy and
  mix results carry no money, `22 FE` does.
- NPCs (`npc.py`): section 0 of the spawn file, the types this client has (`monster.NPC_TYPES`), at their spot and
  direction in the monsters' ids, `Monster.attackable` keeps them out of hits, skills and summons. Traps hit the
  nearest player within their attack range (0: on them) at their attack speed. One window per connection
  (`c.window`), talking within 5 tiles; closed by `31` / `82` / `87`, another talk, farther than 5 tiles, death, a
  relocate (`82` / `87` tell the client) and leaving the game. NPCs without a window yet (guards, Sevina, Charon, the
  guild master) answer nothing.
- Shops (`shop.py`): `data/shop` is the later server's files, filtered to this client's items (and no +3 arrows /
  bolts); Hanzo's goods aren't in this client, he sells Leah's beginner weapons and the first shields (mup's). Goods
  placed in file order. Buy, sell and repair at the client's prices (its float steps included), `22 FE` then `32`,
  `33` with the money, `2A` per repaired item then `34`. Money capped at 2 000 000 000.
- Wear (`item.wear`, `combat.py`): weapons by the defense they hit (`defense * 2 / (min damage * 3 / 2)`, a point at
  more than 564, bows 780, staffs on wizard skills 1050), a random piece of armor or the shield by the damage taken
  (`damage * 2 / (defense * 3 / 2)`, 69): the later servers' shape, mup's numbers, not stored. `2A` and the values
  again for each point lost (nothing from an item at 0, M4). `item.max_durability` is now the tooltip's.
- Warehouse (`warehouse.py`): per account, loaded on the first open of the connection, `24` with window 2,
  `81` (at most 100 000 000 zen stored, usual), saved with the character in one transaction (owner `warehouse`,
  `warehouses.zen`) on close, logout and autosave.
- Jewels (`jewel.py`): bless +1 up to +6, soul 50% (+25% luck) up to +9, a failure from +7 to +0 and below one level
  down, life + 1 option step up to +16 (the highest the client prices) at 50%, a failure removes it. Full durability
  after. `F3 14` and `28`, refused: `F3 14` puts the jewel back, `26 FD`.
- Chaos machine (`chaos.py`): the client's recognition ported, rates and zen from `data/ChaosMix.txt` (`[world]
  mixes`, -1 the client's own). Chaos weapon mix: a chaos weapon of level 0..4 (2/6, 4/6, 5/7) or the first wings
  when a chaos weapon was mixed, skill / luck / option by the rate; failed: jewels gone, the rest loses levels. +10,
  +11 and the dinorant: the item up a level / a new horn, failed: all gone. `22 FE`, `86`, `31` 3 after a failure.
  The Devil Square invitation is refused until M7. Migration 4 adds the item owner `chaos`: the box is stored with
  the character, what is left in it goes back into the inventory when the window closes and on entering, `31` 3
  shows the client what stayed (or clears what it may still show).
- Test: Amy in view (13) and her goods (31), a swing and a skill on her doing nothing, a potion bought (`22 FE`,
  `32`) and sold (`33`), refused buys (no money, no 2 x 2 room), the sword's `2A` on the golem and its repair at
  Hanzo's (`2A`, `34` with the cost by the formula), the rapier and 1000 zen into the vault, stored with the account,
  taken out by Elfa after a restart, a jewel of bless (+1) and one refused, a certain +10 mix, walking away closing
  the window (`82`), a trap hit.
- Left: Devil Square (Charon, the invitation mix), guild master, quests and the server division dialog (M7), the vault
  lock (`83`), stacking potions.

## M6 social: whisper, party, trade

- Whisper `02` / `0C` (usual), confirm the client chat layout `00` (not reviewed yet).
- Party `40`..`44`: invite, list, member life, exp share.
- Trade `36`..`3D`.
- GM commands through chat: moved to M4.

Done when: two real clients whisper, party up and share the exp of a kill, and trade an item and zen.

Steps:

0. Reverse engineering into the doc:
   - chat: the client's `00` (senders `0x41f0e0`, `0x4d2b21`, handler `0x414960`), the whisper request (not in the
     sender index, near the chat input), `02` whisper (`0x45e470`), `0C` (`0x45e860`, usual: not online). `01`, `03`,
     `0B` from the backlog if they turn out chat related.
   - party: request `40` (`0x46a340`), the question `40` (inline at `0x422231`), the answer (not in the index), `41`
     results 0..5, `42` list (`0x41de50`), `43` leave / kick (request `0x49c5b0`), `44` member life (inline at
     `0x422300`), the party window `0x4a44e0`.
   - trade: request `36` (`0x46a340`), the question `36` (its handler builds a packet itself: an answer when busy?),
     the answer `37` (not in the index) and its result (`0x41d1b0`), the other side's items `38` / `39` (`0x48e0d0` /
     `0x48d940`), money `3A` / `3B`, ok `3C` (`0x497760`, `0x4a1070`), end `3D` (`0x41d6f0`, request `0x4a1070`),
     `24` with window 1 (8 x 4).
1. Chat: `00` fixed if it differs, whisper by name on any map, `0C` when the name isn't in game, the prefixes the
   client shows (`~` party in step 2, `@` guild in M7), server messages as notices (`0D`).
2. Party (`mup/server/party.py`, in memory): invite a player in view, accept / refuse, at most 5 (usual), leave, kick
   by the leader, gone when one is left; `42` to every member on each change, `44` every few seconds, party chat `~`.
   Exp share: members on the map within view of the kill split it by level with a bonus per member (usual 0.97
   formula, mup's choice where unknown), `16` to each. Logout and disconnect leave the party.
3. Trade (`mup/server/trade.py`, in memory): request to a player in view, neither busy (window or trade open), answer,
   an 8 x 4 grid per side, `24` window 1 moves, `38` / `39` and the money to the other, ok `3C`, any change clears
   both oks. Both ok: room in both inventories, items and zen swapped at once, both characters saved in one
   transaction (items move by serial already), `3D`, `F3 10` and money to both. Cancel, walking away, death and
   disconnect give everything back. A `trades` table (migration) logs each trade for B2's market memory.
4. Test (raw offsets): A whispers B and an offline name (`0C`), party invite and accept with `42` on both, party chat,
   A's kill gives B exp (`16`), leave; trade: request, accept, A puts in the sword and zen, a change resets the oks,
   both ok, the sword is B's after a restart, a cancelled trade gives A its items back. Then two real clients.

Done:
- Doc: [Chat](protocol-097.md#chat), [Party](protocol-097.md#party), [Trade](protocol-097.md#trade) and the packets
  `00` / `02` both ways, `01`, `03`, `0B` (located, not reviewed), `0C`, `36`..`3D`, `40`..`44`, all from code. `36`
  must be encrypted (its handler answers `F1 03` otherwise), the client sends `36`, `40`, `41`, `3C`, `3D` as C3 and
  `00`, `02`, `37`, `3A`, `43` as C1. `/trade` and `/party` are chat commands the client handles (target within 1
  tile), `/whisper off` is the client's own. `41` has no success value, a refusal shows "denied". The client's window
  close empties both trade grids without putting the own items back, so every trade end comes with `F3 10` and `22 FE`.
  `16` for a monster the client doesn't have writes past its object table.
- Chat (`chat.py`): lines go to everyone in game under the speaker's real name, `~` lines to the party, `@` lines
  wait for M7. Whispers by name (any case) on any map, `0C` when nobody has it.
- Party (`party.py`, in memory): a request to a player in view, refused with `41` (full at 5, in another party, a level
  gap of 120, gone), the answer within 60 s. The leader puts anyone out, the others leave, one left alone is out, the
  next member leads when the leader leaves (mup's choice). `42` on each change and when a member moved, `44` every
  2 s. Leaving the game leaves the party (`43` still goes to a client back at character select).
- Exp share (`experience.py`): what a party member's damage earned goes to the members alive on the map who have the
  monster in view (every exp `16` now needs it in view): the monster's exp for their average level, 160 / 180 / 200 /
  220% for 2..5 members, 160 / 230 / 270 / 300% with 3 classes or more (usual 0.97 numbers, the average level and the
  class rule mup's), split by level. `16` with bit 15 for the members who didn't hit.
- Trade (`trade.py`, on the connections): a request to a free player (level 6, no window, no trade) in view within 5
  tiles, the question waits 30 s. Items move with `24` window 1 into `Player.trade_box`, stored with the character
  (owner `trade`, migration 5) and given back into the inventory when the trade ends or on the next entry after a
  crash. Zen stays in the money until the exchange, the client is shown what is left. Any change takes back both
  oks (`3C` 2 and 0). Both ok: room for everything on both sides (the bigger items placed first) and the money below
  the limit, otherwise `3D` 2 to the side without room and everything back; the exchange saves both characters and
  the trade (`trades`, `trade_items` with what each side gave) in one transaction. Cancel (`3D`), walking more than 5
  tiles away, a relocation (map change, teleport, GM commands that refresh), death and leaving the game end it.
  Nobody talks to NPCs or picks things up during a trade.
- Test: whispers to B and to a name not in game, a party (`40`, `41`, `42` and `44` on both, party chat), A's energy
  ball on the dragon gives B his share (`16` bit 15), B leaves (`43` to both); trades: refused (`37` 0), the sword and
  5000 zen for nothing with a change taking back B's ok, the exchange (`3D` 1, `F3 10`, `22 FE`) logged and saved, a
  canceled one and one ended by walking away giving A her item back, and after a restart the sword and zen are B's.
- Left: guild chat and the guild mark in `37` (M7), murderers in parties and trades (M7), the party list's positions
  update only every 2 s.

## M7 guilds, quests, events, PK

- Guilds `50`..`56`, `5A`..`5D`, guild war `60`..`64`, 32 byte guild mark.
- Second class quests `A0`..`A3` (client `quest.bmd`).
- Devil Square `90`..`96`, `99`.
- PK: levels, timers, item drop on death.

Four features: PK and quests in one session, guilds and Devil Square in another if one isn't enough.

Done when: in the real client a murderer changes colour and drops an item when killed, a level 150 character (GM
`/level`) does Sevina's two quests and comes back a soul master / blade knight / muse elf, a guild with a mark gets a
second member, a Devil Square round runs from entry to the ranking.

Steps:

0. Reverse engineering into the doc:
   - PK: `F3 08` (`0x41c2b0`, code: `[4..5]` cid BE, `[6]` pk level stored at object `+0x2b9`, 6 and up sets
     `+0x18e`; the name colour per level), how the client attacks a player (which `15` / `19` it sends at a player
     cid, a modifier key?).
   - quests: the rest of [Quest window](#quest-window): when the client asks for `A0`, what the dialogs (`Dialog.bmd`
     50..73) say each quest gives. `Quest.bmd` (files): quest 0 wants 14/23 from dark wizards, knights and elves,
     level 150 and 1 000 000 zen (magic gladiators: a level 10000 requirement, so never); quest 1 wants 14/24 (knights),
     14/25 (elves), 14/26 (wizards) and 2 000 000 zen.
   - guilds: `50` (inline), `51` (`0x41df50`), `52` (inline), `53` (`0x41e110`), `54`, `55` (`0x45d160`), `56`
     (`0x41ea70`), `5A` (`0x41e8b0`), `5B` (`0x41e900`), `5C` (`0x41e750`), `5D` (`0x41e860`), war `60`..`64`; the
     requests (`50` from `0x46a340`, the create request with the name and the 32 byte mark), the guild master's
     window (`30` result for NPC 241).
   - Devil Square: `90` (`0x41fa70`, request `0x49d500`), `91` (`0x41fec0`), `92` (`0x45d100`), `93` (`0x41ff30`),
     `94`..`96`, `99`, the requests `97` / `98` (`0x49dff0`), Charon's (237) window, the invitation 14/19 (from the
     eye 14/17 and key 14/18), gates 58..61.
1. PK: hits on players with M4's formulas outside safe zones. Killing a player who isn't a murderer and didn't attack
   first raises the pk count, the pk level follows it (usual steps), attacking back is self defense for a while
   (usual), `F3 08` to the viewers, the level in `12` `[+30]` and `F3 03` `[40]`, saved (`pk_level`, `pk_count`). The
   count goes down with time in game (mup's choice), murderers drop an item on death (usual chance), shops refuse them
   and guards (M5 NPCs) attack them. No pk count in the Arena (map 6).
2. Quests: `data/Quest.bmd` (the client's), states in `characters.quest_state` at the bit positions the client reads
   (doc). Sevina (235): `30` answered with `A0` / `A1` instead of a window, `A2` proceed: level, zen and the quest item
   checked and taken, the new state, `A2` result. Rewards with `A3`: `C8` level up points, `C9` the class change
   (second class `CharacterClass`, saved, in `F3 00`, `12` `[+4]` and `F3 03`), after which second class items and
   skills (M3 / M4 checks) open. Quest items drop only for a character with the quest in progress (usual monsters).
3. Guilds: `guilds` / `guild_members` (M1, a migration for what's missing), create at the guild master (level, name
   rules, mark), join by asking a guild master in view, leave, kick, disband by the master, member list `52`, the guild
   of players in view (`5B`, `5C` with the mark), guild chat `@`, loaded on start and kept in memory. Guild war
   (`60`..`64`) last, if there is time.
4. Devil Square: a schedule from the config, Charon's window, the square by level and invitation (usual 0.97 four
   squares, magic gladiators lower), `90` entry, map 9 through its gates, monster waves (the later server's event
   sections for map 9 or mup's table, M2 left them out), the timer packets, a score per kill, at the end the ranking
   `93`, exp / zen by score, everyone back to town. The invitation mix in the chaos machine (M5 step 7).
5. Test (raw offsets): A kills B outside town (`17`, `F3 08` to both, the pk level in `F3 03` after relog, an item
   dropped); B's quests through GM commands (`A0`, `A1`, `A2` with the item and zen taken, `A3` class change, the
   class in the character list); B joins A's guild (both see `5B`); a Devil Square round on a short test schedule:
   entry, a kill's score, the ranking. Then the real client.

Not in M7: Blood Castle, Chaos Castle and the other later events, guild alliances, duels.

## Bots

AI players: ordinary accounts and characters that start at level 1, play through the same rules as clients and grow
by a career plan. Each B milestone follows the M milestones it needs.

Design:
- In process, no socket: a `BotSession` is a connection the game can't tell from a client. `view.py` shows every
  non monster connection as a player, so real clients see bots with no extra packets.
- Input: the bot builds client packets (`CMove`, `CAttack`, `CJoinGame`, ...) and dispatches them through
  `server.handlers` like `protocol.py` does. Bots can do nothing a client can't, every server check applies to them.
- Output: `write()` hands the built server packets to the brain. `Packet` keeps its values as attributes, so they are
  typed events (`SDamage`, `SKill`, `SLevelUp`, later trade and party requests) without parsing.
- Perception: `c.view`, what a client standing there has been shown.
- Brain in three layers:
  - career: hunting grounds derived from data, not hand written. `Monster.txt` levels and `MonsterSetBase.txt`
    spawns grouped by map and area; pick the one near the bot's level. Map progression from the `Gate.bmd` graph
    (entrance -> target, minimum level, MG 2/3). Stat build per class as point ratios. Personality: risk, greed,
    chattiness, play schedule (log in and out in sessions, progress only while online).
  - activity: small state machines (travel, hunt, loot, rest, restock / sell, trade, idle in town) with timeouts,
    picked by priority every few seconds: survive > restock > sell / repair > upgrade > level.
  - motor: `path.find_path` for short paths, cached gate to gate waypoints for long ones, attack speed cadence,
    skill choice by mana and range.
- Driven by the M2 game tick, each bot thinks every 0.5..1 s, staggered. No timers of its own.
- Storage: a migration with `bots (character_id, personality, career state as JSON, rng seed, schedule)`. Bot
  characters are ordinary `characters` rows saved by `GameServer.save`. `bin/account.py` creates bots.
- Bots get items and zen only from the drops, shops and kills players get, nothing out of thin air.
- Players can tell a bot when they ask or trade with it.

## B0 bots: session, hunting, levelling

- `Session` base for `BaseProtocol` and `BotSession` (cid, acc, player, view, playing, write). Move logic the
  handlers reach through the connection (`send_all`, which skips non `BaseProtocol` connections) into `mup/server`.
- Bot accounts and characters: the `bots` table, creation in `bin/account.py`, login without a password (set
  `acc`, dispatch `CJoinGame`), cids from the player range.
- Walk pacing: `move_handler` sets the position to the walk target at once, a bot sends short segments and waits
  for each like M2 monsters do (`next_step_at`). Measure the real client's walk speed per tile from logged traffic.
- Hunting grounds from `Monster.txt` / `MonsterSetBase.txt`, hunt / rest / return to town, death and respawn.
- Stat points through `F3 06` (handler still to write, see M4) by the class build.
- A simulation script: game and bots without sockets on a fast clock (`GameServer.now`), reports levels over
  simulated hours. Used to balance exp rates and bot behaviour.

Done when: the test's client sees a bot appear, walk, attack and kill; the simulation takes bots of all four
classes a few levels up without getting stuck; the real client watches a bot hunt outside Lorencia.

## B1 bots: items, shops, map progression

- Loot (`22`), potions (`26`), equip upgrades by class and stat requirements, gear requirements feed the stat build.
- Town trips: sell, buy potions, repair (M5 shops).
- Skills (M4), map progression through gates as levels unlock the next hunting ground.

Done when: a bot left alone goes from Lorencia to the next map's hunting ground with better gear than it started
with.

## B2 bots: party, whisper, trade

- Party: accept invites from players near the bot's level, follow the leader, share exp.
- Whisper and chat: canned lines per situation, a tiny command grammar (`price X`, `buy X`, `sell X`), wts / wtb
  ads in town chat. A language model for chat lines only, optional: async, with a timeout, never in the tick, no
  decisions.
- Item value: base price from `Item/ItemValue.txt` / `Shop/*.txt`, use to the bot (upgrade for its class and
  stats, jewels it needs), market memory: a `trades` log table, median price per item, level and options.
- Bot to bot: a server side order book matches wants and offers, bots meet in town and trade through the real
  `36`..`3D` flow so players see it.
- Bot to player: trade requests arrive as events, the bot checks every change of the window against its reserve
  price, accepts only after the other side has been unchanged for ~2 s, never takes unknown items, daily spend cap
  per bot.

Done when: a player buys an item from a bot and sells one to it in the real client; two bots trade with each other
in Lorencia.

## B3 bots: guilds, quests, events

- Join and create guilds, second class quest when the career reaches it, Devil Square entry.

## Reverse engineering backlog

- Unknown server packets: `01` and `0B` (located in M6, not reviewed), `03` (a check the client answers), `1A`,
  `71`, `F1 04` / `05` / `12`, `F3 07` / `08` / `13` / `20` / `22` / `23` / `40`.
- Client packets missed by the sender index, and `97`, `98`, `C1`.
