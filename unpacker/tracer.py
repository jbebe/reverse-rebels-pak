from pymem import Pymem

fileStruct = (0x6d9100)
bufferOffset = (3-1)*4

pm = Pymem('Rebels.exe')
bufferPtr = pm.read_uint(fileStruct + bufferOffset)

content = []
idx = 0
while True:
    ch = pm.read_uchar(bufferPtr + idx)
    if ch in [0x0D, 0xF0, 0xAD, 0xBA]:
        break
    content.append(ch)
    idx += 1

print(''.join([chr(x) for x in content]))