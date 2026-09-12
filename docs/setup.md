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

Lần đầu xác nhận đúng board có thể thêm `--trust-new-host`. Script cài client ở
chế độ tương thích chung; không tạo hoặc chuyển credential riêng theo dự án.
