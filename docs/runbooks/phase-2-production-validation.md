# Hướng dẫn test production pipeline Phase 2

Tài liệu này mô tả cách chứng minh cron schema sync, reviewer loop, metadata bot và VectorDB apply
hoạt động end-to-end. Không bỏ qua gate và không dùng tài khoản ClickHouse có quyền ghi làm DSN của
pipeline.

## 1. Luồng cần quan sát

```text
ClickHouse schema thay đổi
  -> Scheduled Schema Sync trên self-hosted runner
  -> tạo hoặc cập nhật một Draft PR
  -> Telegram pr_review
  -> reviewer sửa YAML, giữ needs_review
  -> Metadata PR bot sinh structured JSON + Markdown preview
  -> reviewer đọc preview
  -> commit riêng: document_status=approved
  -> bot promote đúng candidate đã xem
  -> reviewer approve PR trên GitHub và merge
  -> Index Manifest tạo audit package
  -> Apply Vector Index reconcile Qdrant
  -> live retrieval pass
  -> Telegram index_done
```

`document_status: approved` và nút **Approve** của GitHub là hai việc khác nhau. Trạng thái YAML
quyết định document có được index hay không; GitHub approval quyết định PR có được phép merge hay
không.

## 2. Provision secrets nhưng chưa bật production

Giữ hai variables:

```bash
gh variable set SCHEMA_SYNC_ENABLED --body false
gh variable set INDEX_APPLY_ENABLED --body false
```

Tạo secrets qua GitHub UI hoặc chạy từng lệnh dưới đây và nhập giá trị khi CLI yêu cầu. Không đặt
giá trị secret trong command line, workflow input, PR hoặc tài liệu:

```bash
gh secret set TBLS_DSN_COMMERCE_DEMO
gh secret set TBLS_DSN_URCARD
gh secret set TBLS_DSN_URGIFT
gh secret set GEMINI_API_KEY
gh secret set QDRANT_URL
gh secret set QDRANT_API_KEY
```

Kiểm tra chỉ tên secret:

```bash
gh secret list
```

Ba ClickHouse DSN phải dùng user chỉ có quyền đọc metadata của đúng database/table allowlist. Tài
khoản thực hiện `ALTER` trong UAT là một identity khác, do data owner kiểm soát.

## 3. Chốt allowlist UrCard và UrGift

Data owner cung cấp chính xác tên table. Không suy ra allowlist bằng cách lấy toàn bộ
`system.tables` và không dùng wildcard.

Trong `config/databases/urcard/database.yml`:

```yaml
enabled: true
scheduled_sync: true
tbls_dsn_env: TBLS_DSN_URCARD
tables:
  - <approved_table_1>
  - <approved_table_2>
```

Tạo `config/databases/urcard/tbls.yml` với cùng danh sách `include`. Làm tương tự cho `urgift` và
`TBLS_DSN_URGIFT`. Profile, `tbls.yml`, raw schema ban đầu và reviewer templates phải đi qua một PR
onboarding trong khi repository flag vẫn `false`.

Checkpoint:

```bash
make catalog-check-all
make review-validate DATABASE=urcard
make review-validate DATABASE=urgift
```

## 4. PR-17A — test schema sync và một active Draft PR

### 4.1 Baseline production

Sau khi config/allowlist đã merge vào `main`, dispatch thủ công nhưng không bật cron production:

```bash
gh workflow run schema-sync.yml --ref main -f force_run=true
gh run list --workflow schema-sync.yml --limit 1
```

Mở run mới nhất và kiểm tra:

- job chạy trên runner có labels `self-hosted,schema-sync`;
- số database inspected đúng với profile đã schedule;
- baseline đồng bộ trả `noop`, hoặc tạo Draft PR đầu tiên nếu raw schema chưa tồn tại;
- không DSN nào xuất hiện trong log/report.

### 4.2 Comment change

Chỉ trên database/table UAT được data owner cho phép, lưu comment cũ để rollback. Dùng identity có
quyền DDL riêng, không dùng read-only DSN của pipeline:

```sql
ALTER TABLE <database>.<table>
COMMENT COLUMN <column> 'phase-2-uat-comment-20260722';
```

Dispatch lại `force_run=true`. Kỳ vọng:

1. tbls phát hiện đúng một table modified;
2. reviewer YAML của table quay về `document_status: needs_review`;
3. automation tạo Draft PR có label `automation:schema-sync`;
4. Telegram gửi `pr_review created`;
5. PR có hidden marker `metadata-notification:pr_review:<commit>`.

### 4.3 Additive/change lần hai và PR reuse

Khi PR đầu tiên vẫn mở, thực hiện một thay đổi additive đã được phê duyệt trên cùng nguồn UAT, ví dụ
thêm một cột nullable hoặc table UAT. Dispatch lại. Kỳ vọng:

- không có PR thứ hai;
- cùng PR number nhận thêm một bot commit;
- reviewer edits đã có trên branch vẫn còn;
- Telegram gửi `pr_review updated` cho commit mới;
- PR body hiển thị cumulative impact.

Rollback DDL UAT bằng quy trình của data owner rồi dispatch lần nữa để automation ghi nhận trạng
thái đã phục hồi. Không chạy DROP trên table nghiệp vụ chỉ để test.

### 4.4 Bật cron thật

Chỉ sau baseline, comment/additive và PR reuse đều pass:

```bash
gh variable set SCHEMA_SYNC_ENABLED --body true
```

Manual dispatch chứng minh runtime; nó không chứng minh trigger cron. Để chứng minh cron, chờ run
`event=schedule` tiếp theo lúc 01:17 Asia/Ho_Chi_Minh và kiểm tra:

```bash
gh run list --workflow schema-sync.yml --event schedule --limit 1
```

Scheduled workflow chạy trên commit mới nhất của default branch và có thể trễ khi GitHub Actions tải
cao. Không đổi cron production thành tần suất ngắn chỉ để demo.

## 5. Reviewer thao tác trên Draft PR

### 5.1 Bổ sung metadata

Reviewer chỉ sửa:

```text
catalog/<database>/review/<table>.yml
```

Điền business description, grain, columns, relationships, caveats và giữ:

```yaml
document_status: needs_review
```

Commit vào cùng branch của Draft PR. `Metadata PR / pr-gate` validate input, gọi LLM gateway và bot
commit `generated/structured` cùng `generated/published`.

### 5.2 Đọc preview và approve document

Đọc Markdown trong PR diff. Nếu chưa đúng, tiếp tục sửa YAML với `needs_review`. Khi đúng, tạo một
commit riêng chỉ đổi:

```yaml
document_status: approved
```

Không sửa business content cùng commit approval. Bot kiểm tra fingerprint và promote đúng candidate
đã review mà không gọi LLM lại.

### 5.3 Approve và merge PR

Khi latest SHA có `Quality` và `Metadata PR / pr-gate` xanh:

1. chuyển Draft thành Ready for review;
2. dùng GitHub Review → **Approve**;
3. merge vào `main`;
4. ghi lại merge SHA để theo dõi hai workflow index.

## 6. PR-17B — VectorDB live UAT khi global flag vẫn false

Qdrant collection phải có suffix khớp model/dimension, ví dụ:

```bash
gh variable set EMBEDDING_PROVIDER --body gemini
gh variable set EMBEDDING_MODEL --body gemini-embedding-001
gh variable set EMBEDDING_DIMENSION --body 768
gh variable set QDRANT_COLLECTION --body metadata_uat__gemini_embedding_001__768
```

Gemini dùng `RETRIEVAL_DOCUMENT` cho chunks và `RETRIEVAL_QUERY` cho câu hỏi. Qdrant collection dùng
vector size 768 và cosine distance. `force_run=true` chỉ bypass feature flag; credential, collection,
manifest và retrieval gates vẫn bắt buộc.

### 6.1 Bootstrap và initial apply

```bash
gh workflow run apply-index.yml --ref main \
  -f force_run=true \
  -f bootstrap_collection=true
```

Artifact phải có:

- `manifest.json` đúng source SHA;
- `apply-summary.json` có `outcome=applied`, `verified=true`;
- `vector-retrieval-report.json` pass;
- Telegram nhận đúng một `index_done`.

### 6.2 No-op reapply

```bash
gh workflow run apply-index.yml --ref main \
  -f force_run=true \
  -f bootstrap_collection=false
```

Kỳ vọng `outcome=noop`, upsert/delete bằng 0, retrieval vẫn pass và không có `index_done` thứ hai.

### 6.3 Changed và removed chunk

Sau khi reviewer PR ở mục 5 merge, chạy manual force apply. Một thay đổi business field chỉ re-embed
các chunk có `body_hash` đổi. Kiểm tra `upserted_count > 0` và số còn lại nằm trong
`skipped_count`.

Để test removal, chỉ dùng một document UAT chuyên dụng: đưa nó từ `approved` về `needs_review` qua
normal reviewer/bot PR, merge, rồi force apply. Kiểm tra `deleted_count > 0`. Sau test, approve lại
document và force apply để phục hồi. Không demote document production đang phục vụ retrieval.

### 6.4 Bật automatic apply

Chỉ sau initial, no-op, changed, removed và retrieval đều pass:

```bash
gh variable set INDEX_APPLY_ENABLED --body true
```

Từ lúc này, merge vào `main` có thay đổi `generated/structured` hoặc `generated/published` sẽ tự chạy
`Apply Vector Index`. `index_done` chỉ được gửi khi Qdrant thực sự changed và retrieval pass.

## 7. Quan sát và rollback

```bash
gh run list --workflow schema-sync.yml --limit 5
gh run list --workflow metadata-pr.yml --limit 5
gh run list --workflow index.yml --limit 5
gh run list --workflow apply-index.yml --limit 5
```

Soft stop ngay lập tức:

```bash
gh variable set SCHEMA_SYNC_ENABLED --body false
gh variable set INDEX_APPLY_ENABLED --body false
```

Nếu VectorDB apply fail, không phát `index_done`; `job_failed` là tín hiệu vận hành. Rerun cùng commit
sẽ đọc actual Qdrant state và bỏ qua points đã đúng. Không xóa/recreate collection khi dimension sai;
tạo collection version mới và chuyển read-side sau khi retrieval UAT pass.

Ghi mọi run URL và kết quả vào [`docs/uat/metadata-phase-2.md`](../uat/metadata-phase-2.md).
