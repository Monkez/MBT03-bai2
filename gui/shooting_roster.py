"""Excel roster and pedestal assignments, independent of the scoring workers."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime

from openpyxl import load_workbook
from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QFileDialog, QListWidget, QListWidgetItem, QMessageBox, QPushButton

import config as cf
from gui.client_widget import classify_hits


@dataclass(frozen=True)
class Shooter:
    number: int
    name: str
    unit: str
    birthday: str
    pedestal: int


def read_roster(path, pedestal_count):
    """Read the active sheet using the same A:D columns as MBT03-wireless."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    people = []
    numbers = set()
    try:
        for row_number, row in enumerate(
                workbook.active.iter_rows(min_row=2, max_col=4, values_only=True), start=2):
            if all(value is None or str(value).strip() == "" for value in row):
                continue
            number, name, unit, birthday = row
            try:
                parsed = int(number)
                if isinstance(number, bool) or parsed <= 0 or float(number) != parsed:
                    raise ValueError()
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f"Dòng {row_number}: STT phải là số nguyên dương.") from None
            if parsed in numbers:
                raise ValueError(f"Dòng {row_number}: STT {parsed} bị trùng.")
            if name is None or not str(name).strip():
                raise ValueError(f"Dòng {row_number}: thiếu họ tên.")
            birthday = (birthday.strftime("%d/%m/%Y") if isinstance(birthday, (date, datetime))
                        else str(birthday or "").strip())
            people.append(Shooter(parsed, str(name).strip(), str(unit or "").strip(),
                                  birthday, (parsed - 1) % pedestal_count + 1))
            numbers.add(parsed)
    finally:
        workbook.close()
    if not people:
        raise ValueError("File chưa có người bắn. Dòng 1 là tiêu đề; dữ liệu bắt đầu từ dòng 2.")
    return people


class ShootingRoster(QObject):
    loaded = pyqtSignal(object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.people = {}
        self.assignments = {}
        self.results = {}
        self.session_id = None
        self.session_assignments = {}
        self.loading = False
        self.closed = False
        self.file_path = ""
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Roster")
        self.loaded.connect(self._finish_load)
        self.list = QListWidget(window)
        self.list.setAccessibleName("Danh sách người bắn")
        self.list.setWordWrap(True)
        self.list.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #d1d5db; font-size: 14px; }"
            "QListWidget::item { padding: 10px 8px; border-bottom: 1px solid #e5e7eb; }"
            "QListWidget::item:selected { background: #dbeafe; color: #111827; }"
        )
        window.verticalLayout_2.replaceWidget(window.scrollArea, self.list)
        window.scrollArea.hide()
        self.assign_button = QPushButton("Chọn người để vào bệ", window)
        self.assign_button.setMinimumHeight(36)
        self.assign_button.setStyleSheet(
            "QPushButton { background: #008d00; color: white; border: 1px solid #007500;"
            "border-radius: 8px; padding: 6px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background: #007500; }"
            "QPushButton:focus { border: 2px solid #111827; }"
            "QPushButton:disabled { background: #e5e7eb; color: #6b7280; border-color: #d1d5db; }"
        )
        window.verticalLayout_2.insertWidget(
            window.verticalLayout_2.indexOf(self.list) + 1, self.assign_button)
        self.assign_button.clicked.connect(self.assign_selected)
        self.list.itemActivated.connect(lambda _item: self.assign_selected())
        self.list.currentItemChanged.connect(lambda *_args: self.refresh_controls())
        window.select_file_btn.clicked.connect(self.choose_file)
        window.excel_file_option.triggered.connect(self.choose_file)
        window.new_route_btn.clicked.connect(self.next_group)
        window.new_route_btn.setToolTip("Xếp người chưa bắn tiếp theo vào mỗi bệ, theo thứ tự trong file")
        # This pre-existing UI placeholder has no Excel export implementation in Bài 2.
        window.save_result_btn.setEnabled(False)
        window.save_result_btn.setToolTip("Chưa hỗ trợ xuất kết quả Excel trong Bài 2")
        for widget in window.client_widgets:
            widget.go_out_btn.clicked.disconnect(widget.reset_shooter)
            widget.go_out_btn.clicked.connect(lambda _checked=False, port=widget.id: self.clear(port))
            widget.go_out_btn.setToolTip("Bỏ người đang được chọn ở bệ này")
        self._items = {}
        self._rebuild_list()

    def pending(self):
        window = self.window
        sid = window._active_review_session_id if window.testing else window._previous_review_session_id
        return any(count > len(window._review_sessions.get(sid, {}).get(port, []))
                   for (session, port), count in window._review_shot_counters.items() if session == sid)

    def locked(self):
        return self.loading or self.window.testing or self.pending()

    def choose_file(self):
        if self.locked():
            return
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Chọn danh sách bắn", self.file_path or cf.DATA_DIR, "Excel (*.xlsx)")
        if path:
            self.load_file(path)

    def load_file(self, path):
        if self.locked() or self.closed:
            return False
        self.loading = True
        self.refresh_controls()
        future = self._pool.submit(read_roster, path, self.window.p_num)

        def done(job):
            try:
                payload = (path, job.result(), None)
            except Exception as exc:
                payload = (path, None, str(exc))
            if not self.closed:
                try:
                    self.loaded.emit(payload)
                except RuntimeError:  # Parent was destroyed while the file was being read.
                    pass
        future.add_done_callback(done)
        return True

    def _finish_load(self, payload):
        if self.closed:
            return
        path, people, error = payload
        self.loading = False
        if error:
            self.refresh_controls()
            QMessageBox.warning(self.window, "Không nạp được danh sách",
                                f"{error}\n\nDùng file .xlsx có các cột: STT, Họ tên, Đơn vị, Ngày sinh.")
            return
        # Commit the new list only after the entire workbook has been validated.
        self.people = {person.number: person for person in people}
        self.file_path = path
        self.assignments.clear()
        self.results.clear()
        self.session_id = None
        self.session_assignments.clear()
        for widget in self.window.client_widgets:
            self._show_person(widget.id, None)
        self._rebuild_list()

    def _rebuild_list(self):
        self.list.clear()
        self._items.clear()
        for person in self.people.values():
            item = QListWidgetItem()
            item.setData(Qt.UserRole, person.number)
            self.list.addItem(item)
            self._items[person.number] = item
            self._refresh_item(person.number)
        if not self.people:
            item = QListWidgetItem("Chưa có danh sách bắn.\nChọn file Excel để nạp người bắn.")
            item.setFlags(Qt.NoItemFlags)
            self.list.addItem(item)
        self.window.label_17.setText(f"Danh sách bắn · {len(self.people)} người" if self.people else "Danh sách bắn")
        self.window.label_17.setToolTip(self.file_path)
        self.window.select_file_btn.setToolTip(self.file_path or "Nạp STT, Họ tên, Đơn vị, Ngày sinh từ Excel")
        self.refresh_controls()

    def _refresh_item(self, number):
        person = self.people[number]
        selected = self.assignments.get(person.pedestal) == number
        result = self.results.get(number)
        state = (f"{result[0]}/16 viên · {result[1]}/4 mục tiêu · {result[2]}"
                 if result is not None else "Chưa bắn")
        if self.window.testing and self.session_assignments.get(person.pedestal) == number:
            state = "Đang bắn"
        item = self._items[number]
        detail = " · ".join(value for value in (person.unit, person.birthday) if value)
        item.setText(f"{number}. {person.name}\n{detail + ' · ' if detail else ''}Bệ {person.pedestal}"
                     f"{' · Đã vào bệ' if selected else ''}\n{state}")
        item.setToolTip(item.text())
        item.setBackground(QColor("#e8f5e9" if selected else "#ffffff"))

    def refresh_controls(self):
        enabled = not self.locked()
        window = self.window
        reason = ("Đang đọc danh sách Excel" if self.loading else "Đang thực hiện bài bắn" if window.testing
                  else "Đang chấm nốt ảnh của bài vừa kết thúc" if self.pending() else "")
        window.select_file_btn.setEnabled(enabled)
        window.select_file_btn.setText("Đang đọc Excel…" if self.loading else "Chọn danh sách bắn")
        window.excel_file_option.setEnabled(enabled)
        window.new_route_btn.setEnabled(enabled and any(n not in self.results for n in self.people))
        window.new_route_btn.setToolTip(reason or "Xếp người chưa bắn tiếp theo vào mỗi bệ, theo thứ tự trong file")
        item = self.list.currentItem()
        number = item.data(Qt.UserRole) if item else None
        person = self.people.get(number)
        self.assign_button.setText(f"Vào bệ {person.pedestal}" if person else "Chọn người để vào bệ")
        self.assign_button.setEnabled(enabled and person is not None)
        self.assign_button.setToolTip(reason or "Chọn người trong danh sách rồi bấm để vào bệ tương ứng")
        for widget in window.client_widgets:
            widget.go_out_btn.setEnabled(enabled)
        # The start button remains usable to stop an active exercise.
        ready = not self.loading and (not self.people or (bool(self.assignments) and not self.pending()))
        window.start_btn.setEnabled(window.testing or ready)
        window.start_btn.setToolTip(reason if not window.testing and reason else
                                    "Chọn người vào bệ hoặc bấm Loạt bắn mới" if not ready else "")

    def _show_person(self, port, number):
        widget = self.window.client_widgets[port - 1]
        self.window._result_sound.stop()
        widget.reset_results()
        widget.reset_shooter()
        if number is not None:
            person = self.people[number]
            widget.set_shooter(" — ".join(value for value in (person.name, person.unit) if value))
        widget.set_review_available(False)

    def assign_selected(self):
        item = self.list.currentItem()
        if item:
            self.assign(item.data(Qt.UserRole))

    def assign(self, number):
        if self.locked() or number not in self.people:
            return False
        port = self.people[number].pedestal
        old = self.assignments.get(port)
        if old == number:
            return True
        self.assignments[port] = number
        self._show_person(port, number)
        if old is not None:
            self._refresh_item(old)
        self._refresh_item(number)
        self.refresh_controls()
        return True

    def clear(self, port):
        if self.locked():
            return
        old = self.assignments.pop(port, None)
        self._show_person(port, None)
        if old is not None:
            self._refresh_item(old)
        self.refresh_controls()

    def next_group(self):
        if self.locked():
            return
        selected = {}
        for person in self.people.values():
            if person.number not in self.results:
                selected.setdefault(person.pedestal, person.number)
        if not selected:
            return
        for widget in self.window.client_widgets:
            self.clear(widget.id)
        for number in selected.values():
            self.assign(number)

    def begin_session(self, session_id):
        self.session_id = session_id
        self.session_assignments = dict(self.assignments)
        for number in self.session_assignments.values():
            self.results.pop(number, None)
            self._refresh_item(number)
        self.refresh_controls()

    def matches_session(self, session_id, port):
        return (not self.people or (session_id == self.session_id and
                self.assignments.get(port) == self.session_assignments.get(port)))

    def update_results(self, session_id):
        if session_id != self.session_id:
            return
        for port, number in self.session_assignments.items():
            shots = self.window._review_sessions.get(session_id, {}).get(port, [])[:16]
            hits = {shot["target_index"] for shot in shots if shot.get("hit") is True}
            rank = classify_hits(hits)
            if not self.window.testing:
                self.results[number] = (len(shots), len(hits), rank)
            self._refresh_item(number)
        self.refresh_controls()

    def shutdown(self):
        self.closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)
