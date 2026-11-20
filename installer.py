import base64
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_NAME = "Foldr"
DEFAULT_INSTALL_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", APP_NAME
)


def resource_path(name):
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), name)


def create_shortcut(shortcut_path, target_path):
    script = "\n".join(
        [
            "$shortcutPath = " + ps_quote(shortcut_path),
            "$targetPath = " + ps_quote(target_path),
            "$shell = New-Object -ComObject WScript.Shell",
            "$shortcut = $shell.CreateShortcut($shortcutPath)",
            "$shortcut.TargetPath = $targetPath",
            "$shortcut.WorkingDirectory = Split-Path -Parent $targetPath",
            "$shortcut.Save()",
        ]
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def refresh_icon_cache(path):
    try:
        shell = ctypes.windll.shell32
        shell.SHChangeNotify.argtypes = [
            ctypes.c_long, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p
        ]
        shell.SHChangeNotify(0x00002000, 0x0005, path, None)
    except Exception:
        pass
    try:
        for option in ("-ClearIconCache", "-show"):
            subprocess.run(
                ["ie4uinit.exe", option],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
                timeout=10,
            )
    except Exception:
        pass


def ps_quote(value):
    return "'" + value.replace("'", "''") + "'"


class Installer:
    def __init__(self, root):
        self.root = root
        self.root.title("Setup")
        self.root.minsize(580, 420)
        self.root.geometry("610x465")
        self.root.resizable(False, False)

        style = ttk.Style(root)
        for theme in ("vista", "xpnative", "winnative"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Wizard.TLabel", background="#f0f0f0", font=("Segoe UI", 10))

        self.root.configure(background="#f0f0f0")
        try:
            self.root.iconbitmap(resource_path("Foldr-build.ico"))
        except tk.TclError:
            self.window_icon = tk.PhotoImage(file=resource_path("icon.png"))
            self.root.iconphoto(True, self.window_icon)

        self.install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.desktop_shortcut = tk.BooleanVar(value=True)
        self.start_menu_shortcut = tk.BooleanVar(value=True)
        self.page = "welcome"
        self.busy = False
        self.warning = ""

        self.header = tk.Frame(root, bg="white", height=88)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        self.header_title = tk.Label(
            self.header,
            text="Welcome to Foldr Setup",
            bg="white",
            fg="#111111",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.header_title.place(x=28, y=19)
        self.header_description = tk.Label(
            self.header,
            text="This wizard will install Foldr on your computer.",
            bg="white",
            fg="#111111",
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.header_description.place(x=46, y=43)
        self.header_icon = tk.PhotoImage(file=resource_path("icon.png"))
        scale = max(1, (self.header_icon.width() + 47) // 48)
        if scale > 1:
            self.header_icon = self.header_icon.subsample(scale, scale)
        self.header_art = tk.Label(self.header, image=self.header_icon, bg="white", borderwidth=0)
        self.header_art.place(relx=1.0, x=-22, y=16, anchor="ne")

        ttk.Separator(root, orient="horizontal").pack(fill="x")
        self.content = tk.Frame(root, bg="#f0f0f0")
        self.content.pack(fill="both", expand=True)
        self.footer = tk.Frame(root, bg="#f0f0f0", height=48)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)
        ttk.Separator(self.footer, orient="horizontal").pack(fill="x", side="top")
        self.buttons = ttk.Frame(self.footer, padding=(6, 8, 14, 4))
        self.buttons.pack(fill="both", expand=True)

        self.back_button = ttk.Button(self.buttons, text="< Back", command=self.back, width=10)
        self.next_button = ttk.Button(self.buttons, text="Next", command=self.next, width=10)
        self.next_button.pack(side="right")
        self.cancel_button = ttk.Button(self.buttons, text="Cancel", command=root.destroy, width=10)
        self.cancel_button.pack(side="right", padx=(8, 0))

        self.show_welcome()

    def clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def set_header(self, title, description):
        self.header_title.configure(text=title)
        self.header_description.configure(text=description)

    def body_label(self, text, **kwargs):
        return tk.Label(
            self.content,
            text=text,
            bg="#f0f0f0",
            fg="#111111",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            **kwargs,
        )

    def show_welcome(self):
        self.page = "welcome"
        self.clear_content()
        self.set_header("Welcome to Foldr Setup", "This wizard will install Foldr on your computer.")
        self.body_label(
            "To continue, click Next. You can choose the install location and optional shortcuts during setup.",
            wraplength=515,
        ).pack(anchor="w", padx=40, pady=(18, 0))
        self.back_button.state(["disabled"])
        self.next_button.configure(text="Next", state="normal")

    def show_location(self):
        self.page = "location"
        self.clear_content()
        self.set_header("Choose Install Location", "Where should Foldr be installed?")
        self.body_label("Setup will install Foldr in the following folder:").pack(anchor="w", padx=40, pady=(18, 8))
        path_row = ttk.Frame(self.content, padding=(40, 0, 40, 0))
        path_row.pack(fill="x")
        ttk.Entry(path_row, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="Browse...", command=self.browse).pack(side="left", padx=(8, 0))
        self.body_label(
            "Window size settings will be saved in this folder.",
            wraplength=515,
        ).pack(anchor="w", padx=40, pady=(12, 0))

        self.back_button.state(["!disabled"])
        self.next_button.configure(text="Next", state="normal")

    def show_tasks(self):
        self.page = "tasks"
        self.clear_content()
        self.set_header("Select Additional Tasks", "Which additional tasks should be performed?")
        self.body_label(
            "Select the additional tasks you want Setup to perform while installing Foldr, then click Next."
        ).pack(anchor="w", padx=40, pady=(14, 13))
        ttk.Checkbutton(
            self.content,
            text="Create a Start Menu shortcut",
            variable=self.start_menu_shortcut,
        ).pack(anchor="w", padx=44, pady=(0, 3))
        ttk.Checkbutton(
            self.content,
            text="Create a desktop shortcut",
            variable=self.desktop_shortcut,
        ).pack(anchor="w", padx=44)
        self.back_button.state(["!disabled"])
        self.next_button.configure(text="Next", state="normal")

    def show_installing(self):
        self.page = "installing"
        self.clear_content()
        self.set_header("Installing Foldr", "Please wait while Setup installs Foldr.")
        self.progress = ttk.Progressbar(self.content, mode="indeterminate")
        self.progress.pack(fill="x", padx=40, pady=(22, 8))
        self.progress.start(12)
        self.status = self.body_label("Preparing installation...")
        self.status.pack(anchor="w", padx=40)
        self.back_button.state(["disabled"])
        self.next_button.configure(state="disabled")
        self.cancel_button.configure(state="disabled")

    def show_finished(self, error=""):
        self.page = "finished"
        self.clear_content()
        if error:
            self.set_header("Installation failed", "Foldr could not be installed.")
            self.body_label(error, wraplength=515).pack(anchor="w", padx=40, pady=(18, 0))
            self.next_button.configure(text="Close", state="normal", command=self.root.destroy)
        else:
            self.set_header("Installation Complete", "Setup has finished installing Foldr.")
            if self.warning:
                self.body_label(
                    "Foldr was installed, but a shortcut could not be created: " + self.warning,
                    wraplength=480,
                ).pack(anchor="w", padx=40, pady=(18, 0))
            else:
                self.body_label("You can start Foldr from the shortcut you selected.").pack(
                    anchor="w", padx=40, pady=(18, 0)
                )
            self.next_button.configure(text="Finish", state="normal", command=self.root.destroy)
        self.back_button.pack_forget()
        self.cancel_button.pack_forget()

    def browse(self):
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Choose installation folder",
            initialdir=self.install_dir.get() or DEFAULT_INSTALL_DIR,
            mustexist=False,
        )
        if selected:
            self.install_dir.set(selected)

    def back(self):
        if self.page == "location":
            self.show_welcome()
        elif self.page == "tasks":
            self.show_location()

    def next(self):
        if self.page == "welcome":
            self.show_location()
        elif self.page == "location":
            self.show_tasks()
        elif self.page == "tasks":
            self.install()

    def install(self):
        raw_destination = self.install_dir.get().strip()
        if not raw_destination:
            messagebox.showerror("Foldr Setup", "Choose an installation folder.", parent=self.root)
            return
        destination = os.path.abspath(os.path.expandvars(os.path.expanduser(raw_destination)))
        if os.path.exists(destination) and not os.path.isdir(destination):
            messagebox.showerror("Foldr Setup", "The selected location is not a folder.", parent=self.root)
            return

        self.install_dir.set(destination)
        self.busy = True
        self.show_installing()
        threading.Thread(
            target=self.install_worker,
            args=(destination, self.desktop_shortcut.get(), self.start_menu_shortcut.get()),
            daemon=True,
        ).start()

    def install_worker(self, destination, desktop_shortcut, start_menu_shortcut):
        try:
            os.makedirs(destination, exist_ok=True)
            executable = os.path.join(destination, "Foldr.exe")
            shutil.copy2(resource_path("Foldr.exe"), executable)

            shortcut_errors = []
            if desktop_shortcut:
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                try:
                    os.makedirs(desktop, exist_ok=True)
                    create_shortcut(os.path.join(desktop, "Foldr.lnk"), executable)
                except Exception as error:
                    shortcut_errors.append(str(error))

            if start_menu_shortcut:
                programs = os.path.join(
                    os.environ.get("APPDATA", os.path.expanduser("~")),
                    "Microsoft",
                    "Windows",
                    "Start Menu",
                    "Programs",
                )
                try:
                    os.makedirs(programs, exist_ok=True)
                    create_shortcut(os.path.join(programs, "Foldr.lnk"), executable)
                except Exception as error:
                    shortcut_errors.append(str(error))

            refresh_icon_cache(executable)
            self.warning = "; ".join(shortcut_errors)
            self.root.after(0, self.show_finished)
        except Exception as error:
            message = str(error)
            self.root.after(0, lambda: self.show_finished(message))


def main():
    root = tk.Tk()
    Installer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
