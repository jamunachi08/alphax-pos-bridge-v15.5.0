"""
AlphaX POS Bridge — first-run setup wizard.

Three-screen Tk wizard:

  1. Welcome + port selection.
  2. Auth token generation / paste.
  3. Hardware discovery — show what's plugged in, let the user
     name each device, then write a config.yaml that maps them.
  4. Test + finish.

Pure stdlib (Tkinter is shipped with every Python install on Win/Mac
and is in `python3-tk` on Linux). No external GUI framework needed.

Run via:
    python -m alphax_bridge.wizard

Or auto-launched on first install by the platform installers
(Inno Setup post-install on Windows, postinstall script on macOS,
postinst on Debian).
"""
from __future__ import annotations

import os
import secrets
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
from pathlib import Path

CONFIG_DIR = Path.home() / ".alphax-bridge"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
TOKEN_FILE = CONFIG_DIR / "auth.token"

ALPHAX_GREEN = "#0F6E56"
ALPHAX_BG    = "#fafafa"
ALPHAX_FG    = "#1a1a1a"
ALPHAX_MUTED = "#6b6a65"


class SetupWizard(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("AlphaX POS Bridge — Setup")
        self.configure(bg=ALPHAX_BG)
        self.geometry("640x480")
        self.resizable(False, False)

        # State carried across screens
        self.port_var = tk.StringVar(value="8420")
        self.token_var = tk.StringVar(value=secrets.token_urlsafe(24))
        self.discovered = []          # list of dicts from discover_all()
        self.device_names = {}        # discovered_id -> user-given name

        # Header
        header = tk.Frame(self, bg=ALPHAX_GREEN, height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="AlphaX POS Bridge",
            font=("", 18, "bold"),
            fg="white", bg=ALPHAX_GREEN,
        ).pack(pady=(16, 0))
        self.subtitle = tk.Label(
            header, text="One-time setup",
            font=("", 11),
            fg="white", bg=ALPHAX_GREEN,
        )
        self.subtitle.pack()

        # Body
        self.body = tk.Frame(self, bg=ALPHAX_BG)
        self.body.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)

        # Footer
        footer = tk.Frame(self, bg=ALPHAX_BG)
        footer.pack(fill=tk.X, padx=30, pady=(0, 20))
        self.back_btn = tk.Button(footer, text="← Back", command=self.go_back,
                                   bd=0, padx=12, pady=8,
                                   bg=ALPHAX_BG, fg=ALPHAX_MUTED)
        self.back_btn.pack(side=tk.LEFT)
        self.next_btn = tk.Button(footer, text="Continue →",
                                   command=self.go_next,
                                   bd=0, padx=18, pady=8,
                                   bg=ALPHAX_GREEN, fg="white",
                                   font=("", 10, "bold"),
                                   cursor="hand2")
        self.next_btn.pack(side=tk.RIGHT)

        self.screen_idx = 0
        self.screens = [
            ("Welcome", self.screen_welcome),
            ("Authentication", self.screen_auth),
            ("Hardware", self.screen_hardware),
            ("Done", self.screen_done),
        ]
        self.show_screen()

    # ---- navigation ----------------------------------------------------

    def show_screen(self):
        for w in self.body.winfo_children(): w.destroy()
        title, fn = self.screens[self.screen_idx]
        self.subtitle.config(text=f"{title} — step {self.screen_idx + 1} of {len(self.screens)}")
        fn(self.body)
        self.back_btn.config(state=tk.NORMAL if self.screen_idx > 0 else tk.DISABLED)
        if self.screen_idx == len(self.screens) - 1:
            self.next_btn.config(text="Finish")
        else:
            self.next_btn.config(text="Continue →")

    def go_next(self):
        # Per-screen validation before advancing
        if self.screen_idx == 0:
            try:
                p = int(self.port_var.get())
                if not (1024 <= p <= 65535): raise ValueError
            except ValueError:
                messagebox.showerror("Invalid port",
                    "Port must be a number between 1024 and 65535.")
                return
        elif self.screen_idx == 1:
            if not self.token_var.get().strip():
                messagebox.showerror("Missing token",
                    "Please generate or paste an auth token.")
                return
        elif self.screen_idx == 2:
            self.write_config()

        if self.screen_idx == len(self.screens) - 1:
            self.destroy()
            return
        self.screen_idx += 1
        self.show_screen()

    def go_back(self):
        if self.screen_idx > 0:
            self.screen_idx -= 1
            self.show_screen()

    # ---- screens -------------------------------------------------------

    def screen_welcome(self, parent):
        tk.Label(parent,
            text="Welcome to AlphaX POS Bridge.",
            font=("", 16, "bold"), bg=ALPHAX_BG, fg=ALPHAX_FG,
        ).pack(anchor="w", pady=(0, 10))
        tk.Label(parent,
            text=("This wizard will get the bridge connected to your "
                  "printer, drawer, and other hardware.\n\n"
                  "It takes about 2 minutes."),
            wraplength=560, justify="left",
            font=("", 11), bg=ALPHAX_BG, fg=ALPHAX_FG,
        ).pack(anchor="w", pady=(0, 20))

        tk.Label(parent, text="Port the bridge listens on:",
                 font=("", 11), bg=ALPHAX_BG, fg=ALPHAX_FG).pack(anchor="w")
        tk.Entry(parent, textvariable=self.port_var, width=10,
                 font=("", 12)).pack(anchor="w", pady=(2, 8))
        tk.Label(parent,
            text=("8420 is the default. Only change this if you know "
                  "another program is using it."),
            font=("", 9), bg=ALPHAX_BG, fg=ALPHAX_MUTED,
        ).pack(anchor="w")

    def screen_auth(self, parent):
        tk.Label(parent,
            text="Authentication token",
            font=("", 16, "bold"), bg=ALPHAX_BG, fg=ALPHAX_FG,
        ).pack(anchor="w", pady=(0, 10))
        tk.Label(parent,
            text=("The cashier UI sends this token with every request, "
                  "so only your authorized terminal can use the bridge. "
                  "We've generated one for you."),
            wraplength=560, justify="left",
            font=("", 11), bg=ALPHAX_BG, fg=ALPHAX_FG,
        ).pack(anchor="w", pady=(0, 20))

        tk.Entry(parent, textvariable=self.token_var, width=60,
                 font=("Courier", 11), state="readonly").pack(anchor="w", pady=(0, 6))

        btnrow = tk.Frame(parent, bg=ALPHAX_BG)
        btnrow.pack(anchor="w")
        tk.Button(btnrow, text="Regenerate", command=self._regen_token,
                  bd=1, padx=10, pady=4).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btnrow, text="Copy to clipboard",
                  command=self._copy_token,
                  bd=1, padx=10, pady=4).pack(side=tk.LEFT)

        tk.Label(parent,
            text=("\nSave this somewhere safe. You'll paste it into the "
                  "AlphaX cashier UI's hardware settings."),
            wraplength=560, justify="left",
            font=("", 10), bg=ALPHAX_BG, fg=ALPHAX_MUTED,
        ).pack(anchor="w")

    def _regen_token(self):
        self.token_var.set(secrets.token_urlsafe(24))

    def _copy_token(self):
        self.clipboard_clear()
        self.clipboard_append(self.token_var.get())
        messagebox.showinfo("Copied", "Token copied to clipboard.")

    def screen_hardware(self, parent):
        tk.Label(parent,
            text="Hardware discovery",
            font=("", 16, "bold"), bg=ALPHAX_BG, fg=ALPHAX_FG,
        ).pack(anchor="w", pady=(0, 10))
        tk.Label(parent,
            text=("Plug in your printer, drawer, scale, etc. and click "
                  "Scan. We'll list everything we find. You can give "
                  "each device a name and pick its role; we'll save "
                  "those settings to the config file."),
            wraplength=560, justify="left",
            font=("", 11), bg=ALPHAX_BG, fg=ALPHAX_FG,
        ).pack(anchor="w", pady=(0, 14))

        scan_btn = tk.Button(parent, text="Scan for hardware",
                             command=lambda: self._do_scan(parent),
                             bg=ALPHAX_GREEN, fg="white",
                             padx=14, pady=6, bd=0,
                             font=("", 10, "bold"),
                             cursor="hand2")
        scan_btn.pack(anchor="w")

        self.scan_output = scrolledtext.ScrolledText(
            parent, height=10, width=72,
            font=("Courier", 9),
            bg="#fff", fg="#222", bd=1, relief="solid",
        )
        self.scan_output.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.scan_output.insert(tk.END,
            "(Click 'Scan for hardware' once your devices are plugged in.)\n")
        self.scan_output.config(state=tk.DISABLED)

    def _do_scan(self, parent):
        self.scan_output.config(state=tk.NORMAL)
        self.scan_output.delete("1.0", tk.END)
        self.scan_output.insert(tk.END, "Scanning…\n")
        self.scan_output.config(state=tk.DISABLED)
        self.update()

        def run_scan():
            try:
                from alphax_bridge.devices import discover_all
                self.discovered = discover_all()
            except Exception as e:
                self.discovered = []
                err = str(e)
                self.after(0, lambda: self._show_scan_error(err))
                return
            self.after(0, self._show_scan_results)

        threading.Thread(target=run_scan, daemon=True).start()

    def _show_scan_error(self, err):
        self.scan_output.config(state=tk.NORMAL)
        self.scan_output.delete("1.0", tk.END)
        self.scan_output.insert(tk.END,
            f"Scan failed: {err}\n\n"
            "You can still continue — write your config.yaml manually after install.\n"
            "See the bridge docs for examples.\n")
        self.scan_output.config(state=tk.DISABLED)

    def _show_scan_results(self):
        self.scan_output.config(state=tk.NORMAL)
        self.scan_output.delete("1.0", tk.END)
        if not self.discovered:
            self.scan_output.insert(tk.END,
                "No devices detected.\n\n"
                "Possible reasons:\n"
                "  - No hardware is plugged in\n"
                "  - Drivers aren't installed (Windows: install vendor drivers; Linux: add user to 'dialout')\n"
                "  - On Linux, you may need to run with sudo to read USB device IDs\n\n"
                "You can still continue and edit config.yaml later.\n")
        else:
            self.scan_output.insert(tk.END,
                f"Found {len(self.discovered)} device(s):\n\n")
            for i, d in enumerate(self.discovered, 1):
                kind = d.get('kind', 'unknown')
                desc = d.get('description', d.get('name', 'unknown'))
                addr = d.get('address', d.get('port', d.get('vendor_id', '')))
                self.scan_output.insert(tk.END,
                    f"  [{i}] {kind:8s}  {desc:40s}  {addr}\n")
            self.scan_output.insert(tk.END,
                "\n✓ These will be saved to config.yaml when you click Continue.\n"
                "  Edit ~/.alphax-bridge/config.yaml later to fine-tune device names\n"
                "  and roles, or do it from the cashier UI's hardware settings.\n")
        self.scan_output.config(state=tk.DISABLED)

    def screen_done(self, parent):
        tk.Label(parent, text="✓ Setup complete",
                 font=("", 16, "bold"), bg=ALPHAX_BG, fg=ALPHAX_GREEN
                 ).pack(anchor="w", pady=(0, 14))
        tk.Label(parent,
            text=(f"Configuration saved to:\n"
                  f"   {CONFIG_FILE}\n\n"
                  f"Auth token saved to:\n"
                  f"   {TOKEN_FILE}\n\n"
                  "The bridge will start automatically when you log in.\n"
                  "A small icon will appear in your system tray:\n"
                  "  - Green dot = running\n"
                  "  - Red dot   = error (right-click → View logs)\n"
                  "  - Grey dot  = stopped\n\n"
                  "Next: open the AlphaX cashier UI in your browser, go to\n"
                  "Hardware Settings, and paste the auth token from step 2."),
            wraplength=560, justify="left",
            font=("", 11), bg=ALPHAX_BG, fg=ALPHAX_FG,
        ).pack(anchor="w")

    # ---- config write --------------------------------------------------

    def write_config(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Auth token to its own file (mode 600 on POSIX).
        TOKEN_FILE.write_text(self.token_var.get())
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass    # Windows; ACLs handle it differently

        lines = [
            "# AlphaX POS Bridge configuration",
            "# Generated by the setup wizard. Edit freely; comments preserved.",
            "",
            "bridge:",
            f"  bind_host: 127.0.0.1",
            f"  bind_port: {self.port_var.get()}",
            f"  auth_token: \"{self.token_var.get()}\"",
            "",
            "devices:",
        ]
        if self.discovered:
            for i, d in enumerate(self.discovered, 1):
                kind = d.get("kind", "device")
                desc = d.get("description", d.get("name", "unknown"))
                lines.append(f"  # Discovered: {desc}")
                lines.append(f"  - name: {kind}-{i}")
                lines.append(f"    kind: {kind}")
                if d.get("profile_hint"):
                    lines.append(f"    profile: {d['profile_hint']}")
                else:
                    lines.append(f"    profile: TBD-edit-this  # see `alphax-bridge --list-profiles`")
                if d.get("transport"):
                    lines.append(f"    transport:")
                    for k, v in (d["transport"] or {}).items():
                        lines.append(f"      {k}: {v}")
                lines.append("")
        else:
            lines.append("  []  # no hardware detected; add manually")
            lines.append("  # Example:")
            lines.append("  # - name: receipt-printer")
            lines.append("  #   kind: printer")
            lines.append("  #   profile: epson-tm-t20iii")
            lines.append("  #   transport:")
            lines.append("  #     type: usb")
            lines.append("  #     vendor: 0x04b8")
            lines.append("  #     product: 0x0e15")

        CONFIG_FILE.write_text("\n".join(lines))


def main():
    app = SetupWizard()
    app.mainloop()


if __name__ == "__main__":
    main()
