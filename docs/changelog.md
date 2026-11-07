# V55-071126 — Áp dụng kênh LoRa E32

- Kênh 1/2/3 cấu hình E32 bằng mã 01/03/05 ở 9600 bps. Áp dụng kênh đã lưu khi mở cổng, kể cả lúc tự kết nối lại.
- Xác nhận phản hồi đủ sáu byte và phục hồi RTS trước khi truyền nhận. Cài đặt được lưu trước khi áp dụng, thanh trạng thái báo kết quả của thiết bị.

# V54-071126 — Khôi phục lệnh dựng thủ công 8C

- Nút HIỆN BIA dựng 8C bằng @441#. Lịch bài dùng @444# để chạy xe và @448# để đọc trạng thái.

# V53-071126 — Nhập mốc ẩn tuyệt đối cho 8C

- Ô Ẩn 8C nhập thời điểm từ đầu bài như ba bia còn lại: Hiện 64, Ẩn 80 => thời gian chạy 16, giới hạn chờ 20 giây từ @444#. Lưu/nạp trực tiếp mốc tuyệt đối.
- Giữ cập nhật trạng thái @448 và kết thúc sau gập 2 giây.

# V52-071126 — Điều khiển xe bia 8C bằng trạng thái thực

- Gửi @444# một lần, hỏi @448# mỗi giây; nhận @4480/@4481 kèm xuống dòng để cập nhật gập/hiện. Không gập sớm 8C khi trúng, theo lịch hoặc khi kết thúc bài.
- Ô Ẩn của 8C là thời gian chạy: nhập 16 thì giới hạn chờ 20 giây từ lần ghi lệnh chạy thực tế. Nếu xe đã hiện rồi báo gập, kết thúc sau 2 giây, không vượt giới hạn chờ.
- Giữ cấu hình thời gian cũ; Cài đặt chuyển đổi ô Ẩn 8C thành thời gian chạy và lưu/nạp đúng. Mất phản hồi vẫn kết thúc; phản hồi cũ không ảnh hưởng bài mới.

# V51-071126 — Nâng riêng bia 10

- Nâng riêng ảnh bia số 10 thêm một chút, giới hạn trong vùng ảnh để không đè lên dải đạn; giữ cố định vị trí khi bắn.

# V50-071126 — Nâng nhẹ vị trí bia

- Giảm vùng chừa dải đạn để bia cao lên một chút; vẫn cố định vị trí trước/sau bắn, giữ viên lẻ khung vàng và loạt khung blue.

# V49-071126 — Thử màu khung phân loạt trên bia

- Viên lẻ khung vàng; loạt từ hai viên khung xanh blue. Màu trong ô giữ xanh lá khi trúng, đỏ khi trượt.

# V48-071126 — Cố định bia trước khi bắn

- Chừa sẵn vùng dải đạn theo giới hạn đạn ngay từ đầu; thêm viên hoặc xuống hàng không dịch/thu nhỏ bia.
- Áp dụng cho toàn bộ bia, bia đang gập, bia đang hiện và chồng bia.

# V47-071126 — Dải đạn riêng từng bia

- Hiển thị toàn bộ viên đã nhận theo từng bia, căn trái phía trên ảnh, giữ số phát và xuống hàng khi cần.
- Trúng xanh lá, trượt đỏ, đang chấm xám; viên lẻ cũng là ô vuông và có khung đỏ, các loạt có khung vàng. Thay icon bắn lẻ đơn lẻ.
- Nhóm theo receipt trước inference; giữ đúng loạt khi chấm xong khác thứ tự, không bỏ viên thiếu điểm chạm.

# V46-071126 — Giới hạn đạn xem lại và icon bắn lẻ

- Chỉ nhận chấm và xem lại tối đa max_bullets viên mỗi bệ/phiên (mặc định 16), chặn phát vượt giới hạn trước khi phân loạt.
- Lọc lịch sử cũ và dữ liệu về trễ; dải đạn và điều hướng giữ đúng giới hạn.
- Thay ô vuông vàng bằng icon viên đạn vàng đồng trong vòng đỏ, concept A do người dùng chọn.

# V44-071126 — Chuyển bia ở mốc giữa và ký hiệu bắn lẻ

- Giữ bia gập đến giữa lúc gập thực tế và lịch hiện bia kế tiếp, kể cả gập sớm khi trúng.
- Gắn viên bắn lẻ với bia hiển thị khi nhận phát, kể cả đang gập; cảnh báo bằng ô vuông vàng góc trên phải, giữ viền xanh/đỏ.

# V43-061126 — Bắn loạt và bia xem lại cố định

- Bia xem lại căn giữa, kích thước không đổi theo điểm chạm; ẩn điểm ngoài khung.
- Có loạt một viên: hạ một bậc cả bài (Giỏi → Khá → Đạt, giữ mức Đạt); bia liên quan viền vàng.
- Đồng bộ xếp loại trên màn hình, đọc kết quả và Excel. Nhóm theo thời điểm nhận, không theo thứ tự chấm xong; chờ hết khoảng loạt trước khi kết luận viên cuối.

# Lịch sử thay đổi

## 2026-10-12

- Khi bật Q0, gửi `0F003` rồi `0Q000` sau 300 ms đến bệ đang chọn; hủy lệnh chờ khi tắt Q0, đổi bệ hoặc đóng cửa sổ. Không thu mẫu trong thời gian chuẩn bị.
- Mở cửa sổ nhận trúng sớm 1 giây trước lịch dựng và muộn 2 giây sau thời lượng cơ sở hoặc lệnh gập sớm; giới hạn bài vẫn 85 giây, không đổi lịch lệnh dựng.
- Tăng khoảng chờ giữa lệnh bắt đầu `0F016` và `0A000` từ 100 ms lên 300 ms; vẫn hủy lệnh đang chờ khi dừng bài hoặc đóng ứng dụng.

## 2026-10-10

- Hiển thị lỗi súng E1 (giữ cò quá lâu) và E2 (bắn quá nhanh) trên đúng bệ, tự ẩn sau 7 giây như MBT03-wireless; không ảnh hưởng điểm hoặc số đạn.
- Khi bắt đầu bài, gửi UART `0F016` rồi `0A000` sau khoảng 100 ms bằng timer; hủy lệnh chờ khi dừng bài hoặc đóng ứng dụng.
- Gửi UART `0S000` đến tất cả súng khi kết thúc bài hoặc đóng cửa sổ cài đặt, bao gồm Hủy/Esc/X.
- Thêm `build.bat`, PyInstaller và bộ đóng gói portable tự tăng tên `MBT03-Bai2-V<version>-<ddmmyy>`; hỗ trợ `--dry-run`, kiểm tra output, chỉ ghi phiên bản sau build thành công, không đóng gói dữ liệu ghép nối/Wi-Fi riêng.
- Thêm Ctrl + S mở UART Debug: chọn bệ/all online, ba lệnh đèn, gửi UART nền và đổi Wi-Fi qua giao thức hiện có; theo dõi ACK, tự xác nhận khi board kết nối lại và hiển thị trạng thái khôi phục. Khóa gửi trong bài bắn và chặn bắt đầu khi thao tác thiết bị còn chờ.

- Tự kết thúc bài ở giây 75; kiểm tra bia theo thứ tự 6 → 10 → 7B → 8 và cửa sổ 7 giây, đóng sớm khi gửi lệnh gập vì trúng. Sai bia/ngoài cửa sổ chỉ tính đạn, lưu lý do trong xem lại. Giữ kết quả các phát đã nhận trước khi dừng dù xử lý xong muộn.
- Phát tiếng nổ `TN.mp3` qua Qt cho mỗi ảnh bắn trong bài và Q0; khóa cài đặt khi đang bắn và bỏ phím `D` ghi điểm ngẫu nhiên. Chỉ cần khởi động lại ứng dụng PC.

- Sửa riêng phía PC: khi hàng đợi giải mã đầy, chờ có chỗ thay vì bỏ ảnh bắn; khi chấm ảnh báo lỗi, vẫn cộng đạn của phiên đang chạy và lưu lỗi trong xem lại, không tạo điểm chạm/trúng giả. Kiểm thử mô phỏng tái hiện cả hai đường mất đạn; chưa xác nhận đây là nguyên nhân phiên bắn thực tế. Các thay đổi này chỉ cần khởi động lại phần mềm PC.
- Sửa mất lượt bắn nhanh: client Orange Pi xử lý từng tín hiệu UART trong cùng một lần đọc và giữ phần tín hiệu chưa đủ; mỗi tín hiệu phần cứng tạo một lượt gửi ảnh, không bị bộ lọc 15 ms loại bỏ. Server cũng không loại thông báo theo khoảng cách nhận qua mạng. Cần deploy lại client trên từng board và khởi động lại phần mềm PC để áp dụng đầy đủ.
- Mở cài đặt gửi LoRa `@114#` dựng bia 6, đóng gửi `@112#` gập bia (Chấp nhận, Hủy, Esc, X); dọn trạng thái và gửi gập cả khi vòng lặp dialog báo lỗi. Lịch bài bắn vẫn dùng `@111#`.
- Đổi lệnh bắt đầu bài bắn thành `0F016\n`; chế độ Q0 vẫn dùng `0Q000\n`. Thêm cấu hình lệnh dựng/gập cho cửa sổ cài đặt.

## 2026-10-09

- Đồng bộ offset vận hành và mặc định theo LAB: bia 10 `[0, -0.15]`, bia 6 `[0, 0]`, bia 7B `[0, -0.30]`, bia 8 `[-0.60, 0]`. Kết quả trúng/trượt dùng điểm sau offset.
- Thu gọn màn hình xem lại, thêm danh sách chọn nhanh phát bắn và chú thích tại mỗi ảnh. Hiển thị dấu thập xanh dương trước offset, dấu thập đỏ sau offset; giữ nguyên tọa độ ngoài ảnh bia trên vùng nền mở rộng.
- Bổ sung kiểm thử đồng bộ cấu hình, kết quả chấm qua biên vùng trúng, lưu hai tọa độ và điều hướng xem lại.

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

## 2026-11-06 — Đọc điểm chạm bằng bộ âm thanh mới

- Phát “Bắt đầu tập” khi bắt đầu bài.
- Đọc bệ, số điểm chạm từng bia 6 → 10 → 7b → 8c an pha 45, rồi xếp loại; 0 đọc “Không trúng”, 1–16 dùng bản ghi tương ứng.
- Đếm riêng điểm chạm hợp lệ, không phụ thuộc hiển thị dấu chạm; giữ quy tắc xếp loại.
- Đóng gói đủ bộ WAV mới trong bản V28.

## 2026-11-06 — Hiển thị theo lượt bia

- Trong bài bắn chỉ phóng to bia hiện tại: mờ đen trắng với nhãn ĐANG GẬP, có màu với nhãn ĐANG HIỆN.
- Chuyển theo lịch bia 6 → 10 → 7B → 8C, giữ trạng thái vừa gập khoảng 0,8 giây rồi xem trước bia kế tiếp. Tự động gập khi trúng cũng cập nhật trạng thái chung của các bệ.
- Khi mở app hoặc kết thúc/dừng bài, hiển thị lại bốn bia cùng toàn bộ dấu chạm. Tách trạng thái hiện bia khỏi khoảng cho phép chấm điểm ảnh đến trễ.
- Tên bia và trạng thái cùng một hàng; thống nhất nhãn BIA SỐ 8C không ghi góc alpha. Viền xanh/đỏ bo góc, khử răng cưa, có lớp nền nhạt cùng màu để dễ phân biệt.

## 2026-11-06 — Kết quả và vùng điểm chạm quanh bia

- Kết thúc/dừng bài: bia chưa trúng mờ đen trắng với viền đỏ; bia đã trúng có màu và viền xanh. Mở app/reset kết quả vẫn hiển thị bia có màu.
- Thu nhỏ ảnh bia 10% trong khung, giữ đúng vị trí tương đối của dấu chạm. Cho phép điểm lệch ngoài ảnh hiện trong phần trống của khung bia, ẩn điểm xa và cắt dấu tại vùng bên trong khung.
- Giữ tọa độ ngoài khoảng 0–1; không kéo phát trượt vào mép ảnh. Tọa độ lỗi không làm mất số đạn; tính điểm không thay đổi.
- Nền nhãn CHƯA KẾT NỐI đổi sang rgb(0, 170, 255).

## 2026-11-06 — Cài đặt thời gian và bù trễ phần cứng

- Bia gập mờ hơn; thêm bảng ảnh và mốc Hiện/Ẩn bốn bia trong time_setting_frame, thêm ba mục vào channel_combo có sẵn (chưa điều khiển theo kênh).
- Lưu/nạp các mốc và kênh qua JSON, ghi nguyên tử và báo lỗi tại form; giữ các cấu hình khác. Mốc không hợp lệ không được lưu.
- Dùng lệnh hiện/ẩn thủ công, gửi sớm hardware_delay_time (mặc định 1,5 giây). Nhận điểm từ lúc gửi hiện đến gửi ẩn + 2 lần bù trễ. Dừng bài hủy lịch và gập các bia đã dựng còn lại. Cho phép chồng lịch và cùng hiển thị nhiều bia. Tự kết thúc sau lệnh ẩn cuối thực tế +4 lần bù trễ, thay cho hạn cố định 85 giây.
- Với nhiều bia cùng hiện, đặt “ĐANG HIỆN” cạnh tên từng bia và bỏ nhãn chung để tăng diện tích ảnh bia.

## 2026-11-06 — Giữ stylesheet cửa sổ cài đặt

- Bỏ ghi đè stylesheet hai nút Hiệu chỉnh camera và Bắn quy không khi khởi tạo, kết nối và đặt lại; dùng định dạng trong setting.ui.
- Tiêu đề THỜI GIAN HIỆN / ẨN BIA dùng nền trong suốt; bỏ dòng ghi chú và hàng trống bên dưới.
- Bốn ô ảnh bia trong Cài đặt dùng nền trắng.
- Nền tên bia, nhãn Hiện/Ẩn trong suốt; bo góc hai nút camera/Q0 còn 8 px qua thuộc tính radius trong setting.ui.

## 2026-11-06 — Xem lại theo concept B

- Hai ảnh lớn trên nền tối, dải ô đạn phía trên điều hướng, không còn chú giải và text debug trên giao diện chính. Xem log cạnh Đóng mở riêng thông tin chi tiết.
- Ô đạn theo max_bullets: chưa có kết quả xám, trúng xanh, trượt đỏ; viên đang chọn viền blue. Loạt khung vàng có khoảng cách lớn hơn, ghi nhận theo thời gian PC nhận ảnh trước khi chấm. Ngưỡng burst_gap_seconds mặc định 0,3 giây, so sánh nhỏ hơn.
- Bia mô phỏng thu nhỏ với nền trắng mở rộng, bỏ viền kết quả và giữ đúng phép chiếu điểm. Kết quả đến trễ cập nhật dải đạn mà giữ lựa chọn.

## 2026-11-06 — Sửa mô phỏng khi không sử dụng LoRa

- Không sử dụng LoRa chạy mô phỏng đầy đủ theo lịch thay vì chờ tín hiệu ghi serial không thể xảy ra; chế độ có COM vẫn yêu cầu gửi thực tế.
- Ngắt cổng xóa lựa chọn cũ để không tự mở lại; cổng không còn khả dụng hiển thị đúng trạng thái.
- Ẩn hoàn toàn dòng báo lỗi thời gian khi rỗng; hiện lại khi sai mốc hoặc không lưu được.
