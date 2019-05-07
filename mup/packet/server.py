from mup.packet.server_packet.server_list import ServerList as ServerList097
from mup.packet.server_packet.server_info import ServerInfo as ServerInfo097
from mup.packet.server_packet.handshake import Handshake as Handshake097
from mup.packet.server_packet.server_join import ServerJoin as ServerJoin097
from mup.packet.server_packet.login_result import LoginResult as LoginResult097
from mup.packet.server_packet.account_id import AccountID as AccountID097
from mup.packet.server_packet.char_list import CharList as CharList097
from mup.packet.server_packet.char_created import CharCreated as CharCreated097
from mup.packet.server_packet.char_deleted import CharDeleted as CharDeleted097
from mup.packet.server_packet.stats import Stats as Stats097
from mup.packet.server_packet.inventory import Inventory as Inventory097
from mup.packet.server_packet.announcement import Announcement as Announcement097
from mup.packet.server_packet.meet_player import MeetPlayer as MeetPlayer097
from mup.packet.server_packet.meet_monster import MeetMonster as MeetMonster097
from mup.packet.server_packet.clear import Clear as Clear097
from mup.packet.server_packet.move import Move as Move097
from mup.packet.server_packet.damage import Damage as Damage097
from mup.packet.server_packet.kill import Kill as Kill097
from mup.packet.server_packet.exp import Exp as Exp097
from mup.packet.server_packet.effect import Effect as Effect097
from mup.packet.server_packet.level_up import LevelUp as LevelUp097
from mup.packet.server_packet.magic import Magic as Magic097


SServerList = ServerList097
SServerInfo = ServerInfo097
SHandshake = Handshake097
SServerJoin = ServerJoin097
SLoginResult = LoginResult097
SAccountID = AccountID097
SCharList = CharList097
SCharCreated = CharCreated097
SCharDeleted = CharDeleted097
SStats = Stats097
SInventory = Inventory097
SAnnouncement = Announcement097
SMeetPlayer = MeetPlayer097
SMeetMonster = MeetMonster097
SClear = Clear097
SMove = Move097
SDamage = Damage097
SKill = Kill097
SExp = Exp097
SEffect = Effect097
SLevelUp = LevelUp097
SMagic = Magic097


head_code_map = {
    0x00: {
        0x01: SHandshake
    },
    0x01: SAccountID,
    0x10: SMove,
    # 0x11: SPush,
    0x12: SMeetPlayer,
    0x13: SMeetMonster,
    0x14: SClear,
    0x15: SDamage,
    0x16: SExp,  # C3?
    0x17: SKill,
    0x19: SMagic,
    #  0x20 - Items
    #  0x65 - Guild info
    #  0x2C - Stat fruit?
    #  0x1F - Summoned monster
    #  C1 0x0B - Event
    0x0D: SAnnouncement,
    # 0x1E: SMagicAOE,
    0xF1: {
        0x00: SServerJoin,
        0x01: SLoginResult,
    },
    0xF3: {
        0x00: SCharList,
        0x01: SCharCreated,
        0x02: SCharDeleted,
        0x03: SStats,
        #  0x04 - Regen
        #  0x05 - Level Up
        #  0x06 - Level up point add
        #  0x07 - damage
        #  0x08 - PK level
        0x10: SInventory,
        #  0x11 - Magic List (multiple)
        #  0x13 - Equipment (set) send
        #  0x14 - Inventory one item (pos, info)
        #  0x20 - Summoned monster life
        #  C1 0x16 - kill
        #  C1 0x17 - die
        #  C1 0x22 - Time send, seconds. bc?
        #  C3 0x22 - get item (zen)
        #  C1 0x23 - Soccer goal send
        #  C3 0x23 - Item throw? (drop request)
        #  C3 0x24 - Inventory Item move
        #  C3 0x30 - Shop item count?
        #  C1 0x32 - buy result
        #  C1 0x33 - sell result
        #  C1 0x34 - repair cost
        #  C3 0x36 - trade request
        #  C1 0x38 - trade canceled
        #  C1 0x39 - trade canceled move
        #  C1 0x3B - trade other money set
        #  C1 0x3D - trade result
        #  C1 0x40 - party request
        #  C1 0x42 - party list count
        #  C1 0x43 - party close
        #  C1 0x81 - zen change
        #  C1 0x83 - warehouse state

    },
    0xF4: {
        0x02: SServerList,
        0x03: SServerInfo,
    }
}
