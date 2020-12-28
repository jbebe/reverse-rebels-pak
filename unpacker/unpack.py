import os
import glob
import json
import codecs
import struct
import zlib
from enum import Enum
from math import log2

def humanSize(size):
    _suffixes = ['bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    # determine binary order in steps of size 10 
    # (coerce to int, // still returns a float)
    order = int(log2(size) / 10) if size else 0
    # format file size
    # (.4g results in rounded numbers for exact matches and max 3 decimals, 
    # should never resort to exponent values)
    return '{:.4g} {}'.format(size / (1 << (order * 10)), _suffixes[order])

class SeekMode(Enum):
    START = 0
    RELATIVE = 1
    END = 2

def dbg(x): print(json.dumps(x, indent="  ", separators=("", "")))

def getSize(file):
    oldPos = file.tell()
    file.seek(0, SeekMode.END.value)
    size = file.tell()
    file.seek(oldPos, SeekMode.START.value)
    return size

def skip(file, x): file.seek(x, SeekMode.RELATIVE.value)

def getOffset(file, fr, to, seekMode = SeekMode.RELATIVE.value):
    file.seek(fr, seekMode)
    offset = file.read(to)
    return offset

def dbgOffset(file, fr, to, seekMode = SeekMode.RELATIVE.value):
    offset = getOffset(file, fr, to, seekMode)
    # offsetStr = b''.join([bytes(x) if x >= 32 else b'.' for x in offset]).decode("cp1250")
    offsetStr = b''.join([chr(x).encode('cp1250') if x >= 32 and x < 128 else b'.' for x in offset]).decode("cp1250")
    dbg(offsetStr)

def getInt(file, fr, to, seekMode = SeekMode.RELATIVE.value):
    offset = getOffset(file, fr, to, seekMode)
    hexStr = offset.hex()
    return int(struct.unpack("<I", codecs.decode(hexStr, "hex") )[0])

def dbgHex(file, fr, to, seekMode = SeekMode.RELATIVE.value):
    i = getInt(file, fr, to, seekMode)
    s = getSize(file)
    dbg("{offset}/{size}".format(offset=i, size=s))
    return i

class FileInfo:
    def __init__(self, name: str, offset: int, size: int, zipFlag: int, compressedSize: int):
        self.name = name
        self.offset = offset
        self.size = size
        self.zipFlag = zipFlag
        self.compressedSize = compressedSize
    def __str__(self):
        return "@{:08x}: \"{}\" actual: {}, compressed: {} {}".format(
            self.offset, self.name, humanSize(self.size), self.compressedSize, 
            "(zipped)" if self.zipFlag == 1 else "")

class CType(Enum):
    BYTE = 0
    SHORT = 1
    INT = 2

def getBytesAsInt(x, size = CType.INT.value):
    return int.from_bytes(x[:2**size], "little"), x[(2**size):]

def getCString(content) -> (str, bytes):
    i = 0
    while True:
        if content[i] == 0:
            return content[:i].decode('cp1250'), content[i + 1:]
        i += 1

def parseFile(content) -> (FileInfo, bytes):
    # skip first null
    content = content[2:]
    fileName, content = getCString(content)
    fileOffset, content = getBytesAsInt(content)
    # skip unused 4 bytes of file offset 
    content = content[4:]
    # decompressed length
    fileSize, content = getBytesAsInt(content)
    # skip unused 4 bytes of decompressed length
    content = content[4:]
    # skip unused 2 bytes (tag?)
    zipFlag, content = getBytesAsInt(content, CType.SHORT.value)
    compressedSize, content = getBytesAsInt(content)
    # skip unused 4 bytes of compressed size
    content = content[4:]
    return FileInfo(fileName, fileOffset, fileSize, zipFlag, compressedSize), content

def extractByFileType(fileInfo: FileInfo, data: bytes):
    # get extension
    _, extension = os.path.splitext(fileInfo.name)
    if fileInfo.zipFlag == 0: # or extension.lower() in [".alr", ".las"]:
        return data
    else:
        return zlib.decompress(data)

def extractFile(fileInfo: FileInfo, data: bytes, path: str):
    # get compressed file from pak
    data = data[fileInfo.offset:fileInfo.offset+fileInfo.compressedSize]
    data = extractByFileType(fileInfo, data)
    # create path from filename
    path = os.path.join(path, fileInfo.name)
    # write to file
    with open(path, 'wb') as file:
    	file.write(data)

def parseDirectories(content, dataRaw, pakPath):
    # skip unused properties
    content = content[13 + 4 + 4 + 4:]
    # get directory count
    dirCount, content = getBytesAsInt(content, CType.SHORT.value)
    for dirIdx in range(dirCount):
        # get directory name
        dirName, content = getCString(content)
        dirPath = os.path.join(pakPath, dirName)
        if not os.path.exists(dirPath): os.mkdir(dirPath)
        dbg("#{} dirName: {}".format(dirIdx + 1, dirName))
        # parse files
        isFolderEnd = False
        while not isFolderEnd:
            if content[:2] == b"\x04\x00" or content[:2] == b"\x01\x00":
                isFolderEnd = True
            else:
                fileInfo, content = parseFile(content)
                print(fileInfo)
                extractFile(fileInfo, dataRaw, dirPath)
                # extract file content optionally

def parsePak(pakFile):
    dbg("- - - {file} - - - ".format(file=pakFile.name))
    pakFolderName = os.path.basename(os.path.dirname(pakFile.name))
    # create root of pak dir (pak dir will be created from parseDirectories)
    if not os.path.exists(pakFolderName): os.mkdir(pakFolderName)
    # header + null
    dbgOffset(pakFile, 0, 17)
    # get directory offset
    dirOffset = getInt(pakFile, 0, 4)
    dirSize = getSize(pakFile) - dirOffset
    # dbgOffset(pakFile, dirOffset, dirSize, seekMode=SeekMode.START.value)
    dbg("dir offset: {}, size: {}".format(dirOffset, humanSize(dirSize)))
    # get raw data as binary
    pakHeaderSize = 16 + 1 + 8
    pakFile.seek(pakHeaderSize, SeekMode.START.value)
    dataRaw = pakFile.read(dirOffset)
    pakFile.seek(dirOffset, SeekMode.START.value)
    dirContentRaw = pakFile.read(dirSize)
    parseDirectories(dirContentRaw, dataRaw, pakFolderName)
    # ???
    # dbgOffset(pakFile, 0, 147 - 1)

def main():
    dataPath = "..\\rebels_data"
    paks = []
    for x in os.walk(dataPath):
        for y in glob.glob(os.path.join(x[0], '*.pak')):
            paks.append(os.path.abspath(y))

    #for pak in ["E:\\Games\\Rebels\\rebels_data\\common\\gui.pak"]:
    for pak in paks:
        with open(pak, "rb") as pakFile:
            parsePak(pakFile)
            
if __name__ == "__main__":
    main()