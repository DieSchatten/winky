// Konfiguration aus /etc/winky/winky.conf (root-eigen, nicht für Gruppe/andere beschreibbar).
// Unbekannte Schlüssel oder Werte außerhalb der Grenzen: Dienst lehnt ab, das Passwort greift.
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
  bool keepassxc = false;     // KeePassXC per Gesicht entsperren
  bool keepassxc_geste = true;  // dabei zusätzlich ✌ verlangen
  bool sudo = false;          // sudo per Gesicht und ✌ bestätigen
  int sudo_ms = 8000;         // Zeitfenster der Gestenprüfung (sudo, KeePassXC)
  std::string freigaben;      // Polkit-Gruppen mit ✌, kommagetrennt (leer = keine)
};

bool ladeKonfig(const std::string& pfad, Konfig& k, std::string& fehler);

}  // namespace winky
