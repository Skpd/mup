from dataclasses import dataclass

GM = 0x20  # ctl code bit: GM commands (mup.server.command)


@dataclass
class Account:
    id: int = None  # accounts.id, None until stored
    name: str = ''
    password_hash: str = ''  # mup.common.password
    personal_code: str = ''  # asked by the client to delete a character
    ctl_code: int = 0  # GM
    active: bool = True  # False: banned
