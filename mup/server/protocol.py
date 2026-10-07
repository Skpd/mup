import sys
import binascii
import logging
from asyncio import Protocol
from asyncio.transports import Transport
from mup.common.crypt import Crypt
from mup.model.account import Account
from mup.model.player import Player
from mup.packet.base import Base
from mup.packet.client import factory
from mup.server.game import GameServer

logger = logging.getLogger('connection')
log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(logging.Formatter('\r%(asctime)s %(levelname)s: %(message)s\r'))
logger.addHandler(log_handler)
logger.setLevel(logging.DEBUG)


class BaseProtocol(Protocol):
    transport: Transport
    server: GameServer
    crypt: Crypt
    player: Player = None
    acc: Account = None

    cid = None
    connected = False
    joined = False
    playing = False
    server_tick = None
    client_tick = None

    def __init__(self, gs):
        self.crypt = Crypt(decode_keys='data/Dec1.dat', encode_keys='data/Enc2.dat')
        # self.crypt = Crypt(decode_keys='/tmp/server065/data/Dec1.dat', encode_keys='/tmp/server065/data/Enc2.dat')
        self.server = gs
        self.buffer = bytearray()
        self.logger = logger

    def disconnect(self):
        self.transport.close()

    def connection_made(self, transport):
        self.transport = transport
        self.server.add_connection(self)
        self.connected = True

    def connection_lost(self, exc):
        self.connected = False
        self.server.disconnect(self)
        self.logger.debug('Connection {} closed'.format(self.cid))

    def write(self, what, raw=False):
        if self.transport.is_closing():
            return

        self.logger.debug('> {}'.format(binascii.hexlify(what, sep=' ')))
        if what[0] in {0xC3, 0xC4} and not raw:
            what = self.crypt.encrypt(what)
            self.logger.debug('!!> {}'.format(binascii.hexlify(what, sep=' ')))
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
                self.logger.error('Not a packet: {}'.format(binascii.hexlify(self.buffer, sep=' ')))
                self.disconnect()
                return

            header_size = 3 if self.buffer[0] in {0xC2, 0xC4} else 2
            if len(self.buffer) < header_size:
                return

            size = self.buffer[1] << 8 | self.buffer[2] if header_size == 3 else self.buffer[1]
            if size <= header_size:
                self.logger.error('Invalid packet size: {}'.format(binascii.hexlify(self.buffer, sep=' ')))
                self.disconnect()
                return

            if len(self.buffer) < size:
                return

            message = Base(self.buffer[:size])
            del self.buffer[:size]
            self.packet_received(message)

    def packet_received(self, message: Base):
        self.logger.debug('< {}'.format(binascii.hexlify(message, sep=' ')))

        if message[0] in {0xC3, 0xC4}:
            try:
                message = self.crypt.decrypt(message)
            except RuntimeError as e:
                self.logger.error('{} ({} bytes)'.format(e, len(message)))
                return
            self.logger.debug('Decrypted {}'.format(binascii.hexlify(message, sep=' ')))
        elif message[0] in {0xC1, 0xC2} and self.joined:
            self.crypt.extract(message, message[0] == 0xC2)
            self.logger.debug('Extracted {}'.format(binascii.hexlify(message, sep=' ')))

        try:
            packet = factory(message)

            if packet and packet.key in self.server.handlers:
                callbacks = self.server.handlers[packet.key]
                if not len(callbacks):
                    self.logger.warning('No handlers for {}'.format(packet.key))

                for c in callbacks:
                    c(packet, self)
            else:
                self.logger.warning('No handlers for {}'.format(binascii.hexlify(message, sep=' ')))
        except Exception:
            # keep the connection, one broken handler shouldn't kick the player
            self.logger.exception('Failed to handle {}'.format(binascii.hexlify(message, sep=' ')))
