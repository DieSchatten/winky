# Winky security

**English** · [Deutsch](SICHERHEIT.md)

Winky is a **convenience** for the lock screen, not a replacement for a good password and not
disk encryption. This page honestly describes what Winky protects against, what it does not
protect against, and which risks lie in its use and in the technology itself.

As of version 0.15.0. Winky was developed by one person with AI assistance and has **not been
independently reviewed**. Recognition was measured on one laptop with a Windows Hello
camera with the owner and one other person, and tried on a Microsoft Surface Laptop 4.

## In short

- Your face only opens the **lock screen of a running session**. For su, SSH and the
  console, the password always applies; after switching on the computer and in graphical
  administrator dialogs too, unless you turn these on separately.
- **sudo in the terminal** can optionally be confirmed with your face **and** the ✌ sign.
  This is off until an administrator turns it on.
- **The password always works.** If Winky does not recognize you, the usual prompt appears
  after three seconds at most (lock screen) or after the time set for the ✌ (8 to 30
  seconds, sudo).
- The security level roughly corresponds to **Windows Hello without enhanced
  anti-spoofing**: photos on screens fail. Winky does not reliably stop a deliberately made
  infrared printout or a mask.

## What Winky protects against and what it does not

| Situation | What happens | Assessment |
|---|---|---|
| Someone sits down at your locked computer | Their face does not match; after three seconds the password field appears. | protected, as long as the person does not look very similar to you |
| Photo or video of you on a phone or screen | Screens are black in the infrared image. In the measurement, a phone photo was not even detected as a face. | protected |
| A printout of your face that is visible in infrared, or a mask | Not tested. Winky has no real liveness detection. | **not reliably protected** |
| Twin or very similar sibling | No face recognition system tells them apart reliably. | **not protected** |
| Someone holds the computer up to your face, or you are asleep | Winky does not check whether you agree or have your eyes open. | **not protected** by default; protected with “Unlock only with ✌” (sudo always needs the ✌) |
| Computer is stolen while switched off | Winky plays no role. Without an encrypted disk, the data is open. | a matter for disk encryption |
| Computer is stolen while locked but switched on | The thief needs your face (or see printout/mask). | as above |
| Remote access (SSH) | Winky is not involved; the password or SSH key applies. | unchanged |
| Other users on the same computer | Everyone only has their own face; recording a face only works with your own password. | protected |
| Malware running under your account | It can trigger sudo requests, but gets nothing without your ✌. Details below. | largely protected, with a residual risk |

## Risks in use

This is in your own hands:

1. **Unlocked computer.** Winky only protects what is locked. Get used to Super+L and set up
   automatic locking.
2. **Similar people in your household.** Do the check with a second person, ideally with
   the most similar family member. If the result is close, make Winky stricter or use only
   the password. Twins should not use Winky.
3. **Lowering the strictness.** A lower threshold makes Winky more convenient, but other
   faces get through more easily. In the measurement, the person themselves without glasses
   scored above 0.69, mostly between 0.84 and 0.96; another person reached at most 0.24,
   far below the default of 0.65. That is one sample, not statistics. This makes the check with a second person (item 2) all the more important:
   it shows whether the margin is enough for your household.
4. **Reflexive ✌.** The sudo confirmation only protects you if you show ✌ exclusively for
   commands you have just typed yourself. If a Winky message appears that you do not
   expect: no ✌, just ignore it.
5. **Forced unlocking.** Anyone who can force you to look into the camera opens the lock
   screen. Against someone simply holding the computer up to your face, turn on “Unlock
   only with ✌”. Against real coercion, nothing helps but turning Winky off (Pause or
   uninstall).
6. **KeePassXC with your face.** By default, Winky requires your face **and** ✌ for
   KeePassXC, as with sudo. If you turn off the ✌, your face alone opens the password
   database: anyone who clicks “Unlock” on your unlocked computer while you are sitting in
   front of it would then get in without any action from you. After every restart of
   KeePassXC, the master password applies again. Only works with KeePassXC 2.8 or later.
7. **Backups.** The face data is stored under `/var/lib/winky`. If a backup program backs up
   the system directory (e.g. Timeshift), the face data ends up in the backup too; sealed in
   the TPM chip (see 12), only in encrypted form.
8. **Outdated version.** Winky ships its own recognition runtime (ONNX Runtime). Its bug
   fixes only arrive with a new Winky version, not through the normal Ubuntu updates.
9. **Login after startup with your face** (off by default). Then anyone who can fool your
   face gets in after a restart too, not just into the locked session. Your login keyring
   stays locked, because only the password opens it. Without disk encryption, the extra risk
   is small: whoever has the computer can read the disk anyway.
10. **Keyring password in the TPM chip** (experimental, off by default). Your login password
    is stored sealed and can be recovered on this computer. The TPM chip only checks the
    Secure Boot state (PCR 7), not which system is running: someone with physical access can
    start the computer from a USB stick with Ubuntu or a related Linux and unseal it there,
    and without Secure Boot it is even easier. That reveals the password itself, which many
    people also use elsewhere. A BIOS password that blocks starting from USB helps. Winky only
    hands it out right after a recognized face login, checks it against `/etc/shadow` first
    and discards it after a password change.
11. **Administrator dialogs with ✌.** Works like sudo with ✌: a harmful program running as
    you can open such a dialog, and a ✌ at the wrong moment approves it, with full
    administrator rights. The dialog itself shows what is requested; only show ✌ for dialogs
    you started yourself. Background permission checks never reach Winky.
12. **Face data in the TPM chip** (optional, off by default). On the disk, the face data is
    then stored only encrypted (`systemd-creds`, host key and TPM chip, PCR 7). This helps if
    the disk is read in another computer or from Windows on the same computer. It does not
    help against a USB stick with Ubuntu or a related Linux started on this computer (see
    10); only disk encryption or a BIOS password that blocks starting from USB helps. After a
    BIOS or firmware update or a change to Secure Boot, the data can no longer be unsealed:
    face unlock then stops until you record your face again, the password still works. When
    it is turned on, the previous unencrypted file is deleted; on SSDs, remnants cannot be
    ruled out.

## Risks in the technology itself

These cannot be avoided by how you use Winky:

1. **No liveness detection.** Winky only uses the infrared camera. Screens and phone photos
   are invisible there. If the infrared emitter blinks, the light and dark pattern of the
   images has to match; this is a plausibility check against injected images, not liveness
   detection. A printout that is visible in infrared, or a mask, has not been tested and
   might get through.
2. **Recognition errors are possible.** Face detection (YuNet) and face comparison (SFace)
   are small models. How often a stranger's face gets through is not statistically proven,
   only measured with a few people.
3. **New code in the login.** The PAM module `pam_winky.so` is listed in `common-auth` and
   therefore runs in every login program, as root. That is why it is kept small (only libc
   and libpam), first checks a fixed list of allowed services (lock screen `gdm-password`,
   `sudo`) and answers “not responsible” to anything unexpected; then the normal password
   prompt follows. A programming error in this module could still disrupt the login or, in
   the worst case, be exploitable.
4. **The verification service decides.** Camera, recognition models and decision run in the
   `winky-matcher` service as its own user `_winky`, without root rights, without network
   and without access to personal folders (systemd sandbox, `systemd-analyze security`:
   1.0). Anyone who takes over this service could report “recognized” and thereby open the
   lock screen and, if enabled, confirm sudo. It can only be attacked through the camera
   images.
5. **Fake camera.** Anyone who opens the computer and, instead of the built-in camera,
   connects a device that plays back recorded infrared images of your face can unlock.
   Winky uses the fixed connection of the built-in camera; simply plugging in a USB stick is
   not enough for this.
6. **sudo with ✌ and malware.** A program running under your account can start sudo in its
   own invisible terminal. Then the camera turns on and a message with the command appears.
   Without your ✌ nothing happens. In addition, the following safeguards are in place:
   - Two requests at the same time are both cancelled. So malware cannot piggyback on your
     own confirmation.
   - After three unconfirmed requests, only the password works for ten minutes.
   - The ✌ must be visible next to the recognized face, with exactly one face in the
     picture.

   A residual risk remains: if malware starts its request right after your own, while your
   hand is still raised, your ✌ could apply to it. However, the camera first needs almost a
   second to start, and the message shows the other command.

   For comparison: against malware under your account, the sudo password is weak too. For
   example, it can redirect `sudo` in your shell configuration and capture the password.
   With ✌ there is no password to steal, and the message shows the command that is actually
   run.
7. **Notices can be faked.** Any program can show windows and desktop notifications,
   including a fake Winky notice window with a harmless command. The real one still appears
   as well. When in doubt: no ✌.
8. **Visibility of sudo commands.** The command of a running sudo request is stored in
   `/run/winky/anfrage/<uid>.json` for the desktop notice, and in the system log. Other
   users of the same computer can read it. They can see running sudo commands in the process
   list anyway, and sudo also logs commands itself.
9. **Biometric data.** No images are stored, only feature vectors (30 series of 128 values
   each per person). They are readable only by the system, under `/var/lib/winky/<uid>/`
   (root:_winky 0640). On an unencrypted disk, anyone with physical access can read them;
   sealing them in the TPM chip narrows this, but does not rule it out (Risks in use, 12).
   According to research, roughly face-like images can be reconstructed from such vectors;
   they are not directly usable as a substitute for your real face in front of the camera.
10. **Camera on at every attempt.** At every unlock attempt and every sudo request, the
    infrared camera turns on for a few seconds. Images are only analyzed in memory, never
    stored. During setup, the app shows the camera image. Independently of Winky, every
    program in your account can normally switch on the cameras; under Advanced, the infrared
    camera can be reserved for Winky (a udev rule takes away the logged-in user's access).
11. **Third-party models.** The recognition models come from third-party sources (OpenCV
    Zoo, Google MediaPipe). They are pinned by checksum, but for their origin you have to
    trust these sources.
## Built-in safeguards

- **Allow list in the PAM module:** only the lock screen (recognized by the GDM marker for
  re-authentication) and, if turned on, sudo. No remote access (`PAM_RHOST`), not for
  root, emergency off switch `/etc/winky/disabled`, lid closed at an external monitor =
  password right away.
- **Fixed time limits:** 3 seconds on the lock screen, at most 30 seconds for sudo, at most
  9 seconds over Polkit. No `fork`, no
  dependency on files in the home directory.
- **Password instead of ✌:** the first key turns the camera off; the password is shown only
  as stars and handed to the normal password check. The terminal is
  restored on every path, including Ctrl+C.
- **Isolated verification service:** starts only when needed, checks the caller via the
  socket and logind (local, active, graphical session on seat0).
- **Root-owned data:** configuration, templates, switches and approvals are opened without
  following links and checked for owner, permissions and size.
- **Infrared camera only for Winky (optional):** A udev rule removes the logged-in user's
  access to exactly this camera and gives it to the verification service. Refused if another
  node on the same connection delivers color images; on failure, the previous state stays.
  The app checks whether the protection is in effect. Uninstalling gives the camera back.
- **Face data in the TPM chip (optional):** sealed for all users or for none; if it fails for
  one, the previous state stays. At startup, a small sandboxed service unseals the data into
  memory (`/run/winky/vorlagen`); the verification service then reads only this copy and
  never falls back to the disk. If unsealing fails, the app asks for a new recording.
- **Adding to your face only with you in the picture:** An addition is only saved if Winky
  recognizes you in the recording at least three times at the set threshold. Images more
  than 0.20 below it are discarded; if someone else sits in front of the camera in between,
  they don't end up in your data. At most three named additions of up to 11 images each; the
  original recording always stays.
- **Failed attempts:** After five faces that were detected but did not match, face unlock
  stays blocked until the next login with password. sudo: ten minutes after three
  unconfirmed requests.
- **Step-by-step activation:** It can only be turned on after a successful test, and is
  blocked if the check with a second person was too close. sudo with ✌ additionally
  requires the administrator password and, for each person, their own passed ✌ test.
- **Rollback:** turning off via `pam-auth-update`; `common-auth` is backed up each time
  before Winky is turned on. Uninstalling removes everything, including the face data.
- **Tests:** components, PAM with the real libpam, the app with a mock, and the whole
  package in throwaway systems. See the [developer notes (German)](ENTWICKLUNG.md).

## Recommendations

1. Encrypt your disk. Winky only protects the running session.
2. Do the check with a second person, with the most similar person in your household.
3. Do not lower the strictness below the default.
4. Only turn on sudo with ✌ if you take the messages seriously.
5. Lock the screen when you walk away, and set a short automatic lock time (Winky:
   Unlocks → Lock automatically).
6. Install Winky updates.

## Privacy

- No network access, no telemetry. The verification service runs without network.
- Stored per person: feature vectors, time and result of the tests (for the app) and the
  passed ✌ test. No images.
- For each attempt, the system log contains the time, result, similarity score and, for
  sudo, the command line.
- Uninstalling deletes the face data of all users.

## Use at your own risk

You use Winky at your own risk. This page describes the known limitations to the best of
current knowledge; such a list is never complete.

## Reporting bugs

Winky is provided as is; maintenance and fixes are not promised. Bugs, including security
problems, are welcome as an issue on the
[project page](https://github.com/DieSchatten/winky/issues), with version, distribution and
a description of how to reproduce the bug. There is no confidential reporting channel.
Under the MIT license, anyone may develop Winky further themselves.
