# Trạng thái dự án

## Kiến trúc hiện tại

- Ứng dụng PC khởi động từ `main.py`.
- Giao diện và xử lý kết quả bài bắn nằm trong `gui/`.
- Lõi kết nối không dây phía PC và giao thức dùng chung nằm trong `assets/server_client/`.
- Mã triển khai phía Orange Pi Zero 2W nằm trong `assets/OrangePiZero2W/`.
- Cấu hình `assets/server_client/client_port_config.json` là dữ liệu riêng của thiết bị, không đồng bộ máy móc từ dự án khác.

## Đồng bộ từ MBT03-wireless

Ngày 2026-09-12 đã đồng bộ server/client theo commit nguồn `0bbf79c`:

- Runtime dùng ba kênh plain ZeroMQ: control, stream latest-only và shoot-data; cổng stream là control + 200, data là control + 100.
- `protocol.py`, `server_core.py`, `client_core.py`, `discovery.py` và `test_integration.py` trong `assets/server_client/` khớp code nguồn.
- Client fallback quét cổng ổn định trong subnet khi cached server IP/mDNS không dùng được; chỉ chấp nhận endpoint hoàn tất handshake MBT03.
- Backend board `r_client.py`, `wifi_manager.py`, `wifi_sync.py` đã đồng bộ; deploy giữ layout riêng của Bài 2 nhưng triển khai cùng runtime, bật UART Wi-Fi sync và phối hợp `wifi-watchdog` qua marker.
- `security.py` và kiểm thử CURVE/HMAC cũ đã được thay bằng kiểm thử transport plain ba kênh vì code nguồn không còn dùng credential theo từng project.
- GUI hiển thị RTT trung bình trượt từ quality payload.

Lần đồng bộ ngày 2026-08-06 tại commit nguồn `b4e5c5c` đã được thay thế bởi bản
2026-09-12 ở trên. Các quyết định vẫn còn hiệu lực:

- Board không phụ thuộc khóa hoặc system ID riêng của từng dự án.
- Deploy không tạo/chuyển credential và dọn credential runtime cũ trên board.
- App PC không có nhóm cấu hình `security`, allow-list hoặc bước ghép cặp client.

Ngày 2026-07-29 đã đồng bộ các tệp sau từ dự án `MBT03-wireless`:

- `assets/server_client/protocol.py`
- `assets/server_client/server_core.py`
- `assets/server_client/client_core.py`
- `assets/OrangePiZero2W/r_client.py`

Các thay đổi chính gồm cổng kết nối ổn định có fallback, hàng đợi gửi điều khiển ZMQ theo đúng thread sở hữu socket, cải thiện bắt tay/kết nối lại, dừng thread sạch hơn, heartbeat và gửi ảnh bắn ổn định hơn.

## Kiểm tra gần nhất

- Ngày 2026-09-12, `test.bat` đạt 97/97. Kiểm tra tích hợp localhost xác nhận bắt tay, heartbeat, nhận stream qua cổng riêng và dữ liệu hai chiều đều thành công; client báo ba cổng control/stream/data đúng theo ACK của server.

- Ngày 2026-08-29, tạm tắt xoay vector offset bằng
  `scoring.TARGET_OFFSET_ROTATION_ENABLED = False` trong cả project chính và công cụ `LAB`.
  Offset hiện bám theo trục ảnh bia chuẩn. Logic bật lại đã đồng bộ: chỉ offset ngang bia 8 dùng
  góc đối xứng `θ → -θ`; offset dọc bia 8 và các bia khác dùng góc bình thường. `test.bat` đạt
  96/96 bài kiểm thử.

- Ngày 2026-08-15, thêm `scoring.target_offsets_by_class`. Offset được áp dụng sau khi chọn bia
  và chỉ tồn tại trong hệ tọa độ ảnh tham chiếu, không chiếu ngược về camera. Metadata mới gồm
  `transformed_click_point`, `transformed_point` và `target_offset`; không đổi nghĩa
  `transformed_point` đối với các nơi hiển thị/mô phỏng điểm chạm.
- Vector offset được xoay bằng thành phần rotation gần nhất của ma trận camera-to-reference
  (polar decomposition qua SVD). Không nhân scale/shear vào vector vì khoảng cách trên ảnh bia
  mô phỏng là giá trị hiệu chỉnh cần được giữ nguyên.

- Ngày 2026-08-08, sửa `ClientWidget.set_connection_quality_state("healthy")` luôn gọi lại trạng thái kết nối đầy đủ. Không được tối ưu bằng điều kiện `if not self.connected`, vì trạng thái `degraded` vẫn giữ `connected=True` nhưng dùng nền nâu; bỏ qua bước này sẽ tạo nhãn đã kết nối/Ping mới với màu cảnh báo cũ.
- Ngày 2026-08-08, cấu hình cấp cao nhất `save_raw_data` mặc định bật. `MainWindow._on_shoot_image()` sao chép frame ngay khi nhận, trước nhánh Q0/chấm điểm, rồi ghi PNG lossless qua executor riêng vào `raw_camera_images`; khi đóng app phải flush executor để không mất ảnh cuối.
- Ngày 2026-08-08, UX Quy không trong `gui/setting_window.py` đã được đồng bộ với `MBT03-wireless`: chấm xanh đếm số phát còn thiếu, chữ thập vàng đánh dấu phát hợp lệ, Q0 đã lưu dùng chữ thập xanh; vẫn giữ xử lý nhận diện nền của Bài 2 và stream trực tiếp.

- `test.bat`: đạt 91/91 bài kiểm thử ngày 2026-08-08; gồm hồi quy client dùng chung, phục hồi màu nhãn kết nối, lệnh ẩn bia số 8, stream Q0, chỉ báo tiến độ Quy không và lưu ảnh camera gốc theo cấu hình.
- `assets/server_client/test_integration.py`: kết nối qua Hub thành công trên cổng điều khiển/dữ liệu `1711/1811`, gửi dữ liệu hai chiều và kết nối lại thành công.
- Luồng bắt đầu bài bắn tạm thời gửi lệnh Q0 `0Q000\n` qua từng `MBT03ServerCore`; Orange Pi nhận gói `UART_CMD` và ghi lệnh xuống UART của súng.
- Cửa sổ cài đặt không giữ ảnh chụp tĩnh sau phát Q0; luôn hiển thị frame stream mới nhất và vẽ chồng các dấu Q0 đã xử lý lên stream.
- Review session được tính từ `start_test()` đến `stop_test()`. Mỗi bệ giữ ảnh camera, điểm chạm và kết quả mô phỏng của phiên vừa kết thúc; `start_test()` xóa toàn bộ dữ liệu review cũ.
- Khi nhiều detection chứa cùng điểm chạm, hệ thống ưu tiên bia có phép chiếu affine hợp lệ trên ảnh tham chiếu, vị trí tương đối gần tâm/ở sâu trong khung, khung nhỏ sát mục tiêu hơn và sau cùng mới xét confidence. Không dùng độ sâu pixel tuyệt đối vì sẽ thiên lệch về khung lớn.
- Dữ liệu review lưu toàn bộ detection của từng phát. `ReviewWindow` vẽ khung vàng cho detection được chọn và khung xanh cho các detection còn lại để đối chiếu trực quan.
- Ảnh camera review được crop quanh điểm chạm và phóng lên 1.5x; bounding box được biến đổi theo cùng vùng crop trước khi vẽ.
- Marker điểm chạm trên ảnh mô phỏng luôn dùng màu đỏ, phóng 1.45 lần và có nhiều lớp viền đen/trắng để không chìm vào màu bia hoặc viền trạng thái trúng.
- Thanh điều khiển review chỉ hiển thị `Phát trước`, bộ đếm, `Phát sau` và `Đóng`; Home/End vẫn gọi `show_first()`/`show_last()`.
- `OptionWindow.automatic_close_target_enabled` lưu lựa chọn gập bia tự động; nút hiển thị `Gập bia: BẬT/TẮT`. Một bệ mặc định bật, từ hai bệ mặc định tắt. Ánh xạ class sang lệnh gập/ẩn: class 1/bia 6 → `@112#`, class 0/bia 10 → `@222#`, class 2/bia 7B → `@332#`, class 3/bia 8 → `@442#`. Mỗi class chỉ nhận lệnh một lần trong một bài và tập đánh dấu được xóa tại `start_test()`.
- `config.py` nạp `assets/configurations/config.json`, chỉ merge các khóa có trong `DEFAULT_CONFIG`, điền khóa thiếu và bỏ qua khóa lạ. Các module lấy tham số bằng helper có kiểm tra kiểu và giới hạn.
- Cấu hình tập trung gồm `shooting`, `scoring`, `review`, `calibration`, `lora`, `runtime`; xem `docs/configuration.md` trước khi thêm hoặc đổi khóa.
- Cấu hình server/client gồm `connection`, `media`, `wifi`; `MainWindow` áp dụng connection/media trước khi tạo socket và fallback về mặc định nếu policy sai.
- Integration thật tại máy phát triển: Hub P1 cổng `1711/1811`, heartbeat 3 giây, dữ liệu hai chiều và reconnect đều thành công.

## Quy tắc làm việc

- Đọc `docs/` và `agents/` trước khi sửa.
- Giữ các thay đổi chưa commit không liên quan của người dùng.
- Dùng `git`, không dùng `gh`.
- Sau thay đổi phải chạy `test.bat` và cập nhật tài liệu liên quan.
