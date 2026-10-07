from mup.packet.base import Base
from mup.packet.client_packet.login_request import LoginRequest as LoginRequest097
from mup.packet.client_packet.server_list import ServerList as ServerList097
from mup.packet.client_packet.server_info import ServerInfo as ServerInfo097
from mup.packet.client_packet.char_list import CharList as CharList097
from mup.packet.client_packet.char_create import CharCreate as CharCreate097
from mup.packet.client_packet.char_delete import CharDelete as CharDelete097
from mup.packet.client_packet.ping import Ping as Ping097
from mup.packet.client_packet.join_game import JoinGame as JoinGame087
from mup.packet.client_packet.client_close import ClientClose as ClientClose097
from mup.packet.client_packet.exit import Exit as Exit097
from mup.packet.client_packet.rotate import Rotate as Rotate097
from mup.packet.client_packet.move import Move as Move097
from mup.packet.client_packet.chat import Chat as Chat097
from mup.packet.client_packet.attack import Attack as Attack097
from mup.packet.client_packet.magic_attack import MagicAttack as MagicAttack097
from mup.packet.client_packet.magic_aoe import MagicAOE as MagicAOE097

CLoginRequest = LoginRequest097
CServerList = ServerList097
CServerInfo = ServerInfo097
CCharList = CharList097
CCharCreate = CharCreate097
CCharDelete = CharDelete097
CPing = Ping097
CJoinGame = JoinGame087
CClientClose = ClientClose097
CExit = Exit097
CRotate = Rotate097
CMove = Move097
CChat = Chat097
CAttack = Attack097
CMagicAttack = MagicAttack097
CMagicAOE = MagicAOE097

head_code_map = {
    0x00: CChat,
    0x10: CMove,
    0x15: CAttack,
    0x18: CRotate,
    0x0E: {
        0x00: CPing,
    },
    0x19: CMagicAttack,
    0x1E: CMagicAOE,
    # 0x1D: CMagicHit, magic id, x, y, count, cid2b*count
    0xF4: {
        0x02: CServerList,
        0x03: CServerInfo,
    },
    0xF1: {
        0x01: CLoginRequest,
        0x03: CClientClose,
    },
    0xF3: {
        0x00: CCharList,
        0x01: CCharCreate,
        0x02: CCharDelete,
        0x03: CJoinGame,
        0x30: CExit
    },
}


def factory(src: Base):
    if src.head in head_code_map:
        if type(head_code_map[src.head]) == dict and src.sub in head_code_map[src.head]:
            return head_code_map[src.head][src.sub](src)
        elif type(head_code_map[src.head]) != dict:
            return head_code_map[src.head](src)
        else:
            print('\t---- NEW --- sub code {} set, but not exists in {}'.format(src.sub, head_code_map[src.head].keys()))
    else:
        print('\t---- NEW --- head code {} set, but not exists in {}'.format(src.head, head_code_map.keys()))
