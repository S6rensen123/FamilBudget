import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from datetime import date, datetime

from database_service import DatabaseService
from updater import parse_args, run_self_update
from update_manager import UpdateManager
from version import APP_VERSION


class LoginWindow(tk.Toplevel):
    def __init__(self, master, service: DatabaseService, on_success):
        super().__init__(master)
        self.master = master
        self.service = service
        self.on_success = on_success
        self.user_count = self.service.count_users()
        self.full_name_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.loading = False
        self.title("FamilBudget")
        self.configure(bg=master.colors["background"] if hasattr(master, "colors") else "#F8FAFC")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_body()
        self.grab_set()

    def build_body(self):
        for child in self.winfo_children():
            child.destroy()

        header = tk.Frame(self, bg=self["bg"], padx=24, pady=24)
        header.pack(fill="both", expand=True)

        if self.user_count == 0:
            title_text = "Opret konto"
            subtitle_text = "Opret din første konto i FamilBudget."
        else:
            title_text = "Log ind"
            subtitle_text = "Log ind med din eksisterende konto."

        tk.Label(header, text=title_text, font=("Segoe UI", 18, "bold"), bg=self["bg"], fg=self.master.colors["text"]).pack(anchor="w", pady=(0, 10))
        tk.Label(header, text=subtitle_text, bg=self["bg"], fg=self.master.colors["muted"]).pack(anchor="w", pady=(0, 20))

        if self.user_count == 0:
            tk.Label(header, text="Fulde navn", bg=self["bg"], fg=self.master.colors["text"]).pack(anchor="w", pady=(8, 4))
            tk.Entry(header, textvariable=self.full_name_var, width=36).pack()

        tk.Label(header, text="E-mail", bg=self["bg"], fg=self.master.colors["text"]).pack(anchor="w", pady=(12, 4))
        tk.Entry(header, textvariable=self.email_var, width=36).pack()

        tk.Label(header, text="Password", bg=self["bg"], fg=self.master.colors["text"]).pack(anchor="w", pady=(12, 4))
        tk.Entry(header, textvariable=self.password_var, show="*", width=36).pack()

        action_text = "Opret konto" if self.user_count == 0 else "Log ind"
        action_command = self.create_account if self.user_count == 0 else self.login_account

        self.action_button = tk.Button(
            header,
            text=action_text,
            bg=self.master.colors["primary"],
            fg="white",
            bd=0,
            padx=16,
            pady=10,
            relief="flat",
            command=action_command,
        )
        self.action_button.pack(fill="x", pady=(20, 8))

        self.status_label = tk.Label(header, textvariable=self.status_var, bg=self["bg"], fg=self.master.colors["danger"])
        self.status_label.pack(anchor="w", pady=(0, 8))

        if self.user_count != 0:
            switch_frame = tk.Frame(header, bg=self["bg"])
            switch_frame.pack(fill="x", pady=(4, 0))
            tk.Label(switch_frame, text="Ingen konto endnu?", bg=self["bg"], fg=self.master.colors["muted"]).pack(side="left")
            tk.Button(
                switch_frame,
                text="Opret konto",
                bg=self.master.colors["surface_2"],
                fg=self.master.colors["text"],
                bd=0,
                padx=10,
                pady=8,
                relief="flat",
                command=self.switch_to_signup,
            ).pack(side="left", padx=(8, 0))

    def switch_to_signup(self):
        self.user_count = 0
        self.full_name_var.set("")
        self.email_var.set("")
        self.password_var.set("")
        self.status_var.set("")
        self.build_body()

    def switch_to_login(self):
        self.user_count = self.service.count_users()
        self.full_name_var.set("")
        self.email_var.set("")
        self.password_var.set("")
        self.status_var.set("")
        self.build_body()

    def set_loading(self, loading: bool, message: str = ""):
        if not self.winfo_exists():
            return
        self.loading = loading
        if hasattr(self, "action_button"):
            try:
                self.action_button.configure(state="disabled" if loading else "normal")
            except tk.TclError:
                pass
        self.status_var.set(message)

    def create_account(self):
        full_name = self.full_name_var.get().strip()
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not full_name or not email or not password:
            messagebox.showerror("Fejl", "Udfyld Fulde navn, e-mail og password.")
            return
        self.set_loading(True, "Opretter konto…")
        try:
            user_id = self.service.create_user(full_name, email, password)
            user = self.service.get_user_by_id(user_id)
            token = self.service.create_session(user_id)
            self.on_success(user, token)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Fejl", f"Kunne ikke oprette konto: {exc}")
        finally:
            if self.winfo_exists():
                self.set_loading(False)

    def login_account(self):
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not email or not password:
            messagebox.showerror("Fejl", "Udfyld e-mail og password.")
            return
        self.set_loading(True, "Logger ind…")
        try:
            user = self.service.login_user(email, password)
            if user is None:
                messagebox.showerror("Fejl", "E-mail eller password er forkert.")
                return
            token = self.service.create_session(int(user["id"]))
            self.on_success(user, token)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Fejl", f"Kunne ikke logge ind: {exc}")
        finally:
            if self.winfo_exists():
                self.set_loading(False)

    def on_close(self):
        self.master.destroy()


class FamilBudgetApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FamilBudget")
        self.geometry("1400x900")
        self.minsize(1000, 700)
        self.configure(bg="#F8FAFC")

        self.service = DatabaseService()
        self.current_user = None
        self.current_user_id = None
        self.session_token = ""
        self.current_page = "oversigt"
        self.theme = self.service.get_setting("theme", "light")
        self.colors = self.get_theme_colors(self.theme)
        self.create_styles()
        self.bind("<Configure>", self.on_resize)
 
        self.user_name = "Bruger"
        self.household_member = False
        self.transactions = []
        self.notifications = []
        self.alert_count = 0
        self.active_overlay = None
        self.active_panel = None
        self.update_manager = UpdateManager(APP_VERSION)
        self.update_in_progress = False
        self.skip_update_version = self.service.get_setting("skip_update_version", "")

        self.auth_frame = None
        self.top_bar = None
        self.nav_frame = None
        self.sidebar_buttons = []
        self.bottom_nav_buttons = []
        self.canvas_frame = None
        self.canvas = None
        self.canvas_content = None
        self.household = None
        self.dashboard_cards = []
        self._dashboard_data_cache = {"savings_goals": [], "subscriptions": [], "loaded_at": 0.0}
        self._dashboard_loading = False
        self._transactions_loading = False
        self._notifications_loading = False
        self._last_rendered_page = None
        self._render_after_id = None
        self._resize_after_id = None
        self._session_timer_id = None
        self._update_timer_id = None
        self._notify_timer_id = None
        self._last_resize_mode = None

        self.session_token = self.service.get_setting("session_token", "")
        if self.session_token:
            user = self.service.validate_session(self.session_token)
            if user is not None:
                self.current_user = user
                self.current_user_id = int(user["id"])
                self.user_name = user["full_name"]
                self.refresh_household_state()

        if self.current_user is None:
            self.withdraw()
            LoginWindow(self, self.service, self.on_auth_success)
        else:
            self.build_ui()
            self.load_transactions()
            self.load_notifications()
            self.show_page(self.current_page)
            self.schedule_periodic_tasks()

    def get_setting(self, key, default):
        return self.service.get_setting(key, default)

    def save_setting(self, key, value):
        self.service.save_setting(key, value)

    def _perf_log(self, function_name: str, started_at: float):
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        print(f"[PERF] {function_name} {elapsed_ms:.2f} ms")

    def cancel_scheduled_jobs(self):
        for timer_id_attr in ("_render_after_id", "_resize_after_id", "_session_timer_id", "_update_timer_id", "_notify_timer_id"):
            timer_id = getattr(self, timer_id_attr, None)
            if timer_id is not None:
                try:
                    self.after_cancel(timer_id)
                except tk.TclError:
                    pass
                setattr(self, timer_id_attr, None)

    def schedule_periodic_tasks(self):
        if self._notify_timer_id is not None:
            try:
                self.after_cancel(self._notify_timer_id)
            except tk.TclError:
                pass
        if self._update_timer_id is not None:
            try:
                self.after_cancel(self._update_timer_id)
            except tk.TclError:
                pass
        if self._session_timer_id is not None:
            try:
                self.after_cancel(self._session_timer_id)
            except tk.TclError:
                pass

        self._notify_timer_id = self.after(800, self.refresh_notifications)
        self._update_timer_id = self.after(1200, self.start_update_check)
        self._session_timer_id = self.after(5 * 60 * 1000, self.ensure_session_valid)

    def ensure_session_valid(self):
        started_at = time.perf_counter()
        if self.current_user and self.session_token:
            user = self.service.validate_session(self.session_token)
            if user is None:
                messagebox.showwarning("Session udløbet", "Din session er udløbet. Log ind igen.")
                self.logout()
                return
        self._session_timer_id = self.after(5 * 60 * 1000, self.ensure_session_valid)
        self._perf_log("ensure_session_valid", started_at)

    def on_auth_success(self, user, token):
        self.current_user = user
        self.current_user_id = int(user["id"])
        self.user_name = user["full_name"]
        self.session_token = token
        self.service.save_setting("session_token", token)
        self.refresh_household_state()
        self.deiconify()
        self.start_main_app()

    def refresh_household_state(self):
        if self.current_user_id is not None:
            self.household = self.service.get_household_for_user(self.current_user_id)
            self.household_member = self.household is not None
        else:
            self.household = None
            self.household_member = False

    def update_sidebar_profile(self):
        if hasattr(self, "sidebar_user_label"):
            self.sidebar_user_label.configure(text=self.user_name or "Bruger")
        if hasattr(self, "sidebar_avatar"):
            avatar_text = (self.user_name or "Bruger")[:2].upper()
            avatar_url = None
            if self.current_user is not None:
                try:
                    avatar_url = self.current_user["avatar_url"]
                except Exception:
                    avatar_url = None
            if avatar_url and os.path.exists(avatar_url):
                try:
                    image = tk.PhotoImage(file=avatar_url)
                    self.sidebar_avatar.configure(image=image, text="")
                    self.sidebar_avatar.image = image
                except Exception:
                    self.sidebar_avatar.configure(text=avatar_text)
            else:
                self.sidebar_avatar.configure(text=avatar_text)

    def get_theme_colors(self, theme):
        if theme == "dark":
            return {
                "primary": "#5B8CFF",
                "success": "#10B981",
                "warning": "#F59E0B",
                "danger": "#EF4444",
                "background": "#07111F",
                "surface": "#0F172A",
                "surface_2": "#111C2E",
                "text": "#E2E8F0",
                "muted": "#94A3B8",
                "border": "#243449",
                "shadow": "#020617",
                "accent": "#7C3AED",
                "chip": "#1E293B",
            }
        return {
            "primary": "#2563EB",
            "success": "#10B981",
            "warning": "#F59E0B",
            "danger": "#EF4444",
            "background": "#F8FAFC",
            "surface": "#FFFFFF",
            "surface_2": "#F8FAFC",
            "text": "#0F172A",
            "muted": "#64748B",
            "border": "#E2E8F0",
            "shadow": "#CBD5E1",
            "accent": "#7C3AED",
            "chip": "#EFF6FF",
        }

    def create_styles(self):
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
 
        self.style.configure("TFrame", background=self.colors["background"])
        self.style.configure("Card.TFrame", background=self.colors["surface"])
        self.style.configure("TLabel", background=self.colors["background"], foreground=self.colors["text"])
        self.style.configure("TButton", padding=8)
        self.style.map(
            "TButton",
            background=[("active", self.colors["surface_2"]), ("!disabled", self.colors["surface"])],
            foreground=[("active", self.colors["text"]), ("!disabled", self.colors["text"])],
        )
        self.style.configure("Treeview", background=self.colors["surface"], fieldbackground=self.colors["surface"], foreground=self.colors["text"])
        self.style.map("Treeview", background=[("selected", self.colors["primary"])] )
 
    def clear_root(self):
        for child in self.winfo_children():
            child.destroy()
        self.active_overlay = None
        self.active_panel = None
 
    def show_auth_screen(self):
        self.clear_root()
        self.configure(bg=self.colors["background"])
        if self.auth_frame is not None:
            self.auth_frame.destroy()
        self.auth_frame = tk.Frame(self, bg=self.colors["background"])
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")
 
        user_count = self.service.count_users()
        if user_count == 0:
            self.build_signup_form()
        else:
            self.build_login_form()
 
    def start_main_app(self):
        self.clear_root()
        self.build_ui()
        self.load_transactions(callback=lambda: self.show_page(self.current_page, force=True))
        self.load_notifications()
        self.show_page(self.current_page, force=True)
        self.schedule_periodic_tasks()
 
    def build_login_form(self):
        self.clear_root()
        self.configure(bg=self.colors["background"])
        self.auth_frame = tk.Frame(self, bg=self.colors["background"], padx=24, pady=24)
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")
 
        tk.Label(self.auth_frame, text="Log ind", font=("Segoe UI", 20, "bold"), bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w", pady=(0, 12))
        tk.Label(self.auth_frame, text="Fortsæt med din konto.", bg=self.colors["background"], fg=self.colors["muted"]).pack(anchor="w", pady=(0, 20))
 
        email_var = tk.StringVar()
        password_var = tk.StringVar()
        remember_var = tk.BooleanVar(value=True)
 
        tk.Label(self.auth_frame, text="E-mail", bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w", pady=(8, 4))
        tk.Entry(self.auth_frame, textvariable=email_var, width=38).pack()
 
        tk.Label(self.auth_frame, text="Password", bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w", pady=(12, 4))
        tk.Entry(self.auth_frame, textvariable=password_var, show="*", width=38).pack()
 
        remember_check = tk.Checkbutton(
            self.auth_frame,
            text="Husk mig",
            variable=remember_var,
            bg=self.colors["background"],
            fg=self.colors["text"],
            activebackground=self.colors["background"],
            selectcolor=self.colors["surface"],
        )
        remember_check.pack(anchor="w", pady=(12, 4))
 
        def do_login():
            email = email_var.get().strip()
            password = password_var.get()
            if not email or not password:
                messagebox.showerror("Fejl", "Udfyld både e-mail og password.")
                return
            user = self.service.login_user(email, password)
            if user is None:
                messagebox.showerror("Fejl", "E-mail eller password er forkert.")
                return
            self.current_user = user
            self.current_user_id = int(user["id"])
            self.user_name = user["full_name"]
            self.refresh_household_state()
            self.session_token = self.service.create_session(self.current_user_id)
            if remember_var.get():
                self.service.save_setting("session_token", self.session_token)
            else:
                self.service.save_setting("session_token", "")
            self.start_main_app()
 
        tk.Button(
            self.auth_frame,
            text="Log ind",
            bg=self.colors["primary"],
            fg="white",
            bd=0,
            padx=16,
            pady=10,
            relief="flat",
            command=do_login,
        ).pack(fill="x", pady=(16, 8))
 
        switch_frame = tk.Frame(self.auth_frame, bg=self.colors["background"])
        switch_frame.pack(fill="x", pady=(4, 0))
        tk.Label(switch_frame, text="Har du ikke en konto?", bg=self.colors["background"], fg=self.colors["muted"]).pack(side="left")
        tk.Button(
            switch_frame,
            text="Opret konto",
            bg=self.colors["surface_2"],
            fg=self.colors["text"],
            bd=0,
            padx=10,
            pady=8,
            relief="flat",
            command=self.build_signup_form,
        ).pack(side="left", padx=(8, 0))
 
    def build_signup_form(self):
        self.clear_root()
        self.configure(bg=self.colors["background"])
        self.auth_frame = tk.Frame(self, bg=self.colors["background"], padx=24, pady=24)
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")
 
        tk.Label(self.auth_frame, text="Opret konto", font=("Segoe UI", 20, "bold"), bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w", pady=(0, 12))
        tk.Label(self.auth_frame, text="Start din sikre FamilBudget-oplevelse.", bg=self.colors["background"], fg=self.colors["muted"]).pack(anchor="w", pady=(0, 20))
 
        full_name_var = tk.StringVar()
        email_var = tk.StringVar()
        password_var = tk.StringVar()
        confirm_var = tk.StringVar()
 
        tk.Label(self.auth_frame, text="Fulde navn", bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w", pady=(8, 4))
        tk.Entry(self.auth_frame, textvariable=full_name_var, width=38).pack()
 
        tk.Label(self.auth_frame, text="E-mail", bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w", pady=(12, 4))
        tk.Entry(self.auth_frame, textvariable=email_var, width=38).pack()
 
        tk.Label(self.auth_frame, text="Password", bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w", pady=(12, 4))
        tk.Entry(self.auth_frame, textvariable=password_var, show="*", width=38).pack()
 
        tk.Label(self.auth_frame, text="Gentag password", bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w", pady=(12, 4))
        tk.Entry(self.auth_frame, textvariable=confirm_var, show="*", width=38).pack()
 
        def do_signup():
            full_name = full_name_var.get().strip()
            email = email_var.get().strip()
            password = password_var.get()
            confirm_password = confirm_var.get()
            if not full_name or not email or not password or not confirm_password:
                messagebox.showerror("Fejl", "Udfyld alle felter.")
                return
            if password != confirm_password:
                messagebox.showerror("Fejl", "Password matcher ikke.")
                return
            try:
                user_id = self.service.create_user(full_name, email, password)
            except Exception as exc:
                messagebox.showerror("Fejl", f"Kunne ikke oprette konto: {exc}")
                return
            user = self.service.get_user_by_id(user_id)
            self.current_user = user
            self.current_user_id = int(user["id"])
            self.user_name = user["full_name"]
            self.refresh_household_state()
            self.session_token = self.service.create_session(self.current_user_id)
            self.service.save_setting("session_token", self.session_token)
            self.start_main_app()
 
        tk.Button(
            self.auth_frame,
            text="Opret konto",
            bg=self.colors["primary"],
            fg="white",
            bd=0,
            padx=16,
            pady=10,
            relief="flat",
            command=do_signup,
        ).pack(fill="x", pady=(16, 8))
 
        if self.service.count_users() > 0:
            switch_frame = tk.Frame(self.auth_frame, bg=self.colors["background"])
            switch_frame.pack(fill="x", pady=(4, 0))
            tk.Label(switch_frame, text="Har du allerede en konto?", bg=self.colors["background"], fg=self.colors["muted"]).pack(side="left")
            tk.Button(
                switch_frame,
                text="Log ind",
                bg=self.colors["surface_2"],
                fg=self.colors["text"],
                bd=0,
                padx=10,
                pady=8,
                relief="flat",
                command=self.build_login_form,
            ).pack(side="left", padx=(8, 0))

    def build_ui(self):
        self.configure(bg=self.colors["background"])
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"], width=240)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)
        self.nav_frame = self.sidebar

        nav_items = [
            ("🏠 Oversigt", "oversigt"),
            ("💰 Budget", "budget"),
            ("📅 Kalender", "kalender"),
            ("👨‍👩‍👧‍👦 Husstand", "husstand"),
            ("👤 Profil", "profil"),
        ]
        for i, (label, page) in enumerate(nav_items):
            btn = tk.Button(
                self.sidebar,
                text=label,
                anchor="w",
                bg=self.colors["surface"],
                fg=self.colors["text"],
                bd=0,
                padx=16,
                pady=14,
                relief="flat",
                command=lambda p=page: self.show_page(p),
            )
            btn.grid(row=i, column=0, sticky="ew")
            self.bind_hover(btn, self.colors["surface"], self.colors["surface_2"])
            if page == self.current_page:
                btn.configure(bg=self.colors["chip"], fg=self.colors["primary"])
            self.sidebar_buttons.append(btn)

        self.sidebar.rowconfigure(len(nav_items), weight=1)
        self.sidebar_profile_frame = tk.Frame(self.sidebar, bg=self.colors["surface"], padx=16, pady=12)
        self.sidebar_profile_frame.grid(row=len(nav_items) + 1, column=0, sticky="ew")

        self.sidebar_avatar = tk.Label(self.sidebar_profile_frame, text=self.user_name[:2].upper(), bg=self.colors["primary"], fg="white", font=("Segoe UI", 14, "bold"), width=4, height=2)
        self.sidebar_avatar.pack(side="left", padx=(0, 12))
        self.sidebar_user_label = tk.Label(self.sidebar_profile_frame, text=self.user_name, bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 11, "bold"))
        self.sidebar_user_label.pack(side="left", anchor="center")

        self.main_frame = tk.Frame(self, bg=self.colors["background"])
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)
        self.main_frame.rowconfigure(2, weight=0)

        self.top_bar = tk.Frame(self.main_frame, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"])
        self.top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.top_bar.columnconfigure(0, weight=1)
        self.top_bar.columnconfigure(1, weight=0)

        self.app_title = tk.Label(self.top_bar, text="FamilBudget", font=("Segoe UI", 16, "bold"), bg=self.colors["surface"], fg=self.colors["text"])
        self.app_title.grid(row=0, column=0, sticky="w", padx=16, pady=12)

        self.notification_button = tk.Button(
            self.top_bar,
            text="🔔 0",
            bg=self.colors["surface_2"],
            fg=self.colors["text"],
            bd=0,
            padx=12,
            pady=8,
            relief="flat",
            command=self.open_notifications,
        )
        self.notification_button.grid(row=0, column=1, sticky="e", padx=(0, 12), pady=12)
        self.bind_hover(self.notification_button, self.colors["surface_2"], self.colors["chip"])

        self.canvas_frame = tk.Frame(self.main_frame, bg=self.colors["background"])
        self.canvas_frame.grid(row=1, column=0, sticky="nsew")
        self.canvas_frame.columnconfigure(0, weight=1)
        self.canvas_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.canvas_frame, bg=self.colors["background"], highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas_scroll = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas_scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.canvas_scroll.set)
        self.canvas_content = tk.Frame(self.canvas, bg=self.colors["background"])
        self.canvas_window = self.canvas.create_window((0, 0), window=self.canvas_content, anchor="nw")
        self.canvas_content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)

        self.fab = tk.Button(
            self.main_frame,
            text="＋",
            font=("Segoe UI", 22, "bold"),
            bg=self.colors["primary"],
            fg="white",
            bd=0,
            relief="flat",
            padx=16,
            pady=14,
            command=self.open_fab_menu,
        )
        self.fab.place(relx=1.0, rely=1.0, anchor="se", x=-18, y=-90)

        self.bottom_nav = tk.Frame(self.main_frame, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"])
        self.bottom_nav.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.bottom_nav.columnconfigure(0, weight=1)
        self.bottom_nav.columnconfigure(1, weight=1)
        self.bottom_nav.columnconfigure(2, weight=1)
        self.bottom_nav.columnconfigure(3, weight=1)
        self.bottom_nav.columnconfigure(4, weight=1)

        self.bottom_nav_buttons = []
        nav_items = [
            ("🏠", "oversigt"),
            ("💰", "budget"),
            ("📅", "kalender"),
            ("👨‍👩‍👧‍👦", "husstand"),
            ("👤", "profil"),
        ]
        for idx, (icon, page) in enumerate(nav_items):
            btn = tk.Button(
                self.bottom_nav,
                text=icon,
                bg=self.colors["surface"],
                fg=self.colors["text"],
                bd=0,
                pady=12,
                relief="flat",
                command=lambda p=page: self.show_page(p),
            )
            btn.page = page
            btn.grid(row=0, column=idx, sticky="nsew", padx=2)
            self.bind_hover(btn, self.colors["surface"], self.colors["surface_2"])
            self.bottom_nav_buttons.append(btn)

        self.update_sidebar_profile()
        self._apply_resize()

    def _on_mouse_wheel(self, event):
        if self.canvas is None:
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def bind_hover(self, widget, normal_bg, hover_bg):
        widget.bind("<Enter>", lambda e, bg=hover_bg: widget.configure(bg=bg))
        widget.bind("<Leave>", lambda e, bg=normal_bg: widget.configure(bg=bg))

    def close_active_panel(self):
        if self.active_overlay is not None:
            self.active_overlay.destroy()
        self.active_overlay = None
        self.active_panel = None

    def show_modal_panel(self, title, content_builder, width=380):
        self.close_active_panel()

        overlay = tk.Frame(self, bg="#07111F")
        overlay.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)

        panel = tk.Frame(overlay, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"])
        panel.place(relx=0.5, rely=0.5, anchor="center", width=width)

        header = tk.Frame(panel, bg=self.colors["surface"])
        header.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(header, text=title, bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 13, "bold")).pack(side="left")

        close_button = tk.Button(
            header,
            text="✕",
            bg=self.colors["surface"],
            fg=self.colors["muted"],
            bd=0,
            padx=4,
            pady=2,
            relief="flat",
            command=self.close_active_panel,
        )
        close_button.pack(side="right")
        self.bind_hover(close_button, self.colors["surface"], self.colors["surface_2"])

        body = tk.Frame(panel, bg=self.colors["surface"])
        body.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        content_builder(body)

        self.active_overlay = overlay
        self.active_panel = panel
        self.bind("<Escape>", self._handle_modal_escape, add="+")

    def _handle_modal_escape(self, event=None):
        if self.active_overlay is not None:
            self.close_active_panel()

    def clear_content(self):
        for child in self.canvas_content.winfo_children():
            child.destroy()

    def show_page(self, page, force=False):
        started_at = time.perf_counter()
        same_page = (page == self.current_page and self._last_rendered_page == page)
        self.current_page = page
        self.close_active_panel()
        if same_page and not force:
            self.update_nav_state()
            self._perf_log("show_page", started_at)
            return

        if self._render_after_id is not None:
            try:
                self.after_cancel(self._render_after_id)
            except tk.TclError:
                pass
            self._render_after_id = None

        self.clear_content()
        if page != "oversigt":
            self.show_skeleton()
        self._render_after_id = self.after(120, self.render_page)
        self.update_nav_state()
        self._perf_log("show_page", started_at)

    def on_resize(self, event=None):
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        self._resize_after_id = self.after(150, self._apply_resize)

    def _apply_resize(self):
        started_at = time.perf_counter()
        self._resize_after_id = None
        width = self.winfo_width()
        sidebar = getattr(self, "sidebar", None)
        bottom_nav = getattr(self, "bottom_nav", None)
        main_frame = getattr(self, "main_frame", None)
        mode = "desktop" if width > 1000 else "mobile"

        if mode == "desktop":
            if sidebar is not None and sidebar.winfo_exists() and not sidebar.winfo_ismapped():
                sidebar.grid()
            if bottom_nav is not None and bottom_nav.winfo_exists() and bottom_nav.winfo_ismapped():
                bottom_nav.grid_remove()
            if main_frame is not None and main_frame.winfo_exists():
                main_frame.grid_configure(column=1)
            self.columnconfigure(0, weight=0)
            self.columnconfigure(1, weight=1)
        else:
            if sidebar is not None and sidebar.winfo_exists() and sidebar.winfo_ismapped():
                sidebar.grid_remove()
            if bottom_nav is not None and bottom_nav.winfo_exists() and not bottom_nav.winfo_ismapped():
                bottom_nav.grid()
            if main_frame is not None and main_frame.winfo_exists():
                main_frame.grid_configure(column=0)
            self.columnconfigure(0, weight=1)
            self.columnconfigure(1, weight=0)
        self._last_resize_mode = mode

        if self.current_page == "oversigt":
            self.layout_dashboard_cards()
        self._perf_log("_apply_resize", started_at)

    def show_skeleton(self):
        skeleton = tk.Frame(self.canvas_content, bg=self.colors["background"])
        skeleton.pack(fill="x", padx=8, pady=8)

        card = tk.Frame(skeleton, bg=self.colors["surface"], height=140, highlightthickness=1, highlightbackground=self.colors["border"])
        card.pack(fill="x", pady=(0, 12))
        card.pack_propagate(False)

        for _ in range(3):
            block = tk.Frame(skeleton, bg=self.colors["surface"], height=90, highlightthickness=1, highlightbackground=self.colors["border"])
            block.pack(fill="x", pady=(0, 8))
            block.pack_propagate(False)

    def render_page(self):
        started_at = time.perf_counter()
        self._render_after_id = None
        self.clear_content()
        self.update_balance_display()
        if self.current_page == "oversigt":
            self.render_dashboard()
        elif self.current_page == "budget":
            self.render_budget_page()
        elif self.current_page == "kalender":
            self.render_calendar_page()
        elif self.current_page == "husstand":
            self.render_household_page()
        elif self.current_page == "profil":
            self.render_profile_page()
        self._last_rendered_page = self.current_page
        self._perf_log("render_page", started_at)

    def update_nav_state(self):
        started_at = time.perf_counter()
        active_label = self.page_label(self.current_page)
        for btn in getattr(self, "sidebar_buttons", []):
            label = btn.cget("text")
            if label == active_label:
                btn.configure(bg=self.colors["chip"], fg=self.colors["primary"])
            else:
                btn.configure(bg=self.colors["surface"], fg=self.colors["text"])

        for btn in getattr(self, "bottom_nav_buttons", []):
            if getattr(btn, "page", None) == self.current_page:
                btn.configure(bg=self.colors["chip"], fg=self.colors["primary"])
            else:
                btn.configure(bg=self.colors["surface"], fg=self.colors["text"])
        self._perf_log("update_nav_state", started_at)

    def page_label(self, page):
        return {
            "oversigt": "Oversigt",
            "budget": "Budget",
            "kalender": "Kalender",
            "husstand": "Husstand",
            "profil": "Profil",
        }[page]
 
    def load_transactions(self, callback=None):
        started_at = time.perf_counter()
        if self._transactions_loading:
            return
        self._transactions_loading = True
        user_id = self.current_user_id

        def worker():
            worker_started_at = time.perf_counter()
            try:
                rows = self.service.load_transactions(user_id)
            except Exception as exc:
                def on_error():
                    self._transactions_loading = False
                    messagebox.showerror("Fejl", f"Kunne ikke indlæse transaktioner: {exc}")
                    self.transactions = []
                    if callback is not None:
                        callback()
                self.after(0, on_error)
                return

            def on_success():
                self._transactions_loading = False
                self.transactions = rows
                if callback is not None:
                    callback()
                elif self.current_page in ("oversigt", "budget"):
                    self.show_page(self.current_page, force=True)

            self.after(0, on_success)
            self._perf_log("load_transactions_worker", worker_started_at)

        threading.Thread(target=worker, daemon=True).start()
        self._perf_log("load_transactions_dispatch", started_at)

    def load_notifications(self, callback=None):
        started_at = time.perf_counter()
        if self._notifications_loading:
            return
        self._notifications_loading = True
        user_id = self.current_user_id

        def worker():
            worker_started_at = time.perf_counter()
            try:
                rows = self.service.get_notifications(user_id)
            except Exception as exc:
                def on_error():
                    self._notifications_loading = False
                    messagebox.showerror("Fejl", f"Kunne ikke indlæse notifikationer: {exc}")
                    self.notifications = []
                    self.alert_count = 0
                    self.update_notification_badge()
                    if callback is not None:
                        callback()
                self.after(0, on_error)
                return

            def on_success():
                self._notifications_loading = False
                self.notifications = rows
                self.alert_count = sum(1 for notification in self.notifications if notification["read"] == 0)
                self.update_notification_badge()
                if callback is not None:
                    callback()

            self.after(0, on_success)
            self._perf_log("load_notifications_worker", worker_started_at)

        threading.Thread(target=worker, daemon=True).start()
        self._perf_log("load_notifications_dispatch", started_at)

    def format_currency(self, value: float) -> str:
        return f"{value:,.2f} kr"
 
    def calculate_dashboard_metrics(self) -> dict:
        today = date.today()
        first_of_month = today.replace(day=1)
        monthly_expense = 0.0
        monthly_income = 0.0
        expense_categories = {}
        biggest_transaction = None
 
        for row in self.transactions:
            try:
                transaction_date = datetime.fromisoformat(str(row["dato"]))
            except Exception:
                continue
            amount = float(row["beloeb"])
            if row["type"] == "Indtægt":
                if transaction_date.year == today.year and transaction_date.month == today.month:
                    monthly_income += amount
            else:
                if transaction_date.year == today.year and transaction_date.month == today.month:
                    monthly_expense += amount
                expense_categories[row["kategori"]] = expense_categories.get(row["kategori"], 0.0) + amount
 
            if biggest_transaction is None or abs(amount) > abs(biggest_transaction["amount"]):
                biggest_transaction = {
                    "kategori": row["kategori"],
                    "type": row["type"],
                    "amount": amount,
                    "date": row["dato"],
                }
 
        largest_category = None
        if expense_categories:
            largest_category = max(expense_categories.items(), key=lambda item: item[1])
 
        return {
            "balance": self.get_balance(),
            "monthly_income": monthly_income,
            "monthly_expense": monthly_expense,
            "largest_category": largest_category[0] if largest_category else "Ingen kategorier",
            "largest_category_amount": largest_category[1] if largest_category else 0.0,
            "biggest_transaction": biggest_transaction,
        }
 
    def layout_dashboard_cards(self):
        if not hasattr(self, "dashboard_cards") or not self.dashboard_cards:
            return
        width = self.winfo_width()
        one_column = width <= 1000
        for idx, card in enumerate(self.dashboard_cards):
            card.grid_forget()
            if one_column:
                card.grid(row=idx, column=0, sticky="nsew", padx=5, pady=5)
            else:
                row = idx // 2
                col = idx % 2
                card.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)

    def _load_dashboard_datasets(self):
        started_at = time.perf_counter()
        now = time.time()
        cache_age = now - self._dashboard_data_cache["loaded_at"]
        if cache_age <= 10.0:
            self._perf_log("_load_dashboard_datasets_cached", started_at)
            return self._dashboard_data_cache["savings_goals"], self._dashboard_data_cache["subscriptions"]

        if not self._dashboard_loading:
            self._dashboard_loading = True
            user_id = self.current_user_id

            def worker():
                worker_started_at = time.perf_counter()
                savings_goals = []
                subscriptions = []
                try:
                    savings_goals = self.service.get_savings_goals(user_id)
                except Exception:
                    savings_goals = []
                try:
                    subscriptions = self.service.get_subscriptions(user_id)
                except Exception:
                    subscriptions = []

                def on_success():
                    self._dashboard_loading = False
                    self._dashboard_data_cache["savings_goals"] = savings_goals
                    self._dashboard_data_cache["subscriptions"] = subscriptions
                    self._dashboard_data_cache["loaded_at"] = time.time()
                    if self.current_page == "oversigt":
                        self.show_page("oversigt", force=True)

                self.after(0, on_success)
                self._perf_log("_load_dashboard_datasets_worker", worker_started_at)

            threading.Thread(target=worker, daemon=True).start()

        self._perf_log("_load_dashboard_datasets_dispatch", started_at)
        return self._dashboard_data_cache["savings_goals"], self._dashboard_data_cache["subscriptions"]

    def update_notification_badge(self):
        if hasattr(self, "notification_button"):
            self.notification_button.configure(text=f"🔔 {self.alert_count}")

    def update_balance_display(self):
        saldo = 0.0
        for row in self.transactions:
            tipo = row["type"]
            beloeb = float(row["beloeb"])
            if tipo == "Indtægt":
                saldo += beloeb
            else:
                saldo -= beloeb
        self.current_balance = saldo
        return saldo

    def render_dashboard(self):
        started_at = time.perf_counter()
        metrics = self.calculate_dashboard_metrics()
        savings_goals, subscriptions = self._load_dashboard_datasets()

        header = tk.Frame(self.canvas_content, bg=self.colors["background"])
        header.pack(fill="x", padx=12, pady=(12, 12))

        tk.Label(header, text=f"Hej {self.user_name} 👋", font=("Segoe UI", 24, "bold"), bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w")
        tk.Label(header, text="Her er din økonomi for den aktuelle periode.", font=("Segoe UI", 12), bg=self.colors["background"], fg=self.colors["muted"]).pack(anchor="w")

        summary_row = tk.Frame(self.canvas_content, bg=self.colors["background"])
        summary_row.pack(fill="x", padx=12, pady=(0, 12))
        for title, value, color in [
            ("Saldo", self.format_currency(metrics["balance"]), self.colors["primary"]),
            ("Indtægter i måned", self.format_currency(metrics["monthly_income"]), self.colors["success"]),
            ("Udgifter i måned", self.format_currency(metrics["monthly_expense"]), self.colors["danger"]),
            ("Største kategori", metrics["largest_category"], self.colors["text"]),
        ]:
            card = self.create_card(summary_row, title)
            card.configure(padx=12, pady=12)
            card.pack(side="left", fill="both", expand=True, padx=4)
            tk.Label(card, text=value, bg=self.colors["surface"], fg=color, font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(8, 0))

        dashboard_grid = tk.Frame(self.canvas_content, bg=self.colors["background"])
        dashboard_grid.pack(fill="both", expand=True, padx=12, pady=8)
        dashboard_grid.columnconfigure(0, weight=1)
        dashboard_grid.columnconfigure(1, weight=1)

        ai_card = self.create_card(dashboard_grid, "🤖 AI-indsigt")
        insight_lines = [
            f"Største udgiftskategori: {metrics['largest_category']}",
            f"Udgifter denne måned: {self.format_currency(metrics['monthly_expense'])}",
            f"Indtægter denne måned: {self.format_currency(metrics['monthly_income'])}",
            f"Aktuel saldo: {self.format_currency(metrics['balance'])}",
        ]
        if metrics["biggest_transaction"]:
            biggest = metrics["biggest_transaction"]
            insight_lines.append(f"Største transaktion: {biggest['kategori']} {self.format_currency(biggest['amount'])}")

        for line in insight_lines:
            tk.Label(ai_card, text=line, bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", padx=15, pady=4)

        savings_card = self.create_card(dashboard_grid, "🎯 Opsparingsmål")
        if savings_goals:
            for goal in savings_goals[:3]:
                progress = 0.0
                if goal["target_amount"]:
                    progress = min(100.0, (float(goal["current_amount"]) / float(goal["target_amount"]) * 100.0) if goal["target_amount"] else 0.0)
                row = tk.Frame(savings_card, bg=self.colors["surface"])
                row.pack(fill="x", padx=15, pady=8)
                tk.Label(row, text=goal["title"], bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w")
                tk.Label(row, text=f"{self.format_currency(goal['current_amount'])} / {self.format_currency(goal['target_amount'])} ({progress:.0f} %)", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w")
        else:
            tk.Label(savings_card, text="Ingen opsparingsmål endnu.", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=15, pady=15)

        latest_card = self.create_card(dashboard_grid, "🧾 Seneste transaktioner")
        recent = self.transactions[:5]
        if recent:
            for transaction in recent:
                row = tk.Frame(latest_card, bg=self.colors["surface"])
                row.pack(fill="x", padx=15, pady=6)
                tk.Label(row, text=transaction["kategori"], bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 11, "bold")).pack(side="left")
                tk.Label(row, text=self.format_currency(float(transaction["beloeb"])), bg=self.colors["surface"], fg=self.colors["success"] if transaction["type"] == "Indtægt" else self.colors["danger"]).pack(side="right")
                tk.Label(row, text=transaction["dato"], bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w")
        else:
            tk.Label(latest_card, text="Ingen transaktioner endnu.", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=15, pady=15)

        subscriptions_card = self.create_card(dashboard_grid, "📦 Aktive abonnementer")
        active_subs = [sub for sub in subscriptions if sub["active"] == 1]
        if active_subs:
            for sub in active_subs[:3]:
                row = tk.Frame(subscriptions_card, bg=self.colors["surface"])
                row.pack(fill="x", padx=15, pady=8)
                tk.Label(row, text=sub["name"], bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w")
                tk.Label(row, text=f"{self.format_currency(float(sub['amount']))} - {sub.get('billing_date', 'Ingen dato')}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w")
        else:
            tk.Label(subscriptions_card, text="Ingen aktive abonnementer.", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=15, pady=15)

        self.dashboard_cards = [ai_card, savings_card, latest_card, subscriptions_card]
        self.layout_dashboard_cards()
        self._perf_log("render_dashboard", started_at)

    def render_budget_page(self):
        summary = self.create_card(self.canvas_content, "Budgetoversigt", "Se dine seneste transaktioner")
        summary.pack(fill="x", padx=8, pady=(8, 8))
        tk.Label(summary, text=f"Indtægter: {self.get_income():,.2f} kr", bg=self.colors["surface"], fg=self.colors["success"]).pack(anchor="w", padx=16, pady=4)
        tk.Label(summary, text=f"Udgifter: {self.get_expense():,.2f} kr", bg=self.colors["surface"], fg=self.colors["danger"]).pack(anchor="w", padx=16, pady=4)
        tk.Label(summary, text=f"Saldo: {self.get_balance():,.2f} kr", bg=self.colors["surface"], fg=self.colors["primary"]).pack(anchor="w", padx=16, pady=4)

        action_row = tk.Frame(self.canvas_content, bg=self.colors["background"])
        action_row.pack(fill="x", padx=8, pady=(0, 8))
        add_button = tk.Button(action_row, text="Tilføj transaktion", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=10, relief="flat", command=self.open_transaction_form)
        add_button.pack(side="left")
        self.bind_hover(add_button, self.colors["primary"], self.colors["accent"])

        table_card = self.create_card(self.canvas_content, "Transaktioner", "Alle poster er tilgængelige i realtid")
        table_card.pack(fill="x", padx=8, pady=(0, 8))
        columns = ("ID", "Dato", "Kategori", "Beløb", "Type")
        tree = ttk.Treeview(table_card, columns=columns, show="headings", height=8)
        tree.pack(fill="both", padx=12, pady=12)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=90, anchor="w")
        for row in self.transactions:
            tree.insert(
                "",
                tk.END,
                values=(row["id"], row["dato"], row["kategori"], row["beloeb"], row["type"]),
            )

    def render_calendar_page(self):
        card = self.create_card(self.canvas_content, "Kalender", "Planlæg og følg dine betalinger")
        card.pack(fill="x", padx=8, pady=(8, 8))
        for item in [
            ("Mandag 20", "Husleje 3.500 kr"),
            ("Onsdag 22", "El 890 kr"),
            ("Fredag 24", "Løn 24.000 kr"),
        ]:
            row = tk.Frame(card, bg=self.colors["surface"])
            row.pack(fill="x", padx=16, pady=8)
            tk.Label(row, text=item[0], bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(row, text=item[1], bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w")

    def render_household_page(self):
        card = self.create_card(self.canvas_content, "Husstand", "Sådan holder familien økonomien samlet")
        card.pack(fill="x", padx=8, pady=(8, 8))
        if not self.household_member or self.household is None:
            tk.Label(card, text="Du er endnu ikke medlem af en husstand", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
            tk.Label(card, text="Opret en ny husstand eller tilslut med en kode", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=(0, 16))
            btn1 = tk.Button(card, text="Opret husstand", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=10, relief="flat", command=self.open_create_household_dialog)
            btn1.pack(anchor="w", padx=16, pady=4)
            btn2 = tk.Button(card, text="Tilslut med kode", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=12, pady=10, relief="flat", command=self.open_join_household_dialog)
            btn2.pack(anchor="w", padx=16, pady=4)
            return

        admin_name = ""
        if self.household.get("owner_id") is not None:
            owner = self.service.get_user_by_id(self.household["owner_id"])
            admin_name = owner["full_name"] if owner else str(self.household.get("owner_id", ""))

        tk.Label(card, text=self.household["name"], bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(card, text=f"Administrator: {admin_name}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        members = self.service.get_household_members(self.household["id"])
        tk.Label(card, text=f"Medlemsantal: {len(members)}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text=f"Delingskode: {self.household['invite_code']}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text=f"Oprettet: {self.household.get('created_at', '')}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=(2, 16))

        actions = tk.Frame(card, bg=self.colors["surface"])
        actions.pack(fill="x", padx=16, pady=(0, 12))
        copy_btn = tk.Button(actions, text="Kopiér kode", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=8, pady=8, relief="flat", command=self.copy_household_code)
        copy_btn.pack(anchor="w", pady=4)
        share_btn = tk.Button(actions, text="Del kode", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=8, pady=8, relief="flat", command=self.copy_household_code)
        share_btn.pack(anchor="w", pady=4)
        regenerate_btn = tk.Button(actions, text="Generér ny kode", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=8, pady=8, relief="flat", command=self.regenerate_household_code)
        regenerate_btn.pack(anchor="w", pady=4)

        members_card = self.create_card(self.canvas_content, "Medlemmer", "Medlemmerne er samlet i moderne profiler")
        members_card.pack(fill="x", padx=8, pady=(0, 8))
        for member in members:
            row = tk.Frame(members_card, bg=self.colors["surface"])
            row.pack(fill="x", padx=16, pady=8)
            tk.Label(row, text=member["full_name"], bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(row, text=f"{member['role']} • {member['email']}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w")

    def open_create_household_dialog(self):
        def build_content(body):
            tk.Label(body, text="Navn på husstand", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(8, 4))
            name_var = tk.StringVar()
            tk.Entry(body, textvariable=name_var).pack(fill="x")

            def create():
                name = name_var.get().strip()
                if not name:
                    messagebox.showerror("Fejl", "Udfyld navnet på husstanden.")
                    return
                if self.current_user_id is None:
                    messagebox.showerror("Fejl", "Du skal være logget ind for at oprette en husstand.")
                    return
                household_id, invite_code = self.service.create_household(name, self.current_user_id)
                self.refresh_household_state()
                self.close_active_panel()
                self.show_page("husstand")
                messagebox.showinfo("Husstand oprettet", f"Husstanden er oprettet. Kode: {invite_code}")

            tk.Button(body, text="Opret husstand", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=8, relief="flat", command=create).pack(pady=(16, 0))

        self.show_modal_panel("Opret husstand", build_content, width=360)

    def open_join_household_dialog(self):
        def build_content(body):
            tk.Label(body, text="Indtast invitationkode", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(8, 4))
            code_var = tk.StringVar()
            tk.Entry(body, textvariable=code_var).pack(fill="x")

            def join():
                code = code_var.get().strip().upper()
                if not code:
                    messagebox.showerror("Fejl", "Indtast invitationkoden.")
                    return
                if self.current_user_id is None:
                    messagebox.showerror("Fejl", "Du skal være logget ind for at tilslutte dig.")
                    return
                if self.service.join_household(self.current_user_id, code):
                    self.refresh_household_state()
                    self.close_active_panel()
                    self.show_page("husstand")
                    messagebox.showinfo("Tilknytning lykkedes", "Du er nu medlem af husstanden.")
                    return
                messagebox.showerror("Fejl", "Koden er ugyldig.")

            tk.Button(body, text="Tilslut", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=8, relief="flat", command=join).pack(pady=(16, 0))

        self.show_modal_panel("Tilslut til husstand", build_content, width=360)

    def copy_household_code(self):
        if self.household is None:
            return
        self.clipboard_clear()
        self.clipboard_append(self.household["invite_code"])
        messagebox.showinfo("Kode kopieret", "Husstandskoden er kopieret til udklipsholder.")

    def regenerate_household_code(self):
        if self.household is None:
            return
        invite_code = self.service.regenerate_household_invite_code(self.household["id"])
        self.refresh_household_state()
        self.show_page("husstand")
        messagebox.showinfo("Ny kode", f"Ny invite-kode: {invite_code}")

    def render_profile_page(self):
        if self.current_user is None:
            return

        avatar_text = self.user_name[:2].upper()
        try:
            if self.current_user is not None and self.current_user["avatar_url"]:
                avatar_text = os.path.basename(self.current_user["avatar_url"])[:2].upper()
        except Exception:
            pass
        card = self.create_card(self.canvas_content, "Profil", "Personlige indstillinger")
        card.pack(fill="x", padx=8, pady=(8, 8))
        avatar = tk.Label(card, text=avatar_text, bg=self.colors["primary"], fg="white", font=("Segoe UI", 16, "bold"), width=4, height=2)
        avatar.pack(anchor="w", padx=16, pady=(16, 8))
        tk.Label(card, text=self.user_name, bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16)
        email = self.current_user["email"]
        role = self.current_user["role"] if self.current_user is not None and "role" in self.current_user.keys() else "Bruger"
        tk.Label(card, text=f"E-mail: {email}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text=f"Rolle: {role}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=(2, 16))

        settings = self.create_card(self.canvas_content, "Konto", "Opdater dine brugerindstillinger")
        settings.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(settings, text="Rediger navn", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=10, pady=10, relief="flat", command=self.open_edit_name_panel).pack(fill="x", padx=16, pady=(12, 4))
        tk.Button(settings, text="Skift e-mail", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=10, pady=10, relief="flat", command=self.open_change_email_panel).pack(fill="x", padx=16, pady=4)
        tk.Button(settings, text="Skift password", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=10, pady=10, relief="flat", command=self.open_change_password_panel).pack(fill="x", padx=16, pady=4)
        tk.Button(settings, text="Upload avatar", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=10, pady=10, relief="flat", command=self.open_avatar_upload).pack(fill="x", padx=16, pady=4)
        tk.Button(settings, text="Log ud", bg=self.colors["primary"], fg="white", bd=0, padx=10, pady=10, relief="flat", command=self.logout).pack(fill="x", padx=16, pady=(12, 4))
        tk.Button(settings, text="Slet konto", bg=self.colors["danger"], fg="white", bd=0, padx=10, pady=10, relief="flat", command=self.confirm_delete_account).pack(fill="x", padx=16, pady=(0, 12))

    def open_edit_name_panel(self):
        def build_content(body):
            tk.Label(body, text="Fulde navn", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(8, 4))
            name_var = tk.StringVar(value=self.user_name)
            tk.Entry(body, textvariable=name_var).pack(fill="x")

            def save():
                full_name = name_var.get().strip()
                if not full_name:
                    messagebox.showerror("Fejl", "Udfyld dit fulde navn.")
                    return
                try:
                    self.service.update_user_profile(self.current_user_id, full_name)
                    self.current_user = self.service.get_user_by_id(self.current_user_id)
                    self.user_name = self.current_user["full_name"]
                    self.update_sidebar_profile()
                    self.close_active_panel()
                    self.show_page("profil")
                    messagebox.showinfo("Opdateret", "Dit navn er opdateret.")
                except Exception as exc:
                    messagebox.showerror("Fejl", f"Kunne ikke opdatere navn: {exc}")

            tk.Button(body, text="Gem", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=10, relief="flat", command=save).pack(fill="x", pady=(16, 0))

        self.show_modal_panel("Rediger navn", build_content, width=360)

    def open_change_email_panel(self):
        def build_content(body):
            tk.Label(body, text="Ny e-mail", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(8, 4))
            email_var = tk.StringVar(value=self.current_user["email"] if self.current_user is not None else "")
            tk.Entry(body, textvariable=email_var).pack(fill="x")

            def save():
                email = email_var.get().strip()
                if not email:
                    messagebox.showerror("Fejl", "Udfyld e-mail.")
                    return
                try:
                    self.service.update_user_email(self.current_user_id, email)
                    self.current_user = self.service.get_user_by_id(self.current_user_id)
                    self.close_active_panel()
                    self.show_page("profil")
                    messagebox.showinfo("Opdateret", "Din e-mail er opdateret.")
                except Exception as exc:
                    messagebox.showerror("Fejl", f"Kunne ikke opdatere e-mail: {exc}")

            tk.Button(body, text="Gem", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=10, relief="flat", command=save).pack(fill="x", pady=(16, 0))

        self.show_modal_panel("Skift e-mail", build_content, width=360)

    def open_change_password_panel(self):
        def build_content(body):
            tk.Label(body, text="Nuværende password", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(8, 4))
            current_password_var = tk.StringVar()
            tk.Entry(body, textvariable=current_password_var, show="*").pack(fill="x")
            tk.Label(body, text="Nyt password", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(12, 4))
            new_password_var = tk.StringVar()
            tk.Entry(body, textvariable=new_password_var, show="*").pack(fill="x")
            tk.Label(body, text="Gentag nyt password", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(12, 4))
            confirm_password_var = tk.StringVar()
            tk.Entry(body, textvariable=confirm_password_var, show="*").pack(fill="x")

            def save():
                current_password = current_password_var.get()
                new_password = new_password_var.get()
                confirm_password = confirm_password_var.get()
                if not current_password or not new_password or not confirm_password:
                    messagebox.showerror("Fejl", "Udfyld alle felter.")
                    return
                if new_password != confirm_password:
                    messagebox.showerror("Fejl", "Nye passwords matcher ikke.")
                    return
                user = self.service.login_user(self.current_user["email"], current_password)
                if user is None:
                    messagebox.showerror("Fejl", "Nuværende password er forkert.")
                    return
                try:
                    self.service.change_password(self.current_user_id, new_password)
                    self.close_active_panel()
                    messagebox.showinfo("Opdateret", "Dit password er opdateret.")
                except Exception as exc:
                    messagebox.showerror("Fejl", f"Kunne ikke opdatere password: {exc}")

            tk.Button(body, text="Gem password", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=10, relief="flat", command=save).pack(fill="x", pady=(16, 0))

        self.show_modal_panel("Skift password", build_content, width=360)

    def open_avatar_upload(self):
        file_path = filedialog.askopenfilename(
            title="Vælg avatar",
            filetypes=[("Billede", "*.png;*.jpg;*.jpeg;*.gif"), ("Alle filer", "*.*")],
        )
        if not file_path:
            return
        try:
            self.service.update_user_avatar(self.current_user_id, file_path)
            self.current_user = self.service.get_user_by_id(self.current_user_id)
            self.update_sidebar_profile()
            self.show_page("profil")
            messagebox.showinfo("Avatar opdateret", "Din avatar er gemt.")
        except Exception as exc:
            messagebox.showerror("Fejl", f"Kunne ikke opdatere avatar: {exc}")

    def create_card(self, parent, title, subtitle=""):
        card = tk.Frame(parent, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"])
        if title:
            tk.Label(card, text=title, bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        if subtitle:
            tk.Label(card, text=subtitle, bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=(0, 8))
        return card

    def get_balance(self):
        saldo = 0.0
        for row in self.transactions:
            beloeb = float(row["beloeb"])
            if row["type"] == "Indtægt":
                saldo += beloeb
            else:
                saldo -= beloeb
        return saldo

    def get_income(self):
        return sum(float(row["beloeb"]) for row in self.transactions if row["type"] == "Indtægt")

    def get_expense(self):
        return sum(float(row["beloeb"]) for row in self.transactions if row["type"] != "Indtægt")

    def open_transaction_form(self):
        self.show_add_dialog()

    def open_quick_add(self, kind):
        if kind == "Udgift":
            self.show_add_dialog("Udgift", "Udgift")
        elif kind == "Indtægt":
            self.show_add_dialog("Indtægt", "Indtægt")
        elif kind == "Regning":
            self.show_add_dialog("Regning", "Udgift")
        elif kind == "Opsparing":
            self.show_add_dialog("Opsparing", "Udgift")

    def show_add_dialog(self, initial_category="", initial_type="Udgift"):
        def build_content(body):
            tk.Label(body, text="Kategori", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(4, 4))
            category_var = tk.StringVar(value=initial_category)
            entry_category = tk.Entry(body, textvariable=category_var)
            entry_category.pack(fill="x")

            tk.Label(body, text="Beløb", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(10, 4))
            amount_var = tk.StringVar()
            entry_amount = tk.Entry(body, textvariable=amount_var)
            entry_amount.pack(fill="x")

            tk.Label(body, text="Type", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", pady=(10, 4))
            type_var = tk.StringVar(value=initial_type)
            combo = ttk.Combobox(body, textvariable=type_var, values=["Indtægt", "Udgift"], state="readonly")
            combo.pack(fill="x")

            def save():
                kategori = category_var.get().strip()
                beloeb_text = amount_var.get().strip()
                typ = type_var.get()
                if not kategori or not beloeb_text:
                    messagebox.showerror("Fejl", "Udfyld kategori og beløb")
                    return
                try:
                    beloeb = float(beloeb_text)
                except ValueError:
                    messagebox.showerror("Fejl", "Beløbet skal være et tal")
                    return
                self.service.save_transaction(
                    self.current_user_id,
                    str(date.today()),
                    kategori,
                    beloeb,
                    typ,
                )
                self.load_transactions()
                self.refresh_notifications()
                self.close_active_panel()
                self.show_page(self.current_page, force=True)

            tk.Button(body, text="Gem", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=8, relief="flat", command=save).pack(pady=(16, 8))

        self.show_modal_panel("Tilføj transaktion", build_content, width=360)

    def refresh_notifications(self):
        started_at = time.perf_counter()
        user_id = self.current_user_id

        def worker():
            worker_started_at = time.perf_counter()
            try:
                rows = self.service.get_notifications(user_id)
                now_ts = int(time.time())
                last_status_ts = int(self.service.get_setting("last_budget_status_ts", "0") or "0")
                if now_ts - last_status_ts >= 3600:
                    self.service.save_notification(
                        user_id,
                        "Budget status",
                        "Din saldo er stabil og klar til næste uge",
                        "info",
                    )
                    self.service.save_setting("last_budget_status_ts", str(now_ts))
                    rows = self.service.get_notifications(user_id)
            except Exception as exc:
                def on_error():
                    messagebox.showerror("Fejl", f"Kunne ikke opdatere notifikationer: {exc}")
                self.after(0, on_error)
                return

            def on_success():
                self.notifications = rows
                self.alert_count = sum(1 for notification in self.notifications if notification["read"] == 0)
                self.update_notification_badge()

            self.after(0, on_success)
            self._perf_log("refresh_notifications_worker", worker_started_at)

        threading.Thread(target=worker, daemon=True).start()
        self._perf_log("refresh_notifications_dispatch", started_at)

    def save_notification(self, title, message, kind):
        self.service.save_notification(self.current_user_id, title, message, kind)

    def open_notifications(self):
        def build_content(body):
            for notification in self.notifications:
                frame = tk.Frame(body, bg=self.colors["surface_2"], highlightthickness=1, highlightbackground=self.colors["border"])
                frame.pack(fill="x", pady=6)
                tk.Label(frame, text=notification["title"], bg=self.colors["surface_2"], fg=self.colors["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
                tk.Label(frame, text=notification["message"], bg=self.colors["surface_2"], fg=self.colors["muted"]).pack(anchor="w", padx=10, pady=(0, 8))
            tk.Button(body, text="Markér alle som læst", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=8, relief="flat", command=self.mark_all_read).pack(pady=(10, 0))

        self.show_modal_panel("Notifikationer", build_content, width=380)

    def mark_all_read(self):
        self.service.mark_all_notifications_read(self.current_user_id)
        self.load_notifications()
        self.close_active_panel()

    def logout(self):
        self.cancel_scheduled_jobs()
        if self.session_token:
            self.service.logout_user(self.session_token)
        self.service.save_setting("session_token", "")
        self.current_user = None
        self.current_user_id = None
        self.session_token = ""
        self.household = None
        self.household_member = False
        self.transactions = []
        self.notifications = []
        self.alert_count = 0
        self.show_auth_screen()

    def open_fab_menu(self):
        def build_content(body):
            for label, kind in [("Ny udgift", "Udgift"), ("Ny indtægt", "Indtægt"), ("Ny regning", "Regning"), ("Ny opsparing", "Opsparing")]:
                btn = tk.Button(body, text=label, bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=10, pady=8, relief="flat", command=lambda k=kind: self.open_quick_add(k))
                btn.pack(fill="x", pady=4)

        self.show_modal_panel("Hurtige handlinger", build_content, width=260)

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.colors = self.get_theme_colors(self.theme)
        self.save_setting("theme", self.theme)
        self.create_styles()
        self.destroy_ui_and_rebuild()

    def confirm_delete_account(self):
        if messagebox.askyesno("Slet konto", "Er du sikker på, at du vil slette kontoen?"):
            messagebox.showinfo("Konto", "Kontoen er markeret til sletning.")

    def start_update_check(self):
        self.update_manager.check_for_update_async(self.handle_update_result)

    def handle_update_result(self, update_info):
        if not update_info:
            return
        if self.skip_update_version == update_info.version:
            return
        self.after(0, lambda: self.prompt_for_update(update_info))

    def prompt_for_update(self, update_info):
        if not update_info or self.update_in_progress:
            return

        def build_content(body):
            tk.Label(body, text="Der er en ny version tilgængelig", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(4, 8))
            tk.Label(body, text=f"Version {update_info.version} er klar. Vil du opdatere nu?", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", pady=(0, 16))

            button_frame = tk.Frame(body, bg=self.colors["surface"])
            button_frame.pack(fill="x")

            def update_now():
                self.close_active_panel()
                self.download_and_install_update(update_info)

            def update_later():
                self.save_setting("skip_update_version", update_info.version)
                self.skip_update_version = update_info.version
                self.close_active_panel()

            tk.Button(button_frame, text="Opdater nu", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=8, relief="flat", command=update_now).pack(side="left")
            tk.Button(button_frame, text="Senere", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=12, pady=8, relief="flat", command=update_later).pack(side="left", padx=(10, 0))

        self.show_modal_panel("Ny version tilgængelig", build_content, width=420)

    def download_and_install_update(self, update_info):
        if self.update_in_progress:
            return
        self.update_in_progress = True

        def worker():
            downloaded_path = self.update_manager.download_update(update_info)
            if not downloaded_path:
                self.after(0, lambda: messagebox.showerror("Opdatering fejlede", "Ny version kunne ikke hentes. Prøv igen senere."))
                self.update_in_progress = False
                return

            if self.update_manager.install_update(downloaded_path):
                self.after(0, lambda: messagebox.showinfo("Opdatering starter", "FamilBudget lukker og installerer den nye version."))
                self.after(0, self.destroy)
                return

            self.after(0, lambda: messagebox.showerror("Opdatering fejlede", "Installationen kunne ikke startes."))
            self.update_in_progress = False

        threading.Thread(target=worker, daemon=True).start()

    def destroy_ui_and_rebuild(self):
        self.clear_root()
        if self.current_user is not None:
            self.build_ui()
            self.load_transactions()
            self.load_notifications()
            self.show_page(self.current_page, force=True)
        else:
            self.show_auth_screen()


def main() -> int:
    args = parse_args()
    if args.self_update and args.source_path and args.target_path:
        run_self_update(args.source_path, args.target_path)
        return 0

    app = FamilBudgetApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())