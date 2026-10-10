// Fehlversuchszähler je Benutzer in /run/winky/sperre/<uid> (flüchtig, nach Neustart weg).
// Gezählt wird nur ein brauchbares, aber nicht passendes Gesicht.
#pragma once

#include <sys/types.h>

#include <string>

namespace winky {

constexpr const char* kSperreBasis = "/run/winky/sperre";

int leseFehlversuche(const std::string& basis, uid_t uid);
void schreibeFehlversuche(const std::string& basis, uid_t uid, int anzahl);

// Unbestätigte sudo-Anfragen in Folge (Datei sudo-<uid>: "anzahl zeit"). Ab kSudoGrenze gilt
// kSudoPause_s lang nur das Passwort; Treffer oder Passwortanmeldung setzen zurück.
constexpr int kSudoGrenze = 3;
constexpr long kSudoPause_s = 600;
int leseSudoOffen(const std::string& basis, uid_t uid, long jetzt);  // abgelaufene zählen 0
void schreibeSudoOffen(const std::string& basis, uid_t uid, int anzahl, long jetzt);
// Liest neu und zählt eins dazu (gleichzeitige Prüfungen zählen beide)
void erhoeheSudoOffen(const std::string& basis, uid_t uid, long jetzt);

// Nur eine sudo-Prüfung je Benutzer: Eine zweite bricht beide ab, damit sich keine fremde Anfrage
// in eine Bestätigung des Besitzers schmuggelt. Liefert Sperr-fd oder -1 (Abbruchmarke gesetzt).
int sudoSperren(const std::string& basis, uid_t uid);
bool sudoAbbruchGesetzt(const std::string& basis, uid_t uid);
void sudoEntsperren(const std::string& basis, uid_t uid, int fd);

// Erkannte Erstanmeldung: Marke anmeldung-<uid>; der Schlüsselbund-Dienst nimmt sie nur
// wenige Sekunden lang an und löscht sie dabei.
void markiereAnmeldung(const std::string& basis, uid_t uid);

}  // namespace winky
