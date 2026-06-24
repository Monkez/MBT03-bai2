# Sử dụng

Khi mở ứng dụng, chọn số bệ bắn rồi bấm `CHẤP NHẬN`.

Màn hình chính hiện các bệ đã chọn. Mỗi bệ có 4 bia được ghép bằng OpenCV. Khi chọn 2 bệ, bố cục bia chuyển sang dạng dọc để mỗi bệ dễ quan sát hơn. Viền đỏ là mục tiêu chưa trúng, viền xanh lá là mục tiêu đã trúng. Nhãn kết quả hiển thị số đạn đã bắn trên 16 viên, số mục tiêu đã trúng trên 4 mục tiêu và xếp loại.

Ở phiên bản giao diện này, kết nối client, bắn quy không và logic bài bắn thật đang được để lại để triển khai ở bước sau.

Nút `Cài đặt thiết bị` mở cửa sổ cài đặt giao diện từ `assets/qt/setting.ui`. Các chức năng hiệu chỉnh camera và bắn quy không trong cửa sổ này hiện là khung giao diện, chưa nối client thật.
