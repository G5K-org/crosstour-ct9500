#!/usr/bin/env python3
"""Befehl per Telnet auf der CT9500 ausführen und Ausgabe zurückgeben.

  tools/camsh.py 'uname -a; cat /proc/mtd'
  echo 'ls /app' | tools/camsh.py -
"""
import os, re, socket, sys, time, uuid

HOST = os.environ.get("CT9500_HOST", "192.168.0.1")


def run(cmd, timeout=60, host=HOST):
    s = socket.create_connection((host, 23), timeout=10)
    buf = b""

    def recv_until(marker, t):
        nonlocal buf
        end = time.time() + t
        while marker not in buf:
            if time.time() > end:
                raise TimeoutError(buf.decode("utf-8", "replace")[-500:])
            s.settimeout(max(0.1, end - time.time()))
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            # Telnet-Optionsaushandlung (IAC) ablehnen
            out, i = bytearray(), 0
            while i < len(chunk):
                if chunk[i] == 255 and i + 2 < len(chunk):
                    verb, opt = chunk[i + 1], chunk[i + 2]
                    if verb in (251, 252):
                        s.send(bytes([255, 254, opt]))
                    elif verb in (253, 254):
                        s.send(bytes([255, 252, opt]))
                    i += 3
                else:
                    out.append(chunk[i]); i += 1
            buf += bytes(out)

    tag = uuid.uuid4().hex[:8]
    time.sleep(0.3)
    s.send(f"stty -echo 2>/dev/null; echo START{tag}\n".encode())
    recv_until(f"START{tag}\r\n".encode(), 10)
    buf = buf.split(f"START{tag}\r\n".encode(), 1)[1]
    s.send(f"{cmd}\necho \"\"; echo END{tag} $?\n".encode())
    recv_until(f"END{tag}".encode(), timeout)
    recv_until(b"\n", 5)
    s.send(b"exit\n")
    s.close()
    text = buf.decode("utf-8", "replace").replace("\r\n", "\n")
    out, rc = text.rsplit(f"END{tag}", 1)
    return out.rstrip("\n").removesuffix("\n").rstrip(), int(re.findall(r"\d+", rc)[0])


if __name__ == "__main__":
    cmd = sys.stdin.read() if sys.argv[1:] == ["-"] else " ".join(sys.argv[1:])
    out, rc = run(cmd)
    print(out)
    sys.exit(rc)
