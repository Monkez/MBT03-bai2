# Sử dụng

Khi mở ứng dụng, chọn số bệ bắn rồi bấm `CHẤP NHẬN`.

Màn hình chính hiện các bệ đã chọn. Mỗi bệ có 4 bia được ghép bằng OpenCV. Khi chọn 2 bệ, bố cục bia chuyển sang dạng dọc để mỗi bệ dễ quan sát hơn. Viền đỏ là mục tiêu chưa trúng, viền xanh lá là mục tiêu đã trúng. Nhãn kết quả hiển thị số đạn đã bắn trên 16 viên, số mục tiêu đã trúng trên 4 mục tiêu và xếp loại.

Ứng dụng hiện đã khởi động server cho từng bệ được chọn, tự công bố các bệ trong mạng nội bộ và nhận kết nối từ client Orange Pi. Trạng thái bệ phân biệt rõ đang xác nhận, đã kết nối và chưa kết nối; khi client gửi đủ dữ liệu heartbeat, giao diện hiển thị thêm ping và phần trăm pin.

Kết nối mới có thêm trạng thái `KẾT NỐI CHẬP CHỜN` và `MẤT TÍN HIỆU`. Khi mạng
xấu, hệ thống tạm giảm tải luồng camera, giữ chỗ bệ và chỉ tạo phiên mới sau các
mốc timeout cấu hình; khi phục hồi cần nhiều heartbeat hợp lệ liên tiếp.

Video trực tiếp, heartbeat/lệnh và ảnh bắn đi trên ba kênh riêng để camera không
làm nghẽn tín hiệu kết nối. Nếu Orange Pi đang lưu IP server cũ và mạng chặn mDNS,
client tự dò các cổng MBT03 ổn định trong subnet hiện tại rồi cập nhật lại server
sau khi bắt tay hợp lệ.

Nút `Cài đặt thiết bị` mở cửa sổ cài đặt từ `assets/qt/setting.ui`, cho phép chọn bệ đang kết nối, xem luồng camera, hiệu chỉnh camera và thực hiện quy không.

Trong lúc bắn Q0, camera tiếp tục hiển thị stream trực tiếp sau mỗi phát. Các dấu Q0 của những phát đã xử lý được vẽ chồng lên các frame mới để vừa theo dõi hình ảnh hiện tại vừa đối chiếu các phát trước.

Trải nghiệm Quy không được đồng bộ với `MBT03-wireless`: các chấm xanh ở góc trên ảnh camera biểu thị số phát hợp lệ còn thiếu; mỗi phát hợp lệ được đánh dấu bằng chữ thập vàng. Nút `CHẤP NHẬN` chỉ lưu giá trị trung bình và đóng cửa sổ sau khi đã nhận đủ số phát cấu hình. Khi không bắn Quy không, chữ thập xanh hiển thị vị trí Q0 đã lưu của bệ đang chọn.

Tạm thời, khi nhấn `BẮT ĐẦU`, ứng dụng gửi lệnh UART Q0 `0Q000` (kèm ký tự xuống dòng) đến súng ở mỗi bệ đang kết nối trước khi thực hiện lịch điều khiển bia của bài bắn.

Ở màn hình lựa chọn ban đầu, nút hiển thị ngắn gọn `Gập bia: BẬT` với màu xanh khi chức năng đang được chọn; trạng thái tắt hiển thị `Gập bia: TẮT` với màu xám. Khi chỉ chọn 1 bệ, chức năng mặc định bật nhưng vẫn có thể bấm nút để tắt. Khi chọn từ 2 bệ trở lên, chức năng mặc định tắt. Nếu đang bật và phát bắn được xác định là trúng, hệ thống gửi lệnh gập/ẩn bia qua LoRa: bia số 6 dùng `@112#`, bia số 10 dùng `@222#`, bia số 7B dùng `@332#`, bia số 8 dùng `@442#`. Mỗi loại bia chỉ gửi lệnh một lần trong một bài bắn.

Sau khi kết thúc bài bắn, nhấn `Xem lại` tại từng bệ để duyệt các phát bắn của phiên vừa kết thúc. Cửa sổ hiển thị ảnh camera được zoom mặc định 1.5x quanh điểm chạm bên trái, ảnh bia mô phỏng bên phải; dùng hai nút `Phát trước`, `Phát sau` hoặc phím mũi tên để di chuyển. Có thể dùng phím Home/End để nhảy đến phát đầu/cuối. Điểm chạm trên ảnh mô phỏng dùng marker đỏ kích thước lớn với viền trắng và đen để luôn nổi bật trên nền bia. Trên ảnh camera, khung vàng là bia hệ thống đã chọn để tính điểm, các khung xanh là những bia khác được nhận diện trong cùng ảnh. Nhãn trên khung cho biết mã lớp, tên bia và độ tin cậy để tiện kiểm tra trường hợp nhận nhầm. Khi bắt đầu bài bắn mới, dữ liệu xem lại của phiên cũ được xóa.

Khi `save_raw_data` trong `assets/configurations/config.json` là `true`, mọi ảnh chụp gốc nhận từ súng được lưu tự động vào `raw_camera_images`. Tên ảnh chứa thời gian chụp và số bệ để phục vụ thu thập, phân loại dữ liệu. Đặt khóa này thành `false` và mở lại ứng dụng nếu không muốn lưu ảnh.

Điểm chạm dùng để tính trúng/trượt có offset riêng theo từng loại bia vì cự ly và chuyển động
khác nhau. Bia 6 là mốc không offset; các giá trị tạm của bia 10, 7B và 8 có thể chỉnh trong
`scoring.target_offsets_by_class`. Trên ảnh camera, công cụ `LAB/score_test.py` chỉ đánh dấu
điểm click ban đầu. Ảnh bia chuẩn hiển thị `CLICK` màu xanh lơ, `CHAM` màu đỏ và mũi tên nối
hai điểm để kiểm tra offset trực quan; điểm sau offset không được chiếu ngược về camera.
