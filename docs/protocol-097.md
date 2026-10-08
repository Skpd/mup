# MU 0.97 protocol, as the client implements it

Extracted from the client binary itself, not from emulator sources or OpenMU.

| | |
|---|---|
| binary | `~/projects/client/mu/main.exe` (0.97b Chs, "0.97.2.0"), md5 `13068908ce2aaa018627a02c06c6d733` |
| original | `main.exe.orig`, md5 `2ecc66720cac2a461dcf8325f87dd74f`, differs only in server address and serial |
| version | `09704`, stored in the exe as `1;:49` (each byte + position + 1) |
| tools | Ghidra 12.1.4 headless, `tools/ghidra/*.java`, `tools/extract_*.py`, driven by `tools/extract.sh` |

Every layout below is marked with where it was confirmed:

- **code**: read in the decompiled handler / sender
- **traffic**: seen byte for byte in a real client session (`1791384296.log`)
- **index**: only located by the scripts, layout not reviewed
- **files**: checked in the data files of this client and of the later clients in `~/projects/client/Cliente` and
  `~/projects/client/client_wip` (maps up to World79)

Offsets are from the start of the packet, including the header. Multi-byte values are little endian unless
marked BE. Object ids (`cid`) are always 2 bytes BE, the high bit is a flag the client masks off (`& 0x7FFF`).

## Regenerating

```
tools/extract.sh ~/projects/client/mu/main.exe /tmp/mu-extract
```

About 2 minutes. Writes `receive.txt` (dispatch map), `receive_fields.txt` (offsets each handler reads),
`send.txt` (client packets, heuristic) and the decompiled `dispatcher.c`, `handlers.c`, `senders.c`.
The two address arguments of `extract.sh` (receive switch jump `0x4213f4`, receive loop `0x420c93`) are specific
to this exe.

## Where things are in main.exe

| what | address |
|---|---|
| receive loop + dispatcher (`ProtocolCompiler` / `TranslateProtocol` inlined) | `0x420c70` |
| head code switch | `0x4213ee`: `cmp esi, 0xF4`, index table `0x422a50`, jump table `0x4228e4` |
| packet builder `AddData(this, data, size, xor)` | `0x403390` |
| xor range helper (inlined single byte appends) | `0x403290` |
| C3/C4 encrypt | `0x4e7220` (called twice: size, then encrypt) |
| C3/C4 decrypt | `0x4e7290` |
| `send` thunk / import | `0x4e7188` / IAT `0x4f7338` (ws2_32 ordinal 19) |
| default server address pointer, port | `0x503bf8` -> slot `0x4fc35e` (`mu.skpd.dev`, patched, 3 of the 4 address slots), `0x503bfc` = 44405 |
| quest object | pointer at `0x5253a4`: `+0x04` class, `+0x05` second class, `+0x08` `Quest.bmd` records, `+0x1c848` quest states (50 bytes), `+0x1c87a` current quest, `+0x1c87b` quest window open, `+0x1c87c` current dialog, `+0x1c87e` state of the current quest |
| quest window | text selection `0x401710`, answer click `0x401d00`, window click `0x402660`, close `0x401920`, show dialog `0x4017a0` |
| `Dialog.bmd` in memory | `0x7c11330`, `0x400` per entry, index of the dialog shown `0x503c1c` |
| data file loading | `0x4c09b0`: `Quest.bmd` `0x401040`, `Dialog.bmd` `0x459aa0` |
| objects (characters, monsters, NPCs) | 400 of `0x364` bytes at `DAT_07a5f9b8`: `+0x00` in use, `+0x1ac` cid, `+0x2cd` dead, `+0x2d6` / `+0x2d7` walk target, `+0x358` / `+0x35c` tile x / y. Find by cid `0x43dc30` (400 when missing), remove all but one cid `0x43dac0` |
| world load | `0x4bef50`: object models `0x4bd0b0`, then `Data\World{map+1}\`: `Terrain.map` (`0x4aa9c0`), `Terrain{map+1}.att` (`0x4aa820`), `terrain.obj` (`0x4b27d0`), textures, see [Maps](#maps). Current map number at `0x4fd640`, read in 51 functions |
| hero character | pointer at `0x7c0dd1c`: `+0x0e` level, `+0x10` exp, `+0x14` str `+0x16` agi `+0x18` vit `+0x1a` ene, `+0x1c` life `+0x1e` mana `+0x20` max life `+0x22` max mana, `+0x40` next exp, `+0x60` level up points (2 bytes each, exp and next exp 4). Kept encrypted between uses, see [Extending the client](#extending-the-client) |
| next level exp | `0x45c980`, called by the `F3 05` handler, see [Client limits](#client-limits) |
| `Text.bmd` in memory | `0x7c45a4c`, 300 bytes per entry (from the character window's format pointers) |
| frame | `SwapBuffers` in `0x4d1460` (game scenes), `0x4c3b20` (map loading, calls the world load), `0x4d0820` (loading screen) |
| interface | all windows drawn by `0x4a9370` (called from `0x47fa9e` in `0x47f970`), window hotkeys `0x4779b0`. Character window `0x4a20e0` (open flag `0x7dab76e`, position `0x7daae84` / `0x7daae88`, clicks and the `F3 06` sender `0x49c950`), party `0x4a44e0` |
| terrain attributes | `0x828d278`, 256 x 256 bytes, index `0x4aa780`: `(y & 0xFF) << 8 \| (x & 0xFF)` |
| path finder | `0x425720`, state at `0x57c7208` (`+0x08` points to the attributes) |
| gate check, sends `1C` | `0x474030`, every frame. `Gate.bmd` in memory at `0x7c11328` |
| items | see [Items](#items): type from item bytes `0x459b80`, item from bytes `0x45a270`, place in a window `0x48d940`, remove `0x48e0d0`, put the held item back `0x48e650`, free space check `0x493880`. Held item `0x7d92a60` (`0x44` bytes), its source slot `0x7da71e0`, move pending `0x7dab7ad`. Equipment window `0x48eec0`, inventory window clicks and right click use `0x4916f0` |

## Transport

Headers: `C1 size head ...` and `C3 size ...`, `C2 sizeH sizeL head ...` and `C4 sizeH sizeL ...` (code).

**Client -> server, C1/C2.** The header (type, size, head) is plain, everything after it, sub code included,
is xor chained with the 32 byte key `E7 6D 3A 89 ...` (`buf[i] ^= buf[i-1] ^ key[i % 32]`). Exception: the
connect server requests (`F4 02`, `F4 03`) are plain (code, traffic).

**C3/C4.** Built as C1/C2 (fields xor chained as above), then the first byte after the header is replaced by
a serial counter and the rest is SimpleModulus encrypted (code).

- The client keeps one serial counter for packets it sends (`0x57c7113`) and one it expects (`0x57c7114`),
  shared by C3 and C4, incremented per packet, 1 byte.
- **When a received C3/C4 serial doesn't match**, the client resyncs its counter but treats that packet as
  *not encrypted* (code, dispatcher `0x420d4a..`).

**Packets the client only accepts encrypted.** The dispatcher passes an "arrived encrypted" flag to these
handlers. On a C1 or a serial mismatch they drop the packet and the client sends `C1 F1 03 00` (code):

`16` exp, `19` skill animation, `1C` map move, `1E` area skill animation, `24` item move result, `29`,
`30` npc talk, `F1 02` logout result (types 1 and 2), `F3 03` character info, `F3 10` inventory.

**Login fields** (account, password) are additionally xored with `FC CF AB` (repeating) before the chain
(code, traffic).

## Connect server

| dir | packet | layout | src |
|---|---|---|---|
| S>C | `C1 04 00 01` hello | head `00` is shared with chat: while the client is on the server list screen (state 2) any `00` makes it request the server list | code `0x414960` |
| C>S | `C1 04 F4 02` server list request | no fields, not xored, sent on hello (and again when the list is refreshed) | code, traffic |
| S>C | `C2 F4 02` server list | `[5]` count, then **4 bytes per server**: `[+0..1]` server code (`group * 20 + index`), `[+2]` load %, `[+3]` unused. Group 12 has a special name | code `0x411e60` |
| C>S | `C1 06 F4 03` server info request | `[4..5]` server code (little endian) | code `0x4caad0`, traffic |
| S>C | `C1 16 F4 03` server info | `[4..18]` ip string (15 bytes + 0), `[20..21]` port | code `0x421a28` |
| S>C | `C1 F4 05` | no fields, sets the client's scene state to 1, meaning not reviewed | code |

## Game server, server -> client

| packet | layout | src |
|---|---|---|
| `C1 F1 00` join result | `[4]` 1 = ok, `[5..6]` player cid BE, `[7..11]` version, must equal the exe's decoded version (`09704`), otherwise "version not matched" | code `0x4122b0` |
| `C1 F1 01` login result | `[4]` result: 1 ok; 0, 2..6, 8..0x0D, 0x11, 0xC0..0xC2 and 0xD0..0xD2 each show their own message, anything else a generic error. Usual meanings: 0 wrong password, 3 in use, 4 server full, 5 banned, 6 new version | code (dispatcher) |
| `C3 F1 02` logout result | `[4]` type. 0: the client destroys its window (exits), the encryption isn't checked. 1: must be encrypted, back to character select, the client resets its game state and sends `F3 00` itself. 2: must be encrypted, the client closes the connection and goes back to the server list (scene 2). Other values: ignored | code `0x4129f0` |
| `C1 F3 00` character list | `[4]` count, then 26 bytes per character: `[+0]` slot, `[+1..10]` name, `[+11]` 0, `[+12..13]` level, `[+14]` ctl code (`& 0x10` marks the char), `[+15]` class, `[+16..25]` equipment | code `0x4124b0` |
| `C1 F3 01` character created | `[4]` result: 1 ok, 0 opens dialog `0x36`, 2 dialog `0x37` (texts not looked up, mup uses the usual meanings: 0 bad or taken name, 2 no free slot). `[5..14]` name, `[15]` slot: index into the 5 character slots (`0x364` bytes each at `DAT_07a5f9b8`). Class and look come from the create screen, nothing after `[15]` is read | code `0x412600` |
| `C1 F3 02` character deleted | `[4]` 1 opens dialog `0x39` (deleted), anything else dialog `0x3a` showing the value as an error code. mup: 0 no such character of the account, 2 wrong personal code | code (dispatcher) |
| `C3 F3 03` character info | **42 bytes**, must be encrypted: `[4]` x `[5]` y `[6]` map `[7]` direction, `[8..11]` exp, `[12..15]` next exp, then 2 bytes each: `[16]` level up points `[18]` str `[20]` agi `[22]` vit `[24]` ene `[26]` life `[28]` max life `[30]` mana `[32]` max mana, `[34..35]` unused, `[36..39]` money, `[40]` pk level, `[41]` ctl code | code `0x413380` |
| `C1 F3 04` respawn | 20 bytes: `[4]` x `[5]` y `[6]` map `[7]` direction, `[8..9]` life `[10..11]` mana (little endian), `[12..15]` exp `[16..19]` money. Clears all 400 objects, creates the hero again at x, y and loads the map when it isn't the current one. The client sends nothing back | code `0x413b00` (asm: the decompile loses the packet pointer) |
| `C1 F3 05` level up | `[4]` level `[6]` level up points `[8]` max life `[10]` max mana, 2 bytes each. Life and mana are set to the new max, the next level's exp is computed by the client (`0x45c980`, see [Client limits](#client-limits)) | code `0x41b6d0` (asm) |
| `C1 F3 06` level up point result | `[4]` high nibble 0: nothing changes. Otherwise the low nibble is the stat (0 str, 1 agi, 2 vit, 3 ene): the client takes one level up point and adds 1 to the stat itself, vit also sets max life and ene max mana to `[6..7]`. No maximum is checked | code `0x41b9a0` (asm) |
| `C4 F3 10` inventory | must be encrypted. `[5]` count, then 5 bytes each: `[+0]` slot, `[+1..4]` item (see [Items](#items)). Slots 0..11 equipment, 12..75 the 8 x 8 grid (`slot - 12 = y * 8 + x`, the item's top left tile). The client empties equipment and grid first, then places each item (`0x48d940`) | code `0x414310` |
| `C1 F3 11` skill list | `[4]` count (max 20), then 3 bytes each: `[+0]` slot, `[+1]` skill number, `[+2]` unused. `[4]` = `0xFE`: set one skill, `[5]` slot `[6]` number. `[4]` = `0xFF`: remove skill at slot `[5]` | code `0x414010` |
| `C1 F3 30` key settings | 18 bytes: `[4..13]` the skill number on hotkey 0..9, `FF` none: the client looks the number up in its skill list (character `+0x63`) and puts that list index on the hotkey. `[14..17]` other settings, read, not reviewed. Same layout as the client's `F3 30` | code `0x41ff50` |
| `C1 00` chat | `[3..12]` name, `[13..72]` message. Message prefix `~` party, `@` guild, `#` shout, anything else normal chat | code `0x414960` |
| `C1 0D` notice | `[3]` type, `[4..]` text | code `0x414d10` (reads only) |
| `C1 0F` weather | `[3]` high nibble: 0 turns the effect off, 1 turns it on with intensity low nibble * 6, other values are ignored | code (dispatcher) |
| `C1 10` walk | `[3..4]` cid, `[5]` x `[6]` y, `[7]` direction in the high nibble. Any object but the hero (players and monsters alike): x, y becomes its walk target and the client finds the path there from the tile it has the object on (`0x425720`), puts it on the target when there is none. The hero: x, y becomes its tile when it isn't walking. Dead objects (`17`) are ignored | code `0x414ea0` |
| `C1 11` place | `[3..4]` cid, `[5]` x `[6]` y: puts the object on x, y without walking. mup sends it to the players who see a teleport | code `0x415250` |
| `C2 12` players in view | `[4]` count, then **32 bytes** each: `[+0..1]` cid, `[+2]` x `[+3]` y, `[+4]` class `<< 5 \| 2nd class << 4 \| pose` (pose 2..4 pick a sitting / leaning animation), `[+5..14]` equipment, `[+16]` effects bits 0..3 (poison, ice, damage buff, defense buff) and `[+17]` bit 0 another effect, `[+18..27]` name, `[+28]` target x `[+29]` target y, `[+30]` direction << 4 \| pk level, `[+31]` unused. Names containing `webzen` are skipped | code `0x4164b0` |
| `C2 13` monsters in view | `[4]` count, then 12 bytes each: `[+0..1]` cid, `[+2]` type, `[+3]` unused, `[+4..5]` effects (little endian word: bits 0..3 as in players in view, bit 8 the `[+17]` effect), `[+6]` x `[+7]` y, `[+8]` target x `[+9]` target y, `[+10]` direction in the high nibble. The client creates the monster at x, y and walks it to the target. Bit 15 of the cid set: no walk, `0x416ed0` instead (not reviewed, usual meaning: just respawned). Creating fails when the 400 objects are taken, the rest of the list is skipped then | code `0x416fe0` |
| `C2 1F` summons in view | `[4]` count, then **22 bytes** each: `[+0..10]` as in `13` (bit 15 of the cid: no walk), `[+10]` low nibble stored where players keep the pk level, `[+11..20]` the owner's name: the client names the monster after its owner (`Text.bmd` 485 "Of" and the monster's name appended) | code `0x4172c0` |
| `C1 14` out of view | `[3]` count, then cids from `[4]` | code (dispatcher, asm) |
| `C1 15` damage | `[3..4]` target cid, `[5..6]` BE: damage in the low 13 bits (max 8191), flags in bits 13..15 of the BE word, i.e. `[5]` bits 5..7: bit 7 blue (critical), bit 6 green (excellent), bit 5 magenta, green wins over blue over magenta, none: orange, red when the target is you. Damage 0 shows a miss. When the target is you the client also subtracts the damage from its life (hero `+0x1C`, 2 bytes, stops at 0). The mask is `AND EBX, 0x1FFF` at `0x417a0c`, the value's high byte and the flags are both read from `[5]` through `AL` (`0x4179ea`) | code `0x4179a0` |
| `C3 16` kill exp | must be encrypted: `[3..4]` killed cid, bit 15 clear: the hero swings at the object (it is the killer's melee hit), set: `0x42b200` on the object instead (mup sets it for skills and the other players who share the exp), `[5..6]` exp BE, `[7..8]` damage BE, shown like a damage number. The damage is a full 16 bits, unlike `15`. The object's dead flag is set, the exp is added to the hero's 4 byte exp and shown in the chat log when not 0 | code `0x4199a0` |
| `C1 17` killed | `[3..4]` cid of the dying object, nothing else is read. Sets the object's dead flag (`+0x2cd`) and stops its walk, the hero too | code (dispatcher, asm) |
| `C1 18` animation | `[3..4]` cid, `[5]` direction, `[6]` animation, nothing after it is read. Puts the object on its walk target first. Animations: `64` / `65` attack (players: by weapon, monsters: animation 4, every third time 3, their two attacks), `66` / `67` stand, `12` and `6C`..`80` emotes (mapped per class), anything else sets that animation number directly | code `0x417fc0`, `0x42a950` |
| `C3 19` skill animation | must be encrypted: `[3]` skill number, `[4..5]` caster cid, `[6..7]` target cid (bit 15: effect applied, kept on the caster at `+0x2d1` for the hit) | code `0x4186b0` |
| `C1 1B` effect ended | `[3]` skill number, `[4..5]` cid: clears the effect bit (object `+0x76`) of the skill: 1 poison bit 0, 7 ice bit 1, 28 greater damage bit 2, 27 greater defense bit 3, 16 mana shield bit 8. Other skills: nothing | code `0x418500` |
| `C3 1C` map move | must be encrypted: `[3]` 0: teleport on the map with the teleport animation, objects stay. Anything else: map change, the client removes all objects but the hero, loads `[4]` when it isn't the current map and answers `F3 12`. `[4]` map, `[5]` x `[6]` y, `[7]` direction. Also ends the wait after its own `1C` request | code `0x415520` |
| `C3 1E` area skill animation | must be encrypted: `[3]` skill number, `[4..5]` caster cid, `[6]` x `[7]` y | code `0x418fd0` |
| `C2 20` items in view | `[4]` count, then 8 bytes each: `[+0..1]` item id BE (0..999, the client puts larger ids on 0), bit 15 set: just dropped (falls with a sound), `[+2]` x `[+3]` y, `[+4..7]` item. **Zen** (type `0x1CF`, 14/15) takes 9 bytes: the amount is 24 bits, `[+5]` `[+6]` `[+8]` big endian, `[+4]` `CF` and `[+7]` `80` give the type | code `0x419f90`, `0x4b58a0` |
| `C2 21` items gone | `[4]` count, then 2 byte item ids BE from `[5]` | code (dispatcher) |
| `C1 22` pick up result | `[3]` `FF`: nothing picked up. `FE`: zen, `[4..7]` the new money total, **big endian**. Anything else: inventory slot, `[4..7]` item, placed there over what the slot holds (a grown stack keeps its slot). Ends the wait after `22` (one pick up at a time) | code `0x41a0b0` |
| `C1 23` drop result | `[3]` 0: refused, the held item goes back where it was. Otherwise dropped: `[4]` the slot it came from is cleared (below 12 an equipment slot) | code `0x41a3a0` |
| `C3 24` move result | must be encrypted. `[3]` `FF`: refused, the held item goes back (`0x48e650`). Otherwise `[3]` window: 0 inventory (8 x 8, slots as in `F3 10`), 1 trade (8 x 4), 2 warehouse (8 x 15), 3 chaos machine (8 x 4), `[4]` slot, `[5..8]` item placed there. Ends the wait after `24` (one move at a time) | code `0x41a680` |
| `C1 25` look change | `[3..4]` cid, `[5..8]` the item, but `[6]` is slot << 4 \| level. `[5]` `FF`: the slot is empty. Slots 0..8 (right hand, left hand, helm, armor, pants, gloves, boots, wings, pet), the others are ignored. The low nibble is the model level for the right hand and the glow index (as in [Equipment look](#equipment-look)) for slots 1..6. `[8] & 0x3F` excellent | code `0x416060` |
| `C1 26` life | `[3]` `FF`: life, `FE`: max life, value `[4..5]` **big endian**. `FD`: unlocks item use (see [Items](#items)). Other values: an inventory slot (12..75), the count (durability) of the item there goes down by one, at 0 the item is removed. Doesn't unlock item use | code `0x41bcd0` |
| `C1 27` mana | `[3]` `FF`: mana, `FE`: max mana, value `[4..5]` big endian. Other values: mana from `[4..5]` and the item count as in `26` | code `0x41bfc0` (asm) |
| `C1 28` item deleted | `[3]` slot (`FF`: none, equipment slots too), `[4]` not 0: unlocks item use | code (dispatcher), `0x48e0d0` |
| `C1 2A` durability | `[3]` slot (below 12 equipment), `[4]` durability, `[5]` not 0: unlocks item use | code `0x41c3b0` |
| `C1 A0` quest states | `[3]` byte count, then the state bytes (see [Quest window](#quest-window)). The client zeroes its 50 state bytes and copies `[3]` bytes, the count isn't checked against 50. Also sets the quest class from the hero's class (low 3 bits class, bit 3 second class): the only place it is set | code `0x420320`, `0x401160` |
| `C1 A1` quest dialog | `[3]` quest index, `[4]` state byte, stored as state byte `quest >> 2`. Closes the other windows and opens the quest window with the text for the quest's state. Doesn't check which NPC is being talked to | code `0x420350`, `0x4018d0` |
| `C1 A2` quest state result | `[3]` quest index, `[4]` result: 0 does what `A1` does with `[5]` as the state byte, anything else is ignored | code `0x420380` |
| `C1 A3` quest reward | `[3..4]` cid, `[5]` type. `C8`: effect and sound, when the object is the hero `[6]` is added to its level up points (the field `F3 05` `[6]` sets). `C9` class change: `[6]` class as in players in view `[+4]` (class << 5 \| 2nd class << 4), stored on the object as `((v & 0x10) \| v >> 4) >> 1`, also in the hero's character info when it is the hero, effect and sound. Other types do nothing | code `0x4203c0` |

Everything else the client handles is listed in appendix A with the offsets its handler reads.

## Game server, client -> server

| packet | layout | src |
|---|---|---|
| `C3 F1 01` login | 49 bytes: `[4..13]` account, `[14..23]` password (both xor `FC CF AB`), `[24..27]` tick count (GetTickCount, little endian), `[28..32]` version `09704`, `[33..48]` serial | code `0x4cb840`, traffic |
| `C1 F1 03` client report | `[3]` 3, `[4]` reason: 0 = a must-be-encrypted packet arrived unencrypted. When a C3/C4 packet fails to decrypt the client sends reason 6 instead, itself encrypted (C3) with a random byte appended | code (handlers, dispatcher) |
| `C1 F3 00` character list request | no fields | traffic |
| `C1 F3 01` create character | `[4..13]` name, `[14]` class: **class number << 2** (0 dw, 16 dk, 32 elf, 48 mg), everything the server sends uses class number << 3 | traffic |
| `C3 F1 02` logout request | 5 bytes, sent encrypted: `[4]` type as in the result: 0 close the game, 1 character select, 2 server select. Preceded by `F3 30` (types 0 and 1 before, type 2 right after). The sender isn't in the sender index, a byte scan for `F1` head stores doesn't find it either | traffic (`1791402942.log`, `1791403016.log`) |
| `C1 F3 30` key settings | 18 bytes, sent on every logout (`0x4c0000`): `[4..13]` the skill number on hotkey 0..9 (taken from the skill list, all 0 when none set in traffic), `[14..17]` other settings (window flags, values + `0x40`; `09 00 04 08` seen), not reviewed. The server's `F3 30` has the same layout | code, traffic |
| `C3 31` | no fields, sent right after `F3 00` when going back to character select. Usual meaning: close the NPC / shop window. Sent by the quest window's close (`0x401920`: answer return code 2, close button), which the character select reset (`0x412700`) also calls | traffic, code `0x401920` |
| `C3 30` talk | `[3..4]` NPC cid. Sent when clicking an NPC of type 234 (`EA`) or higher, clicks on lower types send nothing | code `0x4650a0` |
| `C3 A0` quest states request | no fields, sent right before `30` while the client has no quest class yet (until the first `A0` arrives) | code `0x4650a0` |
| `C3 A2` quest proceed | `[3]` quest index, `[4]` 1. Sent by a dialog answer with return code 1 (after the client's requirement check) or 3 (no check), and by a click in an area of the quest window (`0x402660`, when it is drawn not reviewed) | code `0x401d00`, `0x402660` |
| `C1 F3 02` delete character | `[4..13]` name of the selected character, `[14..23]` the personal code as typed in the dialog (10 byte buffer, zero padded) | code `0x4c3f40` |
| `C1 F3 03` enter game | `[4..13]` name | traffic |
| `C1 F3 06` add level up point | 5 bytes, `[4]` stat: 0 str, 1 agi, 2 vit, 3 ene (the four buttons of the character window, top to bottom). Sent while the hero has level up points, the stat's value isn't checked | code `0x49c950`, traffic |
| `C1 F3 12` map loaded | 4 bytes, no fields, sent by the `1C` handler after a map change | code `0x415520` |
| `C3 0E 00` ping | 12 bytes: `[4..7]` tick count, `[8..9]` attack speed, `[10..11]` magic speed | code `0x40e2a0`, traffic |
| `C1 10` walk | `[3]` x `[4]` y (start of the walk), `[5]` direction << 4 \| step count, `[6..]` step directions, one per nibble, high nibble first. Sent with 0 steps to only turn | traffic |
| `C1 15` attack | `[3..4]` target cid, `[5]` attack animation (0x64 seen), `[6]` direction | traffic, code `0x4650a0` |
| `C1 18` animation | `[3]` direction, `[4]` animation (0x66 seen when turning) | traffic |
| `C3 19` skill on target | `[3]` skill list index (the selected one, hero object `+0x361`), `[4..5]` target cid. Sent when the target is within the skill's distance (`skill.bmd`, tiles; knight weapon skills 19..23 1.2 times it), otherwise the hero walks there first. Knight weapon skills send a `10` turn before it. The summons (30..36) are sent as `19` too, with the hero's cid presumably (`0x57c70d4`, not reviewed), never on map 10 | code `0x462140`, `0x4650a0` |
| `C3 1E` area skill | `[3]` skill list index, `[4]` x `[5]` y, `[6]` direction | code `0x46f270` |
| `C3 1C` move through a gate | 6 bytes: `[3]` gate number, `[4]` `[5]` 0. Sent while the hero stands in the area of an entrance gate (`Gate.bmd` kind 1) of its map and its level is at least the gate's (magic gladiators: two thirds of it, class number 3), else the client shows the level message. At most every 3 s and only one until a `1C` answer arrives. Gates 45..49, 55, 56 also need the hero not riding a Horn of Uniria / Dinorant (items `0x1A2` / `0x1A3`), 62..65 a check not reviewed | code `0x474030` |
| `C3 1C` teleport | 6 bytes: `[3]` 0, `[4]` x `[5]` y, the target tile. Sent for the teleport skill (6) when the target tile's attribute is 0 (no safe zone, wall or anything), at most every 3 s and one until the `1C` answer, not riding (13/2 check, not reviewed). The answer is `1C` with `[3]` 0 | code `0x46f270` |
| `C3 1D` area skill hits | `[3]` skill list index, `[4]` x `[5]` y, `[6]` serial, `[7]` count, then target cids BE. **Has a byte between y and count** that OpenMU's 0.75 layout doesn't. Sent by the skill effects as they land (`0x442ec0`, `0x447d60`, `0x448120`, `0x450190`), so one cast can send several: at most 5 targets, objects within a radius of the effect's point (80..300 world units, 0.8..3 tiles, per effect), monsters or the one player the skill aims at, not dead, not the hero. Nothing is sent when no object is in reach. x, y and serial come from the effect | code `0x442610` |
| `C1 00` chat | name + message, not reviewed yet: send a chat line and check the log | - |
| `C3 22` pick up | `[3..4]` item id BE. Sent when the hero is within 150 units of the item (1.5 tiles from the tile centre, the client walks there first) and the item fits in the grid (zen always), one at a time until `22` answers | code `0x4650a0` |
| `C3 23` drop | `[3]` x `[4]` y (the tile under the mouse), `[5]` the slot the held item came from | code `0x497760` |
| `C3 24` move | 11 bytes: `[3]` source window, `[4]` source slot, `[5..8]` the item as the client has it, `[9]` target window, `[10]` target slot. Windows and slots as in the result. One at a time until `24` answers. The client also sends it on its own: arrows / bolts from the grid into a hand when a bow / crossbow has none (`0x463d60`), the left hand item to the right hand (`0x474ac0`) | code `0x422db0` |
| `C3 26` use item | `[3]` inventory slot, `[4]` target slot (0 for potions). Sent on a right click on 14/0..6 (apple, potions), 14/8, 14/9, 14/20, group 15 (scrolls), 12/7..14, 12/16..19, and by the potion hotkeys, and by the client itself with a mana potion's slot when the hero lacks the mana for a skill (`0x46f270`). Locks item use until the server unlocks it (see [Items](#items)). mup answers a scroll / orb it teaches with `F3 11` `FE` and `28` (slot, 1), the usual answer, not checked in the client's code | code `0x4916f0` |

## Terrain

`Data\World{map+1}\Terrain{map+1}.att`, read at `0x4aa820` (code): 0x10003 bytes, `00 FF FF`, then 256 x 256
attribute bytes, index `y * 256 + x`. The client refuses the file (and the map) when the size or header differ, a
byte is above `0x7F`, or on maps 0..4 one tile doesn't hold the value it checks. The `Terrain.att` next to it in
most World folders isn't read.

| bit | meaning |
|---|---|
| `01` | safe zone |
| `02` | a character stands there, set and cleared by the client at run time (`0x439670`). A few files have one left |
| `04` | wall |
| `08` | no ground |

The path finder steps only on tiles below 2, so walls, void and other characters block it. A straight line check
(`0x460a30`) passes tiles below 4. Positions: tile x is `(x + 0.5) * 100` in the world, a direction byte d is an
angle of `(d - 1) * 45` degrees (`1C`, `F3 04`, `13`, `18`).

The server's own terrain files (`~/projects/client/Data/Terrain`, a later version) are the same for maps 0, 1, 3, 5,
8, 9, 10 and differ for 2, 4, 6, 7. mup uses the client's, copied to `data/terrain` (`mup/server/terrain.py`).

## Gates

`Data\Gate.bmd`, loaded in `0x4c09b0`: 100 entries of 9 bytes, xor `FC CF AB` (9 is a multiple of 3, so a key
restarting per entry is the same as one run over the file): kind (0 town / warp target, 1 entrance, 2 exit), map,
x1, y1, x2, y2 (inclusive), target gate, direction, minimum level. The gate check (`0x474030`, code) reads kind,
map, area and level; target and direction are server data, their places are from the decoded file matching
`Move/Gate.txt` (index). Copied to `data/Gate.bmd` (`mup/server/gate.py`).

This client has gates 1..27 (Lorencia, Dungeon, Devias, Noria), 50..52 (Arena) and 58..61 (Devil Square), none for
Lost Tower, Atlans, Tarkan and Icarus. Compared with the server's `Move/Gate.txt` the entries match, except the
Dungeon gates 5..16: level 40 / 50 here, 20 there. Town gates: 17 Lorencia, 22 Devias, 27 Noria.

## Maps

What the client loads for map n, the same code for every map number (`0x4bef50`, code):

| `Data\World{n+1}\` | |
|---|---|
| `Terrain.map` | 196609 bytes: a version byte, then three 256 x 256 layers: tile index, second tile index, alpha of the second layer (byte / 255). Layer 2 holds 255 where there is no second tile (files) |
| `Terrain{n+1}.att` | see [Terrain](#terrain) |
| `Terrain.obj` | `[0]` version, `[1..2]` count, then 30 bytes per object: `+0` model slot (2 bytes), `+2` position, `+14` angle, `+26` scale (floats). A missing file shows "file not found" and closes the client |
| `TerrainHeight.OZB`, `TerrainLight.OZJ` | height and light map, asked for as `.bmp` / `.jpg` |
| tiles | `TileGrass01`, `TileGrass02`, `TileGround01..03`, `TileWater01`, `TileWood01`, `TileRock01..07` in bitmap slots `0x23..0x30`: 14 tile textures, presumably tile index 0..13 (the mapping isn't read). Also `TileGrass01..03` OZT, `leaf01` / `leaf02`, `rain01` / `rain02` from World1 and `rain03` from World10 |

Object models (`0x4bd0b0`, code). Lorencia (map 0) loads named models from `Data\Object1\` (`Tree01.bmd`, ...)
into fixed slots. Every other map loads `Data\Object{n+1}\Object01.bmd` .. `Object160.bmd` into model slots 0..159,
textures from the same folder, missing files are skipped. The object type in `Terrain.obj` is the slot. On top come
extras per map in slots above 159: animals (0, 1, 3, 4), the meteors and boss of map 5, Atlans water (7), Tarkan
sand (8), Icarus clouds (10), and a few values set after loading for maps 1 and 8.

`World6` (map 5) has only `Terrain6.att` in this client, no `Terrain.map` or `Terrain.obj`: the map is unused.

**Later clients** (files). `Cliente` and `client_wip` keep the same data, encrypted with the map file xor
(bytes, `k` starts at `0x5E`): `out[i] = (in[i] ^ key[i % 16]) - k; k = in[i] + 0x3D`, key
`D1 73 52 F6 D2 9A CB 27 3E AF 59 31 37 B3 E7 A2`.

| later file | decrypted | for this client |
|---|---|---|
| `EncTerrain{n}.map` | `[0]` version, `[1]` map number, the three layers | drop `[1]` |
| `EncTerrain{n}.obj` | `[0]` version, `[1]` map number, `[2..3]` count, the same 30 byte entries | drop `[1]`. Cliente's `EncTerrain1.obj` counts one entry more than it holds |
| `EncTerrain{n}.att` | then xor `FC CF AB`: `[0]` version, `[1]` map number, `[2..3]` `FF FF`, then 256 x 256 attributes of 1 byte (65540 bytes) or 2 bytes (131076 bytes), depending on the map and the client | the low byte with an `00 FF FF` header. Bits above `0x08` not reviewed, the client refuses bytes above `0x7F` |
| `Object{n}\ObjectNN.bmd` version 12 | `BMD`, `0C`, 4 byte size, then encrypted data. Decrypted it has the layout of version 10 (name, mesh / bone / action counts, checked on World38 `Object01`) | `BMD`, `0A`, the decrypted data. Not tried in the client yet |
| `TerrainHeight.OZB`, `TerrainLight.OZJ`, `.OZJ` / `.OZT` textures | the same as in this client (`TerrainHeight.OZB` 66620 bytes in both) | copy |

Every map of `client_wip` uses tile indices 0..13 only. Object types stay below 160 except World52 (165) and
World58 / World59 (247): the slots above 159 aren't loaded from the map folder and hold the extras above. Later
clients draw some objects, water, sky, fog and effects with code of their own per map, this client's per map code
only knows maps 0..10. Monster models are loaded per monster type in the client (`Data2\Monster\`, `0x4bc4d0`,
not reviewed), so a ported map can only show monster types this client has. Map numbers above 10 are not tried.

## Items

**Types**: `group * 32 + index`, 0..511, 16 groups.

**`Data\Local\item.bmd`** (files, code `0x45a270` reads the fields): 512 records of 56 bytes xor `FC CF AB`, then
4 bytes (a checksum, not checked). In memory as they are, pointer at `0x7c85330`. Copied to `data/item.bmd`.

| offset | field |
|---|---|
| 0..29 | name (some entries in Korean, EUC-KR) |
| 30 | two-handed |
| 31 | level (drop level) |
| 32, 33 | width, height in the grid |
| 34, 35 | damage min, max |
| 36 | defense rate (shields) |
| 37 | defense |
| 38 | magic defense |
| 39 | attack speed (gloves: the bonus) |
| 40 | walk speed (boots) |
| 41 | durability (potions, arrows: the stack size shown) |
| 42 | magic durability, staffs |
| 43, 44, 45 | strength, agility, energy requirement base |
| 46 | level requirement |
| 47 | value (potions: the heal value) |
| 48..51 | classes dark wizard, dark knight, elf, magic gladiator: 0 no, 1 yes, 2 second class only |
| 52..55 | resistances ice, poison, lightning, fire (rings, pendants) |

**Item bytes**, 4 in every packet (code `0x459b80`, `0x45a270`):

| byte | bits |
|---|---|
| 0 | type & 0xFF |
| 1 | bit 7 skill, bits 3..6 level (0..15), bit 2 luck, bits 0..1 option bits 0..1 |
| 2 | durability (count for potions) |
| 3 | bits 0..5 excellent options, bit 6 option bit 2, bit 7 type bit 8 |

The option is 0..7: + 4 damage per step on weapons, + 5 defense rate on shields, + 4 defense on armor, 1% life
regeneration on rings / pendants (usual meanings, the client adds 5 * option to the strength requirement). Excellent
bits: `0x45a270` adds one tooltip line per bit, a set for armor, shields and wings, another for weapons and
pendants (option ids `0x42..0x4f`, their texts not looked up).

**Slots**: 0 right hand, 1 left hand, 2 helm, 3 armor, 4 pants, 5 gloves, 6 boots, 7 wings, 8 pet, 9 pendant,
10 and 11 rings, 12..75 the grid. Hero equipment at hero (`0x7c0dd24`) `+0x224`, grid at `0x7da9ad8`, both
`0x44` bytes per item: `+0x00` type (2 bytes, `FFFF` empty), `+0x04` byte 1, `+0x08` slot class, `+0x1a` durability,
`+0x1b` byte 3, `+0x1c..+0x22` requirements (code).

**Slot class** of a type (`0x45a270`, item `+0x08`): groups 0..5 right hand, except bows and the bolt (4/0..4/7)
and 4/17 left hand (arrows 4/15 and crossbows go right); group 6 (shields) left hand; groups 7..11 slots 2..6;
12/0..6 wings; 13/0..7 pet; 13/8..11 ring; 13/12..31 pendant; anything else can't be worn.

**What the equipment window checks** before it sends `24` (`0x48eec0`, code, the second half not read in full):
the class byte of the item for the hero's class is not 0, a magic gladiator may also wear what dark wizards or dark
knights may; the target slot is the item's slot class, rings go in either ring slot, a right hand weapon of width 1
also goes in the left hand; no width 2 weapon (not a shield) in the left hand while the right hand holds something
but arrows / bolts, nothing in the left hand while the right hand item is width 2. Strength, agility and level
requirements are not checked there (the tooltip shows them red), the server has to.

**Requirements** as the client computes them (`0x45a270`, code), item level L, drop level D (D + 25 for an item
with excellent options), base values from `item.bmd`, 0 means none:

- strength: `(D + 3L) * str * 3 / 100 + 20`, agility the same with agi. Types below `0x180` but arrows / bolts:
  + 5 * option on strength.
- energy: `(D + 3L) * ene * 4 / 10 + 20`; Summon Orb (12/11) by level: 30, 60, 90, 130, 170, 210, 300.
- level: `level + 4L`, + 20 for excellent items; Ring of Transform (13/10): 20 below level 3, 50 from level 3.

Damage and defense grow by 3 per level up to 9, 4 for level 10 and 5 for each level above (same function).

**Equipment look**, 10 bytes in `12` `[+5..14]` and `F3 00` `[+16..25]` (`0x43f6f0`, code):

| byte | |
|---|---|
| 0 | right hand type (0..254), `FF` empty |
| 1 | left hand type, `FF` empty |
| 2 | helm index (high nibble), armor index (low nibble) |
| 3 | pants (high), gloves (low) |
| 4 | boots (high nibble), bits 2..3 wings 12/0..2 (3 none), bits 0..1 pet 13/0..2 (3 none or Dinorant) |
| 5..7 | 24 bits big endian, 3 bits per item: right hand (bits 0..2), left hand, helm, armor, pants, gloves, boots (bits 18..20) |
| 8 | bit 7 helm index bit 4, bit 6 armor, bit 5 pants, bit 4 gloves, bit 3 boots (index 31 = empty), bit 2 Dinorant (13/3) when the pet bits are 3 |
| 9 | excellent: bit 7 helm, 6 armor, 5 pants, 4 gloves, 3 boots, 2 right hand, 1 left hand |

The 3 bit level is a glow index, `0x43f680` maps it to a model level: 0, 3, 5, 7, 8, 9, 10, 11.

**Ground items**: 1000 of `0x1d4` bytes at `0x7d1fa88`, their own ids (not object cids).

**Item use lock** (`0x57c7140`): every `26` request sets it to 10, nothing counts it down. While it is set the
client sends no `26` and the equipment window takes no clicks. Unlocked by `26 FD`, `28` with `[4]` not 0, `2A`
with `[5]` not 0, `29` (not reviewed) and the character select reset. The usual answer to a potion: `2A` slot,
count left, 1, or `28` slot, 1 when it was the last one.

## Character values

What the client computes for the hero from its class, stats and equipment (code): `0x45c9f0` calls `0x45bbd0`
(damage), `0x45c1b0` (wizardry damage), `0x45c400` (attack rate), `0x45c430` (speeds), `0x45c650` (defense rate),
`0x45c7d0` (defense), `0x45c910`, `0x45c940` (from armor and boots, not reviewed); run on equipment changes and by the
`34` handler. The character attributes (pointer at `0x7c0dd1c`, see the hero character) keep them: `+0x44` attack
speed, `+0x46` attack rate, `+0x48` / `+0x4a` damage min / max right hand, `+0x4c` / `+0x4e` left hand, `+0x50`
magic speed, `+0x52` / `+0x54` wizardry damage, `+0x58` defense rate, `+0x5a` defense. Class number is the class byte
`& 7`: 0 dark wizard, 1 dark knight, 2 elf, 3 magic gladiator. Integer division everywhere.

| value | formula |
|---|---|
| damage | a bow / crossbow worn with durability: agi / 8 .. agi / 4. Elves without: (str + agi) / 8 .. (str + agi) / 4. Others: str / 8 .. str / 4. Each hand adds its weapon's damage, its option `3C` and the wings' `3C` (both after the durability factor), then the excellent `49` (+ level / 20) and `4A` (+ 2%) of the weapon and of the pendant. The left hand starts from the same base |
| wizardry damage | ene / 9 .. ene / 4, + the staff's and the wings' option `3D` (after the durability factor), + excellent `4B` (level / 20) of the staff and the pendant, `4C` (+ 2%) of the pendant |
| attack rate | level * 5 + agi * 3 / 2 + str / 4 |
| attack speed | elves agi / 50, knights and gladiators agi / 15, wizards agi / 20. Magic speed: elves agi / 50, others agi / 20. Both add the weapons' attack speed (`item.bmd` 39; the average when both hands hold a weapon below `0xC0` with durability, arrows / bolts not counted), the gloves', 20 while character `+0x38` bit 0 is set (presumably the ale 14/9), excellent `4D` (+ 7) of the hands and the pendant |
| defense rate | elves agi / 4, others agi / 3, + the shield's defense rate and its option `3E` (after the durability factor), then + 10% per excellent `46` on shield, helm, armor, pants, gloves, boots and rings |
| defense | elves agi / 10, knights agi / 3, wizards agi / 4, gladiators agi / 5, + the defense (with option `3F`) of the left hand, helm, armor, pants, gloves, boots and wings, each after its durability factor. A bonus while `0x7a5f9c8` is set (not reviewed) |

The window (`0x4a20e0`) shows `Dmg(rate): min~max (attack rate)` of the right hand, of the left hand when it holds a
bow (and the right no crossbow) or the right is empty. Knights and gladiators with a weapon in each hand: 55% of each
hand added. Character `+0x38` bit 1: + 15 damage (presumably an item effect). `Defense (rate): defense (defense
rate)`. Wizardry damage is the selected skill's (below), with a staff `(+n)`: staff damage min / 2 + 2 * staff
level, after the staff's durability factor (magic durability, `item.bmd` 42). Knights show `Skill Damage: 200 +
ene / 10 %`, gladiators `200 + ene / 30 %`.

**Durability factor** (`0x45baf0`): maximum = `item.bmd` durability + 1 per item level for levels 1..4 and 2 per
level above, + 15 for excellent items. worn = 1 - durability / maximum: above 0.8 the value loses 50%, above 0.7
30%, above 0.5 20%, otherwise nothing (`v - int(v * factor)`).

**Item values** (`0x45a270`): damage min / max, defense rate, defense and magic defense grow with the item level as in
[Items](#items) (shields' defense only + 1 per level). Excellent items add first: damage min and max
`min * 25 / drop level + 5` (the max uses the min's base too), defense rate `rate * 25 / drop level + 5`, defense
`drop level / 5 + defense * 12 / drop level + 4`.

**Options** of an item (`+0x24` count, `+0x25` ids, `+0x2d` values), texts from `Text.bmd`:

| id | | items |
|---|---|---|
| `12`..`18` | the weapon's skill, the id is the skill number: 18 defense (shields 6/4..6/31), 19 falling slash (0/12, 1/2..1/31, 2/1, 2/3, 2/4), 20 lunge (0/3, 0/6, 0/9, 0/11, 0/17, 3/4), 21 uppercut (0/4, 0/7, 0/8), 22 cyclone (0/5, 0/10, 0/13, 0/14, 0/16, 3/0, 3/7..3/9), 23 slash (0/15, 2/5, 2/6, gladiators 0/18), 24 triple shot (elf bows / crossbows). Only with the skill bit and when the class byte allows a knight (an elf for 24, a gladiator for 0/18) | weapons, shields |
| `3C` | damage + 4 * option | weapons, wings of satan 12/2 |
| `3D` | wizardry damage + 4 * option | staffs, wings of heaven 12/1 |
| `3E` | defense rate + 5 * option | shields |
| `3F` | defense + 4 * option | armor |
| `40` | luck: jewel of soul + 25%, critical damage rate + 5% | types below `0x180` but arrows / bolts, wings |
| `41` | automatic life recovery option % | rings, pendants, wings of elf 12/0 |
| `42`..`47` | excellent bits 5..0: life + 4%, mana + 4%, damage decrease 4%, reflect damage 4%, defense rate + 10%, zen + 40% | shields, armor, rings 13/8, 13/9 |
| `48`..`4F` | excellent bits 5..0: excellent damage rate (10%), damage + level / 20 (`4B` wizardry), damage + 2% (`4C` wizardry), attack speed + 7, life + life / 8 after a kill, mana + mana / 8 after a kill | weapons, staffs, pendants 13/12, 13/13 |

## Skills

`Data\Local\skill.bmd` (files, code): 64 records of 38 bytes + 4, xor `FC CF AB` with the key restarting at every
record, the record index is the skill number. Kept in memory at the pointer `0x7c45a48`, encrypted with another key
between uses (`0x45cb20`). Copied to `data/skill.bmd`.

| offset | |
|---|---|
| 0..31 | name |
| 32 | level: equals the drop level of the skill's scroll / orb (unused otherwise, not reviewed) |
| 33 | damage |
| 34..35 | mana |
| 36 | distance, tiles |
| 37 | not reviewed |

- Wizardry damage of a skill (`0x45cb20`): wizardry min + damage .. wizardry max + damage * 3 / 2.
- Mana (`0x45cdc0`): the record's. With too little mana the client sends `26` with a mana potion slot itself
  (`0x46f270`).
- Learning: scroll 15/n teaches skill n + 1 (15/0 poison .. 15/13 inferno), orbs 12/7 skill 41, 12/8 26, 12/9 27,
  12/10 28, the summon orb 12/11 skill 30 + its level (the tooltip `0x487030` names it). The scroll's energy
  requirement is the item's (see Items).

## Client limits

From code, values the client holds or shows:

| value | limit |
|---|---|
| level | 2 bytes (`F3 00`, `F3 05`, hero `+0x0e`), shown unsigned |
| exp | 4 bytes (`F3 03`, `F3 04`, hero `+0x10`). `16` adds at most 65535 per packet |
| next level exp | `F3 03` sets it, every `F3 05` replaces it with the client's own formula (`0x45c980`, 32 bit): `10 (L + 9) L²`, above level 255 plus `1000 (L - 246) (L - 255)²` |
| stats | 2 bytes (`F3 03`, hero `+0x14..+0x1a`), shown unsigned (`0x4a20e0` zero extends them), the item tooltip compares them unsigned (`0x487030`). Neither the `F3 06` sender nor its result checks a maximum. Values the client derives from stats (damage, defense, speeds) not reviewed |
| life, mana | 2 bytes everywhere (`F3 03`, `F3 05`, `26` / `27`, hero `+0x1c..+0x22`) |
| damage | `15`: 13 bits (8191), `16`: 16 bits |

The character window prints exp with `Text.bmd` entry 201, `Exp : %d / %d`, signed: from level 370 the next exp
(2158751000) is above 2³¹ and shows negative. `%u` in that entry fixes the display without touching code. At level
406 the formula passes 2³² and wraps, a higher level cap needs a different `0x45c980`.

Damage above 8191 in `15` needs a change in `0x4179a0`: mask `0xFFFF` and the flags from another byte, which
doesn't fit in place because the value and the flags share `AL`. 65535 stays the limit, the client subtracts the
damage from its 2 byte life. mup shows at most 8191 and applies the whole damage (`SDamage.of`).

## Extending the client

**Room in the exe** (files). `.text` is 0xF5F15 bytes in 0xF6000 raw: 0xEB bytes free, no room for new code. The
headers end at 0x290 and the first section starts at 0x1000, so there is room for more section headers. The exe
imports `LoadLibraryA` and `GetProcAddress`, and a single function of `DSOUND.dll` (a candidate for a proxy dll,
wine needs `WINEDLLOVERRIDES=dsound=n,b` to load it from the client folder). Not looked into in depth: the exe has
window titles of cheat tools (`GameHack 2.0`, `Speed Hack - PCGameHacks.com`), no check of its own bytes was seen.

**Hook points** (code):

- Interface: `0x4a9370` draws all windows once a frame, after the last window (`0x4a90c0`) is the place for new
  ones. Interface coordinates are 640 x 480.
- Drawing: `0x4c2930(bitmap, x, y, w, h, u, v, uw, vh, ...)` draws a bitmap slot (floats), `0x4c2860(x, y, w, h)`
  fills a rectangle in the current `glColor`, text with `0x45d9c0` / `0x45dbb0` (x, y, string, ...), colours from
  `0x4fccdc` / `0x4fcce4` (presumably text and background).
- Textures: `0x4d3df0(name, bitmap, ...)` loads a `.jpg` name from the `.OZJ` file, `0x4d4240` a `.tga` name from the
  `.OZT` file, into a bitmap slot. Slots seen up to `0x532`, free ones not mapped.
- Mouse: x `0x82a4d10`, y `0x82a4d0c` (interface coordinates), left click flag `0x82a4bb8`, cleared by the window
  that handles the click. Each window checks its own rectangle.
- Packets: head codes the client doesn't handle reach the default of the switch at `0x4213ee`. Sending: the builder
  `0x403390` and `send` on the socket at `0x556a590`, `0x49c950` (`F3 06`) is a short example of the whole sequence.
- The hero character (`0x7c0dd1c`, 0x590 bytes) is kept xored between uses: a handler looks it up in the table at
  `0x556a118` with the key `0x7c0dd24`, unlocks it (`0x403b30`, `0x403ca0`, counted) and locks it again
  (`0x403dc0`). Other tables are kept the same way (`0x45cb20`). Code that reads hero values has to do the same.

**Without code**: the interface textures (`Data/Interface/*.OZJ` / `.OZT`, loaded at `0x4bf4e0` and `0x4c09b0`),
the texts in `Text.bmd` (800 entries of 300 bytes), and the windows the server opens: the
[quest window](#quest-window), notices `0D`, chat.

## Quest window

The second class quests (priest Sevina) run on a generic quest window driven by two client data files and the
`A0`..`A3` packets. Everything in this section is from code, none of it seen in traffic yet.

**Data files.** `Data/Local/Quest.bmd` and `Data/Local/Dialog.bmd`, fixed size records, each record xored with
`FC CF AB` with the key **restarting at every record** (`read_text.py` xors the whole file in one run, which only
works for `Text.bmd` because its 300 byte records are a multiple of 3).

`Dialog.bmd`: 200 entries of 1024 bytes. Used in this client: 0..5 (NPC texts) and 50..73 (second class quests).

| offset | |
|---|---|
| 0..299 | text, wrapped at a space into at most 7 lines of 38 bytes |
| 300..303 | answer count (int) |
| 304..343 | 10 links (int): dialog shown after the answer when > 0 |
| 344..383 | 10 return codes (int) |
| 384..1023 | 10 answers of 64 bytes, each shown numbered on one line of 38 bytes |

Text lines and answers share one box, centered on 7 lines. Answer return codes (`0x401d00`):

- `-1`: only follow the link.
- `1`: check the current quest's requirements (level and zen). On failure show the requirement's dialog, nothing
  is sent. Otherwise send `A2 [quest] 01`.
- `2`: close the window, sends `31`.
- `3`: send `A2 [quest] 01` without the check.

Both action codes send the same packet, the server can't tell answers apart, only "proceed" (`A2`) from "close"
(`31`). The link is shown right away; the `A2` result reopens the window with the text for the new state.

`Quest.bmd`: 200 entries of 584 bytes, the entry index is the quest index of `A0`..`A2`. Used: 0 "Find the Scroll
of Emperor" (14/23), 1 "Three Treasures of Mu" (14/24, 14/25, 14/26 per class).

| offset | |
|---|---|
| 0..1 | condition count |
| 2..3 | requirement count |
| 4..5 | `EB 20` in both quests (235 = priest Sevina in the low byte), not read by the code reviewed |
| 6..37 | name |
| 38..325 | 16 conditions of 18 bytes |
| 328..583 | 16 requirements of 16 bytes |

Condition, 18 bytes:

| offset | |
|---|---|
| +0 | not read (1) |
| +1 | type: 1 = bring an item |
| +2, +3 | item group, index (item type `group * 32 + index`) |
| +4 | item count, any item level |
| +5 | requirement group, matched against the requirement's `+1` |
| +6..+9 | one byte per class (dw, dk, elf, mg): 1 applies to the first class, 2 to the second class, 0 not at all |
| +10..+17 | 4 dialog indices (2 bytes each): not started, in progress, item found, done |

Requirement, 16 bytes:

| offset | |
|---|---|
| +0, +2..+3, +14..+15 | not read |
| +1 | condition group it applies to, `FF` all |
| +4..+5 | min level, 0 none |
| +6..+7 | max level, 0 none |
| +8..+11 | zen, only checked by an answer with return code 1 |
| +12..+13 | dialog shown when the requirement fails |

**Text selection** (`0x401710`, on every `A1` / `A2`). The client takes the first condition whose byte for the
hero's class is 1. If there is none it moves to the previous quest index and tries again. Requirements are
checked for conditions whose class byte is `second class + 1`. Then by the quest's state:

- 3, not started: requirements without zen, then the "not started" dialog or the failing requirement's dialog.
- 1, accepted: "in progress" while an item condition has fewer items in the inventory than its count, otherwise
  "item found". A quest without item conditions always shows "item found".
- 2, done: "done".
- 0: nothing selected, the window shows the previous dialog again.

**State bits.** 2 bits per quest, state byte `quest >> 2`. Client bug (`0x4016d0`): the bit position is
`2 * (quest - (quest >> 2))` instead of `2 * (quest & 3)`, used as an 8 bit shift count. The CPU masks it to
`2 * ((quest - (quest >> 2)) & 15)` and positions of 8 or more read as state 0. So only 53 quest indices can hold a
state: 0..4, 21..25, 42..46, 63..68, 85..89, 106..110, 127..132, 149..153, 170..174, 191..196. Quests 0..3 are where
expected, quest 4 is in bits 6..7 of byte 1. The server has to put each quest's bits where the client reads them.

**NPCs.** Only NPC types 234..255 can be talked to (`30`). The server opens the quest window with `A1` (instead of a
shop window) and can send `A1` at any time, but only after an `A0`: without the quest class the text selection
reads past the condition. NPC names come from `Data/Local/NpcName(Eng).txt`, one per type (234 and 252 have none).

## Differences with mup

The layout differences found in the first review were fixed in roadmap M0 (character info, damage, players in view,
ping, login tick, weather, server list / info, `F3 30`). Still open:

1. **C3 serial**: mup's counter (`Crypt.encrypt_sequence`) starts at 0 per connection, matching the client after
   a fresh start. If the client keeps its counter across a reconnect, the first encrypted packet of the new
   connection (character info) would be treated as unencrypted and dropped. Not seen yet, worth knowing when
   adding "switch server".

## Appendix A: server -> client dispatch map

Output of `ReceiveDispatch.java` (head / sub code, case address, functions called) merged with the offsets the
handler reads (`extract_handlers.py`, reads through pointer aliases and list entries are not followed).
`F1` / `F3` / `F4` sub codes are read from `[3]` for C1 and `[4]` for C2 (C3/C4 arrive decrypted as C1/C2).

```
00 @ 00421ace calls [FUN_00414960@00414960]
    414960 reads 3:4, 7:4, 11:2, 13:1, 14:ptr
01 @ 00421adc calls [FUN_0043dc30@0043dc30, FUN_0045f640@0045f640]
02 @ 00421b1f calls [FUN_0045e470@0045e470, FUN_004043d0@004043d0, FUN_0045e860@0045e860]
03 @ 00421bb3 calls [FUN_0040e1d0@0040e1d0, FUN_00403390@00403390, FUN_00408f70@00408f70, FUN_004234a0@004234a0]
0B @ 00421c4a calls [FUN_004b3370@004b3370]
0C @ 00421cf3 calls [FUN_0045e860@0045e860]
0D @ 00421d17 calls [FUN_00414d10@00414d10]
    414d10 reads 3:1, 4:ptr
0F @ 0042215b calls []
10 @ 00421d25 calls [FUN_00414ea0@00414ea0]
    414ea0 reads 3:1, 4:1, 5:1, 6:1, 7:1
11 @ 00421d34 calls [FUN_00415250@00415250]
    415250 reads 3:1, 4:1, 5:1, 6:1
12 @ 00421d42 calls [FUN_004164b0@004164b0]
    4164b0 reads 1:1, 23:ptr
13 @ 00421dd3 calls [FUN_00416fe0@00416fe0]
    416fe0 reads 4:1, 7:ptr
14 @ 00421dfd calls [FUN_0043db80@0043db80]
15 @ 00421f56 calls [FUN_004179a0@004179a0]
    4179a0 reads 1:ptr, 3:1, 4:1, 5:1, 6:1
16 @ 00421fb0 calls [FUN_004199a0@004199a0]
    4199a0 reads 3:1, 4:1, 5:1, 6:1, 7:1, 8:1
17 @ 00421fbf calls [FUN_0043dc30@0043dc30]
18 @ 00421f64 calls [FUN_00417fc0@00417fc0]
    417fc0 reads 3:1, 4:1, 5:1, 6:1
19 @ 00421f73 calls [FUN_004186b0@004186b0]
    4186b0 reads 3:1, 4:1, 5:1, 6:1, 7:1
1A @ 00421f83 calls [FUN_00419570@00419570]
    419570 reads 3:1, 4:1
1B @ 00421fa2 calls [FUN_00418500@00418500]
    418500 reads 3:1, 4:1, 5:1
1C @ 00422191 calls [FUN_00415520@00415520]
    415520 reads 3:1, 4:1, 5:1, 6:1, 7:1
1E @ 00421f92 calls [FUN_00418fd0@00418fd0]
    418fd0 reads 3:1, 4:1, 5:1, 6:1, 7:1
1F @ 00421de1 calls [FUN_004172c0@004172c0]
    4172c0 reads 4:1, 11:ptr
20 @ 00421e3c calls [FUN_00419f90@00419f90]
    419f90 reads 4:1, 5:ptr, 9:ptr
21 @ 00421e4a calls []
22 @ 00421e90 calls [FUN_0041a0b0@0041a0b0]
    41a0b0 reads 1:ptr, 3:1, 4:ptr
23 @ 00421e9e calls [FUN_0041a3a0@0041a3a0]
    41a3a0 reads 3:1, 4:1
24 @ 00421eac calls [FUN_0041a680@0041a680]
    41a680 reads 3:1, 4:1, 5:ptr
25 @ 00421f48 calls [FUN_00416060@00416060]
    416060 reads 3:1, 4:1, 5:ptr, 6:1, 8:1
26 @ 00422130 calls [FUN_0041bcd0@0041bcd0]
27 @ 0042213e calls [FUN_0041bfc0@0041bfc0]
28 @ 00421ffb calls [FUN_0048e0d0@0048e0d0]
29 @ 0042214c calls [FUN_0041c6f0@0041c6f0]
    41c6f0 reads 3:1, 4:2
2A @ 00422504 calls [FUN_0041c3b0@0041c3b0]
    41c3b0 reads 3:1, 4:1, 5:1
30 @ 00422031 calls [FUN_0041abc0@0041abc0]
    41abc0 reads 3:1
31 @ 00422040 calls [FUN_00414890@00414890]
    414890 reads 4:1, 5:1, 6:ptr
32 @ 0042204e calls [FUN_0048d940@0048d940, FUN_004043d0@004043d0]
    48d940 reads 1:ptr
33 @ 0042208c calls [FUN_004239b0@004239b0, FUN_00403940@00403940, FUN_004043d0@004043d0, FUN_0048e650@0048e650]
34 @ 004220de calls [FUN_004239b0@004239b0, FUN_0045c9f0@0045c9f0, FUN_00403940@00403940, FUN_004043d0@004043d0]
    45c9f0 reads 70:2, 88:2, 90:2, 1386:2, 1388:2, 1390:2, 1394:2, 1396:2, 1400:2, 1402:2, 1408:2, 1410:2, 1412:2, 1414:2, 1416:2, 1418:1, 1419:1
36 @ 0042233c calls [FUN_0040e1d0@0040e1d0, FUN_00403390@00403390, FUN_004234a0@004234a0, FUN_0048e650@0048e650]
37 @ 00422413 calls [FUN_0041d1b0@0041d1b0]
    41d1b0 reads 3:1
38 @ 00422421 calls [FUN_0048e0d0@0048e0d0, FUN_004043d0@004043d0]
39 @ 00422446 calls [FUN_0048d940@0048d940, FUN_004043d0@004043d0]
    48d940 reads 1:ptr
3A @ 00422472 calls []
3B @ 0042248b calls []
3C @ 00422498 calls [FUN_004043d0@004043d0]
3D @ 004224f6 calls [FUN_0041d6f0@0041d6f0]
    41d6f0 reads 3:ptr
40 @ 00422231 calls []
41 @ 00422255 calls []
  sub switch on packet[3], 00..05
  41 00 @ 00422266 calls [FUN_0045e860@0045e860]
  41 01 @ 00422274 calls [FUN_0045e860@0045e860]
  41 02 @ 00422282 calls [FUN_0045e860@0045e860]
  41 03 @ 00422290 calls [FUN_0045e860@0045e860]
  41 04 @ 0042229e calls [FUN_0045e860@0045e860]
  41 05 @ 004222ac calls [FUN_0045e860@0045e860]
42 @ 004222cf calls [FUN_0041de50@0041de50]
    41de50 reads 4:1, 16:ptr
43 @ 004222dd calls [FUN_0045e860@0045e860]
44 @ 00422300 calls []
45 @ 00421def calls [FUN_00416a40@00416a40]
    416a40 reads 4:1, 7:ptr
50 @ 0042259b calls []
51 @ 004225bf calls [FUN_0041df50@0041df50]
    41df50 reads 3:1
52 @ 004225cd calls []
53 @ 0042263f calls [FUN_0041e110@0041e110]
    41e110 reads 3:1
54 @ 0042264d calls [FUN_004035b0@004035b0, FUN_004037c0@004037c0]
55 @ 004226db calls [FUN_0045d160@0045d160]
56 @ 00422728 calls [FUN_0041ea70@0041ea70]
    41ea70 reads 3:1
5A @ 00422736 calls [FUN_0041e8b0@0041e8b0]
    41e8b0 reads 4:1, 7:ptr
5B @ 00422744 calls [FUN_0041e900@0041e900]
    41e900 reads 4:1, 8:ptr
5C @ 00422752 calls [FUN_0041e750@0041e750]
    41e750 reads 3:1, 4:1, 5:ptr, 13:ptr
5D @ 00422760 calls [FUN_0041e860@0041e860]
    41e860 reads 3:1, 4:1
60 @ 0042276e calls [FUN_0041eb80@0041eb80]
    41eb80 reads 3:1
61 @ 0042277c calls [FUN_0041eb30@0041eb30]
    41eb30 reads 3:4, 7:4, 11:1
62 @ 0042278a calls [FUN_0041ec90@0041ec90]
    41ec90 reads 3:4, 7:4, 11:1, 12:1
63 @ 00422798 calls [FUN_0041f0e0@0041f0e0]
    41f0e0 reads 3:1
64 @ 004227a6 calls []
71 @ 004227c7 calls [FUN_0041d800@0041d800]
81 @ 004227d5 calls [FUN_0041d970@0041d970]
    41d970 reads 3:1
82 @ 004227e3 calls [FUN_0041dbe0@0041dbe0]
83 @ 004227f1 calls [FUN_0041dc30@0041dc30]
    41dc30 reads 3:1
86 @ 004227ff calls [FUN_0041f960@0041f960]
    41f960 reads 3:1, 4:ptr
87 @ 0042280d calls [FUN_0041fa20@0041fa20]
90 @ 0042281b calls [FUN_0041fa70@0041fa70]
    41fa70 reads 3:1
91 @ 00422829 calls [FUN_0041fec0@0041fec0]
    41fec0 reads 3:1
92 @ 00422837 calls [FUN_0045d100@0045d100]
93 @ 0042284b calls [FUN_0041ff30@0041ff30]
    41ff30 reads 3:1, 4:1, 5:ptr
94 @ 00422859 calls [FUN_00420240@00420240]
    420240 reads 4:2, 6:4, 8:2, 10:2
95 @ 00422867 calls [FUN_004202a0@004202a0]
    4202a0 reads 4:2
96 @ 00422875 calls [FUN_004202c0@004202c0]
    4202c0 reads 4:4, 6:2, 8:2
99 @ 00422883 calls [FUN_004202f0@004202f0]
    4202f0 reads 3:1
A0 @ 00422891 calls [FUN_00420320@00420320]
    420320 reads 3:1
A1 @ 0042289f calls [FUN_00420350@00420350]
    420350 reads 3:1, 4:1
A2 @ 004228ad calls [FUN_00420380@00420380]
    420380 reads 3:1, 4:1, 5:1
A3 @ 004228bb calls [FUN_004203c0@004203c0]
    4203c0 reads 1:ptr, 3:1, 4:1, 5:1, 6:1
F1 @ 004213fb calls []
  sub switch on packet[3], 00..12
  F1 00 @ 00421418 calls [FUN_004122b0@004122b0]
      4122b0 reads 4:1, 5:1, 6:1, 7:1
  F1 01 @ 00421426 calls []
    sub switch on packet[4], 00..D2
    F1 01 00 @ 00421445 calls []
    F1 01 01 @ 0042145e calls [FUN_00408c40@00408c40]
    F1 01 02 @ 00421486 calls []
    F1 01 03 @ 0042149f calls []
    F1 01 04 @ 004214b8 calls []
    F1 01 05 @ 004214d1 calls []
    F1 01 06 @ 004214ea calls []
    F1 01 08 @ 00421503 calls []
    F1 01 09 @ 0042151c calls []
    F1 01 0A @ 00421535 calls []
    F1 01 0B @ 0042154e calls []
    F1 01 0C @ 00421567 calls []
    F1 01 0D @ 00421580 calls []
    F1 01 11 @ 00421599 calls []
    F1 01 C0 @ 004215b2 calls []
    F1 01 C1 @ 004215cb calls []
    F1 01 C2 @ 004215e4 calls []
    F1 01 D0 @ 004215b2 calls []
    F1 01 D1 @ 004215cb calls []
    F1 01 D2 @ 004215e4 calls []
  F1 02 @ 00421616 calls [FUN_004129f0@004129f0]
      4129f0 reads 4:1
  F1 03 @ 00421666 calls []
  F1 04 @ 004216da calls []
    sub switch on packet[4], 00..03
    F1 04 00 @ 0042172e calls []
    F1 04 01 @ 004216ef calls [FUN_00411c90@00411c90]
    F1 04 02 @ 0042173d calls []
    F1 04 03 @ 0042174c calls []
  F1 05 @ 0042175b calls []
    sub switch on packet[4], 00..03
    F1 05 00 @ 0042177f calls []
    F1 05 01 @ 00421770 calls []
    F1 05 02 @ 0042178e calls []
    F1 05 03 @ 0042179d calls []
  F1 12 @ 00421625 calls []
F3 @ 004217ac calls []
  sub switch on packet[4], 00..40
  F3 00 @ 004217d6 calls [FUN_004124b0@004124b0]
      4124b0 reads 4:1, 20:ptr
  F3 01 @ 004217e4 calls [FUN_00412600@00412600]
      412600 reads 4:1, 5:4, 9:4, 13:2, 15:1
  F3 02 @ 004217f2 calls []
  F3 03 @ 00421821 calls [FUN_00413380@00413380]
      413380 reads 4:1, 5:1, 6:1, 7:1, 8:4, 12:4, 16:2, 18:2, 20:2, 22:2, 24:2, 26:2, 28:2, 30:2, 32:2, 36:4, 40:1, 41:1
  F3 04 @ 00421830 calls [FUN_00413b00@00413b00]
  F3 05 @ 0042184d calls [FUN_0041b6d0@0041b6d0]
  F3 06 @ 0042185b calls [FUN_0041b9a0@0041b9a0]
      41b9a0 reads 1:ptr, 4:1
  F3 07 @ 00421869 calls [FUN_004239b0@004239b0, FUN_00403940@00403940]
  F3 08 @ 004218c4 calls [FUN_0041c2b0@0041c2b0]
      41c2b0 reads 4:1, 5:1, 6:1
  F3 10 @ 0042183e calls [FUN_00414310@00414310]
      414310 reads 5:1, 6:ptr
  F3 11 @ 004218d2 calls [FUN_00414010@00414010]
      414010 reads 4:1, 5:1, 6:1
  F3 13 @ 004218e0 calls [FUN_0043dc30@0043dc30, FUN_0043f6f0@0043f6f0]
  F3 14 @ 0042190a calls [FUN_0048d940@0048d940, FUN_004043d0@004043d0]
      48d940 reads 1:ptr
  F3 20 @ 00421941 calls []
  F3 22 @ 00421951 calls []
  F3 23 @ 00421962 calls []
  F3 30 @ 004219d4 calls [FUN_0041ff50@0041ff50]
  F3 40 @ 004219e2 calls [FUN_0041f7e0@0041f7e0]
      41f7e0 reads 4:1, 5:1, 6:1
F4 @ 004219f0 calls [FUN_00423fe0@00423fe0, FUN_00411960@00411960, FUN_004e7c6c@004e7c6c, FUN_0045e860@0045e860, FUN_00411e60@00411e60]
    411e60 reads 1:ptr, 2:ptr, 5:ptr, 6:ptr
```

## Appendix B: client -> server senders

Head codes and the functions building them (`extract_senders.py`). The heuristic misreads some packets because
the client inlines its packet builder in several ways, so treat this as a list of where to look, not as layouts.

```
00  0041f0e0, 004d2b21
03  00420890
0E  0040e2a0
10  004650a0
11  00462140
15  004650a0
18  0041ec90, 0041f0e0, 004650a0, 0046c770, 0046c9c0, 00474ac0
19  00462140
1C  00474030
1D  00442610
1E  0046f270
22  004650a0
23  00497760
24  00422db0, 00474ac0
30  004650a0
31  00401920, 0041fa70, 0049d500, 0049e7b0
33  00497760
34  004a19f0
36  0046a340
3C  00497760, 004a1070
3D  004a1070
40  0046a340
43  0049c5b0
50  0046a340
71  0041d800
81  004232c0
82  004aa5c0
86  00497760
87  004aa3a0
90  0049d500
97  0049dff0
98  0049dff0
A0  004650a0
A2  00401d00, 00402660
C1  004916f0
F1  00408f70, 004129f0, 00413380, 00414310, 00415520, 00418fd0, 004199a0, 0041a680, 0041abc0, 0041c6f0, 004cb840
F3  004129f0, 00415520, 0049c950, 004c0000, 004c3f40, 004d0b30
F4  00414960, 004caad0, 004cb840
```
