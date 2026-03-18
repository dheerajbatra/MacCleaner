#!/usr/bin/env python3
"""
MacCleaner — transparent Mac cleaning utility.
All files are previewed before deletion and moved to Trash (not permanently deleted).
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, List, Optional, Tuple

from scanner import AppInfo, AppScanner
from cleaner import Cleaner
from utils import format_size, get_file_size

# ────────────────────────────────────────────────────────────────────────────
# Design tokens
# ────────────────────────────────────────────────────────────────────────────
C = {
    # Backgrounds
    "bg":          "#141416",
    "sidebar":     "#1a1a1c",
    "card":        "#1e1e20",
    "card_alt":    "#1b1b1d",
    "input_bg":    "#252528",
    # Borders / dividers
    "border":      "#2a2a2c",
    "divider":     "#2e2e30",
    # Accents
    "accent":      "#0a84ff",
    "accent_dim":  "#0060d0",
    "danger":      "#ff3b30",
    "danger_dim":  "#c42d24",
    "success":     "#30d158",
    "warning":     "#ff9f0a",
    "purple":      "#bf5af2",
    # Text
    "text":        "#f5f5f7",
    "text2":       "#98989f",
    "text3":       "#505055",
    # Nav
    "nav_hover":   "#222224",
    "nav_active":  "#252528",
    "nav_accent":  "#0a84ff",
}

FONT_TITLE   = ("SF Pro Display", 20, "bold")
FONT_BODY    = ("SF Pro Text",    13)
FONT_SMALL   = ("SF Pro Text",    11)
FONT_MONO    = ("SF Mono",        11)
FONT_CAPTION = ("SF Pro Text",    10)


# ────────────────────────────────────────────────────────────────────────────
# Colour helpers
# ────────────────────────────────────────────────────────────────────────────

def _darken(hex_color: str, f: float = 0.80) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(
        max(0, int(r * f)), max(0, int(g * f)), max(0, int(b * f)))


# ────────────────────────────────────────────────────────────────────────────
# Reusable widgets
# ────────────────────────────────────────────────────────────────────────────

class Btn(tk.Button):
    """Flat button with hover-darken and clean disabled state."""

    def __init__(self, parent, text: str, command,
                 bg: str = "", fg: str = "white",
                 state=tk.NORMAL, **kw):
        self._base  = bg or C["accent"]
        self._hover = _darken(self._base)
        super().__init__(
            parent, text=text, command=command,
            font=FONT_BODY, fg=fg, bg=self._base,
            activeforeground=fg, activebackground=self._hover,
            disabledforeground=C["text3"],
            relief=tk.FLAT, overrelief=tk.FLAT,
            padx=18, pady=7,
            cursor="hand2", state=state,
            highlightthickness=0, bd=0, **kw,
        )
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def _enter(self, _):
        if str(self["state"]) != "disabled":
            self.config(bg=self._hover)

    def _leave(self, _):
        if str(self["state"]) != "disabled":
            self.config(bg=self._base)

    def enable(self):
        self.config(state=tk.NORMAL, bg=self._base)

    def disable(self):
        self.config(state=tk.DISABLED, bg=C["border"])


class Tag(tk.Label):
    """Coloured pill-shaped badge (simulated with padded label)."""

    def __init__(self, parent, text: str, color: str, **kw):
        super().__init__(
            parent, text=f"  {text}  ",
            font=FONT_CAPTION, fg=color,
            bg=C["card"], padx=0, pady=0, **kw,
        )


def divider(parent, pady: int = 0):
    tk.Frame(parent, bg=C["divider"], height=1).pack(
        fill=tk.X, pady=pady)


def label(parent, text: str, font=None, fg: str = "", **kw) -> tk.Label:
    return tk.Label(parent, text=text,
                    font=font or FONT_BODY,
                    fg=fg or C["text"], bg=C["bg"], **kw)


# ────────────────────────────────────────────────────────────────────────────
# Tree helpers
# ────────────────────────────────────────────────────────────────────────────

def _setup_tree_style():
    s = ttk.Style()
    s.configure("Mac.Treeview",
                 background=C["card"], foreground=C["text"],
                 fieldbackground=C["card"],
                 font=FONT_BODY, rowheight=28, borderwidth=0)
    s.map("Mac.Treeview",
          background=[("selected", "#1d3a5a")],
          foreground=[("selected", C["text"])])
    s.configure("Mac.Treeview.Heading",
                 background=C["sidebar"], foreground=C["text2"],
                 font=FONT_SMALL, relief="flat", borderwidth=0)
    # Remove the dotted focus rectangle on rows
    s.layout("Mac.Treeview", [("Mac.Treeview.treearea", {"sticky": "nswe"})])


def make_tree(parent, col_cfg: Dict) -> ttk.Treeview:
    cols = col_cfg.get("cols", [])
    tree = ttk.Treeview(parent, style="Mac.Treeview",
                        columns=cols, selectmode="extended")
    tree.column("#0", width=col_cfg.get("#0_w", 280),
                minwidth=120, stretch=True)
    tree.heading("#0", text=col_cfg.get("#0_lbl", "Name"), anchor=tk.W)
    for c in cols:
        tree.column(c, width=col_cfg.get(f"{c}_w", 110),
                    anchor=col_cfg.get(f"{c}_anc", tk.W),
                    stretch=(c == cols[-1]))
        tree.heading(c, text=col_cfg.get(f"{c}_lbl", c), anchor=tk.W)
    # Row colour tags
    tree.tag_configure("cat",    background=C["sidebar"],
                       font=("SF Pro Text", 11, "bold"), foreground=C["text2"])
    tree.tag_configure("even",   background=C["card"])
    tree.tag_configure("odd",    background=C["card_alt"])
    tree.tag_configure("danger", foreground=C["danger"])
    tree.tag_configure("dim",    foreground=C["text2"])
    return tree


def attach_sb(frame: tk.Frame, tree: ttk.Treeview):
    sb = tk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview,
                      bg=C["sidebar"], troughcolor=C["card"],
                      width=8, relief=tk.FLAT, bd=0)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)


# ────────────────────────────────────────────────────────────────────────────
# Section header
# ────────────────────────────────────────────────────────────────────────────

def section_hdr(parent: tk.Frame, icon: str, title: str, subtitle: str = ""):
    f = tk.Frame(parent, bg=C["bg"])
    f.pack(fill=tk.X, padx=28, pady=(22, 0))
    row = tk.Frame(f, bg=C["bg"])
    row.pack(fill=tk.X)
    tk.Label(row, text=icon, font=("SF Pro Text", 22),
             bg=C["bg"], fg=C["text"]).pack(side=tk.LEFT, padx=(0, 10))
    tk.Label(row, text=title, font=FONT_TITLE,
             fg=C["text"], bg=C["bg"]).pack(side=tk.LEFT)
    if subtitle:
        tk.Label(f, text=subtitle, font=FONT_SMALL,
                 fg=C["text2"], bg=C["bg"]).pack(anchor=tk.W, pady=(4, 0))
    divider(parent, pady=(14, 0))


# ────────────────────────────────────────────────────────────────────────────
# Panel: App Uninstaller
# ────────────────────────────────────────────────────────────────────────────

class AppUninstallerPanel:

    def __init__(self, parent: tk.Frame, status_var: tk.StringVar):
        self.parent      = parent
        self.status_var  = status_var
        self.scanner     = AppScanner()
        self.cleaner     = Cleaner()

        self._all_apps:       List[AppInfo] = []
        self._displayed_apps: List[AppInfo] = []
        self._selected_app:   Optional[AppInfo] = None
        self._remnants:       Dict[str, List[str]] = {}

        self._build()

    # ── Layout ──────────────────────────────────────────────────────── #

    def _build(self):
        section_hdr(self.parent, "🗑", "App Uninstaller",
                    "Select an app → Scan → review all leftover files → delete.")

        pw = tk.PanedWindow(self.parent, bg=C["divider"],
                            sashwidth=1, orient=tk.HORIZONTAL,
                            sashrelief=tk.FLAT)
        pw.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
        pw.add(self._left_pane(pw),  minsize=250)
        pw.add(self._right_pane(pw), minsize=460)

    def _left_pane(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=C["card"])

        # ── search ── #
        sf = tk.Frame(frame, bg=C["card"], pady=10)
        sf.pack(fill=tk.X, padx=10)
        self._search_var = tk.StringVar()
        self._search_e = tk.Entry(
            sf, textvariable=self._search_var,
            font=FONT_BODY, bg=C["input_bg"], fg=C["text2"],
            insertbackground=C["text"],
            relief=tk.FLAT, bd=7, highlightthickness=0,
        )
        self._search_e.insert(0, "Search apps…")
        self._search_e.pack(fill=tk.X)
        self._search_e.bind("<FocusIn>",  self._search_in)
        self._search_e.bind("<FocusOut>", self._search_out)
        self._search_var.trace_add("write", lambda *_: self._filter())

        # ── app listbox ── #
        lf = tk.Frame(frame, bg=C["card"])
        lf.pack(fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(lf, bg=C["sidebar"], troughcolor=C["card"],
                          width=8, relief=tk.FLAT, bd=0)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._lb = tk.Listbox(
            lf, font=FONT_BODY,
            bg=C["card"], fg=C["text"],
            selectbackground="#1d3a5a", selectforeground=C["text"],
            relief=tk.FLAT, bd=0, highlightthickness=0,
            activestyle="none", yscrollcommand=sb.set,
        )
        self._lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._lb.yview)
        self._lb.bind("<<ListboxSelect>>", self._on_select)

        # ── footer ── #
        ff = tk.Frame(frame, bg=C["card"], pady=8)
        ff.pack(fill=tk.X, padx=10)
        Btn(ff, "↻  Refresh", self._load_apps, bg=C["input_bg"],
            fg=C["text2"]).pack(fill=tk.X)

        threading.Thread(target=self._load_apps, daemon=True).start()
        return frame

    def _right_pane(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=C["bg"])

        # status label
        self._info = tk.Label(
            frame,
            text="Select an app from the list, then click Scan.",
            font=FONT_SMALL, fg=C["text2"], bg=C["bg"],
            anchor=tk.W, padx=4,
        )
        self._info.pack(fill=tk.X, padx=12, pady=(10, 4))

        # legend row
        leg = tk.Frame(frame, bg=C["bg"])
        leg.pack(fill=tk.X, padx=12, pady=(0, 8))
        for dot, txt in [(C["danger"], "App bundle (.app)"),
                         (C["warning"], "Support files / caches / dotfiles")]:
            tk.Label(leg, text="●", fg=dot, bg=C["bg"],
                     font=FONT_CAPTION).pack(side=tk.LEFT, padx=(0, 3))
            tk.Label(leg, text=txt + "    ", fg=C["text3"], bg=C["bg"],
                     font=FONT_CAPTION).pack(side=tk.LEFT)

        # tree
        tf_wrap = tk.Frame(frame, bg=C["border"], padx=1, pady=1)
        tf_wrap.pack(fill=tk.BOTH, expand=True, padx=12)
        tf = tk.Frame(tf_wrap, bg=C["card"])
        tf.pack(fill=tk.BOTH, expand=True)
        self._tree = make_tree(tf, {
            "cols": ["size", "path"],
            "#0_w": 280, "#0_lbl": "File / Group",
            "size_w": 85,  "size_lbl": "Size", "size_anc": tk.E,
            "path_w": 430, "path_lbl": "Full Path",
        })
        attach_sb(tf, self._tree)

        # action bar
        af = tk.Frame(frame, bg=C["bg"], pady=10)
        af.pack(fill=tk.X, padx=12)

        self._scan_btn = Btn(af, "Scan for leftovers",
                             self._scan_app, state=tk.DISABLED)
        self._scan_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._del_all_btn = Btn(af, "🗑  Uninstall (move to Trash)",
                                self._delete_all,
                                bg=C["danger"], state=tk.DISABLED)
        self._del_all_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._del_sel_btn = Btn(af, "Move selected",
                                self._delete_selected,
                                bg=C["danger"], state=tk.DISABLED)
        self._del_sel_btn.pack(side=tk.LEFT)

        tk.Label(af, text="↑ Goes to Trash — fully recoverable",
                 font=FONT_CAPTION, fg=C["success"],
                 bg=C["bg"]).pack(side=tk.RIGHT, padx=6)
        return frame

    # ── Data ─────────────────────────────────────────────────────────── #

    def _search_in(self, _):
        if self._search_e.get() == "Search apps…":
            self._search_e.delete(0, tk.END)
            self._search_e.config(fg=C["text"])

    def _search_out(self, _):
        if not self._search_e.get():
            self._search_e.insert(0, "Search apps…")
            self._search_e.config(fg=C["text2"])

    def _load_apps(self):
        self.status_var.set("Scanning /Applications…")
        self._all_apps = self.scanner.get_installed_apps()
        self.parent.after(0, self._refresh)

    def _refresh(self):
        self._filter()
        self.status_var.set(f"{len(self._all_apps)} apps found.")

    def _filter(self):
        q = self._search_var.get().lower()
        if q in ("", "search apps…"):
            self._displayed_apps = list(self._all_apps)
        else:
            self._displayed_apps = [a for a in self._all_apps
                                    if q in a.name.lower()]
        self._lb.delete(0, tk.END)
        for a in self._displayed_apps:
            ver = f"  {a.version}" if a.version else ""
            self._lb.insert(tk.END, f"  {a.name}{ver}   {format_size(a.size)}")

    def _on_select(self, _):
        sel = self._lb.curselection()
        if not sel or sel[0] >= len(self._displayed_apps):
            return
        self._selected_app = self._displayed_apps[sel[0]]
        self._scan_btn.enable()
        self._del_all_btn.disable()
        self._del_sel_btn.disable()
        self._info.config(
            text=f"{self._selected_app.name}  —  click 'Scan for leftovers' to continue."
        )
        for i in self._tree.get_children():
            self._tree.delete(i)
        self._remnants = {}

    # ── Scan ─────────────────────────────────────────────────────────── #

    def _scan_app(self):
        if not self._selected_app:
            return
        self._scan_btn.config(state=tk.DISABLED, text="Scanning…",
                              bg=C["border"])
        self.status_var.set(f"Scanning {self._selected_app.name}…")
        app = self._selected_app

        def do():
            remnants = self.scanner.find_app_remnants(app)
            self.parent.after(0, lambda: self._show(app, remnants))

        threading.Thread(target=do, daemon=True).start()

    def _show(self, app: AppInfo, remnants: Dict[str, List[str]]):
        for i in self._tree.get_children():
            self._tree.delete(i)

        self._remnants = remnants
        total_files = 0
        total_size  = 0

        # App bundle — always shown, always deletable
        bn = self._tree.insert("", "end",
                               text="  App Bundle (.app)",
                               values=("", ""),
                               open=True, tags=("cat",))
        self._tree.insert(bn, "end",
                          text=f"  {os.path.basename(app.path)}",
                          values=(format_size(app.size), app.path),
                          tags=("danger",))
        total_size += app.size
        total_files += 1

        # Leftover groups
        for cat, files in remnants.items():
            cat_size = sum(get_file_size(f) for f in files)
            cn = self._tree.insert("", "end",
                                   text=f"  {cat}",
                                   values=(format_size(cat_size), ""),
                                   open=True, tags=("cat",))
            for i, fp in enumerate(files):
                sz = get_file_size(fp)
                total_size  += sz
                total_files += 1
                self._tree.insert(cn, "end",
                                  text=f"  {os.path.basename(fp)}",
                                  values=(format_size(sz), fp),
                                  tags=("even" if i % 2 == 0 else "odd",))

        # Status message
        if len(remnants) == 0:
            self._tree.insert("", "end",
                              text="  ✓  No leftover files — app is clean",
                              values=("", ""), tags=("dim",))
            self._info.config(
                text=f"{app.name}  —  no leftover files found. "
                     f"You can still uninstall the .app below."
            )
        else:
            extra = total_files - 1
            self._info.config(
                text=f"{app.name}  —  {extra} leftover file(s), "
                     f"{format_size(total_size - app.size)} extra. "
                     f"Review, then delete."
            )

        # Always enable delete after scan (app bundle is always present)
        self._del_all_btn.enable()
        self._del_sel_btn.enable()
        self._scan_btn.config(state=tk.NORMAL, text="Scan for leftovers",
                              bg=self._scan_btn._base)
        self.status_var.set(
            f"{app.name}  ·  {total_files} items  ·  {format_size(total_size)}"
        )

    # ── Delete ────────────────────────────────────────────────────────── #

    def _leaf_paths(self, items=None) -> List[str]:
        paths: List[str] = []
        for iid in (items or self._tree.get_children()):
            ch = self._tree.get_children(iid)
            if ch:
                paths.extend(self._leaf_paths(ch))
            else:
                v = self._tree.item(iid, "values")
                if v and v[1]:
                    paths.append(v[1])
        return paths

    def _delete_all(self):
        paths = self._leaf_paths()
        if paths:
            self._confirm(paths, f"all {len(paths)} items (including the .app)")

    def _delete_selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Nothing selected",
                                "Click rows to select files first.")
            return
        paths: List[str] = []
        for iid in sel:
            v = self._tree.item(iid, "values")
            if v and v[1]:
                paths.append(v[1])
            for ch in self._tree.get_children(iid):
                cv = self._tree.item(ch, "values")
                if cv and cv[1]:
                    paths.append(cv[1])
        paths = list(dict.fromkeys(paths))
        if paths:
            self._confirm(paths, f"{len(paths)} selected item(s)")

    def _confirm(self, paths: List[str], desc: str):
        preview = "\n".join(f"  • {p}" for p in paths[:12])
        if len(paths) > 12:
            preview += f"\n  … and {len(paths) - 12} more"
        if not messagebox.askyesno(
            "Move to Trash",
            f"Move {desc} to the Trash?\n\n"
            "You can recover them from Trash if needed.\n\n"
            f"{preview}",
            icon="warning",
        ):
            return
        results  = self.cleaner.delete_files(paths)
        ok       = [r for r in results if r[1]]
        fail     = [r for r in results if not r[1]]
        msg      = f"Moved to Trash: {len(ok)}"
        if fail:
            msg += (f"\nFailed (may need admin rights): {len(fail)}"
                    "\n\n" + "\n".join(f"  {r[0]}" for r in fail[:5]))
        messagebox.showinfo("Done", msg)
        self._scan_app()


# ────────────────────────────────────────────────────────────────────────────
# Panel: Generic cleaner (Cache / Log / Orphan)
# ────────────────────────────────────────────────────────────────────────────

class GenericPanel:

    def __init__(self, parent: tk.Frame, status_var: tk.StringVar,
                 icon: str, title: str, subtitle: str,
                 scanner_fn, warning: str = ""):
        self.parent     = parent
        self.status_var = status_var
        self.scanner_fn = scanner_fn
        self.cleaner    = Cleaner()
        self._tree: Optional[ttk.Treeview] = None

        section_hdr(parent, icon, title, subtitle)

        if warning:
            wf = tk.Frame(parent, bg=C["bg"])
            wf.pack(fill=tk.X, padx=28, pady=(10, 0))
            tk.Label(wf, text=f"⚠  {warning}",
                     font=FONT_SMALL, fg=C["warning"],
                     bg=C["bg"]).pack(anchor=tk.W)

        self._build(parent)

    def _build(self, parent):
        # button row
        bf = tk.Frame(parent, bg=C["bg"])
        bf.pack(fill=tk.X, padx=28, pady=12)

        self._scan_btn    = Btn(bf, "Scan", self._scan)
        self._del_sel_btn = Btn(bf, "Move selected to Trash",
                                self._del_sel, bg=C["danger"], state=tk.DISABLED)
        self._del_all_btn = Btn(bf, "🗑  Move ALL to Trash",
                                self._del_all, bg=C["danger"], state=tk.DISABLED)
        self._scan_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._del_sel_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._del_all_btn.pack(side=tk.LEFT)
        tk.Label(bf, text="↑ Goes to Trash — fully recoverable",
                 font=FONT_CAPTION, fg=C["success"],
                 bg=C["bg"]).pack(side=tk.RIGHT, padx=6)

        # tree
        tw = tk.Frame(parent, bg=C["border"], padx=1, pady=1)
        tw.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
        tf = tk.Frame(tw, bg=C["card"])
        tf.pack(fill=tk.BOTH, expand=True)
        self._tree = make_tree(tf, {
            "cols": ["size", "path"],
            "#0_w": 280, "#0_lbl": "Name",
            "size_w": 85,  "size_lbl": "Size",   "size_anc": tk.E,
            "path_w": 520, "path_lbl": "Full Path",
        })
        attach_sb(tf, self._tree)

    # ── Scan ────────────────────────────────────────────────────────── #

    def _scan(self):
        self.status_var.set("Scanning…")
        for i in self._tree.get_children():
            self._tree.delete(i)
        self._del_sel_btn.disable()
        self._del_all_btn.disable()

        def do():
            data = self.scanner_fn()
            self.parent.after(0, lambda: self._populate(data))

        threading.Thread(target=do, daemon=True).start()

    def _populate(self, data: Dict[str, List[Tuple[str, int]]]):
        total_size = 0
        row_idx    = 0
        count      = 0

        for cat, files in data.items():
            cat_size = sum(s for _, s in files)
            total_size += cat_size
            cn = self._tree.insert("", "end",
                                   text=f"  {cat}",
                                   values=(format_size(cat_size), ""),
                                   open=True, tags=("cat",))
            for fp, sz in files:
                count += 1
                tag = "even" if row_idx % 2 == 0 else "odd"
                row_idx += 1
                self._tree.insert(cn, "end",
                                  text=f"  {os.path.basename(fp)}",
                                  values=(format_size(sz), fp),
                                  tags=(tag,))

        if count == 0:
            self._tree.insert("", "end",
                              text="  ✓  Nothing found — all clean",
                              values=("", ""), tags=("dim",))
            self.status_var.set("Nothing found.")
        else:
            self._del_sel_btn.enable()
            self._del_all_btn.enable()
            self.status_var.set(
                f"{count} items  ·  {format_size(total_size)}")

    # ── Delete ───────────────────────────────────────────────────────── #

    def _leaf_paths(self) -> List[str]:
        paths: List[str] = []

        def walk(items):
            for iid in items:
                ch = self._tree.get_children(iid)
                if ch:
                    walk(ch)
                else:
                    v = self._tree.item(iid, "values")
                    if v and v[1]:
                        paths.append(v[1])

        walk(self._tree.get_children())
        return paths

    def _del_all(self):
        p = self._leaf_paths()
        if p:
            self._confirm(p, f"all {len(p)} items")

    def _del_sel(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Nothing selected", "Select rows first.")
            return
        paths: List[str] = []
        for iid in sel:
            v = self._tree.item(iid, "values")
            if v and v[1]:
                paths.append(v[1])
            for ch in self._tree.get_children(iid):
                cv = self._tree.item(ch, "values")
                if cv and cv[1]:
                    paths.append(cv[1])
        paths = list(dict.fromkeys(paths))
        if paths:
            self._confirm(paths, f"{len(paths)} selected item(s)")

    def _confirm(self, paths: List[str], desc: str):
        preview = "\n".join(f"  • {p}" for p in paths[:12])
        if len(paths) > 12:
            preview += f"\n  … and {len(paths) - 12} more"
        if not messagebox.askyesno(
            "Move to Trash",
            f"Move {desc} to the Trash?\n\n{preview}",
            icon="warning",
        ):
            return
        results  = self.cleaner.delete_files(paths)
        ok       = [r for r in results if r[1]]
        fail     = [r for r in results if not r[1]]
        msg      = f"Moved to Trash: {len(ok)}"
        if fail:
            msg += f"\nFailed: {len(fail)}"
        messagebox.showinfo("Done", msg)
        self._scan()


# ────────────────────────────────────────────────────────────────────────────
# App window
# ────────────────────────────────────────────────────────────────────────────

class MacCleanerApp:

    NAV = [
        ("uninstaller", "🗑", "App Uninstaller"),
        ("cache",        "🗂", "Cache Cleaner"),
        ("logs",         "📋", "Log Cleaner"),
        ("orphans",      "🔍", "Orphan Finder"),
    ]

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MacCleaner")
        self.root.geometry("1180x740")
        self.root.minsize(920, 600)
        self.root.configure(bg=C["bg"])

        self._scanner    = AppScanner()
        self._status_var = tk.StringVar(value="Ready.")
        self._nav_rows: Dict[str, Tuple[tk.Frame, tk.Frame, tk.Label, tk.Label]] = {}
        self._current:  Optional[str] = None

        ttk.Style().theme_use("default")
        _setup_tree_style()

        self._build()
        self._go("uninstaller")

    # ── Chrome ───────────────────────────────────────────────────────── #

    def _build(self):
        # ── sidebar ── #
        sb = tk.Frame(self.root, bg=C["sidebar"], width=216)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        sb.pack_propagate(False)

        # logo / brand
        brand = tk.Frame(sb, bg=C["sidebar"])
        brand.pack(fill=tk.X, padx=20, pady=(28, 0))
        tk.Label(brand, text="MacCleaner",
                 font=("SF Pro Display", 14, "bold"),
                 fg=C["text"], bg=C["sidebar"]).pack(anchor=tk.W)
        tk.Label(brand, text="System cleaner",
                 font=FONT_CAPTION, fg=C["text3"],
                 bg=C["sidebar"]).pack(anchor=tk.W, pady=(2, 0))

        divider(sb, pady=(16, 0))

        # section label
        tk.Label(sb, text="TOOLS", font=("SF Pro Text", 9, "bold"),
                 fg=C["text3"], bg=C["sidebar"],
                 padx=20).pack(anchor=tk.W, pady=(12, 4))

        # nav items
        nav_frame = tk.Frame(sb, bg=C["sidebar"])
        nav_frame.pack(fill=tk.X)

        for key, icon, label_text in self.NAV:
            row = tk.Frame(nav_frame, bg=C["sidebar"], cursor="hand2")
            row.pack(fill=tk.X)

            bar = tk.Frame(row, width=3, bg=C["sidebar"])
            bar.pack(side=tk.LEFT, fill=tk.Y)

            ico_lbl = tk.Label(row, text=icon,
                               font=("SF Pro Text", 14),
                               fg=C["text2"], bg=C["sidebar"],
                               padx=10, pady=9, cursor="hand2")
            ico_lbl.pack(side=tk.LEFT)

            txt_lbl = tk.Label(row, text=label_text,
                               font=FONT_BODY,
                               fg=C["text2"], bg=C["sidebar"],
                               anchor=tk.W, pady=9, cursor="hand2")
            txt_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            self._nav_rows[key] = (row, bar, ico_lbl, txt_lbl)

            for w in (row, ico_lbl, txt_lbl):
                w.bind("<Button-1>", lambda e, k=key: self._go(k))
                w.bind("<Enter>",    lambda e, k=key: self._hover(k, True))
                w.bind("<Leave>",    lambda e, k=key: self._hover(k, False))

        # footer
        tk.Frame(sb, bg=C["divider"], height=1).pack(
            side=tk.BOTTOM, fill=tk.X)
        tk.Label(sb,
                 text="All deletions go to Trash.\nNothing is permanent.",
                 font=FONT_CAPTION, fg=C["success"],
                 bg=C["sidebar"], justify=tk.CENTER,
                 wraplength=180).pack(side=tk.BOTTOM, pady=14)

        # ── content ── #
        self._content = tk.Frame(self.root, bg=C["bg"])
        self._content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── status bar ── #
        sb2 = tk.Frame(self.root, bg=C["sidebar"], height=26)
        sb2.pack(side=tk.BOTTOM, fill=tk.X)
        sb2.pack_propagate(False)
        tk.Label(sb2, textvariable=self._status_var,
                 font=FONT_CAPTION, fg=C["text3"],
                 bg=C["sidebar"], padx=16).pack(side=tk.LEFT, pady=4)

    # ── Nav ──────────────────────────────────────────────────────────── #

    def _hover(self, key: str, on: bool):
        if key == self._current:
            return
        row, bar, ico, txt = self._nav_rows[key]
        bg = C["nav_hover"] if on else C["sidebar"]
        for w in (row, ico, txt):
            w.config(bg=bg)

    def _go(self, key: str):
        if key == self._current:
            return
        self._current = key

        for k, (row, bar, ico, txt) in self._nav_rows.items():
            active = (k == key)
            bg  = C["nav_active"] if active else C["sidebar"]
            bar_c = C["nav_accent"] if active else C["sidebar"]
            bar.config(bg=bar_c)
            for w in (row, ico, txt):
                w.config(bg=bg)
            ico.config(fg=C["text"]  if active else C["text2"])
            txt.config(fg=C["text"]  if active else C["text2"],
                       font=("SF Pro Text", 13, "bold" if active else "normal"))

        for w in self._content.winfo_children():
            w.destroy()

        s = self._scanner
        if key == "uninstaller":
            AppUninstallerPanel(self._content, self._status_var)
        elif key == "cache":
            GenericPanel(self._content, self._status_var,
                         "🗂", "Cache Cleaner",
                         "Remove cached data to reclaim disk space.",
                         s.get_cache_files)
        elif key == "logs":
            GenericPanel(self._content, self._status_var,
                         "📋", "Log Cleaner",
                         "Delete old log files — they're regenerated automatically.",
                         s.get_log_files)
        elif key == "orphans":
            GenericPanel(self._content, self._status_var,
                         "🔍", "Orphan Finder",
                         "Find Library entries left behind by uninstalled apps.",
                         s.find_orphaned_files,
                         warning="Review carefully — verify each entry before deleting.")

    def run(self):
        self.root.mainloop()


# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    MacCleanerApp().run()
