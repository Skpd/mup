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
from mup.packet.client_packet.logout import Logout as Logout097
from mup.packet.client_packet.rotate import Rotate as Rotate097
from mup.packet.client_packet.move import Move as Move097
from mup.packet.client_packet.chat import Chat as Chat097, Whisper as Whisper097
from mup.packet.client_packet.attack import Attack as Attack097
from mup.packet.client_packet.magic_attack import MagicAttack as MagicAttack097
from mup.packet.client_packet.magic_aoe import MagicAOE as MagicAOE097
from mup.packet.client_packet.move_gate import MoveGate as MoveGate097
from mup.packet.client_packet.map_ready import MapReady as MapReady097
from mup.packet.client_packet.add_point import AddPoint as AddPoint097
from mup.packet.client_packet.area_hits import AreaHits as AreaHits097
from mup.packet.client_packet.key_settings import KeySettings as KeySettings097
from mup.packet.client_packet.item import (PickUp as PickUp097, DropItem as DropItem097, MoveItem as MoveItem097,
                                           UseItem as UseItem097)
from mup.packet.client_packet.npc import (Talk as Talk097, CloseWindow as CloseWindow097, Buy as Buy097,
                                          Sell as Sell097, Repair as Repair097, WarehouseMoney as WarehouseMoney097,
                                          WarehouseClose as WarehouseClose097, Mix as Mix097,
                                          ChaosClose as ChaosClose097)
from mup.packet.client_packet.party import (PartyRequest as PartyRequest097, PartyAnswer as PartyAnswer097,
                                            PartyLeave as PartyLeave097)
from mup.packet.client_packet.guild import (GuildRequest as GuildRequest097, GuildAnswer as GuildAnswer097,
                                            GuildListRequest as GuildListRequest097, GuildLeave as GuildLeave097,
                                            GuildMasterAnswer as GuildMasterAnswer097, GuildCreate as GuildCreate097,
                                            GuildCancel as GuildCancel097)
from mup.packet.client_packet.devil_square import DevilSquareEnter as DevilSquareEnter097
from mup.packet.client_packet.quest import QuestStates as QuestStates097, QuestProceed as QuestProceed097
from mup.packet.client_packet.trade import (TradeRequest as TradeRequest097, TradeAnswer as TradeAnswer097,
                                            TradeZen as TradeZen097, TradeOk as TradeOk097,
                                            TradeCancel as TradeCancel097)

CLoginRequest = LoginRequest097
CServerList = ServerList097
CServerInfo = ServerInfo097
CCharList = CharList097
CCharCreate = CharCreate097
CCharDelete = CharDelete097
CPing = Ping097
CJoinGame = JoinGame087
CClientClose = ClientClose097
CLogout = Logout097
CRotate = Rotate097
CMove = Move097
CChat = Chat097
CWhisper = Whisper097
CAttack = Attack097
CMagicAttack = MagicAttack097
CMagicAOE = MagicAOE097
CMoveGate = MoveGate097
CMapReady = MapReady097
CAddPoint = AddPoint097
CAreaHits = AreaHits097
CKeySettings = KeySettings097
CPickUp = PickUp097
CDropItem = DropItem097
CMoveItem = MoveItem097
CUseItem = UseItem097
CTalk = Talk097
CCloseWindow = CloseWindow097
CBuy = Buy097
CSell = Sell097
CRepair = Repair097
CWarehouseMoney = WarehouseMoney097
CWarehouseClose = WarehouseClose097
CMix = Mix097
CChaosClose = ChaosClose097
CPartyRequest = PartyRequest097
CPartyAnswer = PartyAnswer097
CPartyLeave = PartyLeave097
CTradeRequest = TradeRequest097
CTradeAnswer = TradeAnswer097
CTradeZen = TradeZen097
CTradeOk = TradeOk097
CTradeCancel = TradeCancel097
CQuestStates = QuestStates097
CQuestProceed = QuestProceed097
CGuildRequest = GuildRequest097
CGuildAnswer = GuildAnswer097
CGuildListRequest = GuildListRequest097
CGuildLeave = GuildLeave097
CGuildMasterAnswer = GuildMasterAnswer097
CGuildCreate = GuildCreate097
CGuildCancel = GuildCancel097
CDevilSquareEnter = DevilSquareEnter097

# head, sub (None for packets without one) -> packet class
head_code_map = {(p.code[1], p.code[2] if len(p.code) > 2 else None): p for p in (
    CChat, CMove, CAttack, CRotate, CPing, CMagicAttack, CMagicAOE, CMoveGate, CMapReady, CAddPoint, CAreaHits, CKeySettings,
    CServerList, CServerInfo,
    CLoginRequest, CClientClose, CLogout,
    CCharList, CCharCreate, CCharDelete, CJoinGame,
    CPickUp, CDropItem, CMoveItem, CUseItem,
    CTalk, CCloseWindow, CBuy, CSell, CRepair, CWarehouseMoney, CWarehouseClose, CMix, CChaosClose,
    CWhisper, CPartyRequest, CPartyAnswer, CPartyLeave,
    CTradeRequest, CTradeAnswer, CTradeZen, CTradeOk, CTradeCancel,
    CQuestStates, CQuestProceed,
    CGuildRequest, CGuildAnswer, CGuildListRequest, CGuildLeave, CGuildMasterAnswer, CGuildCreate, CGuildCancel,
    CDevilSquareEnter,
)}


def factory(src: Base):
    """Packet class instance for a received packet, None if the packet is unknown."""
    sub = src.sub if len(src) > (4 if src.is_double() else 3) else None
    cls = head_code_map.get((src.head, sub)) or head_code_map.get((src.head, None))
    return cls(src) if cls else None
