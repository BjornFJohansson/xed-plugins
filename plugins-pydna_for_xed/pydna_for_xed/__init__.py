import subprocess
import json
import re
import gi
import os

gi.require_version("Xed", "1.0")

from gi.repository import GObject, Gio, Xed, Gtk

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
HELPER_PATH = os.path.join(PLUGIN_DIR, "helper.py")

# helper.py is expected to live next to this plugin file and to have
# an executable shebang pointing to the desired pyenv Python.

ACTION_NAME = "Pydna"
MENU_LABEL = "Pydna"
REVERSE_MENU_ITEM_LABEL = "Reverse Selection"
REVERSE_COMPLEMENT_MENU_ITEM_LABEL = "Reverse Complement Selection"

class PyDNAWorker:
    def __init__(self):
        self.proc = None

    def start(self):
        if self.proc is not None and self.proc.poll() is None:
            return

        self.proc = subprocess.Popen(
            [HELPER_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def request(self, payload: dict) -> dict:
        self.start()

        message = json.dumps(payload) + "\n"
        self.proc.stdin.write(message)
        self.proc.stdin.flush()

        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("helper.py died or returned no output")

        return json.loads(line)

    def stop(self):
        if self.proc is None:
            return

        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                self.proc.stdin.flush()
            except Exception:
                pass
            self.proc.terminate()

        self.proc = None


class InvertSelectionWindowActivatable(GObject.Object, Xed.WindowActivatable):
    __gtype_name__ = "InvertSelectionWindowActivatable"

    window = GObject.Property(type=Xed.Window)

    def __init__(self):
        super().__init__()
        self._action = None
        self._dna_menu_item = None
        self._reverse_menu_item = None
        self._reverse_complement_menu_item = None
        self._menu_bar = None
        self.worker = None

    def do_activate(self):
        self._action = Gio.SimpleAction.new(ACTION_NAME, None)
        self._action.connect("activate", self.on_reverse_selection)
        self._action.set_enabled(True)
        self.window.add_action(self._action)

        self.worker = PyDNAWorker()
        self._add_menu_items()

    def do_deactivate(self):
        self._remove_menu_items()

        if self._action is not None:
            self.window.remove_action(ACTION_NAME)
            self._action = None

        if self.worker is not None:
            self.worker.stop()
            self.worker = None

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

        if self._reverse_complement_menu_item is not None:
            self._reverse_complement_menu_item.set_sensitive(enabled)

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
                                if sublabel == REVERSE_MENU_ITEM_LABEL:
                                    self._reverse_menu_item = subitem
                                elif sublabel == REVERSE_COMPLEMENT_MENU_ITEM_LABEL:
                                    self._reverse_complement_menu_item = subitem
                        return

        submenu = Gtk.Menu()

        self._reverse_menu_item = Gtk.MenuItem.new_with_label(REVERSE_MENU_ITEM_LABEL)
        self._reverse_menu_item.connect("activate", self.on_reverse_menu_activate)
        submenu.append(self._reverse_menu_item)

        self._reverse_complement_menu_item = Gtk.MenuItem.new_with_label(REVERSE_COMPLEMENT_MENU_ITEM_LABEL)
        self._reverse_complement_menu_item.connect("activate", self.on_reverse_complement_menu_activate)
        submenu.append(self._reverse_complement_menu_item)

        self._dna_menu_item = Gtk.MenuItem.new_with_label(MENU_LABEL)
        self._dna_menu_item.set_submenu(submenu)

        self._menu_bar.append(self._dna_menu_item)
        self._dna_menu_item.show_all()

    def _remove_menu_items(self):
        if self._reverse_complement_menu_item is not None:
            parent = self._reverse_complement_menu_item.get_parent()
            if parent is not None:
                parent.remove(self._reverse_complement_menu_item)
            self._reverse_complement_menu_item = None

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

    def _get_selected_text_and_bounds(self):
        view = self.window.get_active_view()
        if view is None:
            return None, None, None

        buf = view.get_buffer()
        if buf is None:
            return None, None, None

        bounds = buf.get_selection_bounds()
        if not bounds:
            return buf, None, None

        start, end = bounds
        text = buf.get_text(start, end, True)
        return buf, (start, end), text

    def _replace_selection(self, buf, start, end, result):
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

    def process_sequence(self, text: str) -> str:
        return text[::-1]

    def process_sequence_compact(self, text: str) -> str:
        seq = re.sub(r"\s+", "", text)
        return seq[::-1]

    def reverse_complement_sequence(self, text: str) -> str:
        if self.worker is None:
            self.worker = PyDNAWorker()

        response = self.worker.request(
            {
                "cmd": "reverse_complement",
                "sequence": text,
            }
        )

        if not response.get("ok"):
            raise RuntimeError(response.get("error", "reverse complement failed"))

        return response["result"]

    def on_reverse_menu_activate(self, menu_item):
        self.on_reverse_selection(None, None)

    def on_reverse_complement_menu_activate(self, menu_item):
        self.on_reverse_complement_selection(None, None)

    def on_reverse_selection(self, action, parameter):
        buf, bounds, text = self._get_selected_text_and_bounds()
        if buf is None or bounds is None or text is None:
            return

        start, end = bounds
        result = self.process_sequence(text)
        self._replace_selection(buf, start, end, result)

    def on_reverse_complement_selection(self, action, parameter):
        buf, bounds, text = self._get_selected_text_and_bounds()
        if buf is None or bounds is None or text is None:
            return

        start, end = bounds

        try:
            result = self.reverse_complement_sequence(text)
        except Exception as exc:
            print(f"InvertSelection: reverse complement failed: {exc}")
            return

        self._replace_selection(buf, start, end, result)
