"""Read-only current-chat evidence derived from the installed Linux WeChat ELF.

No injection, debugger, app patch, external offset table or memory writes. Qt
metadata identifies ChatMessagePage and its session-loaded handler; that handler
identifies the libc++ session-name field it compares with its string argument.
Unrecognized metadata/code, multiple live pages and inconsistent reads fail closed.
"""
import json
import mmap
import os
from pathlib import Path
import pwd
import re
import struct
import subprocess
import time

EXE = Path('/opt/wechat/wechat')
LOCK = Path('/usr/share/weharbor/versions.lock.json')
CACHE = Path('/run/weharbor-session')
CLASS = b'mmui::ChatMessagePage'
SLOT = 'OnNewSessionDataLoaded'

class IdentityError(RuntimeError):
    pass

def require(value, reason='SESSION_LAYOUT_UNSUPPORTED'):
    if not value:
        raise IdentityError(reason)

def version_pair(value):
    match = re.fullmatch(r'(\d+)\.(\d+)(?:[.][0-9]+)*(?:[-+][A-Za-z0-9.+~-]+)?', value.strip())
    require(match, 'SESSION_VERSION_INVALID')
    return tuple(map(int, match.groups()))

class Elf:
    def __init__(self, data):
        self.data = data
        require(data[:6] == b'\x7fELF\x02\x01' and self.unpack('<H', 18)[0] == 62)
        phoff, = self.unpack('<Q', 32)
        phsize, count = self.unpack('<HH', 54)
        require(phsize == 56 and count < 100)
        self.segments = []
        for i in range(count):
            kind, flags, offset, address, _, size, _, _ = self.unpack('<IIQQQQQQ', phoff + i * 56)
            if kind == 1:
                require(offset + size <= len(data))
                self.segments.append((address, address + size, offset, flags))
        self.relocations = {}
        shoff, = self.unpack('<Q', 40)
        shsize, count = self.unpack('<HH', 58)
        require(shsize == 64 and count < 1000)
        for i in range(count):
            section = self.unpack('<IIQQQQIIQQ', shoff + i * 64)
            if section[1] != 4:
                continue
            start, size, entry = section[4], section[5], section[9]
            require(entry == 24 and size % 24 == 0 and start + size <= len(data))
            for pos in range(start, start + size, 24):
                address, info, addend = self.unpack('<QQq', pos)
                if info & 0xffffffff == 8:  # R_X86_64_RELATIVE
                    self.relocations[address] = addend

    def unpack(self, fmt, offset):
        require(0 <= offset <= len(self.data) - struct.calcsize(fmt))
        return struct.unpack_from(fmt, self.data, offset)

    def offset(self, address, size=1, executable=False):
        for low, high, start, flags in self.segments:
            if low <= address and address + size <= high and (not executable or flags & 1):
                return start + address - low
        raise IdentityError('SESSION_LAYOUT_UNSUPPORTED')

    def read(self, address, size):
        offset = self.offset(address, size)
        return self.data[offset:offset + size]

    def words(self, address, count):
        return struct.unpack('<' + 'I' * count, self.read(address, count * 4))

    def strings(self, address):
        first = self.read(address, 24)
        offset, = struct.unpack_from('<q', first, 16)
        require(24 <= offset <= 24000 and offset % 24 == 0)
        result = []
        for index in range(offset // 24):
            header = address + index * 24
            length, = struct.unpack_from('<I', self.read(header, 24), 4)
            relative, = struct.unpack_from('<q', self.read(header, 24), 16)
            require(length < 1024)
            result.append(self.read(header + relative, length).decode('ascii'))
        return result

    def layout(self):
        metas = []
        pos = 0
        while True:
            pos = self.data.find(CLASS + b'\0', pos)
            if pos < 0:
                break
            # Qt 5 QByteArrayData string-table header; relative offsets are
            # independent of ASLR and validated against the metadata below.
            for header in range(max(0, (pos - 24000 + 7) // 8 * 8), pos - 23, 8):
                if self.unpack('<iI', header) != (-1, len(CLASS)):
                    continue
                if header + self.unpack('<q', header + 16)[0] != pos:
                    continue
                address = next((lo + header - start for lo, hi, start, _ in self.segments
                                if start <= header < start + hi - lo), None)
                for relocation, addend in self.relocations.items():
                    if addend == address:
                        metas.append(relocation - 8)
            pos += len(CLASS)
        candidates = []
        for meta in set(metas):
            try:
                strings = self.strings(self.relocations[meta + 8])
                require(strings[0] == CLASS.decode())
                data = self.relocations[meta + 16]
                header = self.words(data, 14)
                require(header[0] == 8 and 0 < header[4] < 1000)
                methods = [self.words(data + (header[5] + i * 5) * 4, 5) for i in range(header[4])]
                slots = [i for i, row in enumerate(methods) if strings[row[0]] == SLOT and row[1] == 1]
                require(len(slots) == 1)
                slot = slots[0]
                args = self.words(data + methods[slot][2] * 4, 3)
                require(args[1] & 0x80000000 and strings[args[1] & 0x7fffffff] == 'std::string')
                call = self.relocations[meta + 24]
                code = self.read(call, 160)
                switch = re.search(rb'\x48\x8d\x15(.{4})\x48\x63\x04\x82\x48\x01\xd0\xff\xe0', code, re.S)
                require(switch)
                table = call + switch.start() + 7 + struct.unpack('<i', switch[1])[0]
                target = table + struct.unpack('<i', self.read(table + slot * 4, 4))[0]
                code = self.read(target, 40)
                require(code.startswith(b'\x48\x8b\x71\x08'))  # argument std::string*
                tail = code.find(b'\x41\x5f\xe9')
                require(0 < tail < 24)
                jump = target + tail + 2
                handler = jump + 5 + struct.unpack('<i', self.read(jump + 1, 4))[0]
                self.offset(handler, 200, executable=True)
                code = self.read(handler, 200)
                require(b'\x49\x89\xf7\x48\x89\xfb' in code[:32])  # preserve argument and this
                fields = re.findall(rb'\x0f\xb6\xbf(.{4})\x40\xf6\xc7\x01', code[:96], re.S)
                require(len(fields) == 1)
                field, = struct.unpack('<I', fields[0])
                require(0x80 <= field < 0x2000 and field % 8 == 0)
                require(b'\x4c\x8d\xb3' + struct.pack('<I', field + 1) in code)
                require(b'\x48\x8b\xb3' + struct.pack('<I', field + 16) in code)
                functions = []
                prefix = b'\x48\x8b\x7f\x08\x48\x83\x7f\x28\x00\x0f\x85'
                for lo, hi, start, flags in self.segments:
                    if not flags & 1:
                        continue
                    cursor = start
                    while True:
                        cursor = self.data.find(prefix, cursor, start + hi - lo)
                        if cursor < 0:
                            break
                        fn = lo + cursor - start
                        fn_code = self.read(fn, 23)
                        if fn_code[15:18] == b'\x48\x8d\x05' and fn_code[22] == 0xc3:
                            if fn + 22 + struct.unpack('<i', fn_code[18:22])[0] == meta:
                                functions.append(fn)
                        cursor += len(prefix)
                vtables = [address for address, value in self.relocations.items() if value in functions]
                require(vtables and functions)
                candidates.append({'field': field, 'vtables': vtables, 'meta': meta,
                    'functions': functions, 'handler': handler,
                    'handler_bytes': self.read(handler, 200).hex()})
            except (IdentityError, KeyError, IndexError, UnicodeError, struct.error):
                continue
        require(len(candidates) == 1)
        return candidates[0]

class Memory:
    def __init__(self, pid):
        self.maps = []
        for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
            fields = line.split()
            low, high = (int(v, 16) for v in fields[0].split('-'))
            self.maps.append((low, high, fields[1], fields[5] if len(fields) > 5 else '', int(fields[2], 16)))
        bases = {low - offset for low, _, _, path, offset in self.maps if path == str(EXE)}
        # Different LOAD segments have different virtual/file deltas. The
        # mapping at file offset zero is the actual ELF load bias.
        roots = [low for low, _, _, path, offset in self.maps if path == str(EXE) and offset == 0]
        require(len(roots) == 1 and bases, 'SESSION_PROCESS_UNVERIFIED')
        self.base = roots[0]
        self.fd = os.open(f'/proc/{pid}/mem', os.O_RDONLY | os.O_CLOEXEC)

    def close(self):
        os.close(self.fd)

    def read(self, address, size):
        require(0 <= size <= 4 * 1024 * 1024 + 128 and any(
            low <= address and address + size <= high and mode[0] == 'r'
            for low, high, mode, _, _ in self.maps), 'SESSION_MEMORY_INVALID')
        value = os.pread(self.fd, size, address)
        require(len(value) == size, 'SESSION_MEMORY_CHANGED')
        return value

    def word(self, address):
        return struct.unpack('<Q', self.read(address, 8))[0]

    def username(self, address):
        header = self.read(address, 24)
        if header[0] & 1:
            capacity, length, pointer = struct.unpack('<QQQ', header)
            require(0 < length <= 256 and length < (capacity & ~1), 'SESSION_STRING_INVALID')
            raw = self.read(pointer, length + 1)
            require(raw[-1:] == b'\0', 'SESSION_STRING_INVALID')
            raw = raw[:-1]
        else:
            length = header[0] >> 1
            require(0 < length <= 22 and header[1 + length] == 0, 'SESSION_STRING_INVALID')
            raw = header[1:1 + length]
        require(re.fullmatch(rb'[A-Za-z0-9_@.:-]{1,256}', raw), 'SESSION_STRING_INVALID')
        require(self.read(address, 24) == header, 'SESSION_MEMORY_CHANGED')
        return raw.decode('ascii')

    def page(self, address, layout):
        require(self.word(address) - self.base in layout['vtables'])
        private = self.word(address + 8)
        require(self.word(private + 8) == address)  # live QObjectData.q_ptr, not freed heap residue
        fn = self.word(self.word(address)) - self.base
        require(fn in layout['functions'])
        code = self.read(self.base + fn, 23)
        require(code[15:18] == b'\x48\x8d\x05' and code[22] == 0xc3)
        require(fn + 22 + struct.unpack('<i', code[18:22])[0] == layout['meta'])
        require(self.read(self.base + layout['handler'], 200).hex() == layout['handler_bytes'])
        return self.username(address + layout['field'])

    def pages(self, layout):
        found = set()
        deadline, scanned = time.monotonic() + 10, 0
        patterns = [struct.pack('<Q', self.base + v) for v in layout['vtables']]
        for low, high, mode, path, _ in self.maps:
            if mode[:2] != 'rw' or (path and path != '[heap]'):
                continue
            require(scanned + high - low <= 2 * 1024**3, 'SESSION_SCAN_LIMIT')
            for start in range(low, high, 4 * 1024 * 1024):
                require(time.monotonic() < deadline, 'SESSION_SCAN_TIMEOUT')
                size = min(4 * 1024 * 1024 + 128, high - start)
                try:
                    data = self.read(start, size)
                except (OSError, IdentityError):
                    continue
                for pattern in patterns:
                    pos = 0
                    while True:
                        pos = data.find(pattern, pos)
                        if pos < 0:
                            break
                        address = start + pos
                        pos += 8
                        if address % 8:
                            continue
                        try:
                            self.page(address, layout)
                            found.add(address)
                        except (OSError, IdentityError, struct.error):
                            continue
                require(len(found) <= 1, 'SESSION_PAGES_AMBIGUOUS')
            scanned += high - low
        require(len(found) == 1, 'SESSION_PAGE_UNAVAILABLE')
        return found.pop()

def capture(account):
    require(isinstance(account, str) and re.fullmatch(r'[A-Za-z0-9_@.-]{1,128}', account), 'SESSION_ACCOUNT_INVALID')
    expected = json.loads(LOCK.read_text())['wechat']['version']
    actual = subprocess.run(['/usr/bin/dpkg-query', '-W', '-f=${Version}', 'wechat'],
        capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    require(version_pair(actual) == version_pair(expected), 'SESSION_VERSION_MISMATCH')
    uid = pwd.getpwnam('abc').pw_uid
    processes = []
    for proc in Path('/proc').iterdir():
        try:
            if proc.name.isdecimal() and proc.stat().st_uid == uid and (proc/'exe').resolve() == EXE:
                args = (proc/'cmdline').read_bytes().split(b'\0')
                if not any(a.startswith(b'--type=') for a in args):
                    processes.append(proc)
        except OSError:
            continue
    require(len(processes) == 1, 'SESSION_PROCESS_UNVERIFIED')
    proc = processes[0]
    identity = (proc/'stat').read_text().rsplit(')', 1)[1].split()[19]
    accounts = set()
    for fd in (proc/'fd').iterdir():
        try:
            path = Path(os.readlink(fd).removesuffix(' (deleted)'))
            if path.is_relative_to('/config') and 'db_storage' in path.parts:
                accounts.add(path.parts[path.parts.index('db_storage') - 1])
        except OSError:
            continue
    require(accounts == {account}, 'SESSION_ACCOUNT_MISMATCH')
    CACHE.mkdir(mode=0o700, exist_ok=True)
    require(not CACHE.is_symlink() and CACHE.stat().st_uid == 0 and CACHE.stat().st_mode & 0o777 == 0o700, 'SESSION_CACHE_INVALID')
    stamp = EXE.stat()
    fingerprint = [stamp.st_dev, stamp.st_ino, stamp.st_size, stamp.st_mtime_ns]
    cache_file = CACHE/'layout.json'
    cached = {}
    try:
        cached = json.loads(cache_file.read_text())
    except (OSError, ValueError):
        pass
    if cached.get('fingerprint') == fingerprint:
        layout = cached['layout']
    else:
        with EXE.open('rb') as binary, mmap.mmap(binary.fileno(), 0, access=mmap.ACCESS_READ) as image:
            layout = Elf(image).layout()
    memory = Memory(int(proc.name))
    try:
        # Always enumerate all live typed pages. A cached pointer alone could
        # miss a second window opened since the preceding request.
        page = memory.pages(layout)
        first = memory.page(page, layout)
        time.sleep(.05)
        second = memory.page(page, layout)
        require(first == second, 'SESSION_MEMORY_CHANGED')
        require((proc/'stat').read_text().rsplit(')', 1)[1].split()[19] == identity, 'SESSION_PROCESS_CHANGED')
        cache_file.write_text(json.dumps({'fingerprint': fingerprint, 'layout': layout}))
        cache_file.chmod(0o600)
        return {'account': account, 'username': first, 'version': actual,
                'source': 'qt_session_loaded_handler', 'verified': True}
    finally:
        memory.close()
