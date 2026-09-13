# Cài đặt

Chạy `setup.bat` để tạo môi trường Python 3.11 trong thư mục `.venv` và cài dependencies.

Sau khi cài xong, chạy ứng dụng bằng `run.bat`.

Để mở riêng công cụ thử điểm chạm và offset, chạy `run-score-test.bat`. Công cụ tự dùng model
và ảnh bia trong `LAB/assets`, không cần mở thêm terminal phụ.

Để kiểm tra nhanh cú pháp phần giao diện, server/client, mã Orange Pi và chạy các bài kiểm thử tự động, dùng `test.bat`.

Các tham số vận hành có thể chỉnh tại `assets/configurations/config.json`. Xem mô tả chi tiết trong `docs/configuration.md`; cần khởi động lại ứng dụng sau khi sửa.

Để cập nhật một Orange Pi đang SSH được, chạy:

```bat
deploy-board.bat DIA_CHI_IP
```

Trước lần deploy đầu tiên, tạo file riêng
`assets/OrangePiZero2W/wifi_defaults.json` với hai trường chuỗi `ssid` và
`password`. File này chứa thông tin Wi-Fi dự phòng khi UART không trả về cấu hình
hợp lệ, đã được loại khỏi Git và được cài lên board với quyền `0600`.

Lần đầu xác nhận đúng board có thể thêm `--trust-new-host`. Script cài client ở
chế độ tương thích chung; không tạo hoặc chuyển credential kết nối server riêng
theo dự án. Sau khi khởi động service, script theo dõi PID và số lần restart trong
24 giây trước khi báo thành công.

Nếu PC có nhiều card mạng hoặc VPN và mDNS quảng bá sai IP, đặt biến môi trường
`MBT03_BIND_IP` thành IPv4 LAN trước khi chạy ứng dụng.
