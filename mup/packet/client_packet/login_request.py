from mup.packet.base import Base


class LoginRequest(Base):
    login = None
    passw = None
    version = None
    serial = None

    def __init__(self, src):
        super().__init__(src)

        self.login = self[4:14].strip(b'\0').decode('ascii')
        self.passw = self[14:34].strip(b'\0').decode('ascii')  # gmo - 20, rest - 10
        self.tick = int.from_bytes(self[34:38], byteorder='little', signed=False)
        self.version = self[38:43]
        self.serial = self[43:]


