# Sử dụng

## Kiểm tra UART và đổi Wi-Fi (Ctrl + S)

Tại màn hình chính, nhấn **Ctrl + S** để mở `UART Debug`, tương tự MBT03-wireless.
Cửa sổ không chặn màn hình chính; nhấn lại phím tắt để mở lại cùng cửa sổ.

- Chọn một bệ hoặc **Tất cả bệ online**, nhập lệnh rồi bấm **Gửi UART** hoặc Enter
  trong ô lệnh. Phần mềm tự thêm ký tự xuống dòng và báo bệ gửi thành công/thất bại.
- Ba nút **Đỏ nhấp nháy / Xanh nhấp nháy / Xanh sáng** điền lần lượt `0LR01`,
  `0LG01`, `0LG00`; bấm Gửi UART để thực hiện.
- Đổi Wi-Fi: chọn **một bệ**, nhập SSID/mật khẩu, bấm **Đổi Wi-Fi an toàn** và xác
  nhận đúng bệ. Ứng dụng dùng giao thức `WIFI_CFG` hiện có, không gửi mật khẩu bằng
  lệnh UART `Wifi#`. Mật khẩu bị xóa khỏi ô sau khi gửi hoặc đóng cửa sổ.
- Board thử mạng mới, ứng dụng xác nhận khi board kết nối khỏe trở lại. Nếu không
  được xác nhận trong thời hạn, board tự khôi phục mạng cũ. Giao diện phân biệt
  đang thử, đã lưu, đang/đã khôi phục và hết thời gian chưa rõ kết quả.
- Đóng cửa sổ vẫn tiếp tục theo dõi yêu cầu đang chạy. Nếu thoát ứng dụng giữa lúc
  đổi mạng, cơ chế khôi phục trên board vẫn áp dụng. Cần client hỗ trợ `WIFI_CFG`.
- Các nút gửi bị khóa trong bài bắn; cần chờ thao tác thiết bị hoàn tất mới bắt đầu
  bài mới. Không thay đổi cấu hình mạng thật trong kiểm thử tự động.

## Bài bắn

Khi súng báo lỗi, cảnh báo màu đỏ xuất hiện ngay trên ô bia của bệ tương ứng:

- `E1`: **Lỗi giữ cò quá lâu** — chờ 7 giây trước khi bắn tiếp.
- `E2`: **Lỗi bắn quá nhanh** — chờ 7 giây trước khi bắn tiếp.

Cảnh báo tự ẩn sau 7 giây; lỗi mới bắt đầu lại thời gian hiển thị. Cảnh báo không
tự cộng đạn hoặc thay đổi điểm. Khi bắt đầu bài mới, cảnh báo cũ được xóa.
Có thể chỉnh thời gian hiển thị bằng `runtime.error_message_duration_ms`
(mặc định `7000`); thời gian này không thay đổi thời gian khóa bắn của phần cứng.

Khi mở ứng dụng, chọn số bệ bắn rồi bấm `CHẤP NHẬN`.

Màn hình chính hiện các bệ đã chọn. Mỗi bệ có 4 bia được ghép bằng OpenCV. Khi chọn 2 bệ, bố cục bia chuyển sang dạng dọc để mỗi bệ dễ quan sát hơn. Viền đỏ là mục tiêu chưa trúng, viền xanh lá là mục tiêu đã trúng. Nhãn kết quả hiển thị số đạn đã bắn trên 16 viên, số mục tiêu đã trúng trên 4 mục tiêu và xếp loại.

Màu vết chạm trên màn hình chính biểu thị kết quả: **xanh dương là trúng, đỏ là trượt**, không phải màu phân biệt bệ. Mỗi vết là điểm sau offset của một phát; nhiều phát trên cùng bia có thể có cả hai màu. Riêng cửa sổ `Xem lại` dùng xanh dương cho điểm trước offset và đỏ cho điểm sau offset của cùng một phát. Để kiểm tra nhầm bệ, bắn riêng từng bệ và theo dõi bộ đếm `Đạn` cùng ảnh camera trong lịch sử của bệ đó.

Ứng dụng hiện đã khởi động server cho từng bệ được chọn, tự công bố các bệ trong mạng nội bộ và nhận kết nối từ client Orange Pi. Trạng thái bệ phân biệt rõ đang xác nhận, đã kết nối và chưa kết nối; khi client gửi đủ dữ liệu heartbeat, giao diện hiển thị thêm ping và phần trăm pin.

Kết nối mới có thêm trạng thái `KẾT NỐI CHẬP CHỜN` và `MẤT TÍN HIỆU`. Khi mạng
xấu, hệ thống tạm giảm tải luồng camera, giữ chỗ bệ và chỉ tạo phiên mới sau các
mốc timeout cấu hình; khi phục hồi cần nhiều heartbeat hợp lệ liên tiếp.

Video trực tiếp, heartbeat/lệnh và ảnh bắn đi trên ba kênh riêng để camera không
làm nghẽn tín hiệu kết nối. Nếu Orange Pi đang lưu IP server cũ và mạng chặn mDNS,
client tự dò các cổng MBT03 ổn định trong subnet hiện tại rồi cập nhật lại server
sau khi bắt tay hợp lệ.

Nút `Cài đặt thiết bị` mở cửa sổ cài đặt từ `assets/qt/setting.ui`, cho phép chọn bệ đang kết nối, xem luồng camera, hiệu chỉnh camera và thực hiện quy không.

Khi mở cửa sổ này, phần mềm gửi LoRa `@114#` để dựng bia số 6 phục vụ bắn Q0. Khi đóng bằng Chấp nhận, Hủy, Esc hoặc nút X, phần mềm gửi `@112#` để gập bia xuống, độc lập với tùy chọn gập bia tự động trong bài bắn. Cần kết nối LoRa để bia nhận được lệnh.

Trong lúc bắn Q0, camera tiếp tục hiển thị stream trực tiếp sau mỗi phát. Các dấu Q0 của những phát đã xử lý được vẽ chồng lên các frame mới để vừa theo dõi hình ảnh hiện tại vừa đối chiếu các phát trước.

Trải nghiệm Quy không được đồng bộ với `MBT03-wireless`: các chấm xanh ở góc trên ảnh camera biểu thị số phát hợp lệ còn thiếu; mỗi phát hợp lệ được đánh dấu bằng chữ thập vàng. Nút `CHẤP NHẬN` chỉ lưu giá trị trung bình và đóng cửa sổ sau khi đã nhận đủ số phát cấu hình. Khi không bắn Quy không, chữ thập xanh hiển thị vị trí Q0 đã lưu của bệ đang chọn.

Khi nhấn `BẮT ĐẦU`, ứng dụng gửi lệnh UART `0F016` đến súng ở mỗi bệ, sau khoảng **100 ms** gửi tiếp `0A000` (cả hai kèm ký tự xuống dòng). Lệnh thứ hai được hủy nếu kết thúc bài hoặc đóng ứng dụng trước khi hết thời gian chờ. Riêng nút bắn Q0 trong cửa sổ cài đặt vẫn gửi `0Q000`.

Bài bắn tự kết thúc sau **75 giây**; vẫn có thể kết thúc sớm bằng nút trên màn hình.
Khi kết thúc bài (thủ công, hết giờ hoặc thoát ứng dụng trong bài), phần mềm gửi
`0S000` kèm xuống dòng đến tất cả súng. Đóng cửa sổ cài đặt bằng Chấp nhận, Hủy,
Esc hoặc nút X cũng gửi lệnh này đến tất cả súng.
Bia hiện theo thứ tự **6 → 10 → 7B → 8**, mặc định tại giây **15 / 32 / 42 / 64**.
Mỗi bia có cửa sổ tính điểm **7 giây**, kết thúc sớm khi có lệnh gập do bắn trúng
và đang bật `Gập bia`. Chỉ tính trúng khi bia nhận diện đúng với bia được phép hiện
tại thời điểm PC nhận ảnh phát bắn. Nhận nhầm bia, bắn trước khi dựng hoặc sau khi
cụp vẫn tính đạn nhưng không tính trúng; `Xem lại` ghi lý do loại kết quả.
Các ảnh đã nhận trước khi kết thúc vẫn được chấm tiếp; kết quả đến muộn không làm
gập bia của lượt sau. Ảnh nhận từ mốc 75 giây trở đi không được nhận vào bài.

Mỗi phát nhận trong bài hoặc khi bắn Q0 phát tiếng nổ `assets/sounds/TN.mp3`, giống
`MBT03-wireless`, kể cả phát trượt hoặc nhận diện lỗi. Âm thanh chạy qua Qt và hỗ trợ
các phát liên tiếp. Trong bài, nút cài đặt thiết bị bị khóa để không dựng bia Q0 xen
vào lịch. Phím thử `D` ghi điểm ngẫu nhiên đã được bỏ.

Ở màn hình lựa chọn ban đầu, nút hiển thị ngắn gọn `Gập bia: BẬT` với màu xanh khi chức năng đang được chọn; trạng thái tắt hiển thị `Gập bia: TẮT` với màu xám. Khi chỉ chọn 1 bệ, chức năng mặc định bật nhưng vẫn có thể bấm nút để tắt. Khi chọn từ 2 bệ trở lên, chức năng mặc định tắt. Nếu đang bật và phát bắn được xác định là trúng, hệ thống gửi lệnh gập/ẩn bia qua LoRa: bia số 6 dùng `@112#`, bia số 10 dùng `@222#`, bia số 7B dùng `@332#`, bia số 8 dùng `@442#`. Mỗi loại bia chỉ gửi lệnh một lần trong một bài bắn.

Sau khi kết thúc bài bắn, nhấn `Xem lại` tại từng bệ để duyệt các phát bắn của phiên vừa kết thúc. Cửa sổ hiển thị ảnh camera được zoom mặc định 1.5x quanh điểm chạm bên trái, ảnh bia mô phỏng bên phải. Chọn trực tiếp một phát trong danh sách bên dưới hoặc dùng `Phát trước`, `Phát sau` và phím mũi tên. Home/End chuyển đến phát đầu/cuối, Esc đóng cửa sổ.

Trong cửa sổ xem lại, trên ảnh bia, dấu thập xanh dương biểu thị điểm trước offset, dấu thập đỏ là điểm sau offset dùng để xét trúng/trượt. Một đường thẳng vàng nối hai điểm; hai dấu thập vẫn đơn giản, không viền hay mũi tên. Khi offset bằng 0, dấu xanh dài hơn một chút để phân biệt hai dấu trùng tâm. Điểm ngoài ảnh bia được giữ đúng tọa độ trên vùng nền mở rộng. Dữ liệu hai điểm được lưu theo từng phát, không tính lại theo cấu hình mới khi xem lại. Với phát không đủ dữ liệu, màn hình thông báo không thể so sánh hai điểm. Bia mô phỏng ở màn hình chính chỉ vẽ điểm sau offset của mỗi phát.

Trên ảnh camera, khung vàng là bia hệ thống đã chọn để tính điểm, các khung xanh là những bia khác được nhận diện trong cùng ảnh. Điểm sau offset chỉ hiển thị trên ảnh bia chuẩn. Nhãn trên khung cho biết mã lớp, tên bia và độ tin cậy để tiện kiểm tra trường hợp nhận nhầm. Khi bắt đầu bài bắn mới, dữ liệu xem lại của phiên cũ được xóa.

Khi `save_raw_data` trong `assets/configurations/config.json` là `true`, mọi ảnh chụp gốc nhận từ súng được lưu tự động vào `raw_camera_images`. Tên ảnh chứa thời gian chụp và số bệ để phục vụ thu thập, phân loại dữ liệu. Đặt khóa này thành `false` và mở lại ứng dụng nếu không muốn lưu ảnh.

Để thử riêng một client có camera trên PC với đúng cơ chế server/client hiện tại,
chạy `client_demo.bat [so_be]` (hoặc `python client_demo.py [so_be]`). Có thể chọn camera bằng đối số thứ hai hoặc
`--camera-index=N`, và chọn backend bằng
`--camera-backend=auto|dshow|msmf|default`. Demo dùng trực tiếp lõi ba kênh trong
`assets/server_client`, không duy trì một bản giao thức riêng.

Điểm chạm dùng để tính trúng/trượt có offset riêng theo từng loại bia vì cự ly và chuyển động
khác nhau. Bia 6 là mốc không offset; các giá trị tạm của bia 10, 7B và 8 có thể chỉnh trong
`scoring.target_offsets_by_class`. Trên ảnh camera, công cụ `LAB/score_test.py` chỉ đánh dấu
điểm click ban đầu. Ảnh bia chuẩn hiển thị `CLICK` màu xanh lơ, `CHAM` màu đỏ và mũi tên nối
hai điểm để kiểm tra offset trực quan; điểm sau offset không được chiếu ngược về camera.
