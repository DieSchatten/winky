/* winky-polkit-pruefung BENUTZER: von 50-winky-keepassxc.rules per polkit.spawn() als polkitd
 * gestartet; fragt den Prüfdienst über /run/winky-polkit.sock nach Gesicht (ggf. mit ✌).
 * Rückgabe 0 = erkannt (ohne Passwort), alles andere: Polkit fragt nach dem Passwort.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <poll.h>
#include <pwd.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#include "protokoll.h"

/* Unter dem 10-s-Limit von polkit.spawn(), über der längsten Prüfung (sudo_ms bis 9,5 s) */
#define FRIST_MS 9800

static long ms_seit(const struct timespec *start) {
  struct timespec jetzt;
  clock_gettime(CLOCK_MONOTONIC, &jetzt);
  return (jetzt.tv_sec - start->tv_sec) * 1000L + (jetzt.tv_nsec - start->tv_nsec) / 1000000L;
}

int main(int argc, char **argv) {
  if (argc != 2 || !argv[1][0] || strlen(argv[1]) > 64) return 2;
  struct passwd pw, *pwp = NULL;
  char puffer[4096];
  if (getpwnam_r(argv[1], &pw, puffer, sizeof(puffer), &pwp) != 0 || !pwp || pw.pw_uid == 0)
    return 2;

  struct timespec start;
  clock_gettime(CLOCK_MONOTONIC, &start);
  const int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  if (fd < 0) return 3;
  struct sockaddr_un sa;
  memset(&sa, 0, sizeof(sa));
  sa.sun_family = AF_UNIX;
  strncpy(sa.sun_path, WINKY_POLKIT_SOCKET, sizeof(sa.sun_path) - 1);
  if (connect(fd, (struct sockaddr *)&sa, sizeof(sa)) != 0) return 3;
  struct ucred cred;
  socklen_t len = sizeof(cred);
  if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &len) != 0 || cred.uid != 0) return 3;
  struct winky_anfrage q = {WINKY_MAGIC, WINKY_OP_KEEPASSXC, (uint32_t)pw.pw_uid, 0};
  if (send(fd, &q, sizeof(q), MSG_NOSIGNAL) != (ssize_t)sizeof(q)) return 3;
  for (;;) {
    const long rest = FRIST_MS - ms_seit(&start);
    if (rest <= 0) return 4;
    struct pollfd p = {fd, POLLIN, 0};
    const int r = poll(&p, 1, (int)rest);
    if (r < 0 && errno == EINTR) continue;
    if (r <= 0) return 4;
    struct winky_antwort a;
    const ssize_t n = recv(fd, &a, sizeof(a), MSG_DONTWAIT);
    if (n < 0 && (errno == EAGAIN || errno == EINTR)) continue;
    if (n != (ssize_t)sizeof(a) || a.magic != WINKY_MAGIC) return 3;
    return a.status == WINKY_TREFFER ? 0 : 1;
  }
}
