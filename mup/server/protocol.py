import logging
from asyncio import Protocol
from asyncio.transports import Transport
from mup.common.crypt import Crypt
from mup.config import PACKET_LOGGER
from mup.packet.base import Base
from mup.server.session import Session

logger = logging.getLogger(__name__)
packet_logger = logging.getLogger(PACKET_LOGGER)


class BaseProtocol(Protocol, Session):
    """A client over the network: framing, crypto and the packet log, the packets go to the server's handlers."""
    transport: Transport
    crypt: Crypt

    peer = None

    def __init__(self, server):
        Session.__init__(self, server)
        self.crypt = Crypt(decode_keys='data/Dec1.dat', encode_keys='data/Enc2.dat')
        # self.crypt = Crypt(decode_keys='/tmp/server065/data/Dec1.dat', encode_keys='/tmp/server065/data/Enc2.dat')
        self.buffer = bytearray()
        self.logger = logger

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

        self.server.dispatch(self, message)
