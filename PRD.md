# PRD — ClickHouse Metadata Review Loop trên GitHub

**Trạng thái:** Draft để review
**Phiên bản:** 1.0
**Ngày:** 2026-07-17
**Quy mô:** MVP nhỏ, chạy được local và GitHub Actions
**Thời gian dự kiến:** 3–5 ngày làm việc

**Kế hoạch triển khai theo Pull Request:** [PR_PLAN.md](./PR_PLAN.md)

## 1. Tóm tắt

Xây một repository demo để kiểm chứng trọn vẹn luồng quản trị metadata:

1. Khởi tạo ClickHouse bằng Docker với vài bảng và dữ liệu giả.
2. `tbls` kết nối trực tiếp vào ClickHouse, đọc schema/comment và sinh tài liệu kỹ thuật cùng `schema.json`.
3. Pipeline tạo bản metadata nghiệp vụ ban đầu trong `catalog/<database>/review/`.
4. Domain reviewer sửa file review và commit lên branch của Pull Request (PR).
5. GitHub Actions nhận commit mới, sinh lại tài liệu chuẩn hóa trong `catalog/<database>/generated/published/` và bot commit vào cùng branch.
6. Reviewer kiểm tra diff mới, approve và merge.
7. Sau khi merge vào `main`, pipeline index chỉ những tài liệu có trạng thái `approved`.

MVP giữ GitHub repository làm source of truth, PR làm trung tâm review và commit vào `catalog/*/review/**` là feedback chính thức.

Repository quản lý hai guideline có version: Guideline 1 hướng dẫn con người bổ sung metadata nghiệp vụ; Guideline 2 quy định cách LLM hợp nhất schema + review metadata thành tài liệu có cấu trúc phù hợp cho chunking và retrieval.

## 2. Vấn đề cần giải quyết

Nếu `tbls`, AI và reviewer cùng sửa một file, lần chạy `tbls doc --force` hoặc `--rm-dist` có thể ghi đè nội dung do con người bổ sung. Ngoài ra, nếu CI không phân biệt input và output, commit của bot có thể tạo vòng lặp generate vô hạn.

MVP giải quyết bằng ba lớp dữ liệu độc lập:

| Lớp | Ai được sửa | Vai trò |
|---|---|---|
| `catalog/<database>/generated/raw/` | Chỉ pipeline `tbls` | Schema kỹ thuật lấy từ database |
| `catalog/<database>/review/` | AI tạo draft, reviewer chỉnh sửa | Nguồn metadata nghiệp vụ có thể audit |
| `catalog/<database>/generated/published/` | Chỉ pipeline generate | Tài liệu chuẩn hóa cuối cùng để index |

Nguyên tắc bắt buộc:

- Reviewer không sửa `catalog/*/generated/raw/**` hoặc `catalog/*/generated/published/**`.
- AI không suy feedback từ file do `tbls` sinh; AI đọc `schema.json`, file review, prompt và guideline.
- Chỉ commit thay đổi `catalog/*/generated/raw/**` hoặc `catalog/*/review/**` mới yêu cầu generate lại.
- Chỉ tài liệu `approved` đã merge vào `main` mới được index.

## 3. Mục tiêu và ngoài phạm vi

### 3.1. Mục tiêu MVP

- Một lệnh có thể dựng ClickHouse local và seed dữ liệu giả.
- `tbls` sinh được Markdown, ER diagram và `schema.json` từ ClickHouse.
- Chứng minh comment của table/column trong ClickHouse xuất hiện trong tài liệu `tbls`.
- Chứng minh quan hệ logic giữa các bảng có thể khai báo trong `config/databases/commerce_demo/tbls.yml` dù ClickHouse không enforce foreign key.
- Có PR workflow hai vòng: human commit → bot commit → human review lại.
- Không có vòng lặp bot commit vô hạn.
- Có validation ngăn metadata sai schema hoặc chưa được duyệt.
- Có index job sau merge; MVP có thể dùng index giả lập dạng JSON để không cần thêm hạ tầng vector database.
- Toàn bộ kết quả có commit history và log GitHub Actions.

### 3.2. Ngoài phạm vi MVP

- Không đọc PR comment tự do làm feedback cho AI.
- Không triển khai webhook service, queue hoặc UI riêng.
- Không kết nối production database.
- Không xây semantic search production hoặc quản lý embedding lifecycle đầy đủ.
- Không hỗ trợ PR từ fork; branch test phải nằm trong cùng repository để bot có thể push an toàn.
- Không tự merge PR.

## 4. Người dùng và vai trò

| Vai trò | Trách nhiệm |
|---|---|
| Data Engineer | Duy trì schema/seed demo; chạy schema sync |
| AI/Data Agent Engineer | Duy trì prompt, generator và validator |
| Domain Reviewer | Sửa `catalog/*/review/**`, xác nhận purpose, grain, rule, caveat |
| GitHub Bot | Commit `catalog/*/generated/raw/**` và `catalog/*/generated/published/**` vào source branch của PR |
| Repository Maintainer | Cấu hình branch protection, secrets, CODEOWNERS và merge |

## 5. Kiến trúc đề xuất

```mermaid
flowchart LR
    A["ClickHouse Docker<br/>commerce_demo"] -->|"tbls doc"| B["catalog/commerce_demo/generated/raw<br/>Markdown + schema.json"]
    B --> C["Draft generator"]
    C --> D["catalog/&lt;database&gt;/review/<br/>Human-editable"]
    D -->|"Reviewer commit"| E["GitHub Pull Request"]
    E -->|"GitHub Actions"| F["Normalize + validate"]
    F -->|"Bot commit"| G["catalog/&lt;database&gt;/generated/published/<br/>Generated only"]
    G --> E
    E -->|"Approve + merge"| H["main"]
    H -->|"Index workflow"| I["Index manifest / Vector DB"]
```

### 5.1. Cấu trúc repository

```text
metadata-demo/
├── .github/
│   ├── CODEOWNERS
│   ├── pull_request_template.md
│   └── workflows/
│       ├── schema-sync.yml
│       ├── metadata-pr.yml
│       └── index.yml
├── db/
│   └── init/
│       ├── 001_schema.sql
│       └── 002_seed.sql
├── schema/
│   └── raw/
│       └── commerce_demo/
├── metadata/
│   └── review/
│       └── commerce_demo/
├── knowledge/
│   └── published/
│       └── commerce_demo/
├── guidelines/
│   ├── reviewer_metadata_guideline.md
│   └── llm_transformation_guideline.md
├── prompts/
│   ├── initial_generation.md
│   └── regenerate_from_feedback.md
├── scripts/
│   ├── wait_for_clickhouse.sh
│   ├── extract_schema.sh
│   ├── create_initial_draft.py
│   ├── regenerate_docs.py
│   ├── validate_metadata.py
│   ├── detect_changed_paths.py
│   └── index_knowledge.py
├── tests/
│   ├── fixtures/
│   └── test_validation.py
├── config/databases/commerce_demo/tbls.yml
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── README.md
```

## 6. Dữ liệu demo trong ClickHouse

### 6.1. Phạm vi dữ liệu

Database: `commerce_demo`

| Table | Grain | Số dòng seed | Mục đích test |
|---|---|---:|---|
| `customers` | Một dòng cho một khách hàng | 5 | PII label, owner, column comment |
| `orders` | Một dòng cho một đơn hàng | 8 | Status, amount, liên kết customer |
| `order_items` | Một dòng cho một sản phẩm trong đơn | 12–16 | Liên kết order, phép tính quantity × unit_price |

Kịch bản schema change sẽ thêm bảng `order_events` để kiểm tra table added và thêm cột `orders.channel` để kiểm tra column added.

### 6.2. Docker Compose tối thiểu

```yaml
services:
  clickhouse:
    image: clickhouse/clickhouse-server:25.8
    container_name: metadata-demo-clickhouse
    environment:
      CLICKHOUSE_DB: commerce_demo
      CLICKHOUSE_USER: demo
      CLICKHOUSE_PASSWORD: demo_password
      CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: "1"
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - clickhouse_data:/var/lib/clickhouse
      - ./db/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "clickhouse-client --user demo --password demo_password --query 'SELECT 1'"]
      interval: 3s
      timeout: 3s
      retries: 30

  tbls:
    image: ghcr.io/k1low/tbls:v1.94.5
    profiles: ["tools"]
    working_dir: /work
    volumes:
      - .:/work
    environment:
      TBLS_DSN: clickhouse://demo:demo_password@clickhouse:9000/commerce_demo
      TBLS_DOC_PATH: catalog/commerce_demo/generated/raw
    depends_on:
      clickhouse:
        condition: service_healthy

volumes:
  clickhouse_data:
```

Khi triển khai, phải pin image bằng patch version hoặc digest đã được test; tag trên chỉ là baseline của MVP.

### 6.3. Schema SQL mẫu

`db/init/001_schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS commerce_demo.customers
(
    customer_id UUID COMMENT 'Định danh duy nhất của khách hàng',
    full_name String COMMENT 'Tên hiển thị của khách hàng; dữ liệu giả trong môi trường demo',
    email String COMMENT 'Email liên hệ; được phân loại là PII',
    segment LowCardinality(String) COMMENT 'Phân khúc: retail, premium hoặc enterprise',
    created_at DateTime COMMENT 'Thời điểm hồ sơ khách hàng được tạo'
)
ENGINE = MergeTree
ORDER BY customer_id
COMMENT 'Danh mục khách hàng dùng cho demo metadata.';

CREATE TABLE IF NOT EXISTS commerce_demo.orders
(
    order_id UUID COMMENT 'Định danh duy nhất của đơn hàng',
    customer_id UUID COMMENT 'Khách hàng tạo đơn; liên kết logic tới customers.customer_id',
    order_status LowCardinality(String) COMMENT 'Trạng thái hiện tại: pending, paid, shipped, cancelled',
    total_amount Decimal(18, 2) COMMENT 'Tổng tiền đơn hàng theo VND, đã gồm giảm giá',
    created_at DateTime COMMENT 'Thời điểm đơn được tạo',
    updated_at DateTime COMMENT 'Thời điểm đơn được cập nhật gần nhất'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (created_at, order_id)
COMMENT 'Sự kiện cấp đơn hàng; một dòng cho một order_id.';

CREATE TABLE IF NOT EXISTS commerce_demo.order_items
(
    order_id UUID COMMENT 'Đơn hàng chứa sản phẩm; liên kết logic tới orders.order_id',
    line_number UInt16 COMMENT 'Số thứ tự sản phẩm trong đơn hàng',
    product_code String COMMENT 'Mã sản phẩm tại thời điểm đặt hàng',
    quantity UInt16 COMMENT 'Số lượng sản phẩm',
    unit_price Decimal(18, 2) COMMENT 'Đơn giá theo VND tại thời điểm đặt hàng'
)
ENGINE = MergeTree
ORDER BY (order_id, line_number)
COMMENT 'Chi tiết sản phẩm; một dòng cho một line item trong đơn hàng.';
```

`db/init/002_seed.sql` chèn UUID cố định để test có thể lặp lại. Không dùng dữ liệu cá nhân thật.

```sql
INSERT INTO commerce_demo.customers VALUES
('00000000-0000-0000-0000-000000000001', 'Nguyen Demo', 'demo1@example.test', 'retail', now() - INTERVAL 30 DAY),
('00000000-0000-0000-0000-000000000002', 'Tran Demo',   'demo2@example.test', 'premium', now() - INTERVAL 20 DAY),
('00000000-0000-0000-0000-000000000003', 'Le Demo',     'demo3@example.test', 'retail', now() - INTERVAL 10 DAY);

INSERT INTO commerce_demo.orders VALUES
('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'paid',      250000, now() - INTERVAL 5 DAY, now() - INTERVAL 5 DAY),
('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000002', 'shipped',   600000, now() - INTERVAL 3 DAY, now() - INTERVAL 1 DAY),
('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000003', 'cancelled', 150000, now() - INTERVAL 2 DAY, now() - INTERVAL 1 DAY);

INSERT INTO commerce_demo.order_items VALUES
('10000000-0000-0000-0000-000000000001', 1, 'SKU-A', 1, 100000),
('10000000-0000-0000-0000-000000000001', 2, 'SKU-B', 3,  50000),
('10000000-0000-0000-0000-000000000002', 1, 'SKU-C', 2, 300000),
('10000000-0000-0000-0000-000000000003', 1, 'SKU-D', 1, 150000);
```

Số dòng trong SQL mẫu có thể thấp hơn bảng mục tiêu; implementation bổ sung đủ 5/8/12 dòng nhưng giữ dữ liệu deterministic.

## 7. Cách `tbls` đọc và mô tả database

### 7.1. Nguồn mô tả

`tbls` thu thập schema kỹ thuật qua DSN ClickHouse:

```text
clickhouse://<user>:<password>@<host>:9000/<database>
```

Mô tả có hai nguồn:

1. `COMMENT` trong DDL của table/column — ưu tiên cho sự thật kỹ thuật nằm gần database.
2. `comments:` trong `config/databases/commerce_demo/tbls.yml` — dùng khi không muốn hoặc không thể `ALTER TABLE`; giá trị tại đây có thể override comment đọc từ schema.

`tbls` không tự biết business purpose, grain, owner hay rule lọc đã được domain xác nhận. Những phần đó thuộc `catalog/*/review/**`, không viết trực tiếp vào tài liệu do `tbls` quản lý.

### 7.2. Cấu hình `config/databases/commerce_demo/tbls.yml`

```yaml
requiredVersion: ">= 1.94, < 2"
name: commerce_demo
desc: Demo schema cho luồng review metadata trên GitHub
dsn: ${TBLS_DSN}
docPath: catalog/commerce_demo/generated/raw

format:
  sort: true
  showOnlyFirstParagraph: true

er:
  format: mermaid
  comment: true

relations:
  - table: orders
    columns: [customer_id]
    parentTable: customers
    parentColumns: [customer_id]
    def: orders.customer_id -> customers.customer_id
  - table: order_items
    columns: [order_id]
    parentTable: orders
    parentColumns: [order_id]
    def: order_items.order_id -> orders.order_id

lint:
  requireTableComment:
    enabled: true
  requireColumnComment:
    enabled: true
```

Quan hệ được khai báo tường minh vì ClickHouse không cung cấp foreign key constraint như OLTP database.

### 7.3. Các lệnh local

```bash
# 1. Dựng database và chạy init scripts
docker compose up -d clickhouse

# 2. Kiểm tra dữ liệu
docker compose exec clickhouse clickhouse-client \
  --user demo --password demo_password \
  --query "SELECT table, total_rows FROM system.tables WHERE database = 'commerce_demo'"

# 3. Sinh lại hoàn toàn raw docs và schema.json
docker compose --profile tools run --rm tbls doc --rm-dist

# 4. Kiểm tra rule comment
docker compose --profile tools run --rm tbls lint

# 5. Kiểm tra database hiện tại có lệch tài liệu đã commit hay không
docker compose --profile tools run --rm tbls diff
```

Kết quả mong đợi:

```text
catalog/commerce_demo/generated/raw/
├── README.md
├── schema.json
└── tables hoặc các file Markdown theo từng table
```

Tên file chi tiết phụ thuộc phiên bản/template `tbls`; pipeline không hard-code đường dẫn table nếu có thể đọc từ `schema.json`.

## 8. Định dạng metadata review

Mỗi table có một YAML file, ví dụ `catalog/commerce_demo/review/orders.yml`:

```yaml
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_scope: clickhouse
database: commerce_demo
table: orders
owner: commerce-analytics
reviewer: unassigned
document_status: needs_review
schema_hash: <sha256-cua-table-schema>
business:
  display_name: Orders
  description: One technical row per order represented in the ClickHouse demo dataset.
  grain: One row per order_id.
  purpose: [Support order lifecycle analysis.]
  appropriate_use: [Analyze order counts after status semantics are approved.]
  inappropriate_use: [Calculate recognized revenue before business rules are confirmed.]
  aliases: [order fact]
  freshness: Unknown — needs confirmation
  caveats: []
  evidence:
    - kind: clickhouse_comment
      reference: catalog/commerce_demo/generated/raw/schema.json#tables.orders.comment
      status: proposed
      note: Requires reviewer confirmation.
columns:
  total_amount:
    business_name: Order total amount
    description: Order total recorded after discounts.
    semantic_type: monetary_amount
    unit: VND
    nullable_meaning: not_applicable
    sensitivity: internal
    allowed_values: {}
    caveats: []
    evidence:
      - kind: clickhouse_comment
        reference: catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.total_amount
        status: proposed
        note: Requires reviewer confirmation.
relationships: []
business_rules: []
data_quality: []
security: []
```

Quy tắc nội dung:

- AI phải gắn nhãn `AI inference — chưa xác minh` cho suy luận không có evidence.
- `document_status: approved` chỉ do reviewer thay đổi trong `catalog/*/review/**`.
- Generator được phép chuẩn hóa câu chữ nhưng không được tự nâng trạng thái lên `approved`.
- File published phải giữ reference về source review, schema hash, prompt version và commit SHA.

### 8.1. Guideline 1 — Hướng dẫn reviewer bổ sung metadata

File: `guidelines/reviewer_metadata_guideline.md`
Đối tượng sử dụng: Domain Reviewer, Data Steward và Data Analyst.
Mục tiêu: giúp reviewer biết chính xác cần bổ sung thông tin gì, viết ở đâu và mức độ evidence nào đủ để approve.

Guideline này phải được liên kết trong PR template và ở đầu mỗi draft review. Reviewer không cần sửa file do `tbls` sinh; toàn bộ thông tin nghiệp vụ được bổ sung trong `catalog/*/review/**`.

Nội dung bắt buộc của Guideline 1:

| Nhóm thông tin | Câu hỏi reviewer phải trả lời | Bắt buộc |
|---|---|---|
| Purpose | Bảng phục vụ quy trình/quyết định nghiệp vụ nào? | Có |
| Grain | Chính xác một dòng đại diện cho thực thể/sự kiện gì? Khóa logic là gì? | Có |
| Owner và reviewer | Ai chịu trách nhiệm nội dung và ai đã xác nhận? | Có |
| Cách sử dụng | Khi nào nên dùng bảng này? | Có |
| Không nên sử dụng | Trường hợp nào bảng có thể cho kết quả sai hoặc thiếu? | Có |
| Key columns | Ý nghĩa nghiệp vụ của identifier, measure, dimension, status và timestamp quan trọng | Có |
| Business rules | Filter, inclusion/exclusion, deduplication, status mapping và công thức | Có nếu tồn tại |
| Quan hệ/join | Join với bảng nào, bằng cột nào, cardinality và nguy cơ duplicate | Có nếu tồn tại |
| Time semantics | Event time hay processing time, timezone, độ trễ và cột thời gian chuẩn | Có nếu có timestamp |
| Unit | Currency, timezone, phần trăm, số lượng hoặc đơn vị đo | Có nếu có measure |
| Value semantics | Ý nghĩa từng status/code quan trọng và giá trị không hợp lệ | Có nếu dùng code/status |
| Freshness | Tần suất cập nhật và độ trễ dự kiến | Khuyến nghị |
| Data quality | Known issue, null bất thường, duplicate, late-arriving data | Có nếu đã biết |
| Security | PII/sensitive fields và hạn chế sử dụng | Có nếu áp dụng |
| Business aliases | Tên gọi khác mà người dùng thường tìm kiếm | Khuyến nghị |
| Example questions | Các câu hỏi nghiệp vụ bảng có thể hoặc không thể trả lời | Khuyến nghị |
| Evidence | Ticket, query, dashboard, policy hoặc commit xác nhận claim | Có với business rule |

Quy tắc viết cho reviewer:

- Viết câu khẳng định ngắn, cụ thể; dùng đúng tên table/column trong dấu backtick.
- Không dùng câu mơ hồ như “dữ liệu chuẩn”, “thường đúng” hoặc “dùng như bình thường” nếu không giải thích điều kiện.
- Tách rõ **fact đã xác nhận**, **giả định**, và **điểm chưa biết**.
- Business rule phải có evidence hoặc ghi `Chưa được xác nhận`; không xóa cảnh báo chỉ để pipeline pass.
- Nếu một cột kỹ thuật có tên khó hiểu, bổ sung business name và alias mà người dùng có thể tìm kiếm.
- Với join, phải nêu join condition, cardinality dự kiến và liệu join có làm tăng số dòng hay không.
- Với measure, phải nêu unit, aggregation hợp lệ và điều kiện lọc cần thiết.
- Không sao chép credential, row data nhạy cảm hoặc thông tin cá nhân thật vào metadata.

Checklist trước khi reviewer đổi trạng thái sang `approved`:

```text
[ ] Purpose và grain đã rõ, không mâu thuẫn schema
[ ] Owner và reviewer đã được gán
[ ] Các cột chính có business meaning
[ ] Filter/status/time/unit quan trọng đã được mô tả
[ ] Join condition và nguy cơ duplicate đã được ghi nhận
[ ] Caveat, PII và known data quality issue đã được nêu
[ ] Business rule có evidence hoặc được đánh dấu chưa xác nhận
[ ] Tên table/column đều tồn tại trong schema.json
```

### 8.2. Guideline 2 — Rule chuyển đổi thành tài liệu tối ưu cho retrieval

File: `guidelines/llm_transformation_guideline.md`
Đối tượng sử dụng: LLM generator, AI/Data Agent Engineer và validator.
Mục tiêu: hợp nhất schema do `tbls` cung cấp với thông tin reviewer xác nhận thành tài liệu nhất quán, tự đủ nghĩa và có cấu trúc ổn định để chunking/indexing.

#### 8.2.1. Thứ tự ưu tiên nguồn

LLM phải áp dụng thứ tự sau khi các nguồn mâu thuẫn:

1. `schema.json` là sự thật kỹ thuật về table, column, data type và relation đã cấu hình.
2. `catalog/*/review/**` là sự thật nghiệp vụ nếu claim đã có reviewer/evidence.
3. Markdown do `tbls` sinh chỉ là bản trình bày hỗ trợ; không được dùng để override `schema.json`.
4. Prompt/guideline quy định cách diễn đạt, không được tạo thêm fact.
5. Suy luận của LLM chỉ được giữ khi có ích và phải gắn `AI inference — chưa xác minh`; tài liệu `approved` không được chứa inference chưa xác minh.

Nếu schema và review mâu thuẫn, generator phải dừng với lỗi có thể hành động, không tự chọn một phía. Ví dụ: review mô tả cột đã bị xóa thì yêu cầu reviewer cập nhật metadata.

#### 8.2.2. Contract đầu ra chuẩn

Mỗi file trong `catalog/*/generated/published/**` phải có front matter tối thiểu:

```yaml
document_id: commerce_demo.orders
database: commerce_demo
table: orders
qualified_name: commerce_demo.orders
business_aliases: [đơn hàng, giao dịch bán hàng]
owner: commerce-analytics
reviewer: <github-user-or-team>
document_status: approved
schema_hash: <sha256>
source_review_path: catalog/commerce_demo/review/orders.md
source_review_commit: <git-sha>
prompt_version: metadata-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
```

Các section theo đúng thứ tự:

1. `# <qualified_name> — <business name>`.
2. `## Tóm tắt` — 2–4 câu tự đủ nghĩa, nêu purpose và grain.
3. `## Khi nào nên dùng`.
4. `## Khi nào không nên dùng`.
5. `## Grain và khóa`.
6. `## Business glossary và cột quan trọng`.
7. `## Business rules và cách tính`.
8. `## Quan hệ và hướng dẫn join`.
9. `## Time, freshness và unit semantics`.
10. `## Data quality, security và caveats`.
11. `## Câu hỏi mẫu`.
12. `## Traceability` — nguồn review, schema hash, guideline và prompt version.

Section không áp dụng vẫn phải được xử lý nhất quán: ghi `Không áp dụng` kèm lý do, hoặc được validator cho phép bỏ qua theo rule định trước. Không để heading rỗng.

#### 8.2.3. Rule diễn đạt cho LLM

- Mỗi claim phải truy được về `schema.json`, review metadata hoặc evidence reference.
- Giữ nguyên identifier kỹ thuật và đặt trong backtick; không dịch tên table/column.
- Mở rộng acronym ở lần xuất hiện đầu tiên và lưu alias phổ biến để tăng khả năng retrieval.
- Không dùng đại từ thiếu chủ thể như “nó”, “bảng này” ở đầu một chunk; lặp lại `qualified_name` khi cần để chunk tự đủ nghĩa.
- Không trộn fact của nhiều table trong cùng đoạn, trừ section relation/join có nêu rõ cả hai phía.
- Không suy ra business rule từ tên column hoặc vài dòng sample data.
- Không biến caveat thành rule chắc chắn và không xóa uncertainty do reviewer ghi nhận.
- Không lặp một fact ở nhiều section với cách diễn đạt có thể mâu thuẫn.
- Với measure, luôn giữ unit, aggregation, filter và time context trong cùng semantic block.
- Với join, luôn giữ source table/column, target table/column, cardinality, join type khuyến nghị, duplicate risk và evidence trong cùng semantic block.

### 8.3. Contract chunking và retrieval

MVP dùng hierarchical chunks: một document summary làm parent và các semantic chunk làm children. Không cắt mù theo số ký tự trước khi nhận diện heading/semantic block.

Các loại chunk chuẩn:

| `chunk_type` | Nội dung | ID ổn định ví dụ |
|---|---|---|
| `overview` | Purpose, grain, when-to-use | `commerce_demo.orders::overview` |
| `columns` | Một nhóm cột liên quan hoặc một cột phức tạp | `commerce_demo.orders::columns::amount` |
| `business_rules` | Rule, filter, calculation và evidence | `commerce_demo.orders::rules::revenue` |
| `relationships` | Join đầy đủ giữa hai table | `commerce_demo.orders::relations::customers` |
| `time_semantics` | Timestamp, timezone, freshness | `commerce_demo.orders::time` |
| `caveats` | Quality, security, exclusion | `commerce_demo.orders::caveats` |
| `examples` | Câu hỏi có thể/không thể trả lời | `commerce_demo.orders::examples` |

Rule chunking mặc định:

- Ưu tiên ranh giới `H2/H3`, bullet group và semantic block; không tách một row/table Markdown hoặc một join rule làm đôi.
- Target 300–600 tokens/chunk, hard limit 800 tokens; nếu section lớn hơn, chia theo cột/rule nhưng lặp context nhận diện cần thiết.
- Overlap 50–100 tokens chỉ dùng khi một semantic block buộc phải chia; không dùng overlap để bù cho output thiếu cấu trúc.
- Mỗi chunk phải trả lời được: đang nói về table nào, chủ đề gì, fact đã xác nhận hay chưa, và nguồn/version nào.
- Metadata gắn với mọi chunk: `document_id`, `chunk_id`, `chunk_type`, `database`, `table`, `qualified_name`, `business_aliases`, `owner`, `document_status`, `schema_hash`, `source_review_commit`, `transformation_guideline_version`.
- Chỉ index child chunks thuộc document `approved`; parent summary được lưu để trả về context hoặc reranking.
- Khi document đổi schema hash hoặc review commit, xóa toàn bộ chunk version cũ trước khi upsert version mới.

Các ngưỡng token là baseline cấu hình của MVP, không hard-code trong prompt; nhóm triển khai phải điều chỉnh bằng kết quả golden retrieval test và giới hạn của embedding/reranking model thực tế.

Ví dụ một relation chunk tự đủ nghĩa:

```text
commerce_demo.orders liên kết logic với commerce_demo.customers bằng
orders.customer_id = customers.customer_id. Cardinality dự kiến là nhiều orders
thuộc một customer. Join này không được ClickHouse enforce. Khi kiểm tra doanh thu,
phải xác nhận customers.customer_id không duplicate để tránh tăng số dòng.
Evidence: reviewer commit abc123.
```

### 8.4. Đánh giá chất lượng retrieval

Tạo `tests/fixtures/golden_questions.yml` gồm ít nhất 10 câu hỏi, bao phủ purpose, grain, column meaning, filter, join, time, unit và caveat. Ví dụ:

```yaml
- question: Để tính doanh thu hoàn tất từ commerce_demo.orders cần loại trạng thái nào?
  expected_document_id: commerce_demo.orders
  expected_chunk_type: business_rules
  required_facts: ["order_status = 'cancelled'"]
```

Tiêu chí MVP:

- Đúng document nằm trong top 3 cho ít nhất 90% golden questions.
- Chunk trả về chứa đủ `required_facts`, không chỉ đúng table name.
- Không có kết quả từ document chưa `approved`.
- Câu hỏi về join phải trả về chunk có đủ hai table, join condition và duplicate risk.

## 9. Luồng tương tác với GitHub

### 9.1. Luồng schema sync

1. Data Engineer chạy workflow **Schema Sync** bằng `workflow_dispatch` hoặc theo schedule.
2. Trong demo, job dựng ClickHouse fixture bằng Docker Compose. Ở production, job dùng self-hosted runner có quyền đọc database.
3. Job chạy `tbls doc --rm-dist`, `tbls lint` và `create_initial_draft.py`.
4. Bot tạo branch `schema-sync/commerce-demo-YYYYMMDD-HHMM`.
5. Bot commit raw schema và các draft review mới.
6. Bot mở draft PR: `chore(schema): sync commerce_demo schema YYYY-MM-DD`.

PR không chứa credential hoặc database data; chỉ chứa cấu trúc schema, comment và metadata draft.

### 9.2. Luồng reviewer feedback

1. Reviewer đọc `guidelines/reviewer_metadata_guideline.md` từ link trong PR template.
2. Reviewer mở `catalog/commerce_demo/review/orders.yml`.
3. Reviewer bổ sung purpose, grain, owner, business rule, alias, join/time/unit semantics, caveat và evidence phù hợp.
4. Reviewer chạy checklist của Guideline 1 rồi commit: `docs(review): confirm orders business rules`.
5. Commit mới trên source branch phát sinh sự kiện `pull_request.synchronize` và chạy workflow **Metadata PR**.
6. Workflow phát hiện file review/schema/guideline thay đổi và validate input.
7. LLM đọc Guideline 2 để chuyển schema + review metadata thành published document theo retrieval contract.
8. Pipeline chạy content validation, chunking dry-run và golden retrieval smoke test.
9. Bot chỉ commit `catalog/*/generated/published/**` với message `docs(ai): regenerate published metadata`.
10. Commit bot tạo một lượt Pull Request workflow mới khi dùng GitHub App/PAT phù hợp.
11. Lượt CI mới phát hiện chỉ `catalog/*/generated/published/**` thay đổi nên không generate lại; nó chỉ validate published output và hoàn tất required check.
12. Reviewer kiểm tra diff published và approve.

Nếu output chưa đúng, reviewer quay lại bước 1. Reviewer không sửa published file.

### 9.3. Luồng sau merge

1. PR merge vào `main`.
2. Workflow **Index Knowledge** đọc diff trong `catalog/*/generated/published/**`.
3. Chỉ file có `document_status: approved` được xử lý.
4. MVP sinh `index-manifest.json`, kiểm tra A/M/D/R và upload làm workflow artifact.
5. UAT phase có thể thay adapter manifest bằng Qdrant/pgvector mà không đổi source format.

## 10. Thiết kế GitHub Actions

### 10.1. Quyết định workflow

Workflow `metadata-pr.yml` chạy cho mọi PR vào `main` để required check luôn có trạng thái rõ ràng. Một bước đầu xác định changed paths; các bước validate/generate dùng điều kiện nội bộ thay vì filter toàn workflow.

- Quality jobs chạy trong mọi PR workflow.
- Generate step chỉ chạy khi `catalog/*/generated/raw/**`, `catalog/*/review/**`, `prompts/**`, `guidelines/**` hoặc contract config thay đổi.
- Bot-only commit chỉ thay đổi `catalog/*/generated/published/**`; lượt tiếp theo chỉ validate, không generate.
- Protected `main` yêu cầu `Metadata PR / pr-gate` pass trước khi merge.
- Generation và index dùng `concurrency` group để tránh hai run cùng ghi một loại output.

Bot push dùng GitHub App installation token; MVP có thể dùng fine-grained PAT giới hạn đúng repository và có expiry. Không dùng `GITHUB_TOKEN` khi cần bot commit kích hoạt workflow tiếp theo.

### 10.2. `.github/workflows/schema-sync.yml` — skeleton

```yaml
name: Schema Sync

on:
  workflow_dispatch:
  schedule:
    - cron: "0 2 * * 1"

concurrency:
  group: schema-sync-commerce-demo
  cancel-in-progress: false

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.METADATA_BOT_TOKEN }}
      - run: docker compose up -d clickhouse
      - run: ./scripts/wait_for_clickhouse.sh
      - run: docker compose --profile tools run --rm tbls doc --rm-dist
      - run: docker compose --profile tools run --rm tbls lint
      - run: metadata draft
      - run: metadata validate-review catalog/&lt;database&gt;/review
      - run: ./scripts/create_schema_sync_pr.sh
```

Script tạo PR phải:

- Kết thúc success mà không tạo branch/PR nếu không có diff.
- Tạo branch `schema-sync/commerce-demo-YYYYMMDD-HHMM` nếu có diff.
- Push bằng `METADATA_BOT_TOKEN` và mở draft PR.
- Chỉ commit `catalog/*/generated/raw/**` và `catalog/*/review/**`.

### 10.3. `.github/workflows/metadata-pr.yml` — behavior bắt buộc

Pseudo workflow:

```yaml
name: Metadata PR

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  pr-gate:
    runs-on: ubuntu-latest
    steps:
      - checkout đúng PR head SHA với fetch-depth: 0
      - xác định changed paths giữa base và head
      - nếu review/schema/guideline/prompt thay đổi:
          validate review
          publish metadata
          validate published
          chunk dry-run
          commit published bằng bot token nếu có diff
      - nếu chỉ published thay đổi:
          xác nhận sender là bot được allowlist
          validate published và chunks
      - ghi Job Summary nêu rõ bước chạy/skip
```

Guard chống vòng lặp:

```text
Input trigger generate:  catalog/*/generated/raw/**, catalog/*/review/**, prompts/**
                         guidelines/**
Bot output allowlist:    catalog/*/generated/published/**
Bot-only commit lần hai: chỉ validate, không generate
Human sửa published:     fail; reviewer phải sửa catalog/*/review/**
```

### 10.4. `.github/workflows/index.yml` — skeleton

```yaml
name: Index Knowledge

on:
  push:
    branches: [main]
    paths:
      - "catalog/*/generated/published/**"

concurrency:
  group: metadata-knowledge-index
  cancel-in-progress: false

jobs:
  index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - run: metadata index \
          --before "${{ github.event.before }}" \
          --after "${{ github.sha }}" \
          --mode manifest \
          --output build/index-manifest.json
      - run: metadata retrieval-smoke-test build/index-manifest.json
      - uses: actions/upload-artifact@v4
        with:
          name: knowledge-index-${{ github.sha }}
          path: build/index-manifest.json
          retention-days: 7
```

Mapping thay đổi:

| Git diff | Hành động index |
|---|---|
| `A` | Thêm document mới |
| `M` | Xóa chunks phiên bản cũ, upsert phiên bản mới |
| `D` | Xóa document |
| `R` | Xóa document ID cũ, thêm document ID mới |

## 11. Generator AI và chế độ test

`regenerate_docs.py` phải có interface tách provider:

```text
--mode mock     Sinh output deterministic, không cần secret
--mode live     Gọi LLM provider được cấu hình bằng repository variable/secret
```

Khuyến nghị:

- CI mặc định chạy `mock` để test ổn định, nhanh và không tốn chi phí.
- Một manual workflow/UAT chạy `live` để kiểm chứng prompt thật.
- Prompt và model identifier phải được version-control hoặc ghi vào metadata output.
- Log không ghi raw secret, email giả vẫn nên được redaction trong prompt nếu không cần thiết.
- Live generator chỉ nhận schema và metadata, không nhận row data từ ClickHouse.

Input bắt buộc:

- `catalog/commerce_demo/generated/raw/schema.json`.
- File tương ứng trong `catalog/commerce_demo/review/`.
- `guidelines/llm_transformation_guideline.md`.
- `prompts/regenerate_from_feedback.md`.
- Commit SHA, prompt version và version của cả hai guideline.

Output bắt buộc:

- Chỉ file trong `catalog/commerce_demo/generated/published/`.
- Nội dung không tham chiếu column/table không tồn tại.
- Mọi claim không có evidence phải được gắn trạng thái chưa xác minh.
- Cấu trúc heading và front matter tuân theo retrieval output contract.
- Có thể chunk deterministic thành các `chunk_type` chuẩn mà không làm mất join, rule, unit hoặc time context.

## 12. Validation trước merge

Pipeline fail nếu có một trong các lỗi:

- Thiếu `database`, `table`, `owner`, `reviewer`, `document_status` hoặc `schema_hash`.
- Thiếu `review_guideline_version` hoặc `transformation_guideline_version`.
- Review đã `approved` nhưng tham chiếu Guideline 1 cũ, hoặc published document không khớp version Guideline 2 hiện hành.
- Thiếu Purpose hoặc Grain.
- Table không tồn tại trong `schema.json`.
- Metadata mô tả column không tồn tại.
- Relation tham chiếu table/column không tồn tại.
- `schema_hash` không còn khớp schema hiện tại.
- Có `TODO`, placeholder trống hoặc `document_status: draft` trong file sắp publish.
- `approved` nhưng thiếu reviewer/evidence.
- Published document không trace được về review source.
- Bot sửa file ngoài `catalog/*/generated/published/**` trong commit generate.
- Phát hiện token, password, private key hoặc DSN có credential trong tài liệu.
- Markdown/front matter không parse được.
- Published document thiếu section bắt buộc của Guideline 2 hoặc có heading rỗng.
- Chunk vượt hard limit mà không có semantic boundary hợp lệ.
- Relation chunk thiếu một phía của join, join condition, cardinality hoặc duplicate risk.
- Measure chunk làm rơi unit, aggregation, filter hoặc time context đã có trong review source.
- Golden retrieval smoke test không đạt ngưỡng đã định.

Trạng thái hợp lệ:

```text
draft → needs_review → approved → deprecated
```

Chỉ `approved` được index. `deprecated` gây xóa document khỏi active index.

## 13. GitHub repository settings

### 13.1. Branch protection cho `main`

Bật:

- Require a pull request before merging.
- Require 1 approval.
- Require review from Code Owners.
- Dismiss stale approvals when new commits are pushed.
- Require status check `Metadata PR / pr-gate`.
- Require conversation resolution.
- Block force push và deletion.
- Không cho bypass, trừ break-glass role được audit.

Việc dismiss stale approval là có chủ đích: sau khi bot đổi published document, reviewer phải approve phiên bản mới nhất.

### 13.2. CODEOWNERS mẫu

```text
/catalog/commerce_demo/review/       @your-org/commerce-domain @your-org/data-team
/catalog/commerce_demo/generated/published/  @your-org/commerce-domain @your-org/data-team
/guidelines/reviewer_metadata_guideline.md       @your-org/data-team @your-org/commerce-domain
/guidelines/llm_transformation_guideline.md      @your-org/ai-team @your-org/data-team
/.github/                             @your-org/platform-team
/prompts/                             @your-org/ai-team
/scripts/                             @your-org/ai-team @your-org/data-team
/config/databases/*/tbls.yml         @your-org/data-team
```

Thay team bằng GitHub users/teams thực tế và bảo đảm target branch được protect để Code Owner approval có hiệu lực.

### 13.3. Bot credential

Ưu tiên GitHub App với quyền `Contents: write`, `Pull requests: write`; workflow mint installation token ngắn hạn. MVP có thể dùng fine-grained PAT giới hạn đúng repository, có expiration và owner chịu trách nhiệm rotation.

Repository secrets đề xuất:

```text
METADATA_BOT_TOKEN          # GitHub App token hoặc fine-grained PAT
LLM_API_KEY                 # chỉ khi chạy live mode
```

Không dùng `pull_request_target` để checkout và chạy code từ PR không tin cậy. MVP chỉ cho bot push trên source branch cùng repository và không cấp secret cho fork/untrusted workflow.

## 14. User stories và tiêu chí nghiệm thu

### US-01 — Dựng database demo

**Là** Data Engineer, **tôi muốn** dựng ClickHouse bằng một lệnh **để** mọi người có cùng fixture.

Acceptance criteria:

- `docker compose up -d clickhouse` đạt healthy trong tối đa 90 giây.
- Có đúng ba table ban đầu.
- Seed có ít nhất 5 customers, 8 orders và 12 order_items.
- Chạy lại từ volume sạch cho kết quả giống nhau.

### US-02 — Sinh raw schema bằng `tbls`

- `tbls doc --rm-dist` thành công.
- Có `README.md`, table docs, ER diagram và `schema.json`.
- Table/column comments xuất hiện trong Markdown.
- ER diagram thể hiện hai quan hệ logic.
- `tbls lint` pass.

### US-03 — Tạo draft review

- Mỗi table mới có đúng một review file.
- Draft có front matter, Purpose, Grain, Columns, Rules, Relations và Caveats.
- Draft có link tới Guideline 1 và version của cả hai guideline.
- Generator không ghi đè nội dung reviewer của table đã tồn tại; chỉ cập nhật phần máy quản lý nếu thiết kế có marker rõ ràng.

### US-03A — Reviewer hoàn thiện metadata theo Guideline 1

- Reviewer có checklist rõ cho purpose, grain, key columns, rule, join, time, unit, quality, security và evidence.
- Validator phân biệt field bắt buộc, field có điều kiện và field khuyến nghị.
- Reviewer không thể đặt `approved` nếu thiếu thông tin bắt buộc theo loại dữ liệu thực tế của table.

### US-03B — LLM chuyển đổi theo Guideline 2

- Published document có front matter và section đúng output contract.
- Mỗi claim trace được về schema, review hoặc evidence.
- Chunking dry-run tạo ID ổn định và các `chunk_type` chuẩn.
- Join, business rule, unit và time context không bị tách mất nghĩa.
- Thay đổi version Guideline 2 kích hoạt regenerate các published documents bị ảnh hưởng.

### US-04 — Bắt commit feedback

- Commit sửa `catalog/*/review/**` kích hoạt Metadata PR workflow.
- Bot tạo tối đa một commit published cho mỗi human commit có thay đổi hợp lệ.
- Commit bot không tạo thêm bot commit thứ hai.
- Latest PR SHA có required check pass.

### US-05 — Chặn metadata sai

- Thêm column giả vào review làm CI fail với thông báo chỉ rõ file/column.
- Đặt status `approved` nhưng reviewer trống làm CI fail.
- Bot hoặc user sửa file published không khớp review làm CI fail.

### US-06 — Index sau merge

- PR chưa merge không chạy index.
- Merge file `approved` tạo artifact index có commit SHA và schema hash.
- File `needs_review` không xuất hiện trong active manifest.
- Rename/delete được ánh xạ đúng thành hành động index.
- Mỗi chunk trong manifest có guideline version, source review commit và stable chunk ID.
- Golden retrieval test đạt ngưỡng top-3 và required-facts đã định.

## 15. Kịch bản demo end-to-end

### Kịch bản A — Happy path

1. Clone repo và chạy `make db-up`.
2. Chạy `make schema-doc`; xác nhận raw docs.
3. Chạy `make draft`; xác nhận ba review file.
4. Push branch và mở PR.
5. Sửa `orders.yml`: owner, reviewer, rule doanh thu; đổi status thành `approved`.
6. Đối chiếu checklist Guideline 1 và commit/push.
7. Quan sát bot commit published theo cấu trúc Guideline 2.
8. Kiểm tra chunking dry-run giữ đủ rule doanh thu, unit và source evidence.
9. Xác nhận lượt CI sau không generate lần nữa.
10. Reviewer approve và merge.
11. Mở index artifact, xác nhận `orders` được index; table chưa approved bị bỏ qua.
12. Chạy golden questions và xác nhận đúng chunk nằm trong top 3.

### Kịch bản B — Schema change

1. Thêm migration tạo `order_events` và cột `orders.channel`.
2. Chạy Schema Sync pipeline.
3. PR phải hiển thị raw schema diff và draft cho table mới.
4. Metadata cũ của `orders` được giữ; `schema_hash` đổi và trạng thái quay về `needs_review`.
5. CI fail cho đến khi reviewer xác nhận cột mới.

### Kịch bản C — Guardrail

1. Thêm `orders.non_existing_column` vào review.
2. CI fail trước khi gọi live LLM.
3. Sửa lại column, CI pass và bot generate đúng một lần.

## 16. Kế hoạch triển khai

### Ngày 1 — Local fixture

- Docker Compose, init SQL, seed deterministic.
- `config/databases/commerce_demo/tbls.yml`, Makefile và README local commands.
- Verify docs, comments, relations và schema JSON.

### Ngày 2 — Metadata scripts

- Viết Guideline 1 cho reviewer và Guideline 2 cho LLM transformation.
- Draft generator mock.
- Regenerator mock/live adapter.
- Schema hash, guideline version và validator.
- Unit tests cho front matter, table/column reference và status.

### Ngày 3 — GitHub workflow

- Schema Sync pipeline.
- Metadata PR workflow và bot push.
- CODEOWNERS, PR template và branch protection checklist.

### Ngày 4 — Index và failure tests

- Manifest index adapter và smoke test.
- Semantic chunker, stable chunk ID và `golden_questions.yml`.
- Test A/M/D/R.
- Test bot loop, stale approval và invalid metadata.

### Ngày 5 — UAT và tài liệu

- Chạy happy path với live LLM một lần nếu có provider credential.
- Ghi lại video/log hoặc screenshot PR.
- Chốt hạn chế và backlog phase 2.

## 17. Rủi ro và biện pháp giảm thiểu

| Rủi ro | Tác động | Giảm thiểu |
|---|---|---|
| Bot commit tạo loop | Tốn CI/LLM, nhiều commit | Input/output path tách biệt; lượt bot chỉ validate |
| Required check bị pending | Không merge được | Workflow chạy mọi PR; điều kiện hóa step thay vì filter workflow |
| Bot token quá rộng | Rủi ro supply-chain | GitHub App hoặc fine-grained PAT, repo-scoped, expiry |
| PR fork lấy secret | Lộ credential | MVP cấm fork; không dùng `pull_request_target` để chạy code PR |
| AI bịa business rule | Metadata sai | Evidence field, unverified label, human approval, validator |
| Guideline thay đổi nhưng document không regenerate | Published docs dùng rule cũ | Lưu guideline version trong front matter; guideline path là input trigger |
| Chunk làm mất join/unit/time context | Retrieval đúng table nhưng trả lời sai | Semantic chunks, required metadata và golden required-facts test |
| Schema sync đọc production tùy ý | Rò rỉ/kết nối ngoài ý muốn | Chỉ manual/schedule, read-only account, self-hosted runner |
| Reviewer sửa published | Mất source of truth | CODEOWNERS, validator và allowlist bot output |
| Schema change làm metadata cũ | Index sai | Schema hash; tự hạ trạng thái về `needs_review` |

## 18. Chỉ số thành công

- 100% table demo có raw docs và `schema.json` entry.
- 100% table/column demo có comment, `tbls lint` pass.
- Một human feedback commit tạo 0 hoặc 1 bot commit, không bao giờ lớn hơn 1.
- 100% published docs trace được tới schema hash, review path và commit SHA.
- 100% published docs/chunks ghi đúng version của Guideline 1 và Guideline 2.
- 0 tài liệu chưa approved xuất hiện trong active index manifest.
- Ít nhất 90% golden questions lấy đúng document trong top 3 và chunk chứa đủ required facts.
- Happy path hoàn tất trong dưới 10 phút CI, không tính thời gian human review.

## 19. Definition of Done

MVP hoàn tất khi:

- Sáu user stories đều pass.
- Ba kịch bản end-to-end được chạy và lưu bằng chứng trong PR/UAT note.
- `main` được bảo vệ và required check hoạt động trên latest SHA.
- Secret không xuất hiện trong git history hoặc job log.
- README cho người mới có thể chạy local từ máy sạch.
- Guideline 1 đủ rõ để reviewer hoàn thiện metadata mà không cần đọc prompt của LLM.
- Guideline 2 tạo published document có thể chunk deterministic và vượt golden retrieval test.
- Có ít nhất một PR đi qua đủ chuỗi: schema sync → reviewer commit → bot commit → approve → merge → index artifact.

## 20. Backlog sau MVP

- Thay manifest adapter bằng Qdrant/pgvector và staging-to-active promotion.
- Hỗ trợ lệnh PR comment `/ai-regenerate` sau khi có rule phân loại comment.
- GitHub Check annotations trỏ thẳng tới dòng metadata lỗi.
- Nhiều database/schema và routing theo domain owner.
- Dashboard theo dõi coverage, freshness, approval SLA và index status.
- GitHub App riêng thay PAT.
- Snapshot/rollback collection và retrieval regression tests.

## 21. Tài liệu tham khảo kỹ thuật

- [`tbls` README](https://github.com/k1LoW/tbls): ClickHouse DSN, `doc`, `diff`, `lint`, `schema.json`, comments và virtual relations.
- [ClickHouse official Docker image](https://hub.docker.com/_/clickhouse): init scripts trong `/docker-entrypoint-initdb.d` và cấu hình user/password.
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): event filters và permissions.
- [Triggering a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow): hành vi của event được tạo bằng `GITHUB_TOKEN`.
- [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches): required review, stale approval và required checks.
- [About CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners): ownership và required Code Owner review.
