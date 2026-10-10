// Komponententests für Konfiguration, Vorlagen, Entscheidungsregel und Sperrzähler.
// Läuft im Bau-Container als (Namensraum-)root, um root-eigene Testdateien anzulegen.

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include "anfrage.h"
#include "entscheidung.h"
#include "konfig.h"
#include "sperre.h"
#include "vorlagen.h"

static int fehler = 0;
#define PRUEFE(bed, text)                                       \
  do {                                                          \
    if (bed) {                                                  \
      std::printf("ok      %s\n", text);                        \
    } else {                                                    \
      std::printf("FEHLER  %s (Zeile %d)\n", text, __LINE__);   \
      ++fehler;                                                 \
    }                                                           \
  } while (0)

static std::string basis;

static void schreibe(const std::string& pfad, const std::string& inhalt, mode_t modus = 0644) {
  std::ofstream(pfad, std::ios::binary) << inhalt;
  chmod(pfad.c_str(), modus);
}

static std::vector<uint8_t> vorlagenDatei(uint32_t anzahl, const char* modell = winky::kErkennungsModellSha,
                                          bool normiert = true, bool nan = false) {
  std::vector<uint8_t> b(winky::kVorlagenKopf + anzahl * winky::kVorlagenDim * sizeof(float));
  std::memcpy(&b[0], "WNKV", 4);
  const uint32_t version = 1, dim = winky::kVorlagenDim;
  std::memcpy(&b[4], &version, 4);
  std::memcpy(&b[8], &dim, 4);
  std::memcpy(&b[12], &anzahl, 4);
  std::memcpy(&b[16], modell, 64);
  const int64_t t = 1790000000;
  std::memcpy(&b[80], &t, 8);
  for (uint32_t i = 0; i < anzahl; ++i) {
    std::vector<float> v(winky::kVorlagenDim, 0.0f);
    v[i % winky::kVorlagenDim] = normiert ? 1.0f : 2.0f;
    if (nan && i == 0) v[3] = NAN;
    std::memcpy(&b[winky::kVorlagenKopf + i * winky::kVorlagenDim * sizeof(float)], v.data(), winky::kVorlagenDim * sizeof(float));
  }
  return b;
}

static void testKonfig() {
  winky::Konfig k;
  std::string f;
  const std::string p = basis + "/winky.conf";
  schreibe(p, "# Kommentar\nschwelle = 0.62\nkamera=/dev/video2\nsitzungspruefung=nein\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && std::fabs(k.schwelle - 0.62f) < 1e-6 &&
             k.kamera == "/dev/video2" && !k.sitzungspruefung,
         "Konfiguration wird gelesen");
  schreibe(p, "schwelle=0.65\nkamera=\nblinkpruefung=nein\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && k.kamera.empty() && !k.blinkpruefung,
         "leere Kamera (nicht eingerichtet) und Blinkprüfung aus werden gelesen");
  schreibe(p, "blinkpruefung=vielleicht\n");
  PRUEFE(!winky::ladeKonfig(p, k, f), "ungültiger Wert für Blinkprüfung wird abgelehnt");
  schreibe(p, "schwelle=0.62\nunbekannt=1\n");
  PRUEFE(!winky::ladeKonfig(p, k, f), "unbekannter Schlüssel wird abgelehnt");
  schreibe(p, "schwelle=0.2\n");
  PRUEFE(!winky::ladeKonfig(p, k, f), "Schwelle unter 0,40 wird abgelehnt");
  schreibe(p, "schwelle=0\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && k.schwelle == 0.0f, "Schwelle 0 bedeutet nicht kalibriert");
  schreibe(p, "kamera=/etc/shadow\n");
  PRUEFE(!winky::ladeKonfig(p, k, f), "Kamera außerhalb von /dev wird abgelehnt");
  schreibe(p, "gesamt_ms=4000\n");
  PRUEFE(!winky::ladeKonfig(p, k, f), "Gesamtzeit über PAM-Frist wird abgelehnt");
  schreibe(p, "schwelle=0.6\n", 0666);
  PRUEFE(!winky::ladeKonfig(p, k, f), "beschreibbare Konfiguration wird abgelehnt");
  chmod(p.c_str(), 0644);
  const std::string link = basis + "/link.conf";
  symlink(p.c_str(), link.c_str());
  PRUEFE(!winky::ladeKonfig(link, k, f), "Konfiguration als Verknüpfung wird abgelehnt");
  chown(p.c_str(), 1000, 1000);
  PRUEFE(!winky::ladeKonfig(p, k, f), "Konfiguration mit fremdem Besitzer wird abgelehnt");
  chown(p.c_str(), 0, 0);
  schreibe(p, "schwelle=0.65\nsudo=ja\nsudo_ms=7000\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && k.sudo && k.sudo_ms == 7000, "sudo-Schalter und Wartezeit werden gelesen");
  schreibe(p, "schwelle=0.65\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && !k.sudo, "sudo ist ohne Eintrag aus");
  schreibe(p, "sudo_ms=40000\n");
  PRUEFE(!winky::ladeKonfig(p, k, f), "sudo-Wartezeit über dem PAM-Zeitlimit wird abgelehnt");
  schreibe(p, "schwelle=0.65\nkeepassxc=ja\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && k.keepassxc && k.keepassxc_geste,
         "KeePassXC verlangt ohne Eintrag Gesicht und ✌");
  schreibe(p, "schwelle=0.65\nkeepassxc=ja\nkeepassxc_geste=nein\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && k.keepassxc && !k.keepassxc_geste,
         "KeePassXC mit Gesicht allein nur ausdrücklich");
  schreibe(p, "keepassxc_geste=vielleicht\n");
  PRUEFE(!winky::ladeKonfig(p, k, f), "ungültiger Wert für keepassxc_geste wird abgelehnt");
  schreibe(p, "schwelle=0.65\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && !k.dialoge, "Administrator-Dialoge ohne Eintrag aus");
  schreibe(p, "dialoge = ja\nfreigaben = updates,software\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && k.dialoge, "Dialog-Schalter gelesen, alte Freigaben-Zeile stört nicht");
  schreibe(p, "schwelle=0.65\nanmeldung=ja\n");
  PRUEFE(winky::ladeKonfig(p, k, f) && k.anmeldung, "Erstanmeldung per Gesicht nur ausdrücklich");
  schreibe(p, "dialoge=vielleicht\n");
  PRUEFE(!winky::ladeKonfig(p, k, f), "ungültiger Wert für dialoge wird abgelehnt");
}

static void testAnfrage() {
  const std::string b = basis + "/anfrage";
  mkdir(b.c_str(), 0755);
  winky::schreibeAnfrage(b, 1000, "wartet", "KeePassXC entsperren", "", 123, "keepassxc");
  std::ifstream in(b + "/1000.json");
  std::string inhalt;
  std::getline(in, inhalt);
  PRUEFE(inhalt.find("\"zweck\":\"keepassxc\"") != std::string::npos &&
             inhalt.find("\"stand\":\"wartet\"") != std::string::npos &&
             inhalt.find("\"frist\":8000") != std::string::npos,
         "Anfragedatei nennt Zweck, Stand und Wartezeit");
  winky::schreibeAnfrage(b, 1000, "wartet", "apt \"x\"\n", "/dev/pts/1", 124);
  std::ifstream in2(b + "/1000.json");
  std::getline(in2, inhalt);
  PRUEFE(inhalt.find("\"zweck\":\"sudo\"") != std::string::npos &&
             inhalt.find("apt \\\"x\\\"") != std::string::npos,
         "sudo ist der Vorgabezweck, Anführungszeichen werden maskiert");
}

static void testVorlagen() {
  const std::string b = basis + "/vorlagen";
  mkdir(b.c_str(), 0755);
  mkdir((b + "/1000").c_str(), 0750);
  const auto datei = vorlagenDatei(5);
  schreibe(b + "/1000/vorlagen.bin", std::string(datei.begin(), datei.end()), 0640);
  winky::Vorlagen v;
  std::string f;
  PRUEFE(winky::ladeVorlagen(b, 1000, v, f) && v.anzahl() == 5, "gültige Vorlagen werden geladen");

  std::vector<float> m(winky::kVorlagenDim, 0.0f);
  m[0] = 1.0f;
  PRUEFE(std::fabs(winky::bewerte(m, v) - 1.0f / 3.0f) < 1e-5,
         "Wert ist Mittel der drei besten Vorlagen");

  PRUEFE(!winky::ladeVorlagen(b, 1001, v, f), "fehlender Benutzer liefert keine Vorlagen");

  chmod((b + "/1000/vorlagen.bin").c_str(), 0660);
  PRUEFE(!winky::ladeVorlagen(b, 1000, v, f), "gruppenbeschreibbare Datei wird abgelehnt");
  chmod((b + "/1000/vorlagen.bin").c_str(), 0640);
  chmod((b + "/1000").c_str(), 0770);
  PRUEFE(!winky::ladeVorlagen(b, 1000, v, f), "gruppenbeschreibbarer Ordner wird abgelehnt");
  chmod((b + "/1000").c_str(), 0750);
  chown((b + "/1000/vorlagen.bin").c_str(), 1000, 0);
  PRUEFE(!winky::ladeVorlagen(b, 1000, v, f), "Datei mit fremdem Besitzer wird abgelehnt");
  chown((b + "/1000/vorlagen.bin").c_str(), 0, 0);

  // Verknüpfung statt Ordner
  mkdir((b + "/echt").c_str(), 0750);
  rename((b + "/1000/vorlagen.bin").c_str(), (b + "/echt/vorlagen.bin").c_str());
  rmdir((b + "/1000").c_str());
  symlink((b + "/echt").c_str(), (b + "/1000").c_str());
  PRUEFE(!winky::ladeVorlagen(b, 1000, v, f), "Benutzerordner als Verknüpfung wird abgelehnt");
  unlink((b + "/1000").c_str());
  mkdir((b + "/1000").c_str(), 0750);
  symlink((b + "/echt/vorlagen.bin").c_str(), (b + "/1000/vorlagen.bin").c_str());
  PRUEFE(!winky::ladeVorlagen(b, 1000, v, f), "Vorlagendatei als Verknüpfung wird abgelehnt");

  auto pruefeRoh = [&](const std::vector<uint8_t>& roh) {
    winky::Vorlagen x;
    std::string g;
    return winky::pruefeVorlagen(roh, x, g);
  };
  std::string fremdesModell(64, 'a');
  PRUEFE(!pruefeRoh(vorlagenDatei(5, fremdesModell.c_str())), "fremdes Modell wird abgelehnt");
  PRUEFE(!pruefeRoh(vorlagenDatei(5, winky::kErkennungsModellSha, false)),
         "nicht normierte Vektoren werden abgelehnt");
  PRUEFE(!pruefeRoh(vorlagenDatei(5, winky::kErkennungsModellSha, true, true)),
         "NaN wird abgelehnt");
  PRUEFE(!pruefeRoh(vorlagenDatei(65)), "mehr als 64 Vorlagen werden abgelehnt");
  auto kurz = vorlagenDatei(5);
  kurz.pop_back();
  PRUEFE(!pruefeRoh(kurz), "abgeschnittene Datei wird abgelehnt");
}

static winky::Beobachtung beob(double t, float wert, float x = 100, float hell = 80,
                             float dunkel = 0) {
  winky::Beobachtung b;
  b.t_ms = t;
  b.gesicht = true;
  b.brauchbar = wert > -1;
  b.wert = wert;
  b.rahmen = {x, 100, x + 120, 240};
  b.hell_gesicht = hell;
  b.dunkel_gesicht = dunkel;
  return b;
}

static void testEntscheidung() {
  const winky::Regeln r{0.6f, 2, 1200, 2600, 15};
  {
    winky::Entscheidung e(r);
    PRUEFE(e.neu(beob(270, 0.9f)) == winky::Ergebnis::Offen, "ein Treffer reicht nicht");
    PRUEFE(e.neu(beob(400, 0.88f)) == winky::Ergebnis::Treffer, "zwei Treffer im Verlauf entsperren");
  }
  {
    winky::Entscheidung e(r);
    e.neu(beob(270, 0.9f, 100, 80, 75));
    PRUEFE(e.neu(beob(400, 0.9f, 100, 80, 75)) == winky::Ergebnis::Offen,
           "ohne Blinkmuster (Bildschirm) kein Treffer");
  }
  {
    winky::Entscheidung e(r);
    e.neu(beob(270, 0.9f, 100, 80, -1));
    PRUEFE(e.neu(beob(400, 0.9f)) == winky::Ergebnis::Offen,
           "Bild ohne dunkles Vorbild zählt nicht");
  }
  {
    winky::Entscheidung e(r);
    e.neu(beob(270, 0.9f, 100));
    PRUEFE(e.neu(beob(400, 0.9f, 400)) == winky::Ergebnis::Offen,
           "Treffer an anderer Stelle beginnen neuen Verlauf");
  }
  {
    winky::Entscheidung e(r);
    e.neu(beob(270, 0.9f, 100));
    e.neu(beob(400, 0.3f, 400));  // fremdes Gesicht dazwischen
    PRUEFE(e.neu(beob(530, 0.9f, 100)) == winky::Ergebnis::Offen,
           "fremdes Gesicht dazwischen setzt den Verlauf zurück");
  }
  {
    winky::Regeln ohne = r;
    ohne.blink_pruefung = false;  // Kamera mit dauerhaft leuchtendem Strahler
    winky::Entscheidung e(ohne);
    e.neu(beob(270, 0.9f, 100, 80, -1));
    PRUEFE(e.neu(beob(400, 0.9f, 100, 80, -1)) == winky::Ergebnis::Treffer,
           "ohne Blinkprüfung genügen zwei Treffer ohne dunkle Zwischenbilder");
  }
  {
    winky::Entscheidung e(r);
    PRUEFE(e.zeit(1199) == winky::Ergebnis::Offen, "vor der Frist noch offen");
    PRUEFE(e.zeit(1200) == winky::Ergebnis::KeinGesicht, "ohne Gesicht nach 1,2 s Schluss");
  }
  {
    winky::Entscheidung e(r);
    e.neu(beob(300, 0.4f));
    PRUEFE(e.zeit(2000) == winky::Ergebnis::Offen, "mit Gesicht weiter bis zur Gesamtfrist");
    PRUEFE(e.zeit(2600) == winky::Ergebnis::KeinTreffer && e.gesichtGesehen(),
           "fremdes Gesicht ergibt Kein Treffer (zählt als Fehlversuch)");
  }
  {
    winky::Entscheidung e(r);
    e.neu(beob(300, 0.59f));
    PRUEFE(e.neu(beob(430, 0.59f)) == winky::Ergebnis::Offen, "knapp unter der Schwelle kein Treffer");
  }
}

// Hand rechts neben dem Gesicht (Gesicht x..x+120, y 100..240)
static winky::HandBeobachtung zeichen(bool ja = true, float hx = 280, float hy = 170) {
  winky::HandBeobachtung h;
  h.zeichen = ja;
  h.x = hx;
  h.y = hy;
  return h;
}

static void testGeste() {
  const winky::Regeln r{0.6f, 2, 8000, 8000, 15};
  const winky::GestenRegeln g;
  {
    winky::GestenEntscheidung e(r, g);
    e.neu(beob(130, 0.9f), 1, zeichen(false));
    e.neu(beob(270, 0.9f), 1, zeichen(false));
    PRUEFE(e.gesichtErkannt(), "Gesicht wird erkannt");
    e.neu(beob(400, 0.9f), 1, zeichen());
    PRUEFE(e.neu(beob(530, 0.9f), 1, zeichen()) == winky::Ergebnis::Offen, "zwei Bilder ✌ reichen nicht");
    PRUEFE(e.neu(beob(660, 0.9f), 1, zeichen()) == winky::Ergebnis::Treffer,
           "Gesicht und drei Bilder ✌ in Folge bestätigen");
  }
  {
    winky::GestenEntscheidung e(r, g);
    winky::Ergebnis x = winky::Ergebnis::Offen;
    for (int i = 1; i <= 10; ++i) x = e.neu(beob(130.0 * i, 0.3f), 1, zeichen());
    PRUEFE(x == winky::Ergebnis::Offen && !e.gesichtErkannt(), "✌ mit fremdem Gesicht bestätigt nicht");
    PRUEFE(e.zeit(8000) == winky::Ergebnis::KeinTreffer, "fremdes Gesicht endet mit Kein Treffer");
  }
  {
    winky::GestenEntscheidung e(r, g);
    e.neu(beob(130, 0.9f), 1, zeichen(false));
    e.neu(beob(270, 0.9f), 1, zeichen(false));
    for (int i = 3; i <= 10; ++i) e.neu(beob(130.0 * i, 0.9f), 1, zeichen(false));
    PRUEFE(e.zeit(8000) == winky::Ergebnis::KeinTreffer && e.gesichtErkannt(),
           "Gesicht ohne ✌ bestätigt nicht (Kein Treffer, Gesicht erkannt)");
  }
  {
    winky::GestenEntscheidung e(r, g);
    e.neu(beob(130, 0.9f), 1, zeichen(false));
    e.neu(beob(270, 0.9f), 1, zeichen(false));
    e.neu(beob(400, 0.9f), 2, zeichen());
    e.neu(beob(530, 0.9f), 2, zeichen());
    PRUEFE(e.neu(beob(660, 0.9f), 2, zeichen()) == winky::Ergebnis::Offen,
           "mit zwei Gesichtern im Bild zählt das Zeichen nicht");
  }
  {
    winky::GestenEntscheidung e(r, g);
    e.neu(beob(130, 0.9f), 1, zeichen(false));
    e.neu(beob(270, 0.9f), 1, zeichen(false));
    e.neu(beob(400, 0.9f), 1, zeichen(true, 600, 170));
    e.neu(beob(530, 0.9f), 1, zeichen(true, 600, 170));
    PRUEFE(e.neu(beob(660, 0.9f), 1, zeichen(true, 600, 170)) == winky::Ergebnis::Offen,
           "✌ weit weg vom Gesicht (Hand einer anderen Person) zählt nicht");
  }
  {
    winky::GestenEntscheidung e(r, g);
    e.neu(beob(130, 0.9f), 1, zeichen(false));
    e.neu(beob(270, 0.9f), 1, zeichen(false));
    e.neu(beob(400, 0.9f), 1, zeichen());
    e.neu(beob(530, 0.9f), 1, zeichen());
    e.neu(beob(660, 0.9f), 1, zeichen(false));
    e.neu(beob(790, 0.9f), 1, zeichen());
    PRUEFE(e.neu(beob(920, 0.9f), 1, zeichen()) == winky::Ergebnis::Offen,
           "Unterbrechung setzt die Folge zurück");
  }
  {
    winky::GestenEntscheidung e(r, g);
    e.neu(beob(130, 0.9f, 100), 1, zeichen(false));
    e.neu(beob(270, 0.9f, 100), 1, zeichen(false));
    e.neu(beob(400, -2, 400), 1, zeichen(true, 580, 170));  // anderes Gesicht, Hand daneben
    e.neu(beob(530, -2, 400), 1, zeichen(true, 580, 170));
    PRUEFE(e.neu(beob(660, -2, 400), 1, zeichen(true, 580, 170)) == winky::Ergebnis::Offen,
           "✌ neben einem anderen Gesicht als dem erkannten zählt nicht");
  }
  {
    winky::GestenEntscheidung e(r, g);
    e.neu(beob(130, -2), 1, zeichen());  // Hand verdeckt das Gesicht teilweise
    e.neu(beob(270, -2), 1, zeichen());
    e.neu(beob(400, 0.9f), 1, zeichen());
    PRUEFE(e.neu(beob(530, 0.9f), 1, zeichen()) == winky::Ergebnis::Treffer,
           "✌ zuerst, Gesicht danach erkannt: bestätigt, sobald beides zusammenkommt");
  }
  {
    winky::GestenEntscheidung e(r, g);
    PRUEFE(e.zeit(7999) == winky::Ergebnis::Offen && e.zeit(8000) == winky::Ergebnis::KeinGesicht,
           "ohne Gesicht offen bis zur sudo-Frist, dann Kein Gesicht");
  }
}

static void testSudoSperre() {
  const std::string b = basis + "/sperre-sudo";
  mkdir(b.c_str(), 0700);
  const long t = 1790000000;
  PRUEFE(winky::leseSudoOffen(b, 1000, t) == 0, "ohne Datei keine offenen sudo-Anfragen");
  winky::schreibeSudoOffen(b, 1000, 3, t);
  PRUEFE(winky::leseSudoOffen(b, 1000, t + 10) == 3, "offene sudo-Anfragen werden gezählt");
  PRUEFE(winky::leseSudoOffen(b, 1000, t + winky::kSudoPause_s + 1) == 0, "nach der Pause zählen sie nicht mehr");
  PRUEFE(winky::leseSudoOffen(b, 1000, t - 5) == 0, "Zeit in der Zukunft zählt nicht (Uhr verstellt)");
  winky::erhoeheSudoOffen(b, 1000, t + 20);
  PRUEFE(winky::leseSudoOffen(b, 1000, t + 20) == 4, "Erhöhen liest den aktuellen Stand neu");
  winky::schreibeSudoOffen(b, 1000, 0, t);
  PRUEFE(winky::leseSudoOffen(b, 1000, t) == 0, "Zurücksetzen löscht den Zähler");
  const int erste = winky::sudoSperren(b, 1000);
  PRUEFE(erste >= 0 && !winky::sudoAbbruchGesetzt(b, 1000), "erste sudo-Prüfung bekommt die Sperre");
  PRUEFE(winky::sudoSperren(b, 1000) < 0, "zweite gleichzeitige Prüfung wird abgelehnt");
  PRUEFE(winky::sudoAbbruchGesetzt(b, 1000), "und die laufende bekommt die Abbruchmarke");
  PRUEFE(winky::sudoSperren(b, 1001) >= 0, "anderer Benutzer ist nicht betroffen");
  winky::sudoEntsperren(b, 1000, erste);
  const int dritte = winky::sudoSperren(b, 1000);
  PRUEFE(dritte >= 0 && !winky::sudoAbbruchGesetzt(b, 1000), "nach dem Ende ist wieder Platz, Marke weg");
  winky::sudoEntsperren(b, 1000, dritte);
}

static void testSperre() {
  const std::string b = basis + "/sperre";
  mkdir(b.c_str(), 0700);
  PRUEFE(winky::leseFehlversuche(b, 1000) == 0, "ohne Datei null Fehlversuche");
  winky::schreibeFehlversuche(b, 1000, 3);
  PRUEFE(winky::leseFehlversuche(b, 1000) == 3, "Fehlversuche werden gespeichert");
  winky::schreibeFehlversuche(b, 1000, 0);
  PRUEFE(winky::leseFehlversuche(b, 1000) == 0, "Zurücksetzen löscht den Zähler");
  const std::string ziel = basis + "/opfer";
  schreibe(ziel, "unverändert");
  symlink(ziel.c_str(), (b + "/1001").c_str());
  winky::schreibeFehlversuche(b, 1001, 2);
  std::ifstream in(ziel);
  std::string inhalt;
  std::getline(in, inhalt);
  PRUEFE(inhalt == "unverändert", "Verknüpfung im Sperrordner wird nicht verfolgt");
}

int main() {
  char vorlage[] = "/tmp/winky-test.XXXXXX";
  basis = mkdtemp(vorlage);
  if (geteuid() != 0) {
    std::printf("Tests brauchen (Namensraum-)root für Besitzerprüfungen\n");
    return 77;
  }
  testKonfig();
  testVorlagen();
  testEntscheidung();
  testSperre();
  testGeste();
  testSudoSperre();
  testAnfrage();
  std::printf("\n%d Fehler\n", fehler);
  return fehler ? 1 : 0;
}
