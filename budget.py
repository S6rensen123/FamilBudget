import sqlite3
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

from updater import parse_args, run_self_update
from update_manager import UpdateManager
from version import APP_VERSION


class FamilBudgetApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FamilBudget")
        self.geometry("480x920")
        self.minsize(420, 760)
        self.configure(bg="#F8FAFC")

        self.conn = sqlite3.connect("budget.db")
        self.cursor = self.conn.cursor()
        self.init_db()

        self.current_page = "oversigt"
        self.theme = self.get_setting("theme", "light")
        self.user_name = self.get_setting("user_name", "Maja")
        self.household_member = self.get_setting("household_member", "0") == "1"
        self.transactions = []
        self.notifications = []
        self.alert_count = 0
        self.active_overlay = None
        self.active_panel = None
        self.update_manager = UpdateManager(APP_VERSION)
        self.update_in_progress = False
        self.skip_update_version = self.get_setting("skip_update_version", "")

        self.colors = self.get_theme_colors(self.theme)
        self.create_styles()
        self.build_ui()
        self.load_transactions()
        self.load_notifications()
        self.show_page(self.current_page)
        self.after(800, self.refresh_notifications)
        self.after(1200, self.start_update_check)

    def init_db(self):
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dato TEXT,
                kategori TEXT,
                beloeb REAL,
                type TEXT
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                message TEXT,
                kind TEXT,
                read INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        self.conn.commit()

    def get_setting(self, key, default):
        self.cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = self.cursor.fetchone()
        return row[0] if row else default

    def save_setting(self, key, value):
        self.cursor.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

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

    def build_ui(self):
        self.configure(bg=self.colors["background"])
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.top_bar = tk.Frame(self, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"])
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        self.top_bar.columnconfigure(1, weight=1)

        self.app_title = tk.Label(self.top_bar, text="FamilBudget", font=("Segoe UI", 16, "bold"), bg=self.colors["surface"], fg=self.colors["text"])
        self.app_title.grid(row=0, column=0, sticky="w", padx=12, pady=12)

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
        self.notification_button.grid(row=0, column=2, padx=(8, 12), pady=12)
        self.bind_hover(self.notification_button, self.colors["surface_2"], self.colors["chip"])

        self.balance_bar = tk.Frame(self, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"])
        self.balance_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.balance_bar.columnconfigure(0, weight=1)
        self.balance_bar.columnconfigure(1, weight=1)

        self.balance_label = tk.Label(self.balance_bar, text="Saldo", font=("Segoe UI", 10), bg=self.colors["surface"], fg=self.colors["muted"])
        self.balance_label.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.balance_value = tk.Label(self.balance_bar, text="0,00 kr", font=("Segoe UI", 18, "bold"), bg=self.colors["surface"], fg=self.colors["text"])
        self.balance_value.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        self.savings_label = tk.Label(self.balance_bar, text="Månedens udvikling", font=("Segoe UI", 10), bg=self.colors["surface"], fg=self.colors["muted"])
        self.savings_label.grid(row=0, column=1, sticky="e", padx=12, pady=(10, 2))
        self.savings_value = tk.Label(self.balance_bar, text="+8,4%", font=("Segoe UI", 14, "bold"), bg=self.colors["surface"], fg=self.colors["success"])
        self.savings_value.grid(row=1, column=1, sticky="e", padx=12, pady=(0, 10))

        self.canvas_frame = tk.Frame(self, bg=self.colors["background"])
        self.canvas_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.rowconfigure(2, weight=1)
        self.canvas = tk.Canvas(self.canvas_frame, bg=self.colors["background"], highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas_scroll = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas_scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.canvas_scroll.set)
        self.canvas_content = tk.Frame(self.canvas, bg=self.colors["background"])
        self.canvas_window = self.canvas.create_window((0, 0), window=self.canvas_content, anchor="nw")
        self.canvas_content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        self.canvas_frame.columnconfigure(0, weight=1)
        self.canvas_frame.rowconfigure(0, weight=1)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self.nav_frame = tk.Frame(self, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"])
        self.nav_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.nav_frame.columnconfigure(0, weight=1)
        self.nav_frame.columnconfigure(1, weight=1)
        self.nav_frame.columnconfigure(2, weight=1)
        self.nav_frame.columnconfigure(3, weight=1)
        self.nav_frame.columnconfigure(4, weight=1)

        pages = [
            ("Oversigt", "oversigt"),
            ("Budget", "budget"),
            ("Kalender", "kalender"),
            ("Husstand", "husstand"),
            ("Profil", "profil"),
        ]
        for i, (label, page) in enumerate(pages):
            btn = tk.Button(
                self.nav_frame,
                text=label,
                bg=self.colors["surface"],
                fg=self.colors["text"],
                bd=0,
                padx=4,
                pady=10,
                relief="flat",
                command=lambda p=page: self.show_page(p),
            )
            btn.grid(row=0, column=i, sticky="nsew", padx=3)
            self.bind_hover(btn, self.colors["surface"], self.colors["surface_2"])
            if page == self.current_page:
                btn.configure(bg=self.colors["chip"], fg=self.colors["primary"])

        self.fab = tk.Button(
            self,
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

    def show_page(self, page):
        self.current_page = page
        self.close_active_panel()
        self.clear_content()
        self.show_skeleton()
        self.after(350, self.render_page)
        self.update_nav_state()

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

    def update_nav_state(self):
        for child in self.nav_frame.winfo_children():
            if isinstance(child, tk.Button):
                child.configure(bg=self.colors["surface"], fg=self.colors["text"])
        for child in self.nav_frame.winfo_children():
            if isinstance(child, tk.Button):
                label = child.cget("text")
                if label == self.page_label(self.current_page):
                    child.configure(bg=self.colors["chip"], fg=self.colors["primary"])

    def page_label(self, page):
        return {
            "oversigt": "Oversigt",
            "budget": "Budget",
            "kalender": "Kalender",
            "husstand": "Husstand",
            "profil": "Profil",
        }[page]

    def load_transactions(self):
        self.cursor.execute("SELECT id, dato, kategori, beloeb, type FROM transactions ORDER BY id DESC")
        self.transactions = self.cursor.fetchall()

    def load_notifications(self):
        self.cursor.execute("SELECT title, message, kind, read FROM notifications ORDER BY id DESC LIMIT 8")
        self.notifications = self.cursor.fetchall()
        self.alert_count = sum(1 for _, _, _, read in self.notifications if read == 0)
        self.update_notification_badge()

    def update_notification_badge(self):
        if hasattr(self, "notification_button"):
            self.notification_button.configure(text=f"🔔 {self.alert_count}")

    def update_balance_display(self):
        saldo = 0.0
        for _, _, _, beloeb, tipo in self.transactions:
            if tipo == "Indtægt":
                saldo += beloeb
            else:
                saldo -= beloeb
        self.balance_value.configure(text=f"{saldo:,.2f} kr")
        self.savings_value.configure(text="+8,4%")
        self.balance_bar.configure(bg=self.colors["surface"])

    def render_dashboard(self):
        title_frame = tk.Frame(self.canvas_content, bg=self.colors["background"])
        title_frame.pack(fill="x", padx=8, pady=(8, 10))
        tk.Label(title_frame, text=f"Hej {self.user_name} 👋", font=("Segoe UI", 20, "bold"), bg=self.colors["background"], fg=self.colors["text"]).pack(anchor="w")
        tk.Label(title_frame, text="Din økonomi ser stabil ud", font=("Segoe UI", 12), bg=self.colors["background"], fg=self.colors["muted"]).pack(anchor="w", pady=(2, 0))

        premium_card = tk.Frame(self.canvas_content, bg=self.colors["primary"], highlightthickness=0)
        premium_card.pack(fill="x", padx=8, pady=(0, 12))
        premium_card.columnconfigure(0, weight=1)
        tk.Label(premium_card, text="Samlet saldo", font=("Segoe UI", 11), bg=self.colors["primary"], fg="white").grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))
        tk.Label(premium_card, text=f"{self.get_balance():,.2f} kr", font=("Segoe UI", 24, "bold"), bg=self.colors["primary"], fg="white").grid(row=1, column=0, sticky="w", padx=16, pady=(0, 4))
        tk.Label(premium_card, text="+ 12,4 % siden sidste måned", font=("Segoe UI", 10), bg=self.colors["primary"], fg="#DBEAFE").grid(row=2, column=0, sticky="w", padx=16, pady=(0, 16))

        icon = tk.Label(premium_card, text="💳", font=("Segoe UI", 24), bg=self.colors["primary"], fg="white")
        icon.grid(row=0, column=1, rowspan=3, padx=16, pady=16)

        actions_frame = tk.Frame(self.canvas_content, bg=self.colors["background"])
        actions_frame.pack(fill="x", padx=8, pady=(0, 12))
        actions_frame.columnconfigure(0, weight=1)
        actions_frame.columnconfigure(1, weight=1)
        actions_frame.columnconfigure(2, weight=1)
        actions_frame.columnconfigure(3, weight=1)

        action_labels = [
            ("Ny udgift", "Udgift"),
            ("Ny indtægt", "Indtægt"),
            ("Ny regning", "Regning"),
            ("Ny opsparing", "Opsparing"),
        ]
        for index, (label, kind) in enumerate(action_labels):
            btn = tk.Button(
                actions_frame,
                text=label,
                bg=self.colors["surface"],
                fg=self.colors["text"],
                bd=0,
                padx=8,
                pady=12,
                relief="flat",
                command=lambda kind=kind: self.open_quick_add(kind),
            )
            btn.grid(row=0, column=index, sticky="nsew", padx=4)
            self.bind_hover(btn, self.colors["surface"], self.colors["surface_2"])

        ai_frame = self.create_card(self.canvas_content, "AI-indsigt", "Din økonomi får en professionel coach-oplevelse")
        ai_frame.pack(fill="x", padx=8, pady=(0, 8))
        for item in [
            "Du bruger 12 % mindre på mad",
            "Din økonomi ser stabil ud",
            "Mulig besparelse: 450 kr/md",
        ]:
            tk.Label(ai_frame, text=f"• {item}", font=("Segoe UI", 11), bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", padx=16, pady=4)

        upcoming = self.create_card(self.canvas_content, "Kommende betalinger", "Hold styr på det næste")
        upcoming.pack(fill="x", padx=8, pady=(0, 8))
        for label, amount in [("Husleje", "3.500 kr"), ("El", "890 kr")]:
            row = tk.Frame(upcoming, bg=self.colors["surface"])
            row.pack(fill="x", padx=16, pady=6)
            tk.Label(row, text=label, bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w")
            tk.Label(row, text=amount, bg=self.colors["surface"], fg=self.colors["danger"]).pack(anchor="e")

        incomes = self.create_card(self.canvas_content, "Kommende indtægter", "Næste indbetalinger")
        incomes.pack(fill="x", padx=8, pady=(0, 8))
        for label, amount in [("Løn", "24.000 kr"), ("Børnebidrag", "4.800 kr")]:
            row = tk.Frame(incomes, bg=self.colors["surface"])
            row.pack(fill="x", padx=16, pady=6)
            tk.Label(row, text=label, bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w")
            tk.Label(row, text=amount, bg=self.colors["surface"], fg=self.colors["success"]).pack(anchor="e")

        saving = self.create_card(self.canvas_content, "Opsparingsstatus", "Din plan er på sporet")
        saving.pack(fill="x", padx=8, pady=(0, 8))
        tk.Label(saving, text="Ferie: 82 % af mål", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", padx=16, pady=6)
        tk.Label(saving, text="Opsparing: 8.400 kr", bg=self.colors["surface"], fg=self.colors["primary"]).pack(anchor="w", padx=16, pady=6)

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
            tree.insert("", tk.END, values=row)

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
        if not self.household_member:
            tk.Label(card, text="Du er endnu ikke medlem af en husstand", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
            tk.Label(card, text="Opret en ny husstand eller tilslut med en kode", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=(0, 16))
            btn1 = tk.Button(card, text="Opret husstand", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=10, relief="flat", command=lambda: self.set_household_state(True))
            btn1.pack(anchor="w", padx=16, pady=4)
            btn2 = tk.Button(card, text="Tilslut med kode", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=12, pady=10, relief="flat", command=lambda: self.set_household_state(True))
            btn2.pack(anchor="w", padx=16, pady=4)
            return

        tk.Label(card, text="Familiehusstand", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(card, text="Administrator: Maja", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text="Medlemsantal: 4", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text="Delingskode: FAM-4821", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text="Oprettet: 12. april 2025", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=(2, 16))

        actions = tk.Frame(card, bg=self.colors["surface"])
        actions.pack(fill="x", padx=16, pady=(0, 12))
        for label in ["Kopiér kode", "Del kode", "Generér ny kode", "Vis QR-kode"]:
            btn = tk.Button(actions, text=label, bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=8, pady=8, relief="flat")
            btn.pack(anchor="w", pady=4)

        members = self.create_card(self.canvas_content, "Medlemmer", "Medlemmerne er samlet i moderne profiler")
        members.pack(fill="x", padx=8, pady=(0, 8))
        for name, role, email in [("Maja", "Administrator", "maja@familbudget.dk"), ("Lars", "Medlem", "lars@familbudget.dk")]:
            row = tk.Frame(members, bg=self.colors["surface"])
            row.pack(fill="x", padx=16, pady=8)
            tk.Label(row, text=name, bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(row, text=f"{role} • {email}", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w")

    def render_profile_page(self):
        card = self.create_card(self.canvas_content, "Profil", "Personlige indstillinger")
        card.pack(fill="x", padx=8, pady=(8, 8))
        avatar = tk.Label(card, text="MJ", bg=self.colors["primary"], fg="white", font=("Segoe UI", 16, "bold"))
        avatar.pack(anchor="w", padx=16, pady=(16, 8))
        tk.Label(card, text=self.user_name, bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16)
        tk.Label(card, text="Fødselsdato: 12.04.1992", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text="E-mail: maja@familbudget.dk", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text="Telefon: +45 12 34 56 78", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=2)
        tk.Label(card, text="Rolle: Administrator", bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=(2, 16))

        settings = self.create_card(self.canvas_content, "Indstillinger", "Justér appen efter dine behov")
        settings.pack(fill="x", padx=8, pady=(0, 8))
        tk.Label(settings, text="Kontoindstillinger", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", padx=16, pady=(10, 4))
        tk.Label(settings, text="Temaindstillinger", bg=self.colors["surface"], fg=self.colors["text"]).pack(anchor="w", padx=16, pady=4)
        theme_btn = tk.Button(settings, text="Skift tema", bg=self.colors["surface_2"], fg=self.colors["text"], bd=0, padx=10, pady=8, relief="flat", command=self.toggle_theme)
        theme_btn.pack(anchor="w", padx=16, pady=(4, 10))
        delete_btn = tk.Button(settings, text="Slet konto", bg=self.colors["danger"], fg="white", bd=0, padx=10, pady=8, relief="flat", command=self.confirm_delete_account)
        delete_btn.pack(anchor="w", padx=16, pady=(0, 10))

    def create_card(self, parent, title, subtitle=""):
        card = tk.Frame(parent, bg=self.colors["surface"], highlightthickness=1, highlightbackground=self.colors["border"])
        if title:
            tk.Label(card, text=title, bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        if subtitle:
            tk.Label(card, text=subtitle, bg=self.colors["surface"], fg=self.colors["muted"]).pack(anchor="w", padx=16, pady=(0, 8))
        return card

    def get_balance(self):
        saldo = 0.0
        for _, _, _, beloeb, tipo in self.transactions:
            if tipo == "Indtægt":
                saldo += beloeb
            else:
                saldo -= beloeb
        return saldo

    def get_income(self):
        return sum(beloeb for _, _, _, beloeb, tipo in self.transactions if tipo == "Indtægt")

    def get_expense(self):
        return sum(beloeb for _, _, _, beloeb, tipo in self.transactions if tipo != "Indtægt")

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
                self.cursor.execute(
                    "INSERT INTO transactions (dato, kategori, beloeb, type) VALUES (?, ?, ?, ?)",
                    (str(date.today()), kategori, beloeb, typ),
                )
                self.conn.commit()
                self.load_transactions()
                self.refresh_notifications()
                self.close_active_panel()
                self.show_page(self.current_page)

            tk.Button(body, text="Gem", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=8, relief="flat", command=save).pack(pady=(16, 8))

        self.show_modal_panel("Tilføj transaktion", build_content, width=360)

    def refresh_notifications(self):
        self.cursor.execute("SELECT title, message, kind, read FROM notifications ORDER BY id DESC LIMIT 8")
        self.notifications = self.cursor.fetchall()
        self.alert_count = sum(1 for _, _, _, read in self.notifications if read == 0)
        self.update_notification_badge()
        self.save_notification("Budget status", "Din saldo er stabil og klar til næste uge", "info")

    def save_notification(self, title, message, kind):
        self.cursor.execute("SELECT id FROM notifications WHERE title = ? AND message = ?", (title, message))
        if self.cursor.fetchone() is None:
            self.cursor.execute(
                "INSERT INTO notifications (title, message, kind, read, created_at) VALUES (?, ?, ?, ?, ?)",
                (title, message, kind, 0, datetime.now().strftime("%Y-%m-%d %H:%M")),
            )
            self.conn.commit()

    def open_notifications(self):
        def build_content(body):
            for title, message, kind, read in self.notifications:
                frame = tk.Frame(body, bg=self.colors["surface_2"], highlightthickness=1, highlightbackground=self.colors["border"])
                frame.pack(fill="x", pady=6)
                tk.Label(frame, text=title, bg=self.colors["surface_2"], fg=self.colors["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
                tk.Label(frame, text=message, bg=self.colors["surface_2"], fg=self.colors["muted"]).pack(anchor="w", padx=10, pady=(0, 8))
            tk.Button(body, text="Markér alle som læst", bg=self.colors["primary"], fg="white", bd=0, padx=12, pady=8, relief="flat", command=self.mark_all_read).pack(pady=(10, 0))

        self.show_modal_panel("Notifikationer", build_content, width=380)

    def mark_all_read(self):
        self.cursor.execute("UPDATE notifications SET read = 1")
        self.conn.commit()
        self.load_notifications()
        self.close_active_panel()

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

    def set_household_state(self, active):
        self.household_member = active
        self.save_setting("household_member", "1" if active else "0")
        self.show_page("husstand")

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
        for child in self.winfo_children():
            child.destroy()
        self.build_ui()
        self.load_transactions()
        self.load_notifications()
        self.show_page(self.current_page)


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