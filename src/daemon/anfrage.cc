#include "anfrage.h"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstdio>

namespace winky {

std::string saeubern(const std::string& s, size_t max) {
  std::string o;
  for (unsigned char c : s) {
    if (o.size() >= max) break;
    if (c >= 0x20 && c != 0x7f) o += static_cast<char>(c);
    else if (c == '\t' || c == '\n') o += ' ';
  }
  // abgeschnittenes UTF-8-Zeichen am Ende entfernen
  while (!o.empty() && (static_cast<unsigned char>(o.back()) & 0xC0) == 0x80) o.pop_back();
  if (!o.empty() && (static_cast<unsigned char>(o.back()) & 0xC0) == 0xC0) o.pop_back();
  return o;
}

namespace {

std::string json(const std::string& s) {
  std::string o = "\"";
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') {
      o += '\\';
      o += static_cast<char>(c);
    } else if (c >= 0x20) {
      o += static_cast<char>(c);
    }
  }
  return o + "\"";
}

}  // namespace

void schreibeAnfrage(const std::string& basis, uid_t uid, const std::string& stand,
                     const std::string& befehl, const std::string& terminal, long zeit,
                     const std::string& zweck) {
  const int dir = ::open(basis.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (dir < 0) return;
  const std::string name = std::to_string(uid) + ".json";
  const std::string tmp = "." + name + ".neu";
  const int fd = ::openat(dir, tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0644);
  if (fd < 0) {
    ::close(dir);
    return;
  }
  ::fchmod(fd, 0644);
  const std::string inhalt = "{\"zeit\":" + std::to_string(zeit) + ",\"stand\":" + json(stand) +
                             ",\"befehl\":" + json(befehl) + ",\"terminal\":" + json(terminal) +
                             ",\"zweck\":" + json(zweck) + "}\n";
  const bool ok = ::write(fd, inhalt.data(), inhalt.size()) == static_cast<ssize_t>(inhalt.size());
  ::close(fd);
  if (ok) ::renameat(dir, tmp.c_str(), dir, name.c_str());
  else ::unlinkat(dir, tmp.c_str(), 0);
  ::close(dir);
}

}  // namespace winky
