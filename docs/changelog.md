# Lịch sử thay đổi

## 2026-09-13

- Thêm `client_demo.bat` để chạy demo từ mọi thư mục, tự ưu tiên Python trong `.venv` và chuyển tiếp đầy đủ tham số dòng lệnh.
- Thêm entry point `client_demo.py` tại thư mục gốc, sử dụng trực tiếp GUI demo và `MBT03ClientCore` hiện hành trong `assets/server_client`; cập nhật hướng dẫn dòng lệnh và test smoke cho chế độ trợ giúp.
- Xác nhận project chính đã áp dụng offset sau phép chiếu affine và trước khi kiểm tra vùng trúng, giống cơ chế trong `LAB/scoring.py`.
- Đồng bộ bộ offset vận hành từ LAB: bia 10 `[0, -0.06]`, bia 6 `[0, 0]`, bia 7B `[0, -0.10]`, bia 8 `[-0.40, 0]`.
- Đồng bộ server/client và runtime Orange Pi từ `MBT03-wireless` commit `424def1`: định danh thiết bị/tiến trình chắc chắn hơn, hủy discovery và reconnect sạch, không để quảng bá mDNS cũ chặn subnet fallback.
- Bổ sung LED trạng thái kết nối trên board, khóa ghi UART và cơ chế Wi-Fi dự phòng bằng `wifi_defaults.json` riêng ngoài Git.
- Tăng an toàn deploy: từ chối file runtime rỗng, kiểm tra đủ dependency/checksum, cài nguyên tử, lưu rollback và theo dõi service ổn định 24 giây.
- Lưu log transport server vào `server.log` xoay vòng và bổ sung test hồi quy cho định danh, discovery, cấu hình nguyên tử, Wi-Fi khởi động, LED và deploy.

## 2026-09-12

- Đồng bộ server/client từ `MBT03-wireless` commit `0bbf79c`: tách video live sang kênh ZeroMQ latest-only riêng, không dùng chung hàng đợi control/heartbeat; bổ sung kiểm tra tích hợp ba kênh chạy trực tiếp trên localhost.
- Thêm fallback quét các cổng MBT03 ổn định trong subnet khi IP server đã lưu bị cũ hoặc mạng không chuyển tiếp mDNS; chỉ lưu lại server sau khi bắt tay MBT03 thành công.
- Đồng bộ xử lý Wi-Fi transaction: bỏ qua file snapshot khi recovery, xác thực tên file trạng thái, phối hợp marker với `wifi-watchdog` và bật UART Wi-Fi sync mặc định trên board.
- Gỡ lớp CURVE/HMAC cũ khỏi runtime/deploy; ba kênh dùng plain ZeroMQ giống project nguồn. Script deploy vẫn tạo backup bền vững và có rollback nếu cập nhật thất bại.
- Nhãn Ping dùng RTT trung bình trượt thay vì mẫu tức thời để tránh nhảy số do một spike Wi-Fi ngắn.

## 2026-08-29

- Tạm tắt ảnh hưởng của góc xoay affine lên offset điểm chạm; offset ngang/dọc hiện bám theo trục
  ảnh bia chuẩn. Logic xoay vẫn được giữ lại sau công tắc `TARGET_OFFSET_ROTATION_ENABLED` để bật
  lại khi cần thử nghiệm thực địa.
- Khi bật lại, riêng thành phần offset ngang của bia số 8 dùng góc đối xứng qua phương ngang
  (`θ → -θ`); thành phần dọc của bia số 8 và offset của các bia khác dùng góc bình thường.

## 2026-08-15

- Thêm offset điểm chạm theo từng class bia, chuẩn hóa theo kích thước ảnh bia tham chiếu: bia 6
  làm chuẩn `(0, 0)`, bia 10 cao hơn 2%, bia 7B cao hơn 4% và bia 8 lệch phải 2,5%.
- `LAB/score_test.py` chỉ vẽ điểm click trên ảnh camera; điểm click và điểm chạm sau offset cùng
  mũi tên chỉ hướng dịch được vẽ trên ảnh bia chuẩn, không chiếu ngược về camera.
- Hiệu chỉnh hướng vector offset theo góc xoay thực tế của bia. Chỉ thành phần quay của affine
  được sử dụng nên khoảng cách offset trên bia mô phỏng vẫn giữ nguyên khi ảnh có scale/shear.

## 2026-08-08

- Sửa trạng thái đã phục hồi từ kết nối chập chờn vẫn giữ nền nâu: mỗi heartbeat `healthy` giờ luôn khôi phục đầy đủ nhãn và nền xanh lá trước khi cập nhật Ping/Pin.
- Thêm cấu hình ẩn `save_raw_data`; khi bật, lưu bất đồng bộ mọi frame chụp gốc từ súng vào `raw_camera_images` dưới dạng PNG không mất dữ liệu, với thời gian và số bệ trong tên tệp.
- Đồng bộ trải nghiệm Quy không với `MBT03-wireless`: giữ camera trực tiếp, hiển thị chấm xanh cho số phát còn thiếu, dấu chữ thập vàng cho các phát hợp lệ và dấu xanh cho Q0 đã lưu.
- Chỉ lưu Quy không sau khi đủ số phát cấu hình; các phát nhận diện lỗi hoặc có tâm nằm ngoài ảnh được bỏ qua để người dùng bắn lại.
- Chuẩn hóa trạng thái mờ/kích hoạt của hai nút hiệu chỉnh camera và Quy không khi chọn bệ chưa kết nối hoặc bệ đang hoạt động.

## 2026-08-06

- Tạm thời đổi lệnh UART khi bắt đầu bài bắn từ `0F016\n` sang lệnh Q0 `0Q000\n` để phục vụ kiểm tra.
- Giữ stream camera liên tục sau mỗi phát Q0 và vẽ các dấu của phát trước lên hình ảnh trực tiếp thay vì đóng băng tại ảnh chụp.
- Đồng bộ `protocol.py`, `server_core.py`, `client_core.py`, `security.py` và backend Orange Pi mới từ `MBT03-wireless`.
- Thêm state machine kết nối healthy/degraded/offline/session-expired, heartbeat thích nghi, phục hồi theo chuỗi ACK và chống race bằng session generation.
- Sửa đường reconnect có thể treo sau bắt tay lỗi; socket thất bại được đóng `LINGER=0`, hàng đợi giữ lại gói khi ZeroMQ tạm bận và không đẩy bỏ lệnh đã nhận.
- Đồng bộ policy heartbeat/RTT và media từ PC xuống Orange Pi trong gói bắt tay.
- Thêm CURVE/HMAC, nonce chống phát lại và token phiên. Chế độ này mặc định tắt để tương thích súng cũ, có thể bật sau khi triển khai đồng loạt.
- Thêm giao dịch đổi Wi-Fi có stage/commit/rollback và chặn lệnh `Wifi#...` chứa mật khẩu trên kênh UART cũ.
- Thêm script `deploy-board.bat` và quy trình deploy có kiểm tra host key, checksum, dependency, cú pháp và rollback.
- Mở rộng bộ kiểm thử từ 22 lên 82 ca và xác nhận kết nối ZMQ thực, heartbeat, dữ liệu hai chiều, reconnect thành công.
- Hoàn tất giai đoạn triển khai bảo mật sau khi Orange Pi được cập nhật: PC và client bật CURVE/HMAC mặc định, đồng bộ cơ sở ghép cặp hiện hành, và giữ `--disable-security` làm đường rollback khẩn cấp.
- Thêm kiểm thử hồi quy bảo đảm cấu hình mặc định và cấu hình vận hành không vô tình tắt kết nối mã hóa.
- Theo yêu cầu vận hành nhiều dự án dùng chung Orange Pi, gỡ CURVE/HMAC khỏi luồng chạy: bỏ cấu hình/allow-list phía PC, client board luôn dùng transport tương thích chung, deploy không còn cấp credential và dọn credential cũ trên board.

## 2026-07-29

- Đồng bộ lõi server/client mới từ dự án `MBT03-wireless`.
- Ưu tiên cổng TCP ổn định để client có thể kết nối lại trực tiếp sau khi ứng dụng PC khởi động lại; vẫn dùng cổng động khi cổng cố định đang bận.
- Chuyển việc gửi trên socket điều khiển ZMQ về thread sở hữu socket để tránh tranh chấp giữa các thread.
- Cải thiện quá trình bắt tay, heartbeat, phát hiện mất kết nối và phục hồi khi Wi-Fi yếu.
- Cải thiện quá trình dừng server/client để thread và socket được đóng an toàn hơn.
- Đồng bộ tối ưu heartbeat, gửi ảnh bắn và camera cho Orange Pi Zero 2W.
- Giữ nguyên `assets/server_client/client_port_config.json` vì đây là cấu hình riêng của thiết bị trong dự án này.
- Khi bắt đầu bài bắn, gửi lệnh UART `0A000\n` đến client của từng bệ để chuyển súng sang chế độ bắt đầu bài.
- Thêm cửa sổ `Xem lại` theo từng bệ với ảnh camera, điểm chạm, ảnh mô phỏng và điều hướng từng phát; dữ liệu phiên cũ được xóa khi bắt đầu bài bắn mới.

## 2026-07-30

- Sửa cơ chế chọn bia khi nhiều khung nhận diện chồng nhau: chuẩn hóa khoảng cách theo kích thước khung, kiểm tra phép chiếu điểm chạm sang ảnh bia tham chiếu, rồi mới xét diện tích khung và độ tin cậy.
- Cửa sổ `Xem lại` vẽ toàn bộ khung bia đã nhận diện; khung vàng là bia được chọn để tính điểm, khung xanh là các detection còn lại.
- Bổ sung kiểm thử hồi quy cho tình huống khung bia lớn chồng lên bia đúng và kiểm tra thứ tự lớp bia với ảnh tham chiếu.
- Ảnh camera trong cửa sổ `Xem lại` mặc định zoom 1.5x quanh điểm chạm và dùng nét bounding box mảnh hơn.
- Đổi lệnh UART bắt đầu bài bắn từ `0A000\n` thành `0F016\n`.
- Thêm lựa chọn gập bia tự động. Một bệ mặc định bật, nhiều bệ mặc định tắt; người dùng vẫn có thể đổi trạng thái. Khi bắn trúng, bia 6/10/7B/8 lần lượt nhận `@112#`/`@222#`/`@332#`/`@442#`.
- Rút gọn nhãn tùy chọn ban đầu thành `Gập bia: BẬT` hoặc `Gập bia: TẮT`.
- Tăng kích thước điểm chạm trên ảnh bia mô phỏng và dùng màu đỏ với viền tương phản, không dùng màu xanh theo trạng thái trúng nữa.
- Bỏ hai nút `Đầu` và `Cuối` khỏi cửa sổ xem lại; giữ điều hướng `Phát trước`, `Phát sau` và phím Home/End.
- Dọn toàn bộ khóa cấu hình cũ không còn được sử dụng trong `assets/configurations/config.json`.
- Gom lệnh bài bắn, ánh xạ gập bia, lịch LoRa, ngưỡng scoring, thông số review/quy không/LoRa và giới hạn runtime vào cấu hình tập trung; có schema mặc định và bỏ qua khóa lạ.
