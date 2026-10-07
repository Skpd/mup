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
CRotate = Rotate097
CMove = Move097
CChat = Chat097
CAttack = Attack097
CMagicAttack = MagicAttack097
CMagicAOE = MagicAOE097

# head, sub (None for packets without one) -> packet class
# todo 0x1D area skill hits: skill index, x, y, serial, count, cids (roadmap M4)
head_code_map = {(p.code[1], p.code[2] if len(p.code) > 2 else None): p for p in (
    CChat, CMove, CAttack, CRotate, CPing, CMagicAttack, CMagicAOE,
    CServerList, CServerInfo,
    CLoginRequest, CClientClose,
    CCharList, CCharCreate, CCharDelete, CJoinGame,
)}


def factory(src: Base):
    """Packet class instance for a received packet, None if the packet is unknown."""
    sub = src.sub if len(src) > (4 if src.is_double() else 3) else None
    cls = head_code_map.get((src.head, sub)) or head_code_map.get((src.head, None))
    return cls(src) if cls else None
