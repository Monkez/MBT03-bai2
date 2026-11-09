## Đặt kênh chỉ qua nút ĐẶT — 2026-11-09

- LoraController tách mở COM và áp dụng kênh. Chỉ force_channel=True từ ĐẶT mới phát C0/đổi RTS. Startup và retry mở COM trực tiếp. Lỗi cấu hình emit configuration_finished riêng, vẫn giữ cổng và gửi lệnh.
- 394 kiểm tra đạt. Native Qt/PYZ giả lập xác nhận ĐẶT lỗi rồi BẮT ĐẦU gửi 0F016/0A000 tới súng và COM mở lại gửi @114# theo lịch. Bản V64-091126 trên Desktop.

## Chiều cao Cài đặt — 2026-11-07

- Hàng ảnh cao 58 px logic, ảnh vừa khung 100 × 52 giữ tỉ lệ. Cửa sổ lấy chiều cao theo sizeHint sau khi tạo nội dung.
- 23 kiểm tra đạt. Native Qt/PYZ xác nhận kích thước 540 × 336 logic ở DPI 200%, ảnh và các hàng thời gian hiện trọn. V63-071126 trên Desktop.

## Tách Cài đặt và Quy không — 2026-11-07

- SettingWindow chỉ có timing/LoRa. Thêm lại lora_log_label trong khung trống của form mới. QuyKhongWindow dùng quy_khong.ui và chứa camera/Quy 0 cùng offline UI từ bản trước.
- MainWindow nối quy_khong_btn, chuyển vòng đời dựng/hạ bia và 0S000 sang Quy không. _quy_khong_window định tuyến ảnh Q0. Khóa hai nút trong bài hoặc thao tác LoRa.
- 394 kiểm tra đạt. Native Qt/PYZ xác nhận cả hai nút mở đúng form, lưu lịch ở Cài đặt và Quy 0 hai súng trong cửa sổ riêng. Bản V62-071126 trên Desktop.

## Lỗi LoRa và súng offline trong Cài đặt — 2026-11-07

- LoraController lưu connection_error cho cổng đã chọn. Cài đặt nhận cả connection_changed, command_finished và configuration_finished. ĐẶT không dùng LoRa hiện cảnh báo vàng.
- Ảnh offline tìm monkez_assets ở gốc bundle trước rồi fallback MonkezCustomWidgets khi chạy nguồn. Stream đang chọn là nguồn frame duy nhất. Khi offline reset Q0 và khóa hai nút hiệu chỉnh.
- 393 kiểm tra đạt. Qt/PYZ dùng cổng và súng giả lập xác nhận lỗi thiếu ACK, lỗi E32, cảnh báo vàng và ảnh offline từ thư mục bundle. Bản V61-071126 trên Desktop.

## Giao diện Quy 0 và cửa sổ chính — 2026-11-07

- setting.ui dùng DeactiveColor trắng, chữ tối cho close_window_btn/cancel_btn. cancel_btn hiển thị BẮN LẠI. Bỏ showMessage LoRa trên MainWindow, giữ dòng lỗi lora_log_label trong Cài đặt và log console. Cập nhật tiêu đề chính.
- 58 kiểm tra liên quan đạt. Native Qt/PYZ xác nhận cả hai màu nút, tiêu đề và lỗi chỉ hiển thị trong Cài đặt. Bản V60-071126 trên Desktop.

## Quy 0 nhiều súng liên tiếp — 2026-11-07

- Đóng cửa sổ mặc định hiện và tự lưu thời gian bia. Khi đủ mẫu Q0 hiện Hủy/Chấp nhận. Hủy rearm 0F003 → 300ms → 0Q000. Chấp nhận gửi SET_Q0, dừng súng vừa hiệu chỉnh và reset UI, giữ stream/cửa sổ.
- request_id phân biệt kết quả worker của các lượt Q0 khi đổi súng hoặc bắt đầu lại. Khi gửi SET_Q0 lỗi, giữ mẫu để thử lại.
- 390 kiểm tra đạt. Native Qt/PYZ + worker thật và súng giả lập xác nhận hủy, nhận hai súng liên tiếp và tự lưu khi đóng. Bản V59-071126 trên Desktop.

## Nút ĐẶT LoRa và tiêu đề — 2026-11-07

- Cài đặt tách lưu channel khỏi lưu timing. lora_accept_btn yêu cầu force_channel=True. Controller lập trình lại trên COM đang mở, đổi cổng mới thì mở lại. Lỗi trên cổng đang mở giữ COM và chặn lệnh điều khiển đến khi xác nhận kênh.
- configuration_finished cập nhật lora_log_label ẩn mặc định, chỉ hiện lỗi ngắn. Khi chuyển cổng/kênh, hạ bia hiệu chỉnh ở link cũ và dựng lại sau khi xác nhận link mới. Tiêu đề ba cửa sổ đặt khi tải .ui.
- 389 kiểm tra đạt. Native Qt/PYZ + LoRa giả lập kiểm tra đổi kênh tại chỗ, gửi lại cùng kênh, chuyển COM, dòng lỗi và cả ba tiêu đề. Bản V58-071126 trên Desktop.

## Hiển thị bia theo lần gửi lệnh — 2026-11-07

- MainWindow truyền display_delays=(0,1) cho ShootingSession. Hiện theo actual sent, gập sau actual hide +1. Khoảng điểm vẫn dùng hardware_delay_time, xe 8C thật dùng feedback.
- 8C mô phỏng tính +2 giây kết thúc từ mốc gập mô phỏng. Test Main xác nhận lệnh gửi trễ không làm ảnh hiện/gập theo mốc dự kiến sai.
- 388 kiểm tra đạt. Test polling 8C chờ tín hiệu timer thay cho qWait cố định. Native Qt/PYZ giả lập xác nhận hiện theo lần gửi, gập đúng ngưỡng +1 và 8C theo feedback. Bản V57-071126 trên Desktop.

## Lịch bia và lời đọc 8C — 2026-11-07

- MainWindow dùng mốc Hiện và Ẩn+1 để hẹn lệnh. Thời lượng theo lịch của ShootingSession khớp hai mốc gửi. 8C thật chỉ gửi @444 và theo dõi @448.
- Preset 8C 64/92, timeout 32 giây từ @444. Giữ preset legacy của ShootingSession trực tiếp. Đọc kết quả bằng bia_so_8c_alpha_90.wav.
- 388 kiểm tra đạt. Native Qt/PYZ xác nhận lịch gửi, timeout mặc định và WAV 90 đã chuẩn bị phát. Bản Desktop V56 cập nhật lịch đã lưu khi khớp đủ mẫu mặc định cũ.

## Cài đặt kênh LoRa E32 — 2026-11-07

- LoraController lập trình E32 9600 8N1 qua RTS và khung C0 00 00 1A CH 44, CH=01/03/05 theo kênh 1/2/3. Ba lần thử, xác nhận đủ khung, phục hồi RTS=True. Chỉ truyền khi áp dụng được kênh. Cổng mở lại áp dụng lại kênh, cổng đang mở cùng kênh bỏ ghi lại.
- MainWindow lưu lựa chọn qua SettingWindow, xếp hạ bia hiệu chỉnh trước yêu cầu đổi kênh trên worker nối tiếp. Thanh trạng thái báo kết quả, khóa điều khiển lúc áp dụng. Startup dùng kênh đã lưu, mặc định 1.
- 387 kiểm tra đạt. Native Qt/PYZ + serial giả lập xác nhận startup Kênh 1, đổi sang 3, lỗi khi Kênh 2 thiếu phản hồi và hạ bia trên link cũ trước đổi kênh. V55-071126, bàn giao Desktop giữ cấu hình/dữ liệu. Chưa thử E32 thật.

## Dựng thủ công 8C — 2026-11-07

- Tách MANUAL_OPEN_TARGET_COMMANDS dùng @441# cho nút HIỆN BIA. RAISE_COMMANDS của bài vẫn dùng @444# và phản hồi @448#.
- 25 kiểm tra đạt. Native Qt/PYZ với cổng LoRa giả lập xác nhận bấm nút gửi @441# và luồng bài dùng @444#/@448#. Build V54-071126.

## Ô Ẩn 8C dùng mốc tuyệt đối — 2026-11-07

- Theo sửa đổi của người dùng, SettingWindow bỏ chuyển đổi duration: hiển thị/lưu/nạp hide_seconds trực tiếp như các bia khác. Hiện64/Ẩn80 => run16, timeout20 từ actual @444. Tooltip giải thích công thức; không đổi polling/deadline.
- 22 tests timing/feedback đạt: lưu/nạp64/80 và timeout20, từ chối Ẩn16 khi Hiện64. Build V53-071126 đạt; native Qt/PYZ + cổng serial giả lập xác nhận GUI64/80, timeout20 và gập+2; bàn giao Desktop giữ cấu hình/dữ liệu. Chưa thử xe thật/EXE mặc định.

## Xe bia 8C — 2026-11-07

- Thay raise8C @441# bằng @444#, gửi một lần không chờ echo/retry để tránh chạy lại xe. Poll @448# mỗi 1000ms, coalesce tối đa một query đang chờ, timeout ≤1s; parse dòng @448[01]\n/CRLF, chịu phân mảnh, không nhận echo làm trạng thái. target_state_received kèm requested_at/observed_at, bỏ phản hồi cũ.
- MainWindow phản ánh trạng thái thực 8C, dừng poll khi gập sau lần hiện, stop/close. Không gửi @442# khi hit/lịch/stop/close; ba bia kia giữ lệnh cũ. Manual HIỆN cũng dùng @444 và poll.
- Session giữ history trạng thái cho attribution tại received_at; 0 ban đầu chưa phải hoàn thành. Giới hạn bài từ actual @444 sent = runtime+4s, feedback gập thì min(deadline, observed+2s). Hết hạn luôn dừng dù thiếu phản hồi/hide khác; ảnh nhận từ deadline bị loại dù timer chưa chạy.
- Cài đặt hiển thị ô Ẩn 8C là duration, nội bộ JSON target_times vẫn absolute để tương thích. target8_timeout_seconds = hide_seconds-show_seconds+4. 16s trên GUI =>20s chờ; lưu/nạp có test.
- 382 tests toàn bộ đạt; 23 test giao thức/lifecycle đạt sau chặn lệnh cũ khi khởi động lại. Build V52-071126 đạt. Native Qt từ PYZ với LoRa worker thật/cổng giả lập đã thử 2 bài, trạng thái hiện/gập, kết thúc +2s, timeout20s, không có @442. Bàn giao Desktop giữ dữ liệu/cấu hình. Chưa thử xe thật/EXE mặc định.

## Nâng riêng bia 10 — 2026-11-07

- _draw_target nâng class 0 (bia 10) thêm 8*scale pixel, chặn tại top vùng ảnh để không chồng dải đạn. Bia khác, kích thước và phép ánh xạ marker giữ nguyên.
- 18 tests đạt. Build V51-071126, native Qt/PYZ kiểm tra ảnh/marker và vị trí cố định 1/2/4 bệ; bàn giao Desktop giữ cấu hình/dữ liệu. Chưa thử EXE mặc định/thiết bị thật.

## Nâng nhẹ bia — 2026-11-07

- Band dải đạn giảm từ min(rows*36*scale, 30% chiều cao) xuống min(rows*30*scale, 24% chiều cao). Ảnh dịch lên nhẹ nhưng giữ cố định theo số viên. Màu vàng/blue của V49 giữ nguyên.
- 18 tests đạt. Build V50-071126 và native Qt/PYZ xác minh 1/2/4 bệ, ảnh trước/sau và 16 viên; bàn giao Desktop giữ cấu hình/dữ liệu. Chưa thử EXE mặc định/thiết bị thật.

## Màu khung dải đạn trên bia — 2026-11-07

- Viên lẻ khung vàng #eab52c, loạt nhiều viên khung blue #1769ff. Chỉ đổi màu khung trên bia; giữ màu hit/miss và kích thước/band cố định.
- 18 tests liên quan đạt; kiểm tra native Qt 1/2/4 bệ và vị trí ảnh trước/sau. Build V49-071126 đạt, native Qt/PYZ kiểm tra màu và vị trí 1/2/4 bệ; bàn giao Desktop giữ cấu hình/dữ liệu. Chưa thử EXE mặc định/thiết bị thật.

## Vùng đạn cố định từ đầu — 2026-11-07

- _draw_target_rounds chừa band cố định theo kích thước khung/giới hạn đạn, kể cả chưa bắn; chỉ ô đạn thích ứng trong band. Ảnh và tọa độ marker không dịch/thu nhỏ khi phát đầu, thêm phát hoặc xuống dòng.
- Test so sánh nguyên rect ảnh trước bắn và sau 1/8/16 viên trên overview/focused/overlap; giữ kiểm tra tỷ lệ ảnh theo sai số 1 pixel vì vùng mới nhỏ hơn.
- 42 tests đạt. Build V48-071126 và native Qt từ PYZ xác nhận rect trước/sau giống nhau ở 1/2/4 bệ; bàn giao Desktop giữ cấu hình/dữ liệu. Chưa thử EXE mặc định hoặc thiết bị thật.

## Dải đạn từng bia — 2026-11-07

- target_round_groups ghép shots/receipt, ưu tiên displayed_target_index, pending xám/completed miss đỏ/hit xanh; phân loạt toàn bài trước khi chia bia, không biến loạt đi qua hai bia thành viên lẻ.
- ClientWidget vẽ dải căn trái trong từng khung, riêng vùng ảnh, tự xuống dòng/thu ô khi khung nhỏ. Viên lẻ ô vuông khung đỏ, loạt khung vàng, số phát chung. Thay icon A, giữ asset cũ. Reset xóa dải; MainWindow cập nhật cả lúc pending/trễ.
- 367 tests đạt trước bổ sung hai test nhóm; 9 test nhóm đạt; native Qt đã xem 1/2/4 bệ và 16 viên lẻ cùng bia. 17 test nhóm/vẽ ảnh đạt sau sửa ô vuông khung đỏ. Build V47-071126 đạt, native Qt từ PYZ đóng gói xác nhận 1/2/4 bệ và xuống hàng, bàn giao Desktop giữ dữ liệu. Chưa thử thiết bị thật/EXE mặc định.

## Giới hạn xem lại — 2026-11-07

- MainWindow chặn receipt vượt bullet_limit trước khi tăng counter/nhóm/submit. ShotReviewDialog lọc cả source ban đầu và refresh, receipt/fired count, chỉ tạo max_bullets ô.
- 367 tests đạt. Người dùng chọn concept A; icon ImageGen ở assets/images/single_shot.png thay ô vàng, QImage giữ alpha và cache hai kích thước để icon nhỏ rõ. Build V46-071126; native Qt/PYZ kiểm tra icon và lịch sử 25 phát chỉ hiện 16, bàn giao Desktop giữ dữ liệu. Chưa kiểm tra EXE mặc định hoặc thiết bị thật.

## Mốc chuyển bia và ô vuông bắn lẻ — 2026-11-07

- target_presentation giữ bia đã gập đến midpoint giữa lần gập thực tế (sau hardware delay) và lịch hiện bia kế tiếp; ưu tiên bia còn đang hiện khi chồng lịch.
- process_shot lưu displayed_target_index tại received_at. Bắn lẻ ưu tiên bia hiển thị, kể cả gập; khi nhiều bia cùng hiện dùng nhận diện. Cảnh báo ô vuông vàng góc trên phải, viền xanh/đỏ giữ cả khi gập.
- 364 tests đạt và 8 tests luồng trình bày đạt sau bổ sung kiểm tra attribution tại mốc chuyển. Build V44-071126 đạt; native Qt từ PYZ đóng gói xác nhận mốc chuyển và ô vuông vàng. Bàn giao Desktop, giữ cấu hình/dữ liệu. Chưa kiểm tra khởi động EXE mặc định hoặc thiết bị thật.

## Bắn lẻ và bia xem lại cố định — 2026-11-06

- Bia xem lại dùng padding cố định 12.5% cạnh dài, căn giữa; điểm ngoài khung bị ẩn, không mở rộng theo điểm.
- single_shot_violations dùng receipt/burst_id trước inference; chỉ chốt viên cuối sau burst_gap_seconds hoặc stop. Có ít nhất một loạt 1 viên: Giỏi→Khá, Khá→Đạt, giữ Đạt/Không đạt; chỉ hạ một bậc. Viền vàng ưu tiên xanh/đỏ của bia liên quan, cả khi gập. Không đoán bia khi chồng bia và thiếu nhận diện.
- Màn hình/âm thanh/Excel cùng xếp loại; Excel J chấp nhận bậc đã hạ, không cho hạ Đạt hoặc hạ hai bậc. Legacy không có cadence không bị suy đoán bắn lẻ.
- 363 tests đạt; 10 test đọc/kiểm tra Excel đạt sau bổ sung chặn hạ hai bậc. Native Qt đã xem viền vàng và bia cố định với điểm xa; ảnh ở outputs/single-rule-v43. Đã build V43-061126, kiểm tra native Qt từ PYZ đóng gói và bàn giao Desktop, giữ 31 file cấu hình/dữ liệu. Chưa kiểm tra khởi động EXE mặc định hoặc thiết bị thật.

## Sửa chế độ không LoRa — 2026-11-06

- Lỗi bia không hiện do đợi command_sent dù không chọn COM. MainWindow chốt _simulate_targets theo port_name ở đầu bài; không LoRa dùng mốc mô phỏng để chạy cả lịch/nhận điểm/tự kết thúc, không gọi gửi serial. Có COM vẫn theo tín hiệu ghi thực tế, không giả lập khi COM lỗi.
- disconnect_port xóa port_name để không mở lại COM cũ; Settings giữ hiển thị tên COM chưa khả dụng thay vì báo nhầm Không sử dụng LoRa.
- timing_error_label chỉ hiện khi có lỗi, nền trong suốt; không còn dải trống khi hợp lệ.
- 354 tests đạt, gồm timer Qt thật ở chế độ không LoRa, chồng bia, kết thúc, COM lỗi và dòng lỗi. Native Qt từ mã/tài nguyên đóng gói V42-061126 xác nhận bia hiện đúng giây 15 và gập ở giây 22. Chưa thử cơ cấu bia thật.

## Xem lại style B — 2026-11-06

- Hai ảnh lớn, dải đạn trên điều hướng, không có chú giải ngoài giao diện chính. Xem log mở riêng; viên đang chọn viền blue, loạt khung vàng. Ảnh mô phỏng có nền trắng rộng, không viền kết quả.
- shooting.max_bullets=16 dùng chung bộ đếm/UART/roster/dải đạn; burst_gap_seconds=0.3 nhóm theo receipt trước inference, riêng bệ/phiên. Giữ nhóm khi chấm xong khác thứ tự; cập nhật kết quả trễ và giữ lựa chọn.
- 348 tests đạt; build V41-061126 và chụp giao diện từ mã PYZ đóng gói đạt. Chưa thử phần cứng thật. Ảnh ở outputs/review-b-v41.

## Chỉnh hình thức Cài đặt — 2026-11-06

- SettingWindow giữ nguyên stylesheet hai nút adjust_btn/Q0_btn từ setting.ui, kể cả chuyển kết nối/reset. Bỏ nền tiêu đề thời gian (transparent) và bỏ dòng ghi chú, dồn các hàng trong grid; bốn ô ảnh bia dùng nền trắng, tên bia/Hiện/Ẩn nền trong suốt. Hai nút camera/Q0 radius=8 được khai báo trong setting.ui để MonkezButton giữ đúng khi hover/check/reset.
- 35 test liên quan đạt; probe native Qt đối chiếu stylesheet trước/sau khởi tạo/kết nối/ngắt, xác nhận note đã xóa. Bản V40-061126, ảnh mới ở outputs/giao-dien-v40/setting.png; giữ cấu hình/dữ liệu khi thay bản Desktop.

## Thời gian bia và bù trễ — 2026-11-06

- SettingWindow dùng time_setting_frame và channel_combo người dùng bố trí: ảnh + mốc Hiện/Ẩn bốn bia; Kênh 1–3 chỉ lưu lựa chọn. userData dùng keyword cho cả ComboBox Fluent và MonkezComboBox. CHẤP NHẬN ghi JSON nguyên tử, giữ khóa khác; Hủy/validation/lỗi ghi giữ dữ liệu cũ. Nạp lại sau restart, áp dụng ở bài tiếp theo.
- shooting.target_times gồm 4 cặp show_seconds/hide_seconds theo 6/10/7B/8C (tối đa 3600 s). Cho phép chồng lịch và mốc hiện bằng nhau; giữ thứ tự hiện theo cột, mốc ẩn độc lập. Chưa có thì lấy mốc lora_timeline cũ và thời lượng 7/7/7/18. shooting.control_channel và shooting.hardware_delay_time (mặc định 1.5); gửi sớm một delay bằng lệnh thủ công hiện @114#/@224#/@334#/@441#, ẩn @112#/@222#/@332#/@442#.
- Nhận điểm chỉ sau actual command_sent của lệnh hiện, kết thúc trước lệnh ẩn thực tế +2*delay. Tự kết thúc sau khi đủ bốn lệnh ẩn thực sự gửi và lệnh cuối +4*delay; bỏ hạn 85 s cố định. Nếu chưa gửi đủ lệnh ẩn thì chờ hoặc kết thúc thủ công. Gập sớm cũng cập nhật các mốc; chỉnh theo serial write thực tế nếu hàng đợi trễ. ShootingSession giữ API legacy khi không truyền delay; MainWindow luôn dùng mode mới.
- Mô phỏng đổi trạng thái sau gửi thực tế +delay; khi lệnh ẩn chưa ghi ra serial thì không cắt sớm khoảng nhận theo lịch dự báo. Nhiều bia cùng hiện chia khung theo viewport, mỗi tên bia kèm ĐANG HIỆN trên cùng hàng (bỏ nhãn chung), từng bia nhận điểm/gập độc lập; không còn ép về chỉ bia mới nhất. Bia gập nhạt hơn (16% ảnh xám).
- Dừng hủy lịch, gửi ẩn các bia đã dựng còn lại. Thoát chặn lệnh hiện còn chờ rồi ghi lệnh ẩn cuối trước khi đóng serial, không chờ ACK lúc thoát.
- 340 tests đạt; native Qt kiểm tra form, 2/4 bia chồng ở 1/2/4 bệ và tự kết thúc theo lần ghi lệnh ẩn trễ. Bản cuối V37-061126; kiểm tra PYZ/tài nguyên cùng lưu/nạp qua file tạm. Chưa thử phần cứng thật hay UI EXE mặc định. Giữ dữ liệu/cấu hình Desktop V32 trước khi chuyển bản cũ vào Recycle Bin.

## Kết quả và điểm chạm quanh bia — 2026-11-06

- Sau stop/kết thúc bài, `_show_final_results` làm ảnh bia chưa trúng mờ đen trắng nhưng giữ viền đỏ; bia đã trúng giữ màu/viền xanh. Reset/mở app trả ảnh màu; kết quả trúng đến trễ cập nhật lại màu đúng bia.
- Ảnh bia thu nhỏ còn 90% mỗi chiều trong khung, căn giữa. `record_shot` giữ tọa độ hữu hạn ngoài 0–1; `_draw_shot` chiếu theo ảnh đã fit, chỉ hiện tâm trong vùng trống bên trong khung và clip marker vào khung đó. Điểm xa ẩn, không kéo vào mép hay tràn sang bia khác; số đạn/tính trúng không đổi.
- Nền nhãn CHƯA KẾT NỐI: rgb(0, 170, 255). Chỉ stage thay đổi màu trong client.ui; các chỉnh kích thước/font người dùng đang làm được giữ ở working tree.
- 326 tests đạt; xem giao diện Windows Qt 1/2/4 bệ có điểm lệch gần/xa và kết quả hỗn hợp; kiểm tra mã PYZ/tài nguyên V32-061126 trong luồng Qt giả lập phần cứng đạt. Chưa kiểm tra súng/bia thật và khởi động EXE mặc định bằng thao tác trực tiếp.
- Bản Desktop V32-061126 giữ cấu hình/dữ liệu từ V31 trước khi dọn bản cũ vào Recycle Bin.

## Hiển thị theo lượt bia — 2026-11-06

- Khi bắt đầu chỉ phóng to bia 6 đang gập, rồi theo thứ tự 6 → 10 → 7B → 8C. Bia gập mờ đen trắng; đến lượt hiện có màu rõ. Sau khi gập (hết giờ hoặc trúng khi bật auto-close), giữ 0,8 giây rồi xem trước bia tiếp theo đang gập. Bia cuối giữ gập đến kết thúc.
- `ShootingSession.target_presentation` dùng thời điểm dựng/gập điều khiển, tách khỏi scoring grace. MainWindow cập nhật 100 ms, chỉ vẽ lại khi trạng thái đổi; dừng bài trả overview cả bốn bia và giữ dấu chạm. Resize theo viewport, marker theo ảnh bia đã fit.
- Tên và trạng thái cùng hàng. Người dùng chốt BIA SỐ 7B, BIA SỐ 8C, không ghi alpha trên nhãn. Viền bo góc khử răng cưa bằng QPainter trên buffer BGR ghi trực tiếp qua sip.voidptr; xanh/đỏ rõ cùng lớp halo nhạt, gập dùng xám.
- 319 tests đạt; đã xem ảnh Windows Qt ở 1/2/4 bệ và kiểm tra luồng từ mã PYZ + tài nguyên bản V31-061126, gồm nhãn một hàng không tràn và hiện/gập/trả overview. Chưa thử cơ cấu bia/súng thật.
- Build cuối V31-061126; chuyển cấu hình/dữ liệu từ V28/V30 sang bản Desktop trước khi dọn bản cũ vào Recycle Bin. V29/V30 là bản trung gian trước các chỉnh nhãn/viền trong cùng task.

## Hoàn tất âm thanh — 2026-11-06

- Dùng `assets/new_sounds`: bắt đầu tập; đọc bệ + các bia class 1/0/2/3 theo thứ tự 6/10/7b/8c alpha 45 (góc do người dùng xác nhận), số điểm chạm 0–16 và xếp loại. Không thêm bia 5/8c alpha 90 vào bài hiện tại.
- `ClientWidget.hit_counts` đếm điểm chạm hợp lệ độc lập marker, reset cùng kết quả; snapshot khi bấm loa. Giữ xếp loại và giao thức phần cứng.
- 312 tests đạt; 17 tests âm thanh đạt sau review cuối; phát thực qua QMediaPlayer Windows hoàn tất không lỗi. Build V28-061126 thành công, đủ 32 WAV được kiểm tra hash ở Desktop.
- EXE khởi chạy nhưng công cụ UI không liệt kê cửa sổ để thao tác. Chưa xác nhận trực tiếp nút bấm trên EXE và chưa thử thiết bị bắn thật.
- Môi trường `.venv` cũ trỏ tài khoản Admin không tồn tại; đã tái liên kết Python 3.11 tại `work/python` bằng uv --allow-existing, giữ dependencies.

# Trạng thái dự án

## Sửa dấu điểm chạm bị ẩn khi xem lại (2026-10-29)

- Bỏ điều kiện `shooting.show_rejected_shots_on_target` khỏi Xem lại: hai panel chỉ theo bốn khóa `review`, kể cả khi `scoring_eligible=false`. Màn hình chính vẫn ẩn phát bị từ chối như trước.
- Giữ nhãn KHÔNG TÍNH ĐIỂM, lý do và thêm chú thích điểm dùng để đối chiếu. Không thay đổi phép tính điểm hoặc số đạn.
- 76 test review/config/luồng bài bắn đạt; ảnh render bia 7B cùng dữ liệu tái hiện bản cũ không có dấu, bản sửa có dấu đỏ.
- Build `MBT03-Bai2-V27-291026` thành công; kiểm tra mã trong PYZ và config đã đóng gói. Chưa chạy thử trực tiếp EXE mới với súng thật.

## Điểm ngắm/điểm chạm và phát bị từ chối (2026-10-28)

- Xem lại chiếu ngược điểm sau offset lên ảnh thật bằng affine của chính phát bắn; lưu tọa độ chuẩn hóa, không tính lại theo config hiện tại. Phép biến đổi không khả nghịch/không hữu hạn không sinh điểm giả; điểm ngoài ảnh/vùng zoom không bị kéo vào mép.
- Bốn khóa `review.show_camera_aim_point`, `show_camera_impact_point`, `show_simulation_aim_point`, `show_simulation_impact_point` mặc định `true/true/false/true`. Khóa cũ `show_before_offset` được đọc dự phòng cho `show_simulation_aim_point`.
- `shooting.show_rejected_shots_on_target=false`: ẩn dấu trên bia chính với phát không đủ điều kiện thời gian/bia (từ V27, Xem lại chỉ theo các công tắc `review`); lưu riêng `scoring_eligible` và `hit_on_image`, hiển thị KHÔNG TÍNH ĐIỂM. Không thay đổi số đạn, lịch sử, điểm số, báo trúng; phát trượt hình học hợp lệ vẫn vẽ bình thường.
- Kiểm chứng: 307 test đạt, gồm 16 tổ hợp hiển thị, affine xoay/scale, điểm ngoài ảnh, phát bị từ chối và nhận đồng thời bốn súng. Đã xem ảnh render của hai panel và trường hợp ẩn dấu. Render Qt offscreen vẫn thiếu chữ nên chưa xác nhận bố cục chữ bằng mắt; test QLabel kiểm tra nội dung/chú thích.
- Build `MBT03-Bai2-V26-281026` thành công; kiểm tra mã trong PYZ, config và asset đóng gói khớp nguồn. Chưa kiểm tra trực tiếp EXE mới và súng thật.

## Cập nhật nút điều khiển và gộp cấp đạn (2026-10-21)

- Thay thế cơ chế thủ công mô tả bên dưới: ẨN BIA gửi `@661#` đúng một lần, không ACK; HIỆN BIA gửi `@114#` → `@224#` → `@334#` → `@441#`, có ACK/retry và chờ 100 ms sau ACK trước lệnh kế tiếp. Bộ lệnh thủ công độc lập với lịch bài bắn.
- UI người dùng đã bỏ `prepare_btn`; BẮT ĐẦU cấp `0F016\n` cho mỗi bệ rồi hẹn `0A000\n` sau 300 ms. Dừng/đóng hủy lệnh đang hẹn; lịch LoRa trong bài bắn giữ nguyên, không tự gập tất cả bia khi START.
- Kiểm chứng: 298 test đạt; Qt kiểm tra click ẨN/HIỆN/BẮT ĐẦU/DỪNG với bốn bệ giả lập đạt. Build `MBT03-Bai2-V20-211026` thành công, UI đóng gói khớp source. Công cụ desktop vẫn không thấy cửa sổ sau khi mở EXE nên chưa xác nhận khởi động bình thường; chưa thử thiết bị thật. Render offscreen thiếu chữ, không dùng làm bằng chứng hiển thị/DPI.

## Điều khiển bia thủ công (2026-10-21)

- Hai nút người dùng thêm trong `main.ui`: `close_target_btn` gửi `@611#` có ACK; `open_target_btn` gửi tuần tự lệnh hiện bia 6/10/7/8 từ `LORA_SCRIPT` (mặc định `@111#`, `@221#`, `@331#`, `@444#`). START bỏ lệnh tự động `@661#` cũ, giữ lịch bia và UART `0A000` sau 300 ms.
- `LoraController.send_sequence` chạy cả chuỗi trên executor một worker: nhận ACK chờ 100 ms trước lệnh sau; thất bại sau các lần thử chuyển ngay. Không xen lệnh khác vào giữa chuỗi; đóng app ngắt khoảng chờ. Khóa hai nút/START/Cài đặt khi gửi và hai nút khi đang bắn; `sequence_finished` mở lại sau hoàn tất.
- Thông tin này thay thế mô tả START tự gửi lệnh gập bia ở các mục cũ bên dưới; ngoại lệ không ACK cho `@661#` vẫn giữ trong controller nhưng không còn được START gọi.
- Kiểm chứng: 297 test đạt; kiểm tra Qt hai nút với kết nối giả lập và DPI 200% đạt. Build `MBT03-Bai2-V18-211026` thành công, đối chiếu UI trong bundle khớp source. Smoke test desktop chưa hoàn tất: cả source và EXE không hiện hộp chọn bệ; source ghi nhận Windows COM `0x8001010d` tại `OptionWindow.exec_()`. Chưa xác định nguyên nhân môi trường này, chưa kiểm ACK với LoRa thật.

## Tiếp nhận đồng thời bốn súng (2026-10-16)

- Tái hiện ảnh đã nhận hợp lệ nhưng bị loại sau giải mã khi heartbeat quá 6 giây dù generation không đổi. Sau giải mã chỉ kiểm tra kết nối còn gắn và generation không đổi; kiểm tra heartbeat khi tiếp nhận vẫn giữ nguyên. Không đổi giao thức/client/firmware hay mốc kết thúc bài 85 giây.
- Tăng hàng đợi ảnh nén mỗi server/bệ lên 64 (trước đây decode 8, socket 5), vẫn hai worker giải mã mỗi bệ. Hàng đợi có giới hạn và chờ khi đầy; log `[ShotTransport]` báo nhận/đầy, `received_at`, `queue_decode_ms`, `ui_delay_ms` để đối chiếu trên máy khác.
- Khóa bắt đầu lượt mới khi còn tác vụ chấm, kể cả không nạp Excel; mở lại sau khi hoàn tất, tránh xóa kết quả cũ đang chờ.
- Regression gồm 4 nguồn TCP đồng thời gửi 16 JPEG 640×480 mỗi nguồn với sender HWM=3/timeout=200 ms; giữ giải mã, làm heartbeat hết hạn sau tiếp nhận rồi nhả, kiểm đủ 64 ảnh và timestamp trước khi nhả. Kiểm riêng 4 worker chấm/Qt với 64 phát, lỗi inference xen kẽ và dừng bài lúc còn chờ, mỗi bệ phải đủ 16.
- `test.bat`: 289 test đạt. Stress TCP lặp 20 lượt (1.280 ảnh) đủ, không trùng; kiểm ngược giới hạn cũ 8 ảnh tái hiện cả bốn bệ chỉ đọc 8/16 trước khi nhả giải mã. Chưa kiểm trên máy đang báo lỗi hoặc bốn súng thật; chưa build EXE.

## Cấp đạn thủ công (2026-10-16)

- `prepare_btn` (CẤP ĐẠN) gửi `0F016\n` đến các bệ, không bắt đầu bài. Giữ khóa config `shooting.start_uart_command` để tương thích nhưng chỉ dùng cho nút cấp đạn.
- Luồng bắt đầu không tự cấp đạn nữa: vẫn gửi LoRa `@661#` một lần không chờ echo, lập lịch bia và gửi `0A000\n` sau 300 ms. Dừng/đóng hủy timer như cũ. Thông tin này thay thế các mô tả chuỗi `0F016` → `0A000` bên dưới.

## Offset trên ảnh client demo (2026-10-15)

- `client_demo.py` vẫn là entry point; `assets/server_client/demo_client.py` vẽ Q0 hiện tại từ `client.q0_value`, dX/dY theo % so với tâm `(0.5, 0.5)` và dấu ngắm xanh. Chỉ vẽ trên QPixmap riêng của preview, giữ nguyên ảnh capture gửi stream/chấm điểm. Cache ảnh gốc để cập nhật Q0 lúc streaming mà không tranh camera; đổi camera/backend xóa cache. Q0 sai/không hữu hạn/ngoài [0,1] hiển thị thông báo, không giả làm tâm.
- Canvas theo DPR để chữ/dấu ngắm rõ ở High DPI; giữ vị trí đúng khi ảnh có khoảng đệm hai bên. Đã kiểm tra UI Qt Windows ở DPR 1.5 bằng ảnh mẫu và client giả lập; `test.bat` đạt 282 test, gồm offset cập nhật, pixel ảnh gốc không đổi, Q0 lỗi, vị trí biên và DPR 2. Chưa thử Q0 từ súng thật; không đổi core/giao thức hay build EXE.

## DPI và Scale Windows (2026-10-14)

- `main.run_app` dùng `HighDpiScaleFactorRoundingPolicy.PassThrough` trước khi tạo QApplication, giống MBT03-wireless; giữ hai cờ High DPI/Pixmaps. Lỗi cấu hình DPI được ghi log thay vì bỏ qua. Không đổi kích thước UI, cấu hình Scale Windows hay file `score_card.ui` người dùng đang chỉnh.
- Tái hiện bằng Qt Windows 5.15.2: Windows báo 144 DPI (150%) nhưng mặc định Qt làm tròn thành DPR 2; cột trái 760 px, hàng danh sách 96 px. PassThrough trả DPR 1.5, tương ứng 570/72 px. 125% mặc định xuống 100%, 175% lên 200%; 100% và 200% thực không đổi sau sửa. Thử tắt High DPI gây chữ bị cắt nên không dùng.
- Kiểm tra startup thực trong tiến trình riêng với `QT_FONT_DPI` 96/120/144/168/192 (giả lập DPI, không đổi thiết lập Windows): test mới thất bại ở 125/150/175% trước sửa, đạt cả năm mức sau sửa; toàn bộ `test.bat` đạt 276 test. Quan sát Qt thực và thao tác chuột/phím 2 bệ ở 1366×768, 100%; 2/4 bệ ở 150%, 4 bệ ở 200%. Phần cứng giả lập; chưa thử chuyển giữa hai màn hình khác DPI, chưa build EXE.

## Danh sách bắn Excel (2026-10-14)

- `gui/shooting_roster.py` đọc sheet active `.xlsx`, bỏ tiêu đề dòng 1; Theo mẫu `c351-d3-HVKTQS.xlsx`: A–E là STT/họ tên/đơn vị/ngày sinh/cấp bậc; F–I là bia 6/10/7b/8c (0/1), J xếp loại. Nạp lại kết quả có sẵn, giữ dòng chưa bắn trống; kết quả đủ bốn bia tự tính xếp loại nếu J trống. Kiểm tra tiêu đề có chuẩn hóa dấu Unicode, dữ liệu 0/1 và xếp loại khớp; báo rõ dòng/cột lỗi. Vẫn nhận danh sách A–D chưa có kết quả. Dùng `openpyxl==3.1.5`, đóng workbook sau đọc, kiểm tra STT nguyên dương/không trùng và họ tên; lỗi giữ nguyên danh sách cũ. Đọc nền qua executor một worker; đóng cửa sổ bỏ kết quả nạp còn chờ.
- Theo yêu cầu dùng đúng UI wireless: nạp từng `assets/qt/score_card.ui` vào `score_card_layout`, nút Vào bắn riêng đổi trắng/xanh. Giữ tên `targets_label` người dùng đã đổi; chuyển widget này thành QLabel rich text, hiển thị `3/4` với riêng số trúng màu đỏ và cập nhật ngay lúc chấm. Ô xếp loại dùng GIOI/KHA/DAT/KDAT như wireless, tooltip đầy đủ; một bệ thêm ngày sinh vào tên danh sách. Bỏ QListWidget và nút Vào bệ chung của bản trước.
- Phân bệ `(STT - 1) % p_num + 1`; Loạt bắn mới bỏ người cũ rồi lấy người chưa bắn đầu tiên từng bệ, kể cả khi đã hết người. Giữ trạng thái kết nối/đèn tìm súng khi đổi người; x bỏ người. Cho phép bắt đầu chưa chọn người như wireless. Khóa nạp/lưu/đổi người/chuyển loạt trong bài và khi còn chấm chờ. Snapshot người–bệ theo phiên để không cộng ảnh trễ sang người mới; dùng chung hàm xếp loại ClientWidget.
- Lưu kết quả nền vào `Kết quả - <tên file>.xlsx` cùng thư mục, cột F–I kết quả từng bia 0/1 và J xếp loại đầy đủ; lưu tập class trúng thay vì chỉ tổng số. Dòng chưa bắn giữ trống F–J, đã bắn không trúng ghi 0/0/0/0 và Không đạt; giữ sheet/định dạng/các cột khác và file gốc. Lưu đúng dòng thực thay vì STT + 1; kiểm tra danh sách nguồn chưa bị đổi và ghi qua file tạm + replace để lỗi/Excel khóa file không làm hỏng kết quả cũ. Bắn lại thay kết quả người đó; cần Lưu kết quả trước khi thoát.
- `test.bat` đạt 275 test, gồm ánh xạ riêng từng bia khi lưu/nạp lại, dữ liệu sai/thiếu, kết quả có sẵn và chuyển loạt, giữ định dạng/file khóa và màu rich text. Đã nạp đủ 10 người từ `c351-d3-HVKTQS.xlsx`, lưu trên bản sao tạm rồi nạp lại: kết quả 3/4 Khá, mọi ô/định dạng/độ rộng cột giữ nguyên, file nguồn không đổi. Đã kiểm tra UI Qt Windows 2 bệ 1366×768 (DPR 2), kết quả nhập hiển thị đúng và chuyển loạt bỏ người đã bắn; dùng dữ liệu mẫu, mock phần cứng. UI 1/4 bệ đã kiểm tra ở lượt trước. Chưa build EXE trong khi chờ hoàn tất âm thanh.

## Kiểm tra thiếu phát bắn phía PC (2026-10-14)

- Giới hạn phạm vi theo yêu cầu: chỉ sửa PC, không đổi client/firmware. Trong đoạn `server.log` 09:56:16–09:57:41, bệ 1 có 13 thông báo/13 ảnh/13 kết quả chấm, bệ 2 có 16/16/16; chưa có bằng chứng PC làm mất ba ảnh trong lượt này. Log cũ chỉ ghi giờ nên không suy ra ngày của lượt từ timestamp.
- Tái hiện và sửa lỗi riêng ở PC: Q0 sai kiểu/thiếu tọa độ gây exception khi định dạng log, làm bỏ ảnh hợp lệ trước khi emit. Chuẩn hóa Q0 về cặp số hữu hạn, fallback tâm `(0.5, 0.5)` như quy ước GUI sẵn có và ghi cảnh báo. Chưa có bằng chứng lỗi này gây lượt 13 viên nói trên.
- Bổ sung `[ShotReceipt]` nhận/loại ảnh, `[Exercise]` đầu bài và thống kê khi dừng (nhận/chấm xong/đang chờ/đạn hiển thị), lưu lỗi chấm và lý do loại sau decode khi kết nối hết hạn/đổi phiên. `Đạn` vẫn tăng sau chấm; ảnh nhận trong bài được hoàn tất sau dừng, bài mới bỏ kết quả cũ.
- `test.bat` đạt 252 test. Mở rộng kiểm tra 16 ảnh khi decode bão hòa, hoàn thành chấm ngược thứ tự có 3 lỗi, 13 kết quả trước dừng + 3 sau dừng, hai kênh localhost nhận 16 ảnh burst/bệ (ngoài 3 ảnh ban đầu). Chưa thử thiết bị thật; chưa build EXE trong khi chờ hoàn tất âm thanh.

## Nới thời gian nhận trúng (2026-10-14)

- Tăng nhận sớm từ 1 lên 2 giây, nhận muộn từ 2 lên 4 giây (kể cả gập sớm tự động do trúng). Giữ thời lượng cơ sở 7/7/7/18 giây, lịch LoRa và giới hạn bài 85 giây. Lịch mặc định nhận bia 6: [13,26), bia 10: [30,43), bia 7B: [40,53), bia 8: [62,85).
- Khoảng nhận được phép chồng nhau: `active_target` ưu tiên class đã nhận diện khi chấm xong, giữ đủ khoảng của bia trước sau khi bia sau dựng. Kiểm tra cấu hình lịch dựa trên thời lượng cơ sở không chồng nhau/không vượt 85 giây; phần grace được giới hạn bởi deadline, không làm cấu hình lệnh LoRa hợp lệ bị thay bằng mặc định.
- `test.bat` đạt 249 test, gồm biên thời gian/serial trễ/gập sớm/chồng cửa sổ/deadline. Đã xác nhận cấu hình LoRa hiện tại được giữ nguyên. Chưa thử phần cứng và chưa build EXE trong khi chờ hoàn tất âm thanh.

## Tên file ảnh gốc trong Xem lại (2026-10-13)

- Mỗi phát mang Future của tác vụ lưu ảnh từ luồng nhận qua chấm điểm (kể cả chấm lỗi) tới dữ liệu review, giữ đúng file khi các tác vụ hoàn thành khác thứ tự. Không chờ ghi đĩa trong luồng giao diện/chấm.
- Review có dòng tên PNG chọn/copy được, tooltip đường dẫn; chỉ hiển thị tên khi lưu thành công. Nếu đang lưu, timer 250 ms cập nhật riêng dòng này; dừng khi xong/chuyển sang phát khác/đóng dialog. Không lưu/lưu lỗi có trạng thái riêng.
- `test.bat` đạt 247 test. Đã mở Qt trên Windows và kiểm tra tên file ở cửa sổ 1180×740 và 920×600. Chưa build EXE trong khi chờ hoàn tất âm thanh.

## Tìm súng và gập bia đầu bài (2026-10-13)

- Bấm trái nhãn bệ (hoặc Enter/Space) bật/tắt tìm súng bằng `0LR01\n` / `0LG00\n`, theo giao thức MBT03-wireless. Nhãn nhấp nháy mỗi 500 ms, ưu tiên màu cảnh báo mạng. Chỉ đổi trạng thái khi gửi thành công; ngắt kết nối xóa trạng thái, thoát app trả đèn xanh cho súng đang tìm còn kết nối.
- Mỗi lần bắt đầu bài gửi thêm `@661#` qua LoRa trước khi lập lịch dựng bia; giữ UART `0F016\n` → 300 ms → `0A000\n`.
- `test.bat` đạt 242 test; đã mở giao diện Qt trên Windows, bấm nhãn và kiểm tra ảnh nhãn đỏ đang tìm súng/cảnh báo kết nối màu cam. Chưa thử súng/cơ cấu bia thật. Chưa build EXE trong khi chờ hoàn tất âm thanh.

## Thông báo loại phát bắn (2026-10-12)

- Review thay cụm “ngoài cửa sổ nhận” bằng “ảnh nhận ngoài thời gian cho phép tính điểm”, ghi mốc PC nhận ảnh từ đầu bài, khoảng mở/đóng và độ sớm/muộn; nhận diện sai ghi cả bia nhận diện và bia được phép tính điểm. Không đổi quy tắc chấm.
- Ghi chẩn đoán chấm vào `server.log` UTF-8 sẵn có, kèm phiên/bệ/phát, kết quả trên ảnh và kết quả sau kiểm tra thời gian. `test.bat` đạt 236 test. Chưa build EXE trong khi chờ hoàn tất âm thanh.

## Nhận trúng và báo trúng một bệ (2026-10-12)

- PC đóng dấu `_server_received_at` bằng monotonic ngay sau nhận gói ảnh, trước decode/UI; trường này luôn ghi đè metadata từ client. MainWindow dùng dấu thời gian đó, giữ cửa sổ các bia trước và nhận ảnh chờ decode/UI của bài vừa dừng nếu nhận trước mốc dừng. Ảnh trước bài mới/sau mốc dừng không được tính.
- LoRa phát `command_sent(command, queued_at, sent_at)` sau lần ghi serial đầu tiên, không cập nhật lại khi retry. ShootingSession hiệu chỉnh mốc dựng/gập theo thời điểm gửi, giữ giới hạn 85 giây, nhận sớm 1 giây/muộn 2 giây; bỏ qua lệnh được xếp hàng ngoài phiên. Kết quả chấm đang chờ được xét lại theo cửa sổ đã hiệu chỉnh. Review thêm giây nhận ảnh/khoảng nhận khi loại vì thời gian.
- Một bệ tắt gập cũng báo số bệ khi trúng; vẫn một lần mỗi cặp bia–bệ. Một bệ bật gập giữ chế độ không đọc số.
- `test.bat` đạt 235 test. Chưa thử bia/súng thật. Người dùng xác nhận các ảnh bị loại lúc bia còn dựng; đã sửa hai nguồn lệch mốc trong PC, vẫn cần đối chiếu thời lượng bộ điều khiển của bia 6/10/7B (phần mềm hiện 7 giây, bia 8 là 18 giây). Chưa build EXE, đang chờ hoàn tất âm thanh.

## Chuyển cụm âm thanh kết quả (2026-10-12)

- `ResultSound` dùng SoundFile giải mã hai MP3, đổi về PCM 44.1 kHz stereo, thêm 120 ms im lặng và fade mép 5 ms, rồi phát một WAV tạm duy nhất. File gốc giữ nguyên; dọn file tạm khi dừng/kết thúc/lỗi. `DAT.mp3` hiện là 22.05 kHz mono, các cụm khác là 44.1 kHz stereo.
- Không dùng QAudioDecoder: stress dừng/đọc lại tái hiện access violation của backend Windows. Không phát qua QBuffer vì thử nghiệm DirectShow bị treo; dùng WAV đã đóng file handle. Dependency `soundfile==0.13.1` có hook PyInstaller đi kèm DLL libsndfile trong môi trường build hiện tại.
- `test.bat` đạt 223 test; 40 lượt stress hủy/đọc lại và lỗi giải mã đạt. Đã phát 4 câu qua Qt thật ở volume 0, kiểm tra dọn file, kiểm tra cả 16 tổ hợp bệ/xếp loại; chuẩn bị câu đo được 5.83–8.31 ms. Chưa xác nhận nghe loa thực tế hoặc build lại EXE trong khi chờ người dùng hoàn tất âm thanh.

## Khởi động Q0 (2026-10-12)

- `SettingWindow` gửi `0F003\n` đến bệ đang chọn rồi timer Qt một lần gửi `calibration.uart_command` (mặc định `0Q000\n`) sau 300 ms. Chưa thu mẫu trong thời gian chuẩn bị; không gửi tiếp khi lệnh đầu thất bại hoặc bệ mất kết nối.
- Timer gắn với dialog, bị hủy khi tắt Q0, đổi bệ hoặc `done()`; đổi bệ reset mẫu/trạng thái Q0 để không lẫn dữ liệu. Không đổi chuỗi bắt đầu bài `0F016` → 300 ms → `0A000`.
- `test.bat` đạt 210 test; đã thử timer Qt thật với server giả lập, bật/tắt lại, đổi bệ, các đường đóng dialog, lỗi gửi và mất kết nối. Chưa thử súng thật hoặc build lại EXE trong khi chờ người dùng hoàn tất âm thanh.

## Cửa sổ nhận bia (2026-10-12)

- `ShootingSession` nhận lịch dựng từ MainWindow, tạo trước cửa sổ để chấm được ảnh đến sớm 1 giây. Kết thúc nhận sau thời lượng cơ sở/lệnh gập sớm thêm 2 giây, không vượt hạn bài 85 giây. Giữ object cửa sổ khi gửi lệnh dựng để job đến sớm vẫn được kiểm tra đúng.
- Lịch mặc định có cửa sổ [14,24), [31,41), [41,51), [63,84). Kiểm tra lịch yêu cầu các mốc cách nhau ít nhất 10 giây và bia cuối dựng không muộn hơn giây 65. Tách thời gian bia đang được dựng khỏi cửa sổ nhận để không gập trước lệnh dựng, trong phần nhận muộn hoặc gập lặp.
- `test.bat` đạt 205 test, bao phủ ranh giới cửa sổ, nhận sớm trước lệnh dựng, timer dựng trễ, gập sớm, hai cửa sổ liền nhau và hạn 85 giây. Chưa thử súng/bia thật hoặc build lại EXE; vẫn chờ người dùng hoàn tất âm thanh.

## Xếp loại và đọc kết quả (2026-10-12)

- Hàng kết quả cách các nút 8 px, thêm lề phải 12 px để nút loa không sát khung; nút loa 28×28 với icon 20×20, nút Xem lại lấy kích thước theo nội dung thay vì giới hạn 50 px. Đã xem widget ở DPI 100%/200%, đo khoảng cách tại ba chiều rộng; bộ 218 test đạt.
- `ClientWidget._rank_text()` xếp loại theo số bia khác nhau đã trúng: 4 = Giỏi; 3 và có bia số 8 (class 3) = Khá; 2 hoặc 3 thiếu bia 8 = Đạt; 0–1 = Không đạt. Cập nhật ngay theo kết quả, không chờ hết 16 viên.
- Nút loa đọc kết quả đang hiển thị bằng `ResultSound`: `Beso{port}.mp3` rồi `GIOI/KHA/DAT/KDAT.mp3`, tốc độ 1×. Hai cụm được ghép thành một lượt phát như mục trên; chỉ một bệ đọc, bấm lại để dừng, lỗi file mở lại nút và báo lỗi. Gửi `0P000\n` đến súng được chọn như wireless. Khóa nút loa trong bài; bắt đầu bài/đóng cửa sổ hủy đọc. Đọc kết quả dừng các thông báo trúng bia đến lần reset bài tiếp theo để không chồng giọng.
- `test.bat` đạt 218 test, bao phủ cả 16 tổ hợp bia, trúng lặp, đọc đủ 4 bệ/4 xếp loại, dừng giữa hai clip, lỗi file/decoder và vòng đời màn hình. Đã chạy decoder Qt thật với cả 8 file ở volume 0 và xem trạng thái nút trên widget Qt. Chưa nghe loa/kiểm tra súng thật hoặc build lại EXE trong khi chờ người dùng hoàn tất âm thanh.

## Bố cục bia mô phỏng (2026-10-11)

- Bố cục đã chỉnh theo ảnh người dùng: bia 6 trên trái, bia 10 dưới trái, bia 7B ở cột giữa cao và bia 8 bên phải. Chế độ 2 bệ dùng thứ tự dọc 6, 10, rồi hàng 7B/8. Bia 7B được phóng vừa ô đứng, giữ cơ chế fit đúng tỉ lệ và ánh xạ dấu đạn theo vùng ảnh đã vẽ.
- Đã xem widget Qt ở bốn kích thước, kiểm tra tỉ lệ/biên ảnh và tọa độ dấu trúng trên cả hai bia. `test.bat` đạt 199 test. Chưa đóng gói bố cục mới vì đang chờ người dùng hoàn tất thay âm thanh.

## Thời gian bài bắn và cấu hình âm thanh (2026-10-11)

- `gui/shooting_session.py`: bài tối đa 85 giây; bia 6/10/7B giữ 7 giây cơ sở, bia 8 tăng lên 18 giây. Lịch mặc định vẫn 15/32/42/64; từ 2026-10-12 nới nhận sớm 1 giây/muộn 2 giây như phần cửa sổ nhận ở trên. Kiểm tra lịch dùng thời lượng riêng từng bia và không cho vượt thời hạn bài.
- Tốc độ đọc lấy từ `shooting.hit_announcement_playback_rate` trong `assets/configurations/config.json`, mặc định 1.75, giới hạn 0.5–4.0; mở lại app sau khi chỉnh. Loader nhận cả số nguyên và số thực cho khóa kiểu float, không nhận bool. Test âm thanh dùng cấu hình riêng để không phụ thuộc giá trị người dùng đang chỉnh.
- `test.bat` đạt 199 test. Đã kiểm tra mã thời gian trong EXE V4, nhưng V4 thiếu bốn âm thanh thông báo do người dùng thay file trong lúc đóng gói; không dùng bản này để bàn giao. Đang chờ người dùng xác nhận chỉnh âm thanh xong trước khi build lại.

## Đọc số bệ khi trúng (2026-10-11)

- Chế độ từ 2 bệ đọc `assets/sounds/noti/1.mp3` đến `4.mp3` ở tốc độ 1.75× sau khi kết quả vượt qua kiểm tra phiên/cửa sổ bia. `gui/hit_sound.py` chống lặp theo cặp bệ–bia trong bài và phát hàng đợi tuần tự; lỗi âm thanh không chặn số tiếp theo.
- Bắt đầu bài mới hủy hàng đợi cũ và xóa trạng thái đã đọc; đóng app dừng phát, bỏ kết quả đến muộn. Kết quả hợp lệ đang chấm khi kết thúc bài vẫn được đọc như cách cập nhật điểm hiện có.
- `test.bat` đạt 195 test. Qt Multimedia phát đủ 4 MP3 ở âm lượng 0, không lỗi: tổng 8.422 giây ở 1× và 5.141 giây ở 1.75× (gồm thời gian nạp/chuyển file). Chưa nghe qua loa hoặc thử với súng thật; EXE hiện có cần build lại để nhận thay đổi.

## Cảnh báo lỗi súng (2026-10-10)

- Nối `data_received_signal` theo đúng bệ với cảnh báo `UART_RX_DEBUG`: E1 giữ cò lâu, E2 bắn nhanh. Chỉ nhận mã đầy đủ, không dò chuỗi con.
- `ClientWidget` hiển thị cảnh báo trên bia, timer riêng mặc định 7 giây (`runtime.error_message_duration_ms`), lỗi mới khởi động lại timer; bắt đầu bài mới xóa cảnh báo cũ. Không cập nhật điểm/số đạn từ mã lỗi.
- `test.bat` đạt 188 test; đã xem ảnh dựng E1/E2 ở kích thước thường và hẹp. Chưa thử lỗi từ súng thật; cần build lại để cập nhật EXE.

## Lệnh bắt đầu/kết thúc (2026-10-10)

- Bắt đầu gửi `0F016`, timer một lần gửi `0A000` sau 300 ms (tăng từ 100 ms ngày 2026-10-12). Dừng bài/thoát ứng dụng hủy timer để không gửi lệnh muộn.
- Kết thúc bài (kể cả hết 75 giây hoặc thoát app trong bài) và đóng Setting gửi `0S000` tới tất cả súng; mọi lệnh UART đều kèm xuống dòng.
- `test.bat` đạt 181 test; chưa thử trên súng thật. Bản EXE V2 trước đó chưa chứa thay đổi này, cần chạy `build.bat` để đóng gói lại.

## Build và UART Debug (2026-10-10)

- `build.bat` gọi `scripts/build_release.py`, dùng `.venv` và `requirements-build.txt`. Output onedir/windowed trong `dist/`, phiên bản lưu sau build thành công ở `build_state.json`; đọc `docs/build.md` khi đổi cách đóng gói.
- `gui/uart_debug_dialog.py` là cửa sổ Ctrl + S, được MainWindow giữ lại khi ẩn để tiếp tục theo dõi giao dịch Wi-Fi. I/O chạy trên executor riêng; không lưu mật khẩu trong trạng thái. Khi thoát app phải gọi `shutdown()` trước khi dừng server.
- Wi-Fi dùng API sẵn có của `MBT03ServerCore`: request → ACK/status → commit khi khỏe. Hết deadline không khẳng định đã rollback nếu chưa nhận trạng thái. Không thay đổi protocol/board cho tính năng này.
- `test.bat` đạt 177 test. Đã build `MBT03-Bai2-V2-101026`, kiểm tra DLL ONNX/Qt Multimedia và dựng ảnh cửa sổ UART ở 620/520 px. Kiểm tra giao diện EXE trên desktop bị người dùng dừng bằng Esc; chưa xác nhận vận hành trên phần cứng hoặc máy sạch.

## Quy tắc bài bắn (2026-10-10)

- `gui/shooting_session.py` hiện giới hạn 85 giây (cập nhật 2026-10-11), thứ tự class `(1, 0, 2, 3)` và cửa sổ 7 giây cho ba bia đầu, 18 giây cho bia 8 theo thời điểm PC gửi lệnh dựng; lệnh gập vì trúng đóng cửa sổ sớm. Chưa có phản hồi vị trí bia thực từ phần cứng.
- Mỗi job chấm mang thời điểm nhận ảnh và cửa sổ bia; kết quả phải qua kiểm tra trước khi cập nhật điểm, review hoặc gửi gập. Job nhận trước khi dừng được cập nhật vào phiên vừa kết thúc; bắt đầu phiên mới loại job cũ.
- `gui/shot_sound.py` dùng Qt Multimedia phát `assets/sounds/TN.mp3`, không thêm dependency. Khóa cài đặt trong bài, bỏ phím `D` ghi điểm ngẫu nhiên.
- Kiểm chứng: `test.bat` đạt 155 test; Qt Multimedia giải mã/phát thử 3 tiếng nổ liên tiếp ở âm lượng 0, không lỗi. Chưa kiểm tra cơ cấu bia thật hoặc nghe qua loa.

## Kiến trúc hiện tại

- Ứng dụng PC khởi động từ `main.py`.
- Giao diện và xử lý kết quả bài bắn nằm trong `gui/`.
- Lõi kết nối không dây phía PC và giao thức dùng chung nằm trong `assets/server_client/`.
- Mã triển khai phía Orange Pi Zero 2W nằm trong `assets/OrangePiZero2W/`.
- Cấu hình `assets/server_client/client_port_config.json` là dữ liệu riêng của thiết bị, không đồng bộ máy móc từ dự án khác.

## Đồng bộ từ MBT03-wireless

Ngày 2026-09-13 đã đồng bộ cơ chế kết nối theo commit nguồn `424def1`:

- Client dùng `device_id` và `instance_id` để server phân biệt đúng board và đúng tiến trình, tránh hai thiết bị trùng tên thay phiên của nhau.
- Discovery có thể hủy ngay, không để mDNS cũ chặn subnet fallback; hỗ trợ `MBT03_BIND_IP` khi PC có nhiều card mạng hoặc VPN.
- Ghi cấu hình client theo cơ chế file tạm, `fsync` và replace nguyên tử; các khoảng chờ reconnect có thể ngắt khi dừng.
- Board có LED trạng thái riêng cho mất Wi-Fi/chờ server/đã nối server, khóa ghi UART và Wi-Fi dự phòng từ file riêng `wifi_defaults.json` nằm ngoài Git.
- Deploy kiểm tra dependency, file rỗng, checksum tại runtime, cài file nguyên tử và theo dõi PID/restart của service trong 24 giây.
- Server lưu chẩn đoán transport vào `server.log` xoay vòng; log ảnh bắn hỏng hoặc bị loại có lý do rõ ràng.

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

- Kiểm tra riêng PC ngày 2026-10-10: bộ đếm chỉ tăng khi chấm xong; nhánh lỗi inference trước đây bỏ qua đạn, còn server bỏ ảnh khi đủ 8 tác vụ decode. Đã sửa đợi chỗ trống trên luồng data trước khi nhận ảnh và cộng đạn không có điểm chạm khi chấm lỗi trong phiên đang chạy. `test.bat` đạt 139/139; test ép quá tải/ép lỗi tái hiện được, nhưng `server.log` hiện tại không có bằng chứng xác nhận hai tình huống này trong phiên thực tế. Không sửa hoặc deploy thêm phía board trong lần kiểm tra này.

- Ngày 2026-10-10: tái hiện 3 tín hiệu UART trong một lần đọc chỉ tạo 1 lượt gửi ảnh. Đã sửa parser xử lý mọi tín hiệu, giữ đuôi chưa đủ và bỏ debounce 15 ms cho tín hiệu phần cứng; giữ debounce thao tác demo. Server bỏ loại thông báo theo thời điểm nhận vì mạng có thể dồn nhiều thông báo. `test.bat` đạt 134/134, bao phủ burst, tín hiệu bị chia đoạn, pin/lỗi xen kẽ và hai client ZeroMQ gửi burst riêng. Chưa deploy/kiểm chứng trên board thật; phải cập nhật runtime Orange Pi cùng phần mềm PC.

- Ngày 2026-10-10: chỉ cửa sổ xem lại vẽ cả hai điểm offset, thêm đường thẳng vàng nối hai điểm bên dưới marker. Bia mô phỏng màn hình chính tiếp tục chỉ nhận `transformed_point` (sau offset) cho mỗi phát.

- Kiểm tra hai bệ ngày 2026-10-10: chưa tái hiện lẫn dữ liệu giữa hai bệ. Test `test_pedestal_isolation.py` bao phủ tín hiệu gắn đúng `port_id`, kết quả chấm trả về khác thứ tự, bộ đếm/marker/review riêng và ảnh/Q0 qua hai client ZeroMQ thực trên cổng localhost tạm. Màn hình chính dùng xanh=trúng, đỏ=trượt; màn hình xem lại dùng xanh=trước offset, đỏ=sau offset. Log phiên 10:21–10:23 và ảnh lưu của từng bệ phù hợp với sự phân tách này; phép chấm lại dùng Q0 làm tròn từ log, không thay thế kiểm chứng thiết bị thật.

- Ngày 2026-10-10: bắt đầu bài bắn dùng `0F016\n` thay cho lệnh Q0 tạm thời. Mở setting gửi `calibration.target_raise_command` (`@114#`), thoát vòng lặp dialog luôn gửi `calibration.target_lower_command` (`@112#`) và xóa `_setting_window` trong `finally`. Nút Q0 vẫn gửi `0Q000\n`; dựng/gập trong setting không phụ thuộc tùy chọn gập bia tự động. Lịch bài bắn vẫn dựng bia 6 bằng `@111#`.
- `test.bat` ngày 2026-10-10 đạt 125/125; kiểm tra vòng lặp dialog Qt và bốn đường đóng với LoRa giả lập. Chưa kiểm tra chuyển động bia hoặc lệnh UART trên thiết bị thật.

- Ngày 2026-10-09: offset vận hành và mặc định đã khớp `LAB/scoring.py`: class 0 `[0, -0.15]`, class 1 `[0, 0]`, class 2 `[0, -0.30]`, class 3 `[-0.60, 0]`; thay thế bộ giá trị ngày 2026-09-13. Vẫn tắt xoay offset. `scoring()` xét vùng trúng bằng điểm sau offset, GUI ghi nhận trực tiếp kết quả đó.
- Review lưu `target_point_before_offset` và `target_point` chuẩn hóa theo ảnh bia, không clamp vào `[0, 1]` và không tính lại từ cấu hình. Màn hình có bộ chọn phát, dấu thập xanh dương trước offset, dấu thập đỏ sau offset và vùng nền mở rộng cho điểm ngoài bia. Marker đơn giản, không viền hay mũi tên; nếu hai điểm trùng tâm, dấu xanh dài hơn một chút.
- Kiểm chứng ngày 2026-10-09: `test.bat` đạt 122/122; đã render cửa sổ Qt trên Windows, kiểm tra bố cục tối thiểu 920×600 và scaling 150%, chọn phát bằng chuột/phím, điểm trùng nhau/ngoài bia và trạng thái rỗng. Dữ liệu UI là fixture; chưa thử phiên bắn mới trên thiết bị thật.

- `client_demo.py` là entry point chạy demo client từ thư mục gốc; phần GUI vẫn nằm ở `assets/server_client/demo_client.py` và dùng trực tiếp lõi server/client chung để không lệch giao thức.

- Ngày 2026-09-13, cơ chế offset của project chính đã được đối chiếu với `LAB/scoring.py`: cùng áp dụng trong hệ tọa độ ảnh bia sau affine và trước kiểm tra vùng trúng. Bộ giá trị chạy thật đã đồng bộ thành bia 10 `[0, -0.06]`, bia 6 `[0, 0]`, bia 7B `[0, -0.10]`, bia 8 `[-0.40, 0]`.

- Ngày 2026-09-13, `test.bat` đạt 116/116. Kiểm tra tích hợp localhost xác nhận ba kênh control/stream/shoot-data, handshake và dữ liệu hai chiều đều thành công; entry point demo có smoke test riêng.

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
- Luồng bắt đầu bài bắn gửi `0F016\n` qua từng `MBT03ServerCore`; Orange Pi nhận gói `UART_CMD` và ghi lệnh xuống UART của súng.
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
