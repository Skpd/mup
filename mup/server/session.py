import logging
from mup.config import PACKET_LOGGER
from mup.model.account import Account
from mup.model.player import Player
from mup.packet.base import Base

packet_logger = logging.getLogger(PACKET_LOGGER)


class Session:
    """
    A connection as the game sees it: a client over the network (mup.server.protocol.BaseProtocol) or one in process
    (LocalSession: mup.sim.Puppet, mup.bot.session.BotSession). What the game keeps on a connection lives here, the
    subclass delivers what the game writes.
    """
    server = None  # GameServer or ConnectServer
    player: Player = None
    acc: Account = None

    cid = None
    connected = False
    joined = False
    playing = False
    server_tick = None
    client_tick = None
    reported_speeds = None  # attack and magic speed of the last ping
    view = None  # players, monsters and ground items this client has in view (mup.server.view)

    def __init__(self, server):
        self.server = server
        self.view = set()
        self.area_casts = {}  # skill number -> mup.server.casting.AreaCast
        self.teleport_at = 0.0  # the next teleport is allowed then
        self.left = None  # the character it logged out of
        self.summon = None  # the player's summoned monster, mup.server.summon
        self.window = None  # the NPC window open, mup.server.npc.Window
        self.warehouse = None  # the account's vault once opened, saved with the character (mup.server.warehouse)
        self.stale_box = False  # the client may still show items in its chaos machine box, mup.server.chaos
        self.trade = None  # the trade asked for or open, mup.server.trade.Trade
        self.party = None  # mup.server.party.Party
        self.party_question = None  # (connection, time) of who asked to party last, mup.server.party
        self.self_defense = {}  # connection -> until when its player may be hit back without a pk count, mup.server.pk
        self.pk_clock = 0.0  # game clock of the last pk time update, mup.server.pk
        self.guild = None  # mup.server.guild.Guild of the player in game
        self.guild_question = None  # (connection, time) of who asked to join last, mup.server.guild
        self.known_guilds = set()  # guild numbers the client was shown (5A), mup.server.view

    def __hash__(self):
        # by cid, so sets of connections iterate in the same order on every run (docs/bots.md, S0). The game server
        # gives the cid before the connection goes into any set; the connect server's have none
        return hash(self.cid) if self.cid is not None else object.__hash__(self)

    @property
    def tag(self):
        """Connection name in the log."""
        return self.cid

    def write(self, packet):
        """Delivers a server packet to the client."""
        raise NotImplementedError

    def disconnect(self):
        """Ends the connection, the server's disconnect follows."""
        raise NotImplementedError

    def saved(self):
        """The game stored the character: a bot stores its own state with it."""


class LocalSession(Session):
    """
    A connection in process, no socket: simulation puppets and bots. send() hands a built client packet to the game
    as bytes, the way one from the network arrives, so every check of the handlers applies; what the game writes
    lands in inbox as the packet objects (typed: SKill, SDamage, ... with their values as attributes). Both
    directions go to the packet log under the cid like a client's.
    """
    tap = None  # callable(session, packet) that sees everything written to it: a simulation's digest

    def __init__(self, server):
        super().__init__(server)
        self.inbox = []

    def write(self, packet):
        if not self.connected:
            return
        if packet_logger.isEnabledFor(logging.DEBUG):
            packet_logger.debug('%s > %s', self.cid, bytes(packet).hex(' '))
        if self.tap is not None:
            self.tap(self, packet)
        self.inbox.append(packet)

    def send(self, packet):
        """A client packet to the game, its handlers run now."""
        data = bytes(packet)
        if packet_logger.isEnabledFor(logging.DEBUG):
            packet_logger.debug('%s < %s', self.cid, data.hex(' '))
        self.server.dispatch(self, Base(bytearray(data)))

    def disconnect(self):
        """The client goes away, as when its connection drops."""
        if self.connected:
            self.connected = False
            self.server.disconnect(self)
