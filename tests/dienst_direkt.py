#!/usr/bin/env python3
"""Startet den Prüfdienst wie systemd (Verbindung auf fd 0) und schickt eine Anfrage.
Nur für Tests im Container. Aufruf: dienst_direkt.py OP UID [DAUER] [-- Dienstoptionen]"""
import json, os, socket, struct, sys
op, uid = int(sys.argv[1]), int(sys.argv[2])
dauer = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != "--" else 0
optionen = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
pid = os.fork()
if pid == 0:
    os.dup2(b.fileno(), 0)
    os.execv("bau/winky-matcher", ["winky-matcher", *optionen])
b.close()
a.send(struct.pack("IIII", 0x314B4E57, op, uid, dauer))
bilder = 0
while True:
    m = a.recv(300000)
    if not m:
        print("Verbindung beendet"); break
    if len(m) == 16:
        print("Antwort", struct.unpack("IIfI", m)); break
    art = chr(m[0])
    if art == "S": print("STATUS", m[1:].decode()[:600])
    elif art == "B": bilder += 1
    elif art == "E": print("ENDE", struct.unpack("IIfI", m[1:]), "Vorschaubilder:", bilder); break
os.waitpid(pid, 0)
