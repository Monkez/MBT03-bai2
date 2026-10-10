# Build bản Windows

Chạy `setup.bat` trước, rồi cài công cụ build một lần:

```bat
uv pip install --python .venv\Scripts\python.exe -r requirements-build.txt
```

Nếu dùng pip thay cho uv:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

Đóng gói bằng `build.bat`. Script dùng Python trong `.venv` và PyInstaller trực tiếp;
không cần mở giao diện auto-py-to-exe. Cách dùng và tên bản phát hành tương tự dự án
MBT03-wireless:

```text
dist\MBT03-Bai2-V1-101026\
  MBT03-Bai2-V1-101026.exe
  _internal\
```

EXE không mở console. Sao chép **cả thư mục bản phát hành**, không chỉ file EXE;
máy sử dụng không cần cài Python. Chọn vị trí có quyền ghi, ví dụ thư mục riêng trên
Desktop, tránh Program Files vì ứng dụng lưu cấu hình và ảnh ngay trong bản portable.

- Bản đầu là V1; số phiên bản tự tăng dựa trên `build_state.json` và các bản đã có
  trong `dist`. File trạng thái chỉ cập nhật khi build thành công, không xóa bản cũ.
- Ngày theo máy build, định dạng `ddmmyy`.
- `build.bat --dry-run` in tên và lệnh build; không tạo output hay tăng phiên bản.
- Lệnh có thể gọi từ thư mục khác; các đường dẫn được tính từ vị trí `build.bat`.
- Model, ảnh bia, UI, âm thanh và cấu hình ứng dụng hiện tại được đóng gói. Không
  đóng gói ảnh camera, log, dữ liệu ghép nối thiết bị, danh tính hệ thống hoặc Wi-Fi.

Trong bản đóng gói, chỉnh `_internal\assets\configurations\config.json` rồi mở lại
EXE. `server.log`, `system_config.json` và `raw_camera_images` được tạo dưới
`_internal` theo đường dẫn runtime hiện tại. Giữ lại dữ liệu cần thiết khi chuyển bản.

Trước bàn giao, chạy `test.bat`, build và thử EXE trên máy đích: mở màn hình chính,
kết nối bệ/LoRa, nhận và chấm ảnh, phát tiếng nổ, kết thúc ở 75 giây và xem lại.
