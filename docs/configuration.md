# Cấu hình ứng dụng

Ứng dụng đọc `assets/configurations/config.json` khi khởi động. Sửa tệp bằng tay cần đóng/mở lại ứng dụng; thời gian và kênh lưu qua Cài đặt thiết bị có hiệu lực ở bài tiếp theo. Nếu thiếu khóa hoặc giá trị sai kiểu, ứng dụng dùng giá trị mặc định an toàn trong `config.py`. Khóa không được tài liệu hóa sẽ bị bỏ qua.

## Thu thập ảnh camera gốc

Khóa ẩn cấp cao nhất `save_raw_data` điều khiển việc thu dữ liệu. Khi đặt thành `true`, mọi ảnh chụp nhận trực tiếp từ súng (bao gồm ảnh trong lúc Quy không) được sao chép trước khi xử lý và lưu dạng PNG không mất dữ liệu trong thư mục `raw_camera_images`.

Tên tệp có dạng `YYYYMMDD_HHMMSS_microseconds_be_NN.png`, ví dụ `20260808_140506_123456_be_03.png`. Đặt `save_raw_data` thành `false` rồi khởi động lại ứng dụng để ngừng lưu. Thư mục dữ liệu này được Git bỏ qua vì có thể tăng dung lượng nhanh.

## Bài bắn

Nhóm `shooting`:

| Khóa | Ý nghĩa |
| --- | --- |
| `max_bullets` | Số viên tối đa mỗi bệ, mặc định 16 (1–999); dùng cho bộ đếm, dải xem lại và tạo lệnh `0Fxxx\n`. |
| `burst_gap_seconds` | Khoảng cách giữa hai viên liên tiếp để cùng loạt, mặc định 0.3 giây (so sánh nhỏ hơn, dùng thời điểm PC nhận ảnh). Loạt một viên làm hạ một bậc xếp loại, không hạ Đạt. |
| `start_uart_command` | Khóa cũ để chuyển số đạn từ dạng `0Fxxx\n` nếu chưa có `max_bullets`. Khi đã khai báo `max_bullets`, số đạn này quyết định lệnh cấp; vẫn gửi tiếp `0A000\n` sau 300 ms. |
| `automatic_close_target.default_single_pedestal` | Mặc định bật/tắt gập bia tự động khi chọn 1 bệ. |
| `automatic_close_target.default_multiple_pedestals` | Mặc định bật/tắt gập bia tự động khi chọn từ 2 bệ. |
| `automatic_close_target.commands_by_class` | Lệnh gập/ẩn bia theo class mô hình. Để `command` thành chuỗi rỗng nếu muốn vô hiệu hóa một bia. |
| `target_times` | Bốn cặp `show_seconds` / `hide_seconds` theo thứ tự 6 → 10 → 7B → 8C; nhập và lưu trong Cài đặt thiết bị. Mốc tính từ lúc bắt đầu bài. |
| `hardware_delay_time` | Thời gian bù trễ phần cứng, mặc định `1.5` giây. Dùng để tính khoảng nhận điểm sau lệnh ẩn. |
| `control_channel` | Kênh E32 đã chọn. Mặc định là 1. Kênh 1, 2, 3 tương ứng mã `01`, `03`, `05`. |
| `lora_timeline` | Cấu hình cũ: khi chưa có `target_times`, lấy các mốc hiện cũ và thời lượng 7/7/7/28 giây làm giá trị ban đầu; chuyển sang dùng lệnh thủ công bên dưới. |

Bài bắn kết thúc theo bia xe 8C: xác nhận gập +2 giây hoặc hết thời gian chạy +4 giây từ @444#, lấy mốc sớm hơn. Với ba bia đầu cần
`hardware_delay_time ≤ Hiện < Ẩn ≤ 3600`; 8C cũng nhập Hiện < Ẩn là mốc từ đầu bài. Thứ tự mốc hiện là 6 → 10 → 7B → 8C, có thể bằng nhau.
Cho phép các khoảng hiện chồng nhau, mốc ẩn không cần cùng thứ tự.
Khi chỉnh xong, nhấn ĐÓNG CỬA SỔ để lưu vào JSON và dùng cho bài kế tiếp. Khi khởi động
lại, phần mềm nạp các mốc và kênh đã lưu. Esc hoặc X bỏ chỉnh sửa thời gian chưa lưu. Lỗi ghi file giữ nguyên
cấu hình cũ và không đóng hộp thoại.

Ba bia đầu hẹn lệnh hiện tại `Hiện` và lệnh ẩn tại `Ẩn + 1 giây`. 8C gửi `@444#` tại `Hiện`. Mặc định 8C đặt Hiện 64, Ẩn 92, tương ứng giới hạn chờ 32 giây từ lần gửi lệnh chạy thực tế.
Với ba bia đầu, khoảng nhận trúng bắt đầu tại lúc lệnh hiện thực sự ghi ra cổng LoRa, kết thúc
**trước** lúc ghi lệnh ẩn cộng `2 × hardware_delay_time`.
Công thức áp dụng cả khi gập sớm do trúng. Không dùng padding 2 giây sớm/4 giây
muộn của bản trước. Ảnh được xét theo thời điểm PC nhận, không phải khi model chấm xong.
Chỉ bắt đầu nhận điểm sau khi đã gửi lệnh hiện. 8C nhận điểm từ lần ghi @444# thực tế, dừng theo giới hạn bài hoặc khi đã gập hết khoảng nhận điểm; không chờ lệnh ẩn 8C.

Khi chọn **Không sử dụng LoRa**, bài dùng mốc mô phỏng thay cho ghi serial để
hiện/ẩn, nhận điểm và tự kết thúc theo cùng công thức; không gửi lệnh đến bia vật lý.
Khi chọn COM, vẫn cần lần ghi thực tế, kể cả khi kết nối đang lỗi.

Hình mô phỏng hiện tại thời điểm gửi lệnh hiện và gập sau lần gửi lệnh ẩn 1 giây. Khi gửi theo lịch, mốc gập trên màn hình là `Ẩn + 2 giây`. Bia 8C khi dùng LoRa cập nhật theo phản hồi @4480/@4481 kèm xuống dòng.

| Class | Bia | Lệnh hiện trong bài | Ẩn trong bài |
| --- | --- | --- | --- |
| `1` | BIA SỐ 6 | `@114#` | `@112#` |
| `0` | BIA SỐ 10 | `@224#` | `@222#` |
| `2` | BIA SỐ 7B | `@334#` | `@332#` |
| `3` | BIA SỐ 8C | `@444#` (chạy một lần) | Tự gập, hỏi `@448#` mỗi giây |

Nút **HIỆN BIA** dựng 8C bằng `@441#` sau ba lệnh dựng `@114#`, `@224#`, `@334#`.

Ô Ẩn của 8C là mốc tuyệt đối từ đầu bài, giống các bia khác. Thời gian chạy = hide_seconds − show_seconds. Giới hạn chờ từ lần ghi @444# thực tế là thời gian chạy +4 giây; nhận gập sau khi đã hiện thì kết thúc sau 2 giây, lấy mốc sớm hơn. Không gập 8C khi trúng và không gửi @442# khi kết thúc. Khóa `shooting.automatic_close_target.commands_by_class.3` cũ không áp dụng cho xe 8C.

Cài đặt và JSON `target_times[3]` đều lưu/nạp trực tiếp mốc tuyệt đối. Ví dụ show_seconds=64, hide_seconds=80 thì xe chạy dự kiến 16 giây, giới hạn chờ 20 giây từ @444#. Mất phản hồi không kéo dài giới hạn này. Trạng thái 0 trước lần hiện đầu tiên được coi là xe chưa hiện, không phải đã hoàn thành.

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

Offset hiện tại đồng bộ với công cụ LAB: bia 10/class `0` là `[0, -0.15]`, bia 6/class `1`
là `[0, 0]`, bia 7B/class `2` là `[0, -0.30]`, bia 8/class `3` là `[-0.60, 0]`. Điểm click/Q0 được dùng để
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
| `uart_command` | Lệnh UART chuyển súng sang chế độ quy không, mặc định `0Q000\n`; gửi 300 ms sau lệnh chuẩn bị `0F003\n`. |
| `target_raise_command` | Lệnh LoRa khi mở cửa sổ cài đặt, mặc định `@114#` dựng bia 6. |
| `target_lower_command` | Lệnh LoRa khi đóng cửa sổ cài đặt, mặc định `@112#` gập bia 6. |
| `sample_count` | Số phát dùng để lấy trung bình quy không. |
| `target_class_id` | Class bia dùng làm chuẩn quy không. |
| `reference_center` | Tâm quy không chuẩn hóa `[x, y]` trên ảnh bia mẫu. |

Nếu đổi `target_class_id`, phải cập nhật `reference_center` đúng với bia mới.

## LoRa

Nhóm `lora`:

| Khóa | Ý nghĩa |
| --- | --- |
| `port_description` | Chuỗi dùng tìm cổng COM LoRa tự động. |
| `baud_rate` | Tốc độ dùng cho E32 là 9600 bps, 8N1. |
| `ack_timeout_seconds` | Thời gian chờ phản hồi lặp lại lệnh. |
| `max_attempts` | Số lần gửi tối đa nếu chưa nhận được phản hồi. |

Khi khởi động hoặc kết nối lại, phần mềm mở cổng ở 9600 bps để truyền lệnh. Thao tác **ĐẶT** trong Cài đặt mới cấu hình E32 theo trình tự RTS của bộ chuyển đổi đang dùng. Mỗi lần thử đặt `RTS=False`, chờ 200 ms, xóa bộ đệm nhận rồi gửi `C0 00 00 1A CH 44`. Sau 200 ms, phần mềm đọc và đối chiếu phản hồi đủ sáu byte. Thử tối đa ba lần rồi đặt `RTS=True` và chờ 200 ms trước khi truyền nhận. Nếu E32 chưa xác nhận, Cài đặt báo lỗi đặt kênh. Cổng vẫn dùng để gửi và nhận lệnh điều khiển.

Nút **ĐẶT** lưu lựa chọn kênh và gửi lại cấu hình, kể cả khi giá trị kênh giữ nguyên. Cổng COM đang mở được dùng lại khi tên cổng giữ nguyên. Dòng báo lỗi LoRa trong Cài đặt hiện khi lỗi kết nối, lỗi đặt kênh hoặc lệnh điều khiển thiếu phản hồi. Chọn Không sử dụng LoRa và bấm ĐẶT hiện thông báo màu vàng.

Khung `C0` lưu tham số khi mất nguồn. Tham khảo [hướng dẫn E32 của Ebyte](https://www.ebyte.com/Uploadfiles/Files/2024-4-12/2024412175886598.pdf).

## Tốc độ đọc số bệ

Trong nhóm `shooting`, chỉnh `hit_announcement_playback_rate` để đổi tốc độ đọc
thông báo trúng bia ở chế độ nhiều bệ. Mặc định `1.75`; `1.0` là tốc độ gốc,
`1.5` là nhanh 1.5 lần, `2` hoặc `2.0` là nhanh 2 lần.
Giá trị được giới hạn trong khoảng `0.5`–`4.0`; thiếu khóa hoặc sai kiểu dữ liệu
sẽ dùng mặc định. Lưu `assets/configurations/config.json` rồi mở lại ứng dụng.

## Tiến trình ứng dụng

Nhóm `runtime`:

| Khóa | Ý nghĩa |
| --- | --- |
| `main_status_refresh_ms` | Chu kỳ cập nhật thời gian/trạng thái màn hình chính. |
| `settings_frame_refresh_ms` | Chu kỳ vẽ ảnh camera trong cửa sổ Quy không. |
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
