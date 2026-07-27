# AlphaX POS Bridge — Setup Kit v15.5.1

The bridge is the small program that connects the AlphaX register to
your shop's hardware: receipt printers, kitchen (KOT) printers, cash
drawers, scales, and customer displays. **One bridge per shop** — it
fans print jobs out to every printer on your network.

Install it on the computer that stays on during trading hours (the
till PC or any mini-PC on the shop network).

---

## Windows — double-click `Install-AlphaX-Bridge.bat`

The installer finds or installs Python automatically, sets the bridge
to start with Windows (system-tray icon), opens the firewall for the
registers, and launches the printer setup wizard. Re-running it later
upgrades in place. Remove with `Uninstall-AlphaX-Bridge.bat`.

If other devices can't reach the bridge afterwards, right-click the
installer once and choose **Run as administrator** (firewall rule).

## macOS — double-click `Install AlphaX Bridge.command`

Uses the Mac's built-in Python (it will offer the one-time Apple
Command Line Tools install if needed — accept, then run the installer
again). Starts at login, wizard opens at the end. Remove with
`Uninstall AlphaX Bridge.command`.

First run: if macOS blocks the file, right-click → Open → Open.

## Linux / mini-PC boxes — `./install-linux.sh`

Installs per-user with a systemd service that survives reboots. Ideal
for a fanless mini-PC living behind the counter.

---

## iPhone / iPad / Android — you don't install the bridge there

This is by design, not a gap. The bridge holds always-on TCP
connections to LAN printers — phones and tablets aggressively suspend
background apps, and iOS does not permit this class of daemon at all.
**Mobile devices never need the bridge locally**: a phone or tablet
running the AlphaX register simply talks to the shop's one bridge over
Wi-Fi, and every printer works from every device.

So the setup for a tablet-only shop is: put the bridge on one mini-PC
(≈200 SAR Android-box-sized machines running Linux work perfectly —
use `install-linux.sh`), and all the iPads/Android tablets print
through it. If a true native Android bridge app ever becomes a
customer requirement, that is a separate product build — tell us and
we'll scope it.

---

## After installing

1. The wizard asks for your printers: give each one a **device name**
   (e.g. `receipt-1`, `kitchen-1`, `juice-1`) and its LAN IP.
2. In the desk, open **AlphaX POS Print Station** and set each
   station's *Bridge Device Name* to match.
3. The register's hardware pill turns green — receipts and KOTs now
   print, station by station, even if the internet drops.

Bridge API: http://localhost:8720 · Support: erpsupport@irsaa.com
