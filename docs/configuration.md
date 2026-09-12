# Cấu hình ứng dụng

Ứng dụng đọc `assets/configurations/config.json` một lần khi khởi động. Sau khi sửa tệp, cần đóng và mở lại ứng dụng. Nếu thiếu khóa hoặc giá trị sai kiểu, ứng dụng dùng giá trị mặc định an toàn trong `config.py`. Khóa không được tài liệu hóa sẽ bị bỏ qua.

## Thu thập ảnh camera gốc

Khóa ẩn cấp cao nhất `save_raw_data` điều khiển việc thu dữ liệu. Khi đặt thành `true`, mọi ảnh chụp nhận trực tiếp từ súng (bao gồm ảnh trong lúc Quy không) được sao chép trước khi xử lý và lưu dạng PNG không mất dữ liệu trong thư mục `raw_camera_images`.

Tên tệp có dạng `YYYYMMDD_HHMMSS_microseconds_be_NN.png`, ví dụ `20260808_140506_123456_be_03.png`. Đặt `save_raw_data` thành `false` rồi khởi động lại ứng dụng để ngừng lưu. Thư mục dữ liệu này được Git bỏ qua vì có thể tăng dung lượng nhanh.

## Bài bắn

Nhóm `shooting`:

| Khóa | Ý nghĩa |
| --- | --- |
| `start_uart_command` | Lệnh UART gửi đến súng khi bắt đầu bài. Ký tự `\n` trong JSON là ký tự xuống dòng thật. |
| `automatic_close_target.default_single_pedestal` | Mặc định bật/tắt gập bia tự động khi chọn 1 bệ. |
| `automatic_close_target.default_multiple_pedestals` | Mặc định bật/tắt gập bia tự động khi chọn từ 2 bệ. |
| `automatic_close_target.commands_by_class` | Lệnh gập/ẩn bia theo class mô hình. Để `command` thành chuỗi rỗng nếu muốn vô hiệu hóa một bia. |
| `lora_timeline` | Danh sách lệnh LoRa theo số giây tính từ lúc bắt đầu bài. Có thể thêm, xóa hoặc đổi thứ tự các phần tử. |

Quy ước class hiện tại:

| Class | Bia | Lệnh dựng | Lệnh gập |
| --- | --- | --- | --- |
| `0` | Bia số 10 | `@221#` | `@222#` |
| `1` | Bia số 6 | `@111#` | `@112#` |
| `2` | Bia số 7B | `@331#` | `@332#` |
| `3` | Bia số 8 | `@444#` điều khiển xe bia | `@442#` ẩn bia |

## Nhận diện và tính điểm

Nhóm `scoring`:

| Khóa | Ý nghĩa |
| --- | --- |
| `model_file` | Đường dẫn model ONNX, tương đối từ thư mục dự án hoặc đường dẫn tuyệt đối. |
| `confidence_threshold` | Confidence tối thiểu để giữ một detection, từ `0` đến `1`. |
| `iou_threshold` | Ngưỡng IoU của NMS, từ `0` đến `1`. |
| `keypoint_confidence_threshold` | Confidence tối thiểu của keypoint dùng tính affine. |
| `ransac_reprojection_ratio` | Sai số RANSAC theo tỷ lệ kích thước ảnh bia tham chiếu. |
| `ransac_max_iterations` | Số vòng lặp tối đa của RANSAC. |
| `target_offsets_by_class` | Offset `[x, y]` theo từng class, tính theo tỷ lệ rộng/cao của ảnh bia chuẩn. `x > 0` dịch điểm chạm sang phải, `y < 0` dịch lên trên. |

Chỉ nên chỉnh các ngưỡng nhận diện từng bước nhỏ và kiểm tra lại bằng ảnh bắn thật.

Offset tạm hiện tại: bia 10/class `0` là `[0, -0.02]`, bia 6/class `1` là `[0, 0]`, bia
7B/class `2` là `[0, -0.04]`, bia 8/class `3` là `[0.025, 0]`. Điểm click/Q0 được dùng để
chọn bia trước; offset của đúng class sau đó chỉ được áp dụng trong hệ tọa độ ảnh bia chuẩn,
không chiếu điểm sau offset ngược về ảnh camera. Vì offset là tỷ lệ thay vì pixel cố định, giá
trị vẫn co giãn theo kích thước từng ảnh bia. Hãy hiệu chỉnh từng giá trị bằng ảnh bắn thực tế
và khởi động lại ứng dụng sau khi sửa.

Ảnh hưởng của góc xoay lên offset hiện đang tạm tắt bằng
`TARGET_OFFSET_ROTATION_ENABLED = False` trong `scoring.py`; offset bám theo trục ngang/dọc của
ảnh bia chuẩn. Logic phân rã SVD vẫn được giữ lại để thử nghiệm sau. Khi bật công tắc, riêng
offset ngang của bia số 8 dùng góc đối xứng qua phương ngang (`θ → -θ`), còn offset dọc của bia
số 8 và offset của các bia khác dùng góc bình thường. Độ co giãn và shear không được nhân vào
vector offset.

## Xem lại

Nhóm `review`:

| Khóa | Ý nghĩa |
| --- | --- |
| `camera_zoom` | Mức zoom ảnh camera quanh điểm chạm; `1.0` là không zoom. |
| `simulation_marker_scale` | Hệ số kích thước marker trên bia mô phỏng. |
| `selected_box_thickness` | Độ dày khung bia được chọn. |
| `other_box_thickness` | Độ dày các khung detection còn lại. |

## Quy không

Nhóm `calibration`:

| Khóa | Ý nghĩa |
| --- | --- |
| `uart_command` | Lệnh UART chuyển súng sang chế độ quy không. |
| `sample_count` | Số phát dùng để lấy trung bình quy không. |
| `target_class_id` | Class bia dùng làm chuẩn quy không. |
| `reference_center` | Tâm quy không chuẩn hóa `[x, y]` trên ảnh bia mẫu. |

Nếu đổi `target_class_id`, phải cập nhật `reference_center` đúng với bia mới.

## LoRa

Nhóm `lora`:

| Khóa | Ý nghĩa |
| --- | --- |
| `port_description` | Chuỗi dùng tìm cổng COM LoRa tự động. |
| `baud_rate` | Tốc độ serial. |
| `ack_timeout_seconds` | Thời gian chờ phản hồi lặp lại lệnh. |
| `max_attempts` | Số lần gửi tối đa nếu chưa nhận được phản hồi. |

## Tiến trình ứng dụng

Nhóm `runtime`:

| Khóa | Ý nghĩa |
| --- | --- |
| `main_status_refresh_ms` | Chu kỳ cập nhật thời gian/trạng thái màn hình chính. |
| `settings_frame_refresh_ms` | Chu kỳ vẽ ảnh camera trong cửa sổ cài đặt. |
| `max_scoring_workers` | Số luồng tính điểm tối đa. Số thực tế không vượt số bệ. |
| `onnx_intra_op_threads` | Số luồng CPU bên trong mỗi phiên ONNX Runtime. |

## Kết nối server/client

Nhóm `connection` được PC kiểm tra rồi gửi xuống client trong gói bắt tay, nhờ đó
hai phía luôn dùng cùng chính sách:

| Khóa | Ý nghĩa |
| --- | --- |
| `heartbeat_interval_seconds` | Nhịp heartbeat bình thường. |
| `heartbeat_min_interval_seconds` | Nhịp dò nhanh khi mạng xấu. |
| `heartbeat_max_interval_seconds` | Nhịp chậm nhất khi mạng ổn định. |
| `degraded_after_seconds` | Thời gian im lặng trước khi báo kết nối chập chờn. |
| `offline_after_seconds` | Thời gian trước khi báo mất tín hiệu. |
| `client_reconnect_after_seconds` | Thời gian client đóng socket cũ và kết nối lại. |
| `session_release_after_seconds` | Thời gian server giữ chỗ bệ trước khi giải phóng. |
| `recovery_ack_count` | Số ACK hợp lệ liên tiếp để trở lại trạng thái khỏe. |
| `rtt_good_ms`, `rtt_warn_ms`, `rtt_bad_ms` | Các mốc đánh giá độ trễ. |
| `rtt_window_size` | Số mẫu RTT dùng làm mượt. |

Phải giữ đúng thứ tự: heartbeat min ≤ heartbeat thường ≤ heartbeat max < chập
chờn < offline < reconnect < giải phóng phiên. Nếu cấu hình sai, app tự quay về
bộ giá trị mặc định.

Phiên bản giao thức hiện tại dùng ba kênh ZeroMQ độc lập: kênh control cho
heartbeat/lệnh, kênh stream latest-only cho video trực tiếp và kênh data cho ảnh
bắn. Cổng stream bằng cổng control cộng `200`; cổng data bằng cổng control cộng
`100`. Các offset này là hằng số giao thức dùng chung giữa PC và Orange Pi, không
phải cấu hình vận hành.

## Ảnh truyền qua mạng

Nhóm `media` cũng được đồng bộ xuống Orange Pi trong lúc bắt tay:

| Khóa | Ý nghĩa |
| --- | --- |
| `shoot_resolution` | Độ phân giải ảnh dùng chấm điểm `[rộng, cao]`. |
| `shoot_jpeg_quality` | Chất lượng JPEG ảnh bắn, từ 20 đến 95. |
| `stream_resolution` | Độ phân giải camera xem trực tiếp. |
| `stream_jpeg_quality` | Chất lượng JPEG của luồng xem trực tiếp. |
| `stream_fps_target` | FPS mục tiêu của luồng xem trực tiếp. |

## Wi-Fi

Nhóm `wifi` chứa thời gian chờ ACK và thời gian rollback của giao dịch đổi Wi-Fi.
Backend Orange Pi giữ mạng cũ cho đến khi kết nối lại và nhận `COMMIT`; mật khẩu
không đi qua lệnh UART thô và không được ghi vào log.

Kết nối server/client dùng chế độ tương thích chung, không có cấu hình ghép cặp
theo từng dự án. Một Orange Pi dùng chung có thể kết nối với mọi dự án MBT03 có
cùng phiên bản giao thức mà không phải cấp lại khóa hoặc sửa client trên board.

## Khóa cũ đã loại bỏ

Các khóa `show_mode`, `Camera`, `Camera_time_sleep`, `Camera_fps`, `Camera_zoom`, `View_zoom`, `CV_CAP`, `s41001`, `s41002`, `s_tolerance`, `Trigger`, `TriggerCode`, `Trigger_time_sleep`, `Accept_all_trigger`, `Q0`, `Q0_bound`, `Test1`, `Test2`, `keypoint_threshold`, `log` và `save_to_desktop` không được code hiện tại sử dụng nên đã bị loại bỏ.
