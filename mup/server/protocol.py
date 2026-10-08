import logging
from asyncio import Protocol
from asyncio.transports import Transport
from mup.common.crypt import Crypt
from mup.config import PACKET_LOGGER
from mup.model.account import Account
from mup.model.player import Player
from mup.packet.base import Base
from mup.packet.client import factory
from mup.server.game import GameServer

logger = logging.getLogger(__name__)
packet_logger = logging.getLogger(PACKET_LOGGER)


class BaseProtocol(Protocol):
    transport: Transport
    server: GameServer
    crypt: Crypt
    player: Player = None
    acc: Account = None

    cid = None
    peer = None
    connected = False
    joined = False
    playing = False
    server_tick = None
    client_tick = None
    reported_speeds = None  # attack and magic speed of the last ping
    view = None  # players, monsters and ground items this client has in view (mup.server.view)

    def __init__(self, gs):
        self.crypt = Crypt(decode_keys='data/Dec1.dat', encode_keys='data/Enc2.dat')
        # self.crypt = Crypt(decode_keys='/tmp/server065/data/Dec1.dat', encode_keys='/tmp/server065/data/Enc2.dat')
        self.server = gs
        self.buffer = bytearray()
        self.logger = logger
        self.view = set()
        self.area_casts = {}  # skill number -> mup.server.casting.AreaCast
        self.teleport_at = 0.0  # the next teleport is allowed then
        self.left = None  # the character it logged out of
        self.summon = None  # the player's summoned monster, mup.server.summon
        self.window = None  # the NPC window open, mup.server.npc.Window
        self.warehouse = None  # the account's vault once opened, saved with the character (mup.server.warehouse)
        self.stale_box = False  # the client may still show items in its chaos machine box, mup.server.chaos

    @property
    def tag(self):
        """Connection name in the log: cid on the game server, address on the connect server."""
        return self.cid if self.cid is not None else self.peer

    def log_packet(self, what, data):
        if packet_logger.isEnabledFor(logging.DEBUG):
            packet_logger.debug('%s %s %s', self.tag, what, data.hex(' '))

    def disconnect(self):
        self.transport.close()

    def connection_made(self, transport):
        self.transport = transport
        self.peer = '{}:{}'.format(*transport.get_extra_info('peername')[:2])
        self.logger.info('Connection from %s', self.peer)
        self.server.add_connection(self)
        self.connected = True

    def connection_lost(self, exc):
        self.connected = False
        self.server.disconnect(self)
        self.logger.info('Connection %s closed', self.tag)

    def write(self, what, raw=False):
        if self.transport.is_closing():
            return

        self.log_packet('>', what)
        if what[0] in {0xC3, 0xC4} and not raw:
            what = self.crypt.encrypt(what)
            self.log_packet('!!>', what)
        self.transport.write(what)

    def send_all(self, msg, except_self=True):
        for c in self.server.connections.values():
            if isinstance(c, BaseProtocol) and c.playing and (not except_self or c != self):
                c.write(msg)

    def send_same_map(self, msg, except_self=False):
        ...

    def send_near(self, msg, except_self=True):
        ...

    def data_received(self, data):
        # tcp is a stream, a read can hold several packets or a part of one
        self.buffer += data

        while self.buffer and not self.transport.is_closing():
            if self.buffer[0] not in {0xC1, 0xC2, 0xC3, 0xC4}:
                self.logger.error('Not a packet: %s', self.buffer.hex(' '))
                self.disconnect()
                return

            header_size = 3 if self.buffer[0] in {0xC2, 0xC4} else 2
            if len(self.buffer) < header_size:
                return

            size = self.buffer[1] << 8 | self.buffer[2] if header_size == 3 else self.buffer[1]
            if size <= header_size:
                self.logger.error('Invalid packet size: %s', self.buffer.hex(' '))
                self.disconnect()
                return

            if len(self.buffer) < size:
                return

            message = Base(self.buffer[:size])
            del self.buffer[:size]
            self.packet_received(message)

    def packet_received(self, message: Base):
        self.log_packet('<', message)

        if message[0] in {0xC3, 0xC4}:
            try:
                message = self.crypt.decrypt(message)
            except RuntimeError as e:
                self.logger.error('%s (%s bytes)', e, len(message))
                return
            self.log_packet('Decrypted', message)
        elif message[0] in {0xC1, 0xC2} and self.joined:
            self.crypt.extract(message, message[0] == 0xC2)
            self.log_packet('Extracted', message)

        try:
            packet = factory(message)

            if packet and packet.key in self.server.handlers:
                for c in self.server.handlers[packet.key]:
                    c(packet, self)
            else:
                self.logger.warning('Unhandled packet %s', message.hex(' '))
        except Exception:
            # keep the connection, one broken handler shouldn't kick the player
            self.logger.exception('Failed to handle %s', message.hex(' '))
