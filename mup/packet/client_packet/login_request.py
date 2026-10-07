from mup.packet.base import Base


class LoginRequest(Base):
    login = None
    passw = None
    version = None
    serial = None

    def __init__(self, src):
        super().__init__(src)

        self.login = self[4:14].strip(b'\0').decode('latin-1')
        self.passw = self[14:24].strip(b'\0').decode('latin-1')  # 0.97 - 10, gmo - 20
        self.tick = int.from_bytes(self[24:28], byteorder='big', signed=False)
        self.version = self[28:33]
        self.serial = self[33:49]
