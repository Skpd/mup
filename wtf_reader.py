import sys

path = sys.argv[1]

c = bytearray(open(path, 'rb').read())

code = c[0]
version = c[1]
title = c[2:23]
title = title[0:title.find(b'\0')].decode()
msg_count = c[24]

messages = {}
p = 25
for i in range(msg_count):
    index = c[p+1] << 8 | c[p]
    p += 2
    size = c[p+1] << 8 | c[p]
    p += 2
    msg = bytearray([x ^ 0xCA for x in c[p:p+size]])
    messages[index] = msg
    p += size
print(code, version, title, msg_count, messages)

