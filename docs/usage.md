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

Xếp loại cập nhật theo số mục tiêu khác nhau đã bắn trúng: **Giỏi: 4**,
**Khá: 3 và phải có bia số 8**, **Đạt: 2 hoặc 3 nhưng thiếu bia số 8**,
**Không đạt: 0–1**. Trúng nhiều viên vào cùng một bia vẫn chỉ tính một
mục tiêu; không cần bắn hết 16 viên mới hiển thị xếp loại.

Sau khi kết thúc bài, bấm nút loa của bệ để đọc kết quả đang hiển thị, ví dụ
**“Bệ số 1, Khá”**. Bấm lại nút đang đọc để dừng; trong lúc đó nút loa của các
bệ khác bị khóa. Bắt đầu bài mới hoặc đóng ứng dụng sẽ dừng đọc. Nút loa bị khóa
trong khi bắn. Ứng dụng gửi `0P000\n` đến súng của bệ được chọn như dự án wireless,
rồi phát `assets/sounds/Beso1.mp3`–`Beso4.mp3` và `GIOI.mp3`/`KHA.mp3`/`DAT.mp3`/
`KDAT.mp3` ở tốc độ gốc. Hai cụm được giải mã về cùng PCM 44.1 kHz stereo,
ghép thành một file WAV tạm và phát một lần để không đổi nguồn âm thanh giữa câu.
Giữa hai cụm có khoảng nghỉ thêm 120 ms; đầu/cuối mỗi cụm được làm mềm trong 5 ms.
File tạm được dọn khi đọc xong hoặc dừng; không sửa các MP3 gốc.
Thiếu hoặc lỗi một trong hai file sẽ báo lỗi và mở lại nút loa, không đọc câu thiếu cụm.
Khi bắt đầu đọc kết quả, các thông báo trúng bia còn chờ được dừng đến bài mới
để tránh chồng giọng. Có thể bấm đọc lại để lấy xếp loại mới nếu còn ảnh đang chấm.

Bố cục thường: bia 6 trên trái, bia 10 dưới trái, bia 7B ở cột giữa và bia 8 bên phải.
Khi chọn 2 bệ, bố cục dọc lần lượt là bia 6, bia 10, rồi hàng cuối gồm bia 7B bên trái
và bia 8 bên phải. Bia 7B được phóng vừa ô đứng; mọi ảnh giữ đúng tỉ lệ, không kéo méo
hoặc cắt bia.

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

Bấm chuột trái vào nhãn **BỆ SỐ …** để súng của bệ đó nhấp nháy đèn đỏ tìm súng
(`0LR01\n`); bấm lại để trở về đèn xanh (`0LG00\n`). Có thể dùng Tab chọn nhãn rồi
nhấn Enter hoặc Space. Nhãn nhấp nháy đỏ/xanh khi đang tìm súng; màu cảnh báo kết
nối vẫn được ưu tiên. Chỉ gửi đến súng đang kết nối, không đổi trạng thái nếu gửi
thất bại. Mất kết nối sẽ xóa trạng thái tìm súng trên giao diện; đóng ứng dụng gửi
lệnh trở về đèn xanh tới các súng đang tìm và còn kết nối.

Khi nhấn `BẮT ĐẦU`, ứng dụng gửi **`@661#` qua LoRa để gập tất cả bia**, một lần mỗi
lượt bắt đầu, trước lịch dựng bia. Đồng thời ứng dụng gửi lệnh UART `0F016` đến súng
ở mỗi bệ, sau khoảng **300 ms** gửi tiếp `0A000` (cả hai kèm ký tự xuống dòng).
Lệnh thứ hai được hủy nếu kết thúc bài hoặc đóng ứng dụng trước khi hết thời gian chờ.

Khi bật **Q0**, phần mềm gửi `0F003` đến súng của bệ đang chọn, chờ **300 ms** rồi
gửi `0Q000` (cả hai kèm xuống dòng). Trong thời gian chờ chưa thu mẫu quy không.
Tắt Q0, đổi bệ hoặc đóng cửa sổ sẽ hủy lệnh còn chờ; đổi bệ cũng xóa mẫu Q0 của
bệ trước. Nếu gửi `0F003` thất bại hoặc bệ mất kết nối trước khi hết thời gian chờ,
phần mềm không gửi tiếp `0Q000`.

Bài bắn tự kết thúc sau **85 giây**; vẫn có thể kết thúc sớm bằng nút trên màn hình.
Khi kết thúc bài (thủ công, hết giờ hoặc thoát ứng dụng trong bài), phần mềm gửi
`0S000` kèm xuống dòng đến tất cả súng. Đóng cửa sổ cài đặt bằng Chấp nhận, Hủy,
Esc hoặc nút X cũng gửi lệnh này đến tất cả súng.
Bia hiện theo thứ tự **6 → 10 → 7B → 8**, mặc định tại giây **15 / 32 / 42 / 64**.
Bia 6, 10 và 7B có thời lượng cơ sở **7 giây**; riêng bia 8 là **18 giây**.
Cửa sổ nhận trúng mở **sớm 2 giây** so với lúc gửi lệnh dựng và đóng **muộn 4 giây** so
với thời điểm kết thúc cơ sở. Mốc được cập nhật khi lệnh thực sự gửi ra cổng LoRa,
không tính thời gian chờ trong hàng đợi gửi. Theo lịch mặc định, khi không gập sớm
và lệnh được gửi đúng lịch:

| Bia | Khoảng nhận trúng từ lúc bắt đầu bài |
| --- | --- |
| 6 | Từ giây 13 đến trước giây 26 |
| 10 | Từ giây 30 đến trước giây 43 |
| 7B | Từ giây 40 đến trước giây 53 |
| 8 | Từ giây 62 đến trước giây 85 (giới hạn toàn bài) |

Nếu bật `Gập bia` và có lệnh gập sớm do trúng, vẫn nhận thêm **4 giây sau lệnh gập**.
Trong khoảng chồng nhau (ví dụ giây 40 đến trước 43 của bia 10 và 7B), phần mềm
xét thời gian riêng của bia được nhận diện; dựng bia tiếp theo không cắt mất phần
nhận thêm của bia trước. Mọi khoảng nhận đều kết thúc chậm nhất tại giây 85.
Phát nhận sớm không gửi lệnh gập trước khi bia được dựng. Chỉ tính trúng khi nhận
diện đúng bia trong cửa sổ nhận tại thời điểm PC nhận ảnh; ngoài cửa sổ hoặc nhận
nhầm bia vẫn tính đạn nhưng không tính trúng. Thời điểm nhận ảnh được ghi ngay
tại luồng nhận mạng trên PC, trước hàng đợi giải mã và giao diện; không dùng đồng
hồ của Orange Pi để so mốc. `Xem lại` ghi lý do loại, giây nhận ảnh và khoảng nhận
của bia để đối chiếu nếu lịch phần mềm khác thời lượng cài trên bộ điều khiển bia.
Thông báo “ảnh nhận ngoài thời gian cho phép tính điểm của bia” là lỗi thời gian,
không phải điểm chạm ngoài vùng hình ảnh bia. Chi tiết ghi mốc PC nhận ảnh tính từ
đầu bài, khoảng cho phép (từ mốc mở đến **trước** mốc đóng), và số giây sớm/muộn.
Nếu nhận diện khác bia được phép tính điểm, thông báo ghi tên cả hai bia.
`server.log` lưu số phiên, bệ, phát, kết quả trúng trên ảnh trước kiểm tra thời gian,
kết quả tính trúng sau kiểm tra và lý do để đối chiếu.
Các ảnh đã nhận trước khi kết thúc vẫn được chấm tiếp; kết quả đến muộn không làm
gập bia của lượt sau. Ảnh nhận từ mốc 85 giây trở đi không được nhận vào bài.

Mỗi phát nhận trong bài hoặc khi bắn Q0 phát tiếng nổ `assets/sounds/TN.mp3`, giống
`MBT03-wireless`, kể cả phát trượt hoặc nhận diện lỗi. Âm thanh chạy qua Qt và hỗ trợ
các phát liên tiếp. Trong bài, nút cài đặt thiết bị bị khóa để không dựng bia Q0 xen
vào lịch. Phím thử `D` ghi điểm ngẫu nhiên đã được bỏ.

Khi chọn từ **2 bệ trở lên**, hoặc **1 bệ và Gập bia: TẮT**, mỗi lần một bệ trúng một bia lần đầu trong bài,
ứng dụng đọc số bệ bằng `assets/sounds/noti/1.mp3` đến `4.mp3`, mặc định **1.75×**.
Chỉnh `shooting.hit_announcement_playback_rate` trong `assets/configurations/config.json`
(ví dụ `1.5` hoặc `2.0`), rồi mở lại ứng dụng để áp dụng.
Mỗi cặp bia–bệ chỉ đọc một lần dù trúng nhiều viên; sang bia khác hoặc bắt đầu
bài mới sẽ được đọc tiếp. Các số được phát lần lượt để không chồng giọng khi
nhiều bệ trúng gần nhau. Phát trượt, nhận diện lỗi hoặc trúng ngoài cửa sổ hợp lệ
không đọc số. Kết quả hợp lệ đang chấm dở khi kết thúc bài vẫn được thông báo;
bắt đầu bài mới hủy thông báo còn chờ của bài cũ.

Ở màn hình lựa chọn ban đầu, nút hiển thị ngắn gọn `Gập bia: BẬT` với màu xanh khi chức năng đang được chọn; trạng thái tắt hiển thị `Gập bia: TẮT` với màu xám. Khi chỉ chọn 1 bệ, chức năng mặc định bật nhưng vẫn có thể bấm nút để tắt. Khi chọn từ 2 bệ trở lên, chức năng mặc định tắt. Nếu đang bật và phát bắn được xác định là trúng, hệ thống gửi lệnh gập/ẩn bia qua LoRa: bia số 6 dùng `@112#`, bia số 10 dùng `@222#`, bia số 7B dùng `@332#`, bia số 8 dùng `@442#`. Mỗi loại bia chỉ gửi lệnh một lần trong một bài bắn.

Sau khi kết thúc bài bắn, nhấn `Xem lại` tại từng bệ để duyệt các phát bắn của phiên vừa kết thúc. Cửa sổ hiển thị ảnh camera được zoom mặc định 1.5x quanh điểm chạm bên trái, ảnh bia mô phỏng bên phải. Chọn trực tiếp một phát trong danh sách bên dưới hoặc dùng `Phát trước`, `Phát sau` và phím mũi tên. Home/End chuyển đến phát đầu/cuối, Esc đóng cửa sổ.

Dòng **File ảnh gốc** hiển thị đúng tên PNG đã lưu cho phát đang xem, ví dụ
`20261011_201504_645194_be_01.png`. Có thể bôi đen để sao chép tên, rê chuột để xem
đường dẫn đầy đủ. Nếu ảnh đang chờ ghi, dòng này báo **Đang lưu…** và tự cập nhật
khi xong; khi không lưu hoặc lưu thất bại sẽ ghi rõ trạng thái thay vì hiện tên file.

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
