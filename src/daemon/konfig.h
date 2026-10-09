// Konfiguration des Prüfdienstes aus /etc/winky/winky.conf.
// Die Datei muss root gehören und darf für Gruppe und andere nicht
// beschreibbar sein. Unbekannte Schlüssel oder Werte außerhalb der Grenzen
// führen zum Abbruch (der Dienst lehnt dann ab, das Passwort greift).
#pragma once

#include <string>

namespace winky {

constexpr const char* kKonfigPfad = "/etc/winky/winky.conf";

struct Konfig {
  float schwelle = 0.0f;  // 0 = noch nicht kalibriert, Gesicht bleibt aus
  std::string kamera;  // leer = noch keine Kamera eingerichtet
  int mindest_treffer = 2;
  int ohne_gesicht_ms = 1200;
  int gesamt_ms = 2600;
  int sperre_nach = 5;
  bool sitzungspruefung = true;
  int threads = 4;
  float blink_abstand = 15.0f;
  bool blinkpruefung = true;  // aus, wenn der IR-Strahler dauerhaft leuchtet
  bool keepassxc = false;     // Schnellentsperren von KeePassXC per Gesicht erlaubt
  bool keepassxc_geste = true;  // KeePassXC nur mit Gesicht und ✌ (wie sudo)
  bool sudo = false;          // sudo mit Gesicht und Handzeichen ✌ bestätigen
  int sudo_ms = 8000;         // so lange wartet die sudo-Prüfung auf das Zeichen
};

bool ladeKonfig(const std::string& pfad, Konfig& k, std::string& fehler);

}  // namespace winky
