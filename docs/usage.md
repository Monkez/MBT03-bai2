# Sử dụng

## Scale màn hình Windows

Ứng dụng giữ đúng tỷ lệ Scale của Windows, gồm 100%, 125%, 150%, 175% và 200%,
với cấu hình Qt `PassThrough` giống MBT03-wireless. Bản cũ có thể làm tròn 150% hoặc
175% thành 200%, khiến nút, chữ và khoảng cách lớn hơn mong muốn; 125% có thể bị
làm tròn xuống 100% khiến chữ và khung lệch tỷ lệ. Cấu hình mới giữ nguyên kích thước
ở 100% và 200% thực. Khởi động lại ứng dụng sau khi cập nhật mã nguồn.

Không cần tắt High DPI hoặc đổi Scale toàn Windows để áp dụng sửa lỗi này.
Tham khảo [cơ chế DPI của Qt 5.15](https://doc.qt.io/archives/qt-5.15/highdpi.html).

## Nạp danh sách bắn từ Excel

1. Bấm **Chọn danh sách bắn**, chọn file `.xlsx` theo mẫu `c351-d3-HVKTQS.xlsx`.
   Sheet đang được chọn trong Excel có dòng 1 là tiêu đề; năm cột A–E lần lượt
   là **STT, Họ và tên, Đơn vị, Ngày sinh, Cấp bậc**. STT phải là số nguyên dương, không
   trùng; họ tên bắt buộc, đơn vị và ngày sinh có thể để trống. Bỏ qua dòng trống.
   Cột **F–I** là **Bia số 6, Bia số 10, Bia số 7b, Bia số 8c** (1 = trúng,
   0 = không trúng); cột **J** là **Xếp loại**. Để trống cả F–J cho người chưa bắn.
   Kết quả có sẵn được nạp lại lên thẻ; Loạt bắn mới bỏ qua người đã có kết quả.
   Nếu đã có đủ bốn giá trị 0/1 nhưng J trống, ứng dụng tự tính xếp loại. Nếu có
   xếp loại thì phải khớp kết quả bốn bia hoặc thấp hơn đúng một bậc do bắn lẻ (không hạ Đạt); dữ liệu thiếu/sai được báo rõ dòng lỗi.
   Vẫn nhận danh sách A–D chưa có cột kết quả; khi lưu sẽ bổ sung tiêu đề F–J.
2. Mỗi người hiển thị bằng `assets/qt/score_card.ui`, có nút **Vào bắn** riêng.
   Bấm nút này để đưa người vào bệ; nút chuyển xanh như bản wireless.
   Bệ được phân theo `(STT - 1) % số bệ + 1`, giống bản wireless. Nút **x** cạnh
   tên người tại bệ bỏ lựa chọn người đó và trả nút về trắng. Dòng tên trên danh sách
   có họ tên và đơn vị; chế độ một bệ thêm ngày sinh. Rê chuột để đọc tên đầy đủ.
3. Bấm **Loạt bắn mới** để xếp người chưa bắn đầu tiên của từng bệ theo thứ tự
   trong file. Loạt cuối thiếu người sẽ để trống các bệ còn lại.
4. Bấm **BẮT ĐẦU**. Ô `targets_label` cập nhật số mục tiêu trúng dạng **3/4**,
   riêng số **3** màu đỏ. Xếp loại sau khi kết thúc hiển thị `GIOI`, `KHA`, `DAT`,
   `KDAT` như wireless; rê chuột để xem tên đầy đủ. Người được chọn khi bắt đầu bài vẫn được đánh dấu
   đã bắn nếu kết thúc mà chưa có phát nào. Có thể chọn lại người đã bắn để bắn
   lại; kết quả của người đó được thay khi bắt đầu bài mới.

5. Bấm **Lưu kết quả** để tạo file **Kết quả - tên danh sách.xlsx** cùng thư mục.
   Giữ các cột thông tin và định dạng; cột **F–I** ghi 0/1 của từng bia theo đúng
   mẫu, cột **J** ghi xếp loại đầy đủ. Người chưa bắn vẫn để trống F–J;
   người đã bắn nhưng không trúng ghi bốn số 0 và **Không đạt**.
   Ghi theo đúng dòng người bắn, kể cả STT
   không liên tiếp hoặc có dòng trống. File danh sách gốc không bị sửa. Lưu lần
   tiếp theo cập nhật file kết quả; nếu đang mở file đó trong Excel, đóng rồi thử lại.

Nạp và lưu file chạy ở nền; lỗi file/dữ liệu không xóa danh sách đang có. Trong lúc bắn
hoặc còn ảnh chờ chấm, ứng dụng khóa nạp file, đổi người và chuyển loạt. Kết quả
ảnh đến trễ vẫn gắn với người của bài trước, không cộng sang người mới. Danh sách
và kết quả được giữ trong phiên mở ứng dụng; bấm Lưu kết quả trước khi thoát để giữ
kết quả vào Excel. Vẫn có thể bắn theo bệ khi chưa chọn người, như bản wireless.

## Đối chiếu số phát bắn trên PC

`Đạn` tăng sau khi chấm xong từng ảnh, kể cả không nhận diện được bia, trượt,
ngoài thời gian tính điểm của bia hoặc chấm lỗi. Khi còn tác vụ chấm đang chờ,
số này có thể tạm thấp hơn số ảnh đã nhận. Các ảnh nhận trong bài vẫn được xử lý
sau khi dừng. Nút bắt đầu lượt mới tạm khóa đến khi chấm xong mọi ảnh đã nhận,
kể cả khi không tải danh sách bắn, để tránh bỏ kết quả còn chờ của lượt trước.

Mỗi bệ có kênh nhận riêng, hàng đợi tối đa 64 ảnh nén và hai luồng giải mã.
Loạt 16 ảnh mỗi bệ không phải chờ bộ giải mã xử lý xong tám ảnh đầu mới được nhận.
Ảnh đã được tiếp nhận hợp lệ không bị bỏ chỉ vì heartbeat quá hạn trong lúc chờ
giải mã; vẫn loại ảnh nếu kết nối đã bị ngắt hoặc thay bằng phiên khác. Khi đầy
hàng đợi, PC chờ chỗ trống và ghi cảnh báo, không âm thầm xóa ảnh khỏi hàng đợi.

Trong `server.log`, đối chiếu cùng phiên (`session`) và bệ:

- `SHOOT ACCEPTED`: thông báo phát bắn nhận qua kênh điều khiển, chưa đảm bảo có ảnh.
- `[ShotTransport] received_at=…`: ảnh đã được đọc từ socket; ghi dung lượng và số
  ảnh đang chờ giải mã. `decode queue full` báo hàng đợi đã đạt giới hạn.
- `Shoot image`: ảnh đã giải mã, chuẩn bị gửi sang giao diện; `queue_decode_ms`
  là thời gian từ đọc socket đến giải mã xong.
- `[ShotReceipt]`: ảnh được nhận để chấm, hoặc lý do không đếm (chưa có bài,
  nhận ngoài thời gian bài, bệ không hợp lệ).
- `received_at` nối log nhận mạng với log giao diện của cùng bệ; `ui_delay_ms`
  đo tổng thời gian từ đọc socket đến giao diện nhận ảnh để chấm.
- `[Scoring]`: kết quả chấm từng phát, kể cả lỗi.
- `[Exercise] ... dừng bài`: tổng ảnh nhận để chấm, số chấm xong, số đang chờ
  và số đạn đang hiển thị tại thời điểm dừng.

Ví dụ `nhận=16, chấm xong=13, đang chờ=3, đạn hiển thị=13` nghĩa là còn ba ảnh
chờ chấm. Đây là số liệu phía PC, không xác nhận số lần bóp cò trên súng.
Log `invalid Q0 metadata` cho biết PC dùng tọa độ tâm mặc định `(0.5, 0.5)` do
dữ liệu Q0 không hợp lệ; ảnh vẫn được giữ để xử lý. Lỗi giải mã ảnh hoặc loại ảnh
do kết nối hết hạn/thay đổi được ghi riêng bằng `decode failed` / `Drop shoot image`.

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

Mỗi loạt yêu cầu ít nhất **2 viên**. Có ít nhất một loạt chỉ một viên thì
hạ **một bậc cho cả bài**: Giỏi → Khá, Khá → Đạt; Đạt và Không đạt giữ nguyên.
Nhiều viên bắn lẻ không hạ cộng dồn. Mỗi bia có dải các viên đã bắn căn trái, phía trên ảnh bia: trúng màu xanh lá, trượt màu đỏ, đang chờ chấm màu xám. Trên dải đạn từng bia, viên lẻ có khung vàng; loạt từ hai viên có khung xanh blue. Số trên viên là số thứ tự chung của phát bắn để đối chiếu với Xem lại. Dải tự xuống hàng khi cần. Vùng dành cho toàn bộ đạn được chừa sẵn phía trên ngay từ đầu, nên ảnh bia giữ nguyên vị trí và kích thước khi có viên mới hoặc xuống hàng. Viền bia vẫn xanh khi trúng, đỏ khi chưa trúng. Viên lẻ được tính cho bia hiển thị tại thời điểm PC nhận phát bắn, kể cả bia đang gập hoặc đang chờ hiện. Khi nhiều bia cùng mở, dùng bia nhận diện trong ảnh để phân biệt. Mốc phân loạt dùng `shooting.burst_gap_seconds`. Khi đang bắn,
chờ đủ khoảng này trước khi kết luận viên cuối là bắn lẻ; khi dừng bài thì chốt ngay.
Ảnh chấm về chậm không tách một loạt đã nhận thành nhiều viên lẻ. Xếp loại trên
màn hình, đọc kết quả và lưu/nạp Excel dùng chung kết quả sau khi hạ bậc.

Khi nhấn Bắt đầu, ứng dụng phát **“Bắt đầu tập”** bằng giọng mới.
Sau khi kết thúc bài, bấm nút loa của bệ để đọc: **“Bệ số 1, Bia số sáu,
Ba điểm chạm, Bia số mười, Không trúng, Bia số bảy bê, Một điểm chạm,
Bia số tám xê an pha bằng chín mươi, Hai điểm chạm, Khá”**.
Thứ tự bia là 6 → 10 → 7b → 8c an pha 90, sau cùng là xếp loại.
Không trúng đọc “Không trúng”; có trúng đọc số điểm chạm từ 1 đến 16.
Số điểm chạm tính riêng từng viên trúng hợp lệ trên từng bia, độc lập với việc
hiện dấu chạm; xếp loại tính số mục tiêu trúng và quy tắc bắn lẻ nêu trên.


Bấm lại nút loa đang đọc để dừng; các bệ khác bị khóa khi đang đọc.
Bắt đầu bài mới hoặc đóng ứng dụng sẽ dừng đọc. Nút loa bị khóa trong khi bắn.
Ứng dụng gửi `0P000\n` đến súng của bệ được chọn, dừng các thông báo trúng còn chờ,
rồi phát các WAV từ `assets/new_sounds` ở tốc độ gốc. Toàn bộ câu được giải mã
về PCM 44.1 kHz stereo và ghép vào một WAV tạm; nghỉ 120 ms giữa các cụm,
làm mềm đầu/cuối mỗi cụm 5 ms. File tạm được dọn khi đọc xong hoặc dừng.
Thiếu hoặc lỗi bất kỳ cụm nào sẽ báo lỗi và mở lại nút loa, không đọc câu thiếu.
Có thể bấm đọc lại để lấy kết quả mới nếu còn ảnh đang chấm.

Trong bài bắn, mỗi bệ chỉ hiển thị một bia được phóng to theo thứ tự
**6 → 10 → 7B → 8C**. Khi bắt đầu, bia 6 mờ đen trắng và có nhãn **ĐANG GẬP**.
Tên bia và trạng thái nằm trên một hàng, ví dụ **BIA SỐ 8C · ĐANG GẬP** (không ghi góc alpha).
Đến thời điểm hiện bia, ảnh chuyển sang màu rõ và nhãn **ĐANG HIỆN**.
Với ba bia đầu, hết thời gian hoặc có phát trúng hợp lệ khi bật tự động gập bia thì ảnh trở lại mờ. 8C tự chạy, chỉ cập nhật gập theo phản hồi.
Bia vừa gập tiếp tục hiển thị đến mốc giữa thời điểm gập thực tế và thời điểm bia kế tiếp hiện theo lịch, rồi chuyển sang bia kế tiếp ở trạng thái gập. Ví dụ gập lúc 20 giây, bia sau hiện lúc 32 giây thì chuyển lúc 26 giây. Nếu đã có bia khác đang hiện, ưu tiên hiển thị các bia đang hiện.
Khi nhiều bia cùng hiện, màn hình chia khung để hiển thị tất cả các bia đang hiện.
Sau lượt bia cuối, giữ bia cuối ở trạng thái gập đến khi kết thúc bài.
Viền bo góc đỏ biểu thị chưa trúng, xanh biểu thị đã trúng; lớp viền ngoài nhạt cùng màu
giúp dễ phân biệt từng bia. Dải đạn giữ rõ cả khi bia gập; viền giữ xanh/đỏ theo kết quả.
Các bệ cùng theo trạng thái bia chung; trúng ở một bệ có thể gập bia chung khi bật chế độ này.

Hình mô phỏng hiện ngay khi lệnh hiện được gửi và gập sau khi gửi lệnh ẩn **1 giây**. Ví dụ bia 6 đặt Hiện 15, Ẩn 22 thì hình hiện ở giây 15 và gập ở giây 24 nếu gửi đúng lịch. Bia 8C khi dùng LoRa hiển thị theo phản hồi `@448`. Khoảng nhận điểm được tính riêng. Dấu chạm chỉ hiện trên bia đang hiện; toàn bộ
dấu chạm được giữ lại để xem khi kết thúc. Khi mới mở ứng dụng hoặc kết thúc/dừng
bài bắn, màn hình hiển thị lại cả bốn bia như trước.

Ở màn hình kết quả sau khi kết thúc/dừng bài, bia chưa trúng mờ đen trắng
và giữ viền đỏ; bia đã trúng giữ ảnh có màu và viền xanh. Dải đạn riêng của từng bia vẫn hiển thị, gồm cả viên trượt hoặc không có điểm chạm để vẽ. Khi mới mở app hoặc
xóa kết quả để bắt đầu lượt mới, cả bốn bia vẫn hiển thị có màu như ban đầu.

Ảnh bia được thu nhỏ 10% theo cả chiều rộng và chiều cao trong khung, giữ đúng
tỉ lệ và căn giữa; riêng bia số 10 được nâng nhẹ trong vùng ảnh. Điểm chạm có thể nằm trên phần trống quanh ảnh, nhưng chỉ
hiển thị khi tâm điểm còn nằm trong vùng bên trong khung của chính bia đó.
Điểm quá xa bị ẩn; không dồn về mép ảnh, không vẽ chồng viền hoặc sang bia khác.
Số đạn, điểm và lịch sử vẫn giữ nguyên kể cả khi dấu chạm không được vẽ.
Nhãn trạng thái CHƯA KẾT NỐI của bệ có nền xanh dương `rgb(0, 170, 255)`.

Bố cục thường: bia 6 trên trái, bia 10 dưới trái, bia 7B ở cột giữa và bia 8C bên phải.
Khi chọn 2 bệ, bố cục dọc lần lượt là bia 6, bia 10, rồi hàng cuối gồm bia 7B bên trái
và bia 8C bên phải. Bia 7B được phóng vừa ô đứng; mọi ảnh giữ đúng tỉ lệ, không kéo méo
hoặc cắt bia.

Màu vết chạm trên màn hình chính biểu thị kết quả: **xanh dương là trúng, đỏ là trượt**, không phải màu phân biệt bệ. Mỗi vết là điểm sau offset của một phát; nhiều phát trên cùng bia có thể có cả hai màu. Riêng cửa sổ `Xem lại` mặc định chỉ vẽ điểm đỏ sau offset trên bia mô phỏng; có thể bật thêm điểm xanh trước offset bằng `review.show_simulation_aim_point`. Để kiểm tra nhầm bệ, bắn riêng từng bệ và theo dõi bộ đếm `Đạn` cùng ảnh camera trong lịch sử của bệ đó.

Ứng dụng hiện đã khởi động server cho từng bệ được chọn, tự công bố các bệ trong mạng nội bộ và nhận kết nối từ client Orange Pi. Trạng thái bệ phân biệt rõ đang xác nhận, đã kết nối và chưa kết nối; khi client gửi đủ dữ liệu heartbeat, giao diện hiển thị thêm ping và phần trăm pin.

Kết nối mới có thêm trạng thái `KẾT NỐI CHẬP CHỜN` và `MẤT TÍN HIỆU`. Khi mạng
xấu, hệ thống tạm giảm tải luồng camera, giữ chỗ bệ và chỉ tạo phiên mới sau các
mốc timeout cấu hình; khi phục hồi cần nhiều heartbeat hợp lệ liên tiếp.

Video trực tiếp, heartbeat/lệnh và ảnh bắn đi trên ba kênh riêng để camera không
làm nghẽn tín hiệu kết nối. Nếu Orange Pi đang lưu IP server cũ và mạng chặn mDNS,
client tự dò các cổng MBT03 ổn định trong subnet hiện tại rồi cập nhật lại server
sau khi bắt tay hợp lệ.

Chọn **Không sử dụng LoRa** để chạy mô phỏng trên màn hình theo các mốc Hiện/Ẩn đã lưu,
bao gồm chồng bia, gập khi trúng và tự kết thúc. Chế độ này không điều khiển bia vật lý.
Khi đã chọn cổng COM, thời điểm hiện bia/nhận điểm vẫn theo lần ghi lệnh serial thực tế;
lỗi kết nối không tự chuyển sang mô phỏng. Cổng đã chọn nhưng không còn trong danh sách
được ghi rõ “chưa kết nối”.

Nút `Cài đặt thiết bị` mở cửa sổ cài đặt từ `assets/qt/setting.ui`, cho phép chọn bệ đang kết nối, xem luồng camera, hiệu chỉnh camera và thực hiện quy không.

Khi mở cửa sổ này, phần mềm gửi LoRa `@114#` để dựng bia số 6 phục vụ bắn Q0. Khi thoát bằng Đóng cửa sổ, Esc hoặc nút X, phần mềm gửi `@112#` để gập bia xuống, độc lập với tùy chọn gập bia tự động trong bài bắn. Cần kết nối LoRa để bia nhận được lệnh.

Trong lúc bắn Q0, camera tiếp tục hiển thị stream trực tiếp sau mỗi phát. Các dấu Q0 của những phát đã xử lý được vẽ chồng lên các frame mới để vừa theo dõi hình ảnh hiện tại vừa đối chiếu các phát trước.

Trải nghiệm Quy không được đồng bộ với `MBT03-wireless`: các chấm xanh ở góc trên ảnh camera biểu thị số phát hợp lệ còn thiếu; mỗi phát hợp lệ được đánh dấu bằng chữ thập vàng. Khi đủ 3 phát hợp lệ theo mặc định, nút **ĐÓNG CỬA SỔ** nhường chỗ cho **HỦY** và **CHẤP NHẬN**. **HỦY** xóa mẫu và cấp lại 3 phát cho súng đang chọn. **CHẤP NHẬN** gửi giá trị trung bình đến súng, kết thúc lượt Quy 0 và hiện lại nút **ĐÓNG CỬA SỔ**. Cửa sổ vẫn mở để chọn súng khác và Quy 0 tiếp. Khi không bắn Quy không, chữ thập xanh hiển thị vị trí Q0 đã lưu của bệ đang chọn.

Bấm chuột trái vào nhãn **BỆ SỐ …** để súng của bệ đó nhấp nháy đèn đỏ tìm súng
(`0LR01\n`); bấm lại để trở về đèn xanh (`0LG00\n`). Có thể dùng Tab chọn nhãn rồi
nhấn Enter hoặc Space. Nhãn nhấp nháy đỏ/xanh khi đang tìm súng; màu cảnh báo kết
nối vẫn được ưu tiên. Chỉ gửi đến súng đang kết nối, không đổi trạng thái nếu gửi
thất bại. Mất kết nối sẽ xóa trạng thái tìm súng trên giao diện; đóng ứng dụng gửi
lệnh trở về đèn xanh tới các súng đang tìm và còn kết nối.

Trong **Cài đặt thiết bị**, chọn **Cổng LoRa** và **Kênh 1, 2 hoặc 3**, rồi bấm **ĐẶT**. Mỗi lần bấm sẽ gửi lại cấu hình kênh cho E32 trên cổng đã chọn, kể cả khi chọn lại kênh hiện tại. Nếu cổng đang mở và giữ nguyên, phần mềm dùng kết nối COM đó. Khi có lỗi, dòng đỏ dưới phần LoRa báo nguyên nhân ngắn gọn. **ĐÓNG CỬA SỔ** tự lưu thời gian bia. Khi khởi động, phần mềm áp dụng kênh đã lưu, mặc định là Kênh 1. Các module LoRa của cùng bộ luyện tập cần dùng cùng kênh.

Nhấn nút **ẨN BIA** (`close_target_btn`) để gửi `@661#` qua LoRa **một lần**,
không chờ ACK và không gửi lại. Nút
**HIỆN BIA** (`open_target_btn`) gửi lần lượt bia **6 → 10 → 7 → 8**, dùng các
lệnh dựng riêng `@114#`, `@224#`, `@334#`, `@441#`, độc lập với `shooting.lora_timeline`.
Các lệnh dựng thủ công chờ ACK (echo đúng lệnh). Nhận ACK thì chờ **100 ms** trước bia kế tiếp;
hết số lần thử tối đa mà không có ACK thì chuyển ngay sang bia kế tiếp. Thời gian
chờ và số lần thử dùng `lora.ack_timeout_seconds` / `lora.max_attempts` (mặc định
1 giây / 3 lần gửi tổng cộng). Trong lúc gửi, hai nút điều khiển bia, Cài đặt và
BẮT ĐẦU tạm khóa; hai nút điều khiển bia cũng khóa khi bài bắn đang chạy.

Nút CẤP ĐẠN đã gộp vào **BẮT ĐẦU**. Khi nhấn `BẮT ĐẦU`, ứng dụng gửi
`0F016\n` cấp 16 viên cho súng ở mỗi bệ, lập lịch bài bắn và sau khoảng **300 ms**
gửi `0A000\n`. Lệnh cấp đạn dùng khóa cấu hình `shooting.start_uart_command`.
Không tự gửi lệnh ẩn tất cả bia; lịch hiện bia trong bài bắn vẫn dùng
`shooting.target_times`, dùng các lệnh hiện `@114#`, `@224#`, `@334#`, `@444#`; chỉ ba bia đầu có lệnh ẩn tương ứng.
Lệnh đang chờ được hủy nếu kết thúc bài hoặc đóng ứng dụng trước khi hết thời gian chờ.

Khi bật **Q0**, phần mềm gửi `0F003` đến súng của bệ đang chọn, chờ **300 ms** rồi
gửi `0Q000` (cả hai kèm xuống dòng). Trong thời gian chờ chưa thu mẫu quy không.
Tắt Q0, đổi bệ hoặc đóng cửa sổ sẽ hủy lệnh còn chờ; đổi bệ cũng xóa mẫu Q0 của
bệ trước. Nếu gửi `0F003` thất bại hoặc bệ mất kết nối trước khi hết thời gian chờ,
phần mềm không gửi tiếp `0Q000`.

Riêng **bia số 8C**, phần mềm gửi **@444# một lần** cho xe chạy, rồi hỏi **@448# mỗi giây**. Phản hồi `@4481` kèm xuống dòng là đang hiện, `@4480` là đã ẩn. Màn hình cập nhật theo phản hồi, không cộng thêm độ trễ hiển thị. Không gửi @442# do trúng, theo lịch, khi hết giờ hoặc thoát bài; xe tự chạy hết hành trình và gập.

Ô **Ẩn của 8C** là **mốc thời gian từ đầu bài**, giống ba bia còn lại. Thời gian chạy bằng **Ẩn − Hiện**; giới hạn chờ từ lần ghi @444# thực tế bằng **Ẩn − Hiện + 4 giây**. Ví dụ **Hiện 64, Ẩn 80 → chạy 16 giây, giới hạn chờ 20 giây**. Nếu đã thấy bia hiện rồi nhận phản hồi gập, kết thúc bài sau **2 giây**, nhưng không vượt giới hạn trên. Phản hồi 0 lúc xe vừa khởi hành chưa làm kết thúc bài; mất phản hồi vẫn kết thúc khi hết giới hạn chờ. Có thể kết thúc thủ công bằng nút trên màn hình. Các khoảng +2/+4 giây riêng của 8C là số giây cố định, không nhân hardware_delay_time.
Khi kết thúc bài (thủ công, hết giờ hoặc thoát ứng dụng trong bài), phần mềm gửi
`0S000` kèm xuống dòng đến tất cả súng. Đóng cài đặt bằng **ĐÓNG CỬA SỔ**,
Esc hoặc nút X cũng gửi lệnh này đến tất cả súng. Chấp nhận Quy 0 gửi lệnh dừng đến súng vừa hiệu chỉnh.
Bia hiện theo thứ tự **6 → 10 → 7B → 8C**. Trong Cài đặt thiết bị, phần THỜI GIAN
HIỆN / ẨN BIA cho phép nhập hai mốc giây tính từ đầu bài cho cả bốn bia. Nhấn **ĐÓNG CỬA SỔ** để lưu và
áp dụng từ bài tiếp theo. Esc và nút X bỏ các chỉnh sửa thời gian chưa lưu. Mặc định Hiện là **15 / 32 / 42 / 64**,
Ẩn là **22 / 39 / 49 / 92**.

Lệnh hiện được hẹn đúng mốc Hiện. Lệnh ẩn theo lịch được hẹn sau mốc Ẩn **1 giây**.
Với ba bia đầu, khoảng nhận điểm tính từ lần ghi lệnh hiện thực tế đến trước lần
truyền lệnh ẩn cộng **3 giây**, bằng hai lần `shooting.hardware_delay_time` mặc định.
Gập sớm khi trúng cũng dùng mốc ghi lệnh thực tế. Bia 8C dùng phản hồi của xe và
thời hạn bài đã nêu ở trên.

| Bia | Hiện / Ẩn đặt trước | Gửi lệnh hiện / ẩn | Khoảng nhận mặc định |
| --- | --- | --- | --- |
| 6 | 15 / 22 | 15 / 23 | Từ 15 đến trước 26 giây |
| 10 | 32 / 39 | 32 / 40 | Từ 32 đến trước 43 giây |
| 7B | 42 / 49 | 42 / 50 | Từ 42 đến trước 53 giây |
| 8C | 64 / 92 | 64 / xe tự gập | Từ 64 đến khi kết thúc bài, chậm nhất giây 96 nếu gửi đúng lịch |

Phát nhận trước khi lệnh hiện thực sự gửi đi không được tính trúng. Chỉ tính trúng khi nhận
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
gập bia của lượt sau. Ảnh nhận từ mốc kết thúc bài trở đi không được nhận vào bài.

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

Sau khi kết thúc bài bắn, nhấn `Xem lại` tại từng bệ. Giao diện có hai ảnh lớn trên
nền tối để dễ so sánh, dải ô đạn bên dưới ảnh và hàng `Phát trước` / số phát hiện tại–tổng /
`Phát sau` ở cuối. Bấm ô đạn đã có kết quả để chuyển trực tiếp đến ảnh tương ứng.
Home/End và phím mũi tên vẫn dùng được; Esc đóng cửa sổ.

Mỗi viên có một ô vuông: xanh lá khi tính trúng, đỏ khi trượt/không tính điểm, xám khi
chưa bắn hoặc đang chờ chấm. Viên đang xem có **viền blue**. Khung vàng bao từng
loạt, khoảng cách giữa các loạt lớn hơn giữa các viên cùng loạt. Một loạt được nối
khi hai viên liên tiếp cùng bệ có thời gian PC nhận ảnh cách nhau **dưới**
`shooting.burst_gap_seconds` (mặc định 0,3 giây); đúng 0,3 giây bắt đầu loạt mới.
Nhóm được ghi nhận trước khi chấm ảnh nên kết quả hoàn thành khác thứ tự không
làm đổi nhóm. Mỗi viên vẫn được chấm và đếm đạn riêng.

`shooting.max_bullets` mặc định 16, dùng chung cho giới hạn đạn, lệnh cấp đạn và số ô.
Ví dụ đặt 24 sẽ cấp `0F024\n` và hiển thị 24 ô; khởi động lại sau khi sửa config.
Khi dải quá dài, có thể cuộn ngang. Bản config cũ chưa có khóa này được chuyển từ
lệnh `start_uart_command` dạng `0Fxxx\n`. Kết quả chấm đến trễ sẽ tự cập nhật màu ô
và giữ nguyên viên đang xem.

Bấm **Xem log** cạnh Đóng để mở riêng chi tiết phát đang chọn: trạng thái, lý do
không tính điểm, tọa độ, thời điểm nhận, loạt và thông tin nhận diện. Tên ảnh gốc,
đường dẫn và tình trạng đang lưu/lỗi lưu nằm trong cửa sổ log, không chiếm diện tích
màn hình so sánh. Văn bản log có thể chọn và sao chép.

Bia mô phỏng bên phải có nền trắng chừa trống xung quanh và không có viền kết quả.
Bia luôn ở giữa, giữ cùng kích thước khi chuyển các phát của cùng bia trong cùng
kích thước cửa sổ. Điểm chạm không làm dịch hoặc thu nhỏ bia. Điểm còn nằm trong
khung trắng được hiển thị đúng vị trí; điểm quá xa ngoài khung bị ẩn. Các thông số kỹ thuật và
chú giải điểm được xem trong log, không hiển thị dưới hai ảnh.

Trong `assets/configurations/config.json`, bốn khóa trong nhóm `review` điều khiển độc lập các dấu điểm:

| Khóa | Nội dung | Mặc định |
| --- | --- | --- |
| `show_camera_aim_point` | Điểm ngắm màu xanh trên ảnh thật bên trái | `true` |
| `show_camera_impact_point` | Điểm chạm sau offset màu đỏ trên ảnh thật bên trái | `true` |
| `show_simulation_aim_point` | Điểm ngắm trước offset màu xanh trên bia mô phỏng bên phải | `false` |
| `show_simulation_impact_point` | Điểm chạm sau offset màu đỏ trên bia mô phỏng bên phải | `true` |

Đổi `true`/`false` rồi khởi động lại phần mềm. Với bản EXE, file nằm tại `_internal/assets/configurations/config.json` trong thư mục bản chạy. Config cũ có `review.show_before_offset` vẫn được đọc làm giá trị dự phòng cho `show_simulation_aim_point`; khi có khóa mới, khóa mới được ưu tiên.

Điểm chạm trên ảnh thật được suy ngược từ điểm sau offset bằng chính phép biến đổi affine đã dùng để chấm phát đó, rồi lưu cùng dữ liệu xem lại. Đây là vị trí suy tính, không phải phát hiện lỗ đạn thực tế trên ảnh. Không tính lại theo offset hiện tại. Nếu thiếu phép biến đổi hợp lệ thì không tạo điểm giả. Điểm nằm ngoài ảnh hoặc ngoài vùng zoom không bị kéo vào mép ảnh; có thể giảm `review.camera_zoom` về `1.0` để xem toàn bộ ảnh gốc.

Khi bật cả hai điểm, dấu xanh dài hơn một chút nếu trùng tâm với dấu đỏ. Bia mô phỏng có đường nối vàng khi cả hai điểm nằm trong khung cố định; không mở rộng khung theo điểm chạm. Trên ảnh camera, khung vàng là bia hệ thống đã chọn để tính điểm, các khung xanh là những bia khác được nhận diện. Mã lớp, tên bia và độ tin cậy được xem trong log.

`shooting.show_rejected_shots_on_target` mặc định `false`: phát bị từ chối vì ngoài thời gian cho phép, thiếu thời điểm nhận hoặc nhận diện khác bia được phép tính điểm sẽ **không vẽ dấu trên bia màn hình chính**. Đặt `true` để hiện lại trên màn hình chính. Cửa sổ **Xem lại luôn hiển thị theo bốn công tắc `review`**, kể cả phát bị từ chối, để đối chiếu điểm chạm và nguyên nhân không tính điểm. Phát trượt hình học trong thời gian hợp lệ vẫn hiển thị bình thường. Bộ đếm Đạn, lịch sử, ảnh camera và kết quả chấm không thay đổi; phần log xem lại ghi rõ **KHÔNG TÍNH ĐIỂM** cùng lý do. Khi bắt đầu bài bắn mới, dữ liệu xem lại của phiên cũ được xóa.

Khi `save_raw_data` trong `assets/configurations/config.json` là `true`, mọi ảnh chụp gốc nhận từ súng được lưu tự động vào `raw_camera_images`. Tên ảnh chứa thời gian chụp và số bệ để phục vụ thu thập, phân loại dữ liệu. Đặt khóa này thành `false` và mở lại ứng dụng nếu không muốn lưu ảnh.

Để thử riêng một client có camera trên PC với đúng cơ chế server/client hiện tại,
chạy `client_demo.bat [so_be]` (hoặc `python client_demo.py [so_be]`). Có thể chọn camera bằng đối số thứ hai hoặc
`--camera-index=N`, và chọn backend bằng
`--camera-backend=auto|dshow|msmf|default`. Demo dùng trực tiếp lõi ba kênh trong
`assets/server_client`, không duy trì một bản giao thức riêng.

Ảnh xem trước trong client demo hiển thị dấu ngắm xanh tại **Q0 hiện tại của súng**,
kèm tọa độ X/Y chuẩn hóa và **Offset dX/dY** so với tâm ảnh `(0.5, 0.5)`.
Offset tính theo phần trăm chiều rộng/cao: X dương sang phải, Y dương xuống dưới.
Ví dụ Q0 `(0.4861, 0.4405)` hiển thị `dX=-1.39%, dY=-5.95%`.
Thông tin đọc từ `q0_value` của client, cập nhật khi Q0 thay đổi; chỉ vẽ trên ảnh
xem trước, không ghi vào ảnh chụp/stream gửi server. Đây là hiệu chỉnh Q0 của súng,
khác với offset từng loại bia bên dưới.

Điểm chạm dùng để tính trúng/trượt có offset riêng theo từng loại bia vì cự ly và chuyển động
khác nhau. Bia 6 là mốc không offset; các giá trị tạm của bia 10, 7B và 8 có thể chỉnh trong
`scoring.target_offsets_by_class`. Trên ảnh camera, công cụ `LAB/score_test.py` chỉ đánh dấu
điểm click ban đầu. Ảnh bia chuẩn hiển thị `CLICK` màu xanh lơ, `CHAM` màu đỏ và mũi tên nối
hai điểm để kiểm tra offset trực quan; điểm sau offset không được chiếu ngược về camera.

Cửa sổ xem lại chỉ hiển thị các viên trong giới hạn `shooting.max_bullets` (hiện là 16), kể cả khi lịch sử cũ có nhiều hơn. Phát nhận sau giới hạn không được đưa vào chấm điểm, phân loạt hoặc lịch sử xem lại.
