// Hinweisdatei offener Anfragen für den Desktop-Hinweis: /run/winky/anfrage/<uid>.json mit zeit
// (Unix), stand (wartet|bestaetigt|nicht_bestaetigt|abgebrochen|passwort|begrenzt), befehl,
// terminal, zweck, frist (Wartezeit auf das ✌ in ms).
// Lesbar für alle (Befehl steht ohnehin in der Prozessliste), damit Unerwartetes sofort auffällt.
#pragma once

#include <sys/types.h>

#include <string>

namespace winky {

constexpr const char* kAnfrageBasis = "/run/winky/anfrage";

// zweck: "sudo" oder "keepassxc" (bestimmt die Texte der Desktop-Meldung)
void schreibeAnfrage(const std::string& basis, uid_t uid, const std::string& stand,
                     const std::string& befehl, const std::string& terminal, long zeit,
                     const std::string& zweck = "sudo", int frist_ms = 8000);

// Nur druckbare Zeichen, höchstens max Bytes (UTF-8 bleibt erhalten)
std::string saeubern(const std::string& s, size_t max);

}  // namespace winky
