import re
import gi

gi.require_version("Xed", "1.0")

from gi.repository import GObject, Gio, Xed, Gtk


ACTION_NAME = "reverse_selection"
MENU_LABEL = "DNA"
MENU_ITEM_LABEL = "Reverse Selection"
SHORTCUT = "<Primary><Alt>R"


class InvertSelectionWindowActivatable(GObject.Object, Xed.WindowActivatable):
    __gtype_name__ = "InvertSelectionWindowActivatable"

    window = GObject.Property(type=Xed.Window)

    def __init__(self):
        super().__init__()
        self._action = None
        self._focus_handler_id = None
        self._notify_handler_id = None

        self._dna_menu_item = None
        self._reverse_menu_item = None
        self._menu_bar = None

    def do_activate(self):
        self._action = Gio.SimpleAction.new(ACTION_NAME, None)
        self._action.connect("activate", self.on_reverse_selection)
        self._action.set_enabled(True)
        self.window.add_action(self._action)

        try:
            self._focus_handler_id = self.window.connect(
                "focus-in-event",
                self.on_focus_in_event,
            )
        except TypeError:
            self._focus_handler_id = None

        try:
            self._notify_handler_id = self.window.connect(
                "notify::is-active",
                self.on_window_active_changed,
            )
        except TypeError:
            self._notify_handler_id = None

        self._ensure_shortcut_registered()
        self._add_menu_items()

    def do_deactivate(self):
        if self._focus_handler_id is not None:
            self.window.disconnect(self._focus_handler_id)
            self._focus_handler_id = None

        if self._notify_handler_id is not None:
            self.window.disconnect(self._notify_handler_id)
            self._notify_handler_id = None

        self._remove_menu_items()

        if self._action is not None:
            self.window.remove_action(ACTION_NAME)
            self._action = None

        app = self.window.get_application()
        if app is not None:
            app.set_accels_for_action(f"win.{ACTION_NAME}", [])

    def do_update_state(self):
        if self._action is None:
            return

        view = self.window.get_active_view()
        enabled = False

        if view is not None:
            buf = view.get_buffer()
            if buf is not None and buf.get_has_selection():
                enabled = True

        self._action.set_enabled(enabled)

        if self._reverse_menu_item is not None:
            self._reverse_menu_item.set_sensitive(enabled)

    def on_focus_in_event(self, widget, event):
        self._ensure_shortcut_registered()
        return False

    def on_window_active_changed(self, widget, pspec):
        self._ensure_shortcut_registered()

    def _ensure_shortcut_registered(self):
        app = self.window.get_application()
        if app is not None:
            app.set_accels_for_action(f"win.{ACTION_NAME}", [SHORTCUT])

    def _add_menu_items(self):
        if self._dna_menu_item is not None:
            return

        self._menu_bar = self._find_menubar(self.window)
        if self._menu_bar is None:
            print("InvertSelection: menubar not found")
            return

        for child in self._menu_bar.get_children():
            if isinstance(child, Gtk.MenuItem):
                label = (child.get_label() or "").strip()
                if label == MENU_LABEL:
                    self._dna_menu_item = child
                    submenu = child.get_submenu()
                    if isinstance(submenu, Gtk.Menu):
                        for subitem in submenu.get_children():
                            if isinstance(subitem, Gtk.MenuItem):
                                sublabel = (subitem.get_label() or "").strip()
                                if sublabel == MENU_ITEM_LABEL:
                                    self._reverse_menu_item = subitem
                                    return

        submenu = Gtk.Menu()

        self._reverse_menu_item = Gtk.MenuItem.new_with_label(MENU_ITEM_LABEL)
        self._reverse_menu_item.connect("activate", self.on_reverse_menu_activate)
        submenu.append(self._reverse_menu_item)

        self._dna_menu_item = Gtk.MenuItem.new_with_label(MENU_LABEL)
        self._dna_menu_item.set_submenu(submenu)

        self._menu_bar.append(self._dna_menu_item)
        self._dna_menu_item.show_all()

    def _remove_menu_items(self):
        if self._reverse_menu_item is not None:
            parent = self._reverse_menu_item.get_parent()
            if parent is not None:
                parent.remove(self._reverse_menu_item)
            self._reverse_menu_item = None

        if self._dna_menu_item is not None:
            parent = self._dna_menu_item.get_parent()
            if parent is not None:
                parent.remove(self._dna_menu_item)
            self._dna_menu_item = None

        self._menu_bar = None

    def _find_menubar(self, widget):
        if isinstance(widget, Gtk.MenuBar):
            return widget

        if not hasattr(widget, "get_children"):
            return None

        try:
            children = widget.get_children()
        except Exception:
            return None

        for child in children:
            result = self._find_menubar(child)
            if result is not None:
                return result

        return None

    def process_sequence(self, text: str) -> str:
        return text[::-1]

    def process_sequence_compact(self, text: str) -> str:
        seq = re.sub(r"\s+", "", text)
        return seq[::-1]

    def on_reverse_menu_activate(self, menu_item):
        self.on_reverse_selection(None, None)

    def on_reverse_selection(self, action, parameter):
        view = self.window.get_active_view()
        if view is None:
            return

        buf = view.get_buffer()
        if buf is None:
            return

        bounds = buf.get_selection_bounds()
        if not bounds:
            return

        start, end = bounds
        text = buf.get_text(start, end, True)
        result = self.process_sequence(text)

        buf.begin_user_action()
        try:
            mark = buf.create_mark(None, start, True)
            buf.delete(start, end)

            insert_iter = buf.get_iter_at_mark(mark)
            buf.insert(insert_iter, result)

            new_start = buf.get_iter_at_mark(mark)
            new_end = new_start.copy()
            new_end.forward_chars(len(result))
            buf.select_range(new_start, new_end)

            buf.delete_mark(mark)
        finally:
            buf.end_user_action()
