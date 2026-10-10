#include "sperre.h"

#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>

namespace winky {

int leseFehlversuche(const std::string& basis, uid_t uid) {
  const int dir = ::open(basis.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (dir < 0) return 0;
  const std::string name = std::to_string(uid);
  const int fd = ::openat(dir, name.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  ::close(dir);
  if (fd < 0) return 0;
  char buf[16] = {0};
  const ssize_t n = ::read(fd, buf, sizeof(buf) - 1);
  ::close(fd);
  if (n <= 0) return 0;
  const long v = std::strtol(buf, nullptr, 10);
  return (v < 0 || v > 1000) ? 0 : static_cast<int>(v);
}

void schreibeFehlversuche(const std::string& basis, uid_t uid, int anzahl) {
  const int dir = ::open(basis.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (dir < 0) return;
  const std::string name = std::to_string(uid);
  if (anzahl <= 0) {
    ::unlinkat(dir, name.c_str(), 0);
    ::close(dir);
    return;
  }
  const int fd =
      ::openat(dir, name.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0600);
  ::close(dir);
  if (fd < 0) return;
  char buf[16];
  const int len = std::snprintf(buf, sizeof(buf), "%d\n", anzahl);
  if (::write(fd, buf, static_cast<size_t>(len)) != len) {
    // nichts zu tun: im Zweifel zählt der nächste Versuch neu
  }
  ::close(fd);
}

namespace {

int ordnerOeffnen(const std::string& basis) {
  return ::open(basis.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
}

}  // namespace

int leseSudoOffen(const std::string& basis, uid_t uid, long jetzt) {
  const int dir = ordnerOeffnen(basis);
  if (dir < 0) return 0;
  const std::string name = "sudo-" + std::to_string(uid);
  const int fd = ::openat(dir, name.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  ::close(dir);
  if (fd < 0) return 0;
  char buf[48] = {0};
  const ssize_t n = ::read(fd, buf, sizeof(buf) - 1);
  ::close(fd);
  if (n <= 0) return 0;
  long anzahl = 0, zeit = 0;
  if (std::sscanf(buf, "%ld %ld", &anzahl, &zeit) != 2 || anzahl < 0 || anzahl > 1000) return 0;
  if (jetzt - zeit > kSudoPause_s || jetzt < zeit) return 0;
  return static_cast<int>(anzahl);
}

void schreibeSudoOffen(const std::string& basis, uid_t uid, int anzahl, long jetzt) {
  const int dir = ordnerOeffnen(basis);
  if (dir < 0) return;
  const std::string name = "sudo-" + std::to_string(uid);
  if (anzahl <= 0) {
    ::unlinkat(dir, name.c_str(), 0);
    ::close(dir);
    return;
  }
  const int fd =
      ::openat(dir, name.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0600);
  ::close(dir);
  if (fd < 0) return;
  char buf[48];
  const int len = std::snprintf(buf, sizeof(buf), "%d %ld\n", anzahl, jetzt);
  if (::write(fd, buf, static_cast<size_t>(len)) != len) {
    // im Zweifel zählt der nächste Versuch neu
  }
  ::close(fd);
}

void erhoeheSudoOffen(const std::string& basis, uid_t uid, long jetzt) {
  schreibeSudoOffen(basis, uid, leseSudoOffen(basis, uid, jetzt) + 1, jetzt);
}

int sudoSperren(const std::string& basis, uid_t uid) {
  const int dir = ordnerOeffnen(basis);
  if (dir < 0) return -1;
  const std::string name = "sudo-" + std::to_string(uid) + ".sperre";
  const int fd = ::openat(dir, name.c_str(), O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (fd < 0) {
    ::close(dir);
    return -1;
  }
  const std::string marke = "sudo-" + std::to_string(uid) + ".abbruch";
  if (::flock(fd, LOCK_EX | LOCK_NB) != 0) {
    const int m = ::openat(dir, marke.c_str(), O_WRONLY | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (m >= 0) ::close(m);
    ::close(fd);
    ::close(dir);
    return -1;
  }
  ::unlinkat(dir, marke.c_str(), 0);  // alte Marke einer beendeten Prüfung
  ::close(dir);
  return fd;
}

bool sudoAbbruchGesetzt(const std::string& basis, uid_t uid) {
  const int dir = ordnerOeffnen(basis);
  if (dir < 0) return true;  // im Zweifel abbrechen
  struct stat st {};
  const std::string marke = "sudo-" + std::to_string(uid) + ".abbruch";
  const bool da = ::fstatat(dir, marke.c_str(), &st, AT_SYMLINK_NOFOLLOW) == 0;
  ::close(dir);
  return da;
}

void sudoEntsperren(const std::string& basis, uid_t uid, int fd) {
  const int dir = ordnerOeffnen(basis);
  if (dir >= 0) {
    const std::string marke = "sudo-" + std::to_string(uid) + ".abbruch";
    ::unlinkat(dir, marke.c_str(), 0);
    ::close(dir);
  }
  if (fd >= 0) ::close(fd);  // gibt die Sperre frei
}

void markiereAnmeldung(const std::string& basis, uid_t uid) {
  const int dir = ::open(basis.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (dir < 0) return;
  const std::string name = "anmeldung-" + std::to_string(uid);
  const int fd =
      ::openat(dir, name.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0600);
  ::close(dir);
  if (fd >= 0) ::close(fd);
}

}  // namespace winky
