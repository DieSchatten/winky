// Entsperren nur mit aktiver, lokaler grafischer Sitzung an seat0 (Abfrage über logind).
#pragma once

#include <sys/types.h>

#include <string>

namespace winky {

bool hatLokaleGrafischeSitzung(uid_t uid, std::string& grund);

// sudo: Gehört das Terminal (z. B. "/dev/pts/3") zu einer entfernten Sitzung (SSH)?
// Terminals im grafischen Desktop gehören zu keiner logind-Sitzung und sind erlaubt.
bool terminalEntfernt(const std::string& terminal);

}  // namespace winky
