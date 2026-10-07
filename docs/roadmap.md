# Roadmap

One milestone per session. Each starts from `CLAUDE.md` and the spec below, ends with `tests/client.py` extended and
passing, a manual test with the real client, and the status updated here.

Packet codes are hex, details in `docs/protocol-097.md`. Where a code's meaning is marked "usual", it is the common
0.97 meaning and still has to be confirmed by reading the client's handler.

| milestone | status |
|---|---|
| M0 protocol fixes, housekeeping | done |
| M1 persistence, character select flow | todo |
| M2 world: maps, gates, monsters | todo |
| M3 items | todo |
| M4 combat and progression | todo |
| M5 NPCs, shops, warehouse, chaos machine | todo |
| M6 social: whisper, party, trade | todo |
| M7 guilds, quests, events, PK | todo |

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

## M4 combat and progression

- Damage formulas per class, stats and weapon, defense, miss, critical / excellent rolls, attack range and speed checks.
- Exp per monster level, experience table, stat points (`F3 06`), derived life / mana per class.
- Skills: data from `skill.bmd` / `Skill/Skill.txt` (mana, range, damage), learned from scrolls / orbs (`26`),
  area hits from the client's `1D` report instead of the server side guess, elf buffs, summons (`1F`), `1B` cancel,
  `F3 11` add / remove.

## M5 NPCs, shops, warehouse, chaos machine

- NPC spawns, talk `30` (result must be C3), shops `31`..`34` from `Shop/*.txt`, repair.
- Warehouse `81`..`83`. Chaos machine `86` / `87`, basic mixes.

## M6 social: whisper, party, trade

- Whisper `02` / `0C` (usual), confirm the client chat layout `00` (not reviewed yet).
- Party `40`..`44`: invite, list, member life, exp share.
- Trade `36`..`3D`.
- GM commands through chat.

## M7 guilds, quests, events, PK

- Guilds `50`..`56`, `5A`..`5D`, guild war `60`..`64`, 32 byte guild mark.
- Second class quests `A0`..`A3` (client `quest.bmd`).
- Devil Square `90`..`96`, `99`.
- PK: levels, timers, item drop on death.

## Reverse engineering backlog

- Item byte layout (M3).
- Unknown server packets: `01`, `0B`, `0C`, `11`, `1A`, `71`, `F1 04` / `05` / `12`, `F3 07` / `08` / `13` / `14` /
  `20` / `22` / `23` / `30` / `40`.
- Client packets missed by the sender index (whisper and others), and `97`, `98`, `A2`, `C1`.
- Client chat layout `00`.
