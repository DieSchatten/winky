// Zähler für Fehlversuche je Benutzer unter /run/winky/sperre/<uid>.
// Liegt im flüchtigen /run und ist nach einem Neustart weg. Gezählt wird nur,
// wenn ein brauchbares Gesicht da war, aber nicht passte.
#pragma once

#include <sys/types.h>

#include <string>

namespace winky {

constexpr const char* kSperreBasis = "/run/winky/sperre";

int leseFehlversuche(const std::string& basis, uid_t uid);
void schreibeFehlversuche(const std::string& basis, uid_t uid, int anzahl);

// Unbestätigte sudo-Anfragen in Folge (Datei sudo-<uid>: "anzahl zeit"). Nach
// kSudoGrenze unbestätigten gilt kSudoPause_s lang nur das Passwort; ein Treffer oder
// eine Passwortanmeldung setzt zurück.
constexpr int kSudoGrenze = 3;
constexpr long kSudoPause_s = 600;
int leseSudoOffen(const std::string& basis, uid_t uid, long jetzt);  // abgelaufene zählen 0
void schreibeSudoOffen(const std::string& basis, uid_t uid, int anzahl, long jetzt);
// Liest den aktuellen Stand neu und zählt eins dazu (gleichzeitige Prüfungen zählen beide)
void erhoeheSudoOffen(const std::string& basis, uid_t uid, long jetzt);

// Nur eine sudo-Prüfung je Benutzer gleichzeitig. Kommt eine zweite, brechen beide ab:
// sonst könnte ein Programm genau dann eine Anfrage stellen, wenn der Besitzer seine
// eigene bestätigt. Liefert den Sperr-fd (>= 0) oder -1, wenn schon eine läuft; dann ist
// die Abbruchmarke für die laufende gesetzt.
int sudoSperren(const std::string& basis, uid_t uid);
bool sudoAbbruchGesetzt(const std::string& basis, uid_t uid);
void sudoEntsperren(const std::string& basis, uid_t uid, int fd);

}  // namespace winky
