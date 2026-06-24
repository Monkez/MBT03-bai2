# Quy tắc làm việc cho AI Agents trong dự án lập trình

# Quy tắc làm việc cho AI Agents trong dự án lập trình

File này dùng để đặt vào các dự án lập trình nhằm yêu cầu AI agents làm việc nhất quán, cẩn thận và có trách nhiệm. Các phần tài liệu, hướng dẫn sử dụng, hướng dẫn cài đặt hoặc nội dung mà người dùng sẽ đọc phải ưu tiên viết bằng tiếng Việt có dấu. Các ghi chú kỹ thuật nội bộ chỉ dành cho AI hoặc developer có thể dùng tiếng Anh nếu giúp diễn đạt chính xác hơn.

## 1. Tài liệu dự án

- Luôn tạo và duy trì tài liệu trong thư mục `docs/`.
- Khi thay đổi, thêm, xóa hoặc sửa tính năng, bắt buộc cập nhật tài liệu liên quan trong `docs/`.
- Các tài liệu người dùng có thể đọc phải ưu tiên tiếng Việt có dấu, rõ ràng, dễ hiểu, không viết kiểu quá kỹ thuật nếu không cần.
- Có thể chia tài liệu thành nhiều file để dễ quản lý, ví dụ:
  - `docs/overview.md`: tổng quan dự án.
  - `docs/setup.md`: hướng dẫn cài đặt môi trường.
  - `docs/usage.md`: hướng dẫn sử dụng.
  - `docs/features.md`: danh sách tính năng.
  - `docs/api.md`: tài liệu API nếu có.
  - `docs/changelog.md`: lịch sử thay đổi quan trọng.
  - `docs/troubleshooting.md`: lỗi thường gặp và cách xử lý.
- Phần hướng dẫn sử dụng, hướng dẫn chạy app, hướng dẫn build, hướng dẫn deploy và troubleshooting phải viết sao cho người dùng không chuyên vẫn có thể làm theo.
- Nếu một thay đổi ảnh hưởng đến cách cài đặt, cấu hình, chạy, build, deploy hoặc sử dụng sản phẩm, phải cập nhật docs tương ứng ngay trong cùng task.
- Không để docs bị lệch so với code hiện tại.

## 2. Môi trường Python và dependencies

- Với mỗi project Python, luôn ưu tiên cài đặt và sử dụng `uv` để quản lý môi trường và dependencies.
- Tạo virtual environment riêng cho từng project khi cần, thường là `.venv/`.
- Không dùng chung môi trường Python toàn cục nếu có thể tránh.
- Tạo và cập nhật `requirements.txt` nếu project cần tương thích với workflow dùng `pip`.
- Nếu project dùng `pyproject.toml`, đảm bảo dependencies được khai báo đúng, gọn và nhất quán.
- Khi thêm, xóa hoặc nâng cấp package, phải cập nhật file quản lý dependencies tương ứng.
- Tài liệu hóa cách cài môi trường trong `docs/setup.md`.
- Nếu có script `setup.bat`, script đó nên tự kiểm tra `uv`, tạo `.venv`, cài dependencies và báo lỗi rõ ràng khi thiếu công cụ cần thiết.

## 3. Git, backup và release

- Nếu project chưa có Git, phải nhắc người dùng tạo Git repository hoặc chủ động hỗ trợ tạo Git nếu được phép.
- Trước khi sửa đổi lớn, cần kiểm tra trạng thái repository bằng  `git status`
- Sau khi có thay đổi quan trọng, phải push code lên remote Git để backup.
- Nếu project có quy trình build/release, sau khi thay đổi ổn định cần build bản release mới.
- Nếu build, test hoặc release thất bại, phải báo rõ:

  - Lệnh đã chạy.
  - Lỗi chính.
  - Nguyên nhân có khả năng cao nhất.
  - Hướng xử lý tiếp theo.

## 4. Script tiện ích để chạy, build và test

- Luôn tạo hoặc cập nhật các file chạy nhanh phù hợp với project, đặc biệt trên Windows:
  - `run.bat`: chạy ứng dụng hoặc dev server.
  - `build.bat`: build project.
  - `test.bat`: chạy test nếu có.
  - `setup.bat`: cài đặt môi trường và dependencies nếu cần.
- Các file `.bat` phải được viết cẩn thận, dễ dùng, có thông báo rõ ràng và xử lý lỗi cơ bản.
- Script phải dùng đường dẫn tương đối an toàn theo vị trí của chính file script, tránh phụ thuộc vào thư mục hiện tại của terminal.
- Nếu project có `.venv/`, script nên tự động kích hoạt virtual environment trước khi chạy lệnh Python.
- Nếu project chạy trên nhiều hệ điều hành, có thể tạo thêm script tương ứng như `.sh`.
- Cập nhật docs để hướng dẫn người dùng chạy các script này.
- Ưu tiên trải nghiệm “double click là chạy được” đối với các workflow phổ biến trên Windows.

## 5. Chất lượng code và cách làm việc

- Luôn làm việc như một kỹ sư phần mềm chuyên nghiệp: nghiêm túc, kỹ tính, có trách nhiệm cao.
- Trước khi sửa, phải đọc và hiểu cấu trúc code hiện có.
- Ưu tiên giải pháp gọn, rõ, dễ bảo trì và phù hợp với phong cách hiện tại của project.
- Không thêm abstraction, framework hoặc dependency mới nếu không thực sự cần thiết.
- Review code chặt chẽ, đặc biệt chú ý:
  - Logic bug.
  - Security issue.
  - Performance issue.
  - Error handling.
  - Edge cases.
  - Maintainability.
  - Scalability.
  - UX/UI consistency.
  - Accessibility nếu có frontend.
- Sản phẩm cuối cùng phải đạt chất lượng tốt về giao diện, tính năng, hiệu năng và độ ổn định.
- Nếu làm frontend, giao diện phải gọn gàng, dễ dùng, responsive, không vỡ layout, không chồng chéo text, không tạo trải nghiệm rối mắt.
- Nếu làm backend/API, phải chú ý validation, error handling, logging và cấu trúc response nhất quán.
- Nếu có test, phải chạy test sau khi sửa. Nếu chưa có test, cần cân nhắc thêm test cho các logic quan trọng.
- Nếu có lint/format/build, phải chạy các bước phù hợp trước khi kết thúc task.

## 6. Quy tắc giao tiếp với người dùng

- Chủ động nhắc người dùng khi cần tạo Git, push code, build release, cập nhật docs hoặc cài dependencies.
- Nếu gặp lựa chọn kỹ thuật quan trọng, đề xuất phương án tốt nhất kèm lý do ngắn gọn.
- Không hỏi lại những điều có thể suy luận hợp lý từ codebase.
- Nếu cần hỏi, hỏi ngắn gọn, đúng trọng tâm.
- Luôn báo rõ khi không thể hoàn thành một bước nào đó và nêu cách khắc phục.
- Sau khi hoàn thành task, phải tóm tắt ngắn gọn:
  - Đã thay đổi gì.
  - Đã kiểm tra/build/test như thế nào.
  - Còn rủi ro hoặc việc cần làm tiếp hay không.

## 7. Nguyên tắc ngôn ngữ trong dự án

- Nội dung dành cho người dùng đọc nên viết bằng tiếng Việt có dấu, nhất là:
  - Hướng dẫn cài đặt.
  - Hướng dẫn sử dụng.
  - Hướng dẫn chạy app.
  - Hướng dẫn build/deploy.
  - Ghi chú lỗi thường gặp.
  - Mô tả tính năng.
- Nội dung chỉ dành cho AI agents hoặc developer có thể dùng tiếng Anh nếu hợp lý, ví dụ:
  - Code comments kỹ thuật ngắn.
  - Internal architecture notes.
  - Prompt/rule dành riêng cho AI.
  - Tên biến, tên hàm, tên module, commit message nếu project đang dùng tiếng Anh.
- Không trộn ngôn ngữ tùy tiện trong cùng một đoạn nếu làm người đọc khó hiểu.
- Ưu tiên sự rõ ràng, nhất quán và dễ bảo trì hơn là dịch máy móc từng thuật ngữ kỹ thuật.

## 8. Checklist bắt buộc trước khi kết thúc task

- [ ] Code đã được sửa đúng yêu cầu.
- [ ] Tài liệu trong `docs/` đã được tạo hoặc cập nhật nếu cần.
- [ ] Hướng dẫn người dùng đọc đã ưu tiên tiếng Việt có dấu.
- [ ] Dependencies đã được cập nhật nếu có thay đổi.
- [ ] Script `run.bat`, `build.bat`, `test.bat`, `setup.bat` đã được tạo hoặc cập nhật nếu phù hợp.
- [ ] Đã chạy test/build/lint phù hợp, hoặc nếu không chạy được thì đã nói rõ lý do.
- [ ] Đã bump version nếu thay đổi cần phát hành bản mới hoặc project có quy ước versioning.
- [ ] Đã build release mới nếu project có workflow build/release và thay đổi đã ổn định.
- [ ] Đã kiểm tra artifact/release output sau khi build nếu có.
- [ ] Đã kiểm tra `git status`.
- [ ] Đã commit với message rõ ràng nếu được phép.
- [ ] Đã push code lên remote Git để backup nếu repository có remote và workflow cho phép.
- [ ] Nếu chưa thể commit/push/build release, đã báo rõ lý do và việc cần làm tiếp theo.
- [ ] Sản phẩm cuối cùng đạt chất lượng tốt, dễ dùng, dễ bảo trì và ổn địn

File này dùng để đặt vào các dự án lập trình nhằm yêu cầu AI agents làm việc nhất quán, cẩn thận và có trách nhiệm. Các phần tài liệu, hướng dẫn sử dụng, hướng dẫn cài đặt hoặc nội dung mà người dùng sẽ đọc phải ưu tiên viết bằng tiếng Việt có dấu. Các ghi chú kỹ thuật nội bộ chỉ dành cho AI hoặc developer có thể dùng tiếng Anh nếu giúp diễn đạt chính xác hơn.

## 1. Tài liệu dự án

- Luôn tạo và duy trì tài liệu trong thư mục `docs/`.
- Khi thay đổi, thêm, xóa hoặc sửa tính năng, bắt buộc cập nhật tài liệu liên quan trong `docs/`.
- Các tài liệu người dùng có thể đọc phải ưu tiên tiếng Việt có dấu, rõ ràng, dễ hiểu, không viết kiểu quá kỹ thuật nếu không cần.
- Có thể chia tài liệu thành nhiều file để dễ quản lý, ví dụ:
  - `docs/overview.md`: tổng quan dự án.
  - `docs/setup.md`: hướng dẫn cài đặt môi trường.
  - `docs/usage.md`: hướng dẫn sử dụng.
  - `docs/features.md`: danh sách tính năng.
  - `docs/api.md`: tài liệu API nếu có.
  - `docs/changelog.md`: lịch sử thay đổi quan trọng.
  - `docs/troubleshooting.md`: lỗi thường gặp và cách xử lý.
- Phần hướng dẫn sử dụng, hướng dẫn chạy app, hướng dẫn build, hướng dẫn deploy và troubleshooting phải viết sao cho người dùng không chuyên vẫn có thể làm theo.
- Nếu một thay đổi ảnh hưởng đến cách cài đặt, cấu hình, chạy, build, deploy hoặc sử dụng sản phẩm, phải cập nhật docs tương ứng ngay trong cùng task.
- Không để docs bị lệch so với code hiện tại.

## 2. Môi trường Python và dependencies

- Với mỗi project Python, luôn ưu tiên cài đặt và sử dụng `uv` để quản lý môi trường và dependencies.
- Tạo virtual environment riêng cho từng project khi cần, thường là `.venv/`.
- Không dùng chung môi trường Python toàn cục nếu có thể tránh.
- Tạo và cập nhật `requirements.txt` nếu project cần tương thích với workflow dùng `pip`.
- Nếu project dùng `pyproject.toml`, đảm bảo dependencies được khai báo đúng, gọn và nhất quán.
- Khi thêm, xóa hoặc nâng cấp package, phải cập nhật file quản lý dependencies tương ứng.
- Tài liệu hóa cách cài môi trường trong `docs/setup.md`.
- Nếu có script `setup.bat`, script đó nên tự kiểm tra `uv`, tạo `.venv`, cài dependencies và báo lỗi rõ ràng khi thiếu công cụ cần thiết.

## 3. Git, backup và release

- Nếu project chưa có Git, phải nhắc người dùng tạo Git repository hoặc chủ động hỗ trợ tạo Git nếu được phép.
- Trước khi sửa đổi lớn, cần kiểm tra trạng thái repository bằng `git status`.
- Sau khi có thay đổi quan trọng, phải commit với message rõ ràng.
- Khi người dùng yêu cầu hoặc workflow cho phép, phải push code lên remote Git để backup.
- Nếu project có quy trình build/release, sau khi thay đổi ổn định cần build bản release mới.
- Nếu build, test hoặc release thất bại, phải báo rõ:

  - Lệnh đã chạy.
  - Lỗi chính.
  - Nguyên nhân có khả năng cao nhất.
  - Hướng xử lý tiếp theo.

## 4. Script tiện ích để chạy, build và test

- Luôn tạo hoặc cập nhật các file chạy nhanh phù hợp với project, đặc biệt trên Windows:
  - `run.bat`: chạy ứng dụng hoặc dev server.
  - `build.bat`: build project.
  - `test.bat`: chạy test nếu có.
  - `setup.bat`: cài đặt môi trường và dependencies nếu cần.
- Các file `.bat` phải được viết cẩn thận, dễ dùng, có thông báo rõ ràng và xử lý lỗi cơ bản.
- Script phải dùng đường dẫn tương đối an toàn theo vị trí của chính file script, tránh phụ thuộc vào thư mục hiện tại của terminal.
- Nếu project có `.venv/`, script nên tự động kích hoạt virtual environment trước khi chạy lệnh Python.
- Nếu project chạy trên nhiều hệ điều hành, có thể tạo thêm script tương ứng như `.sh`.
- Cập nhật docs để hướng dẫn người dùng chạy các script này.
- Ưu tiên trải nghiệm “double click là chạy được” đối với các workflow phổ biến trên Windows.

## 5. Chất lượng code và cách làm việc

- Luôn làm việc như một kỹ sư phần mềm chuyên nghiệp: nghiêm túc, kỹ tính, có trách nhiệm cao.
- Trước khi sửa, phải đọc và hiểu cấu trúc code hiện có.
- Ưu tiên giải pháp gọn, rõ, dễ bảo trì và phù hợp với phong cách hiện tại của project.
- Không thêm abstraction, framework hoặc dependency mới nếu không thực sự cần thiết.
- Review code chặt chẽ, đặc biệt chú ý:
  - Logic bug.
  - Security issue.
  - Performance issue.
  - Error handling.
  - Edge cases.
  - Maintainability.
  - Scalability.
  - UX/UI consistency.
  - Accessibility nếu có frontend.
- Sản phẩm cuối cùng phải đạt chất lượng tốt về giao diện, tính năng, hiệu năng và độ ổn định.
- Nếu làm frontend, giao diện phải gọn gàng, dễ dùng, responsive, không vỡ layout, không chồng chéo text, không tạo trải nghiệm rối mắt.
- Nếu làm backend/API, phải chú ý validation, error handling, logging và cấu trúc response nhất quán.
- Nếu có test, phải chạy test sau khi sửa. Nếu chưa có test, cần cân nhắc thêm test cho các logic quan trọng.
- Nếu có lint/format/build, phải chạy các bước phù hợp trước khi kết thúc task.

## 6. Quy tắc giao tiếp với người dùng

- Chủ động nhắc người dùng khi cần tạo Git, push code, build release, cập nhật docs hoặc cài dependencies.
- Nếu gặp lựa chọn kỹ thuật quan trọng, đề xuất phương án tốt nhất kèm lý do ngắn gọn.
- Không hỏi lại những điều có thể suy luận hợp lý từ codebase.
- Nếu cần hỏi, hỏi ngắn gọn, đúng trọng tâm.
- Luôn báo rõ khi không thể hoàn thành một bước nào đó và nêu cách khắc phục.
- Sau khi hoàn thành task, phải tóm tắt ngắn gọn:
  - Đã thay đổi gì.
  - Đã kiểm tra/build/test như thế nào.
  - Còn rủi ro hoặc việc cần làm tiếp hay không.

## 7. Nguyên tắc ngôn ngữ trong dự án

- Nội dung dành cho người dùng đọc nên viết bằng tiếng Việt có dấu, nhất là:
  - Hướng dẫn cài đặt.
  - Hướng dẫn sử dụng.
  - Hướng dẫn chạy app.
  - Hướng dẫn build/deploy.
  - Ghi chú lỗi thường gặp.
  - Mô tả tính năng.
- Nội dung chỉ dành cho AI agents hoặc developer có thể dùng tiếng Anh nếu hợp lý, ví dụ:
  - Code comments kỹ thuật ngắn.
  - Internal architecture notes.
  - Prompt/rule dành riêng cho AI.
  - Tên biến, tên hàm, tên module, commit message nếu project đang dùng tiếng Anh.
- Không trộn ngôn ngữ tùy tiện trong cùng một đoạn nếu làm người đọc khó hiểu.
- Ưu tiên sự rõ ràng, nhất quán và dễ bảo trì hơn là dịch máy móc từng thuật ngữ kỹ thuật.

## 8. Checklist bắt buộc trước khi kết thúc task

- [ ] Code đã được sửa đúng yêu cầu.
- [ ] Tài liệu trong `docs/` đã được tạo hoặc cập nhật nếu cần.
- [ ] Hướng dẫn người dùng đọc đã ưu tiên tiếng Việt có dấu.
- [ ] Dependencies đã được cập nhật nếu có thay đổi.
- [ ] Script `run.bat`, `build.bat`, `test.bat`, `setup.bat` đã được tạo hoặc cập nhật nếu phù hợp.
- [ ] Đã chạy test/build/lint phù hợp, hoặc nếu không chạy được thì đã nói rõ lý do.
- [ ] Đã bump version nếu thay đổi cần phát hành bản mới hoặc project có quy ước versioning.
- [ ] Đã build release mới nếu project có workflow build/release và thay đổi đã ổn định.
- [ ] Đã kiểm tra artifact/release output sau khi build nếu có.
- [ ] Đã kiểm tra `git status`.
- [ ] Đã commit với message rõ ràng, đầy đủ các file đã thay đổi.
- [ ] Đã push code lên remote Git để backup.
- [ ] Nếu chưa thể commit/push/build release, đã báo rõ lý do và việc cần làm tiếp theo.
- [ ] Sản phẩm cuối cùng đạt chất lượng tốt, dễ dùng, dễ bảo trì và ổn định.
