# Quy trình onboarding database từ ClickHouse đến Markdown approved

Tài liệu này là runbook end-to-end cho một database mới. Ví dụ sử dụng `commerce_demo`, nhưng cùng
một quy trình được áp dụng cho `urgift`, `urcard`, hoặc database ClickHouse khác sau này.

Mục tiêu cuối cùng:

```text
ClickHouse
  -> tbls raw schema
  -> reviewer YAML template
  -> reviewer bổ sung business metadata trên GitHub
  -> CI/bot gọi LLM và sinh candidate + Markdown
  -> reviewer duyệt đúng candidate
  -> merge và index tài liệu approved
```

## 1. Ranh giới trách nhiệm

| Khu vực | Chủ sở hữu | Có được sửa trực tiếp không? |
|---|---|---|
| `config/databases/<database>/database.yml` | Developer | Có |
| `config/databases/<database>/tbls.yml` | Developer | Có |
| `catalog/<database>/generated/raw/**` | tbls | Không |
| `catalog/<database>/review/*.yml` | Reviewer | Có |
| `catalog/<database>/generated/structured/**` | Metadata bot | Không |
| `catalog/<database>/generated/published/**` | Metadata bot | Không |
| `build/**` | Local/CI tạm thời | Không commit |

Quy tắc quan trọng:

- Developer chuẩn bị cấu hình, raw schema và YAML template ban đầu.
- Reviewer chỉ sửa YAML trên GitHub, không chạy Docker, Make hoặc LLM.
- CI/bot validate, gọi LLM và commit output generated.
- Không copy dữ liệu từ `tests/fixtures` sang `catalog`; fixture chỉ phục vụ automated tests.
- Không commit `.env`, API key, DSN chứa password hoặc dữ liệu row từ production.

## 2. Ý nghĩa của `enabled`

```yaml
enabled: false
```

Database đang trong giai đoạn chuẩn bị. Developer vẫn có thể chạy `schema-check`, `review-draft` và
`review-validate`, nhưng CI không tự generate candidate, published Markdown hoặc index database đó.

```yaml
enabled: true
```

Database tham gia Metadata PR automation. Từ commit này, thay đổi raw/config/reviewer trong PR có thể
kích hoạt LLM và metadata bot.

Không bật `enabled: true` trước khi raw schema và reviewer YAML template đã tồn tại và validate được.

## 3. Điều kiện trước khi bắt đầu

Developer cần có:

1. Đúng tên ClickHouse database, có phân biệt chữ hoa/chữ thường.
2. Danh sách table được phép đọc; không dùng wildcard với production.
3. ClickHouse account read-only và kết nối mạng phù hợp.
4. Quan hệ logic đã biết giữa các table, nếu ClickHouse không lưu foreign key.
5. Python environment và Docker hoạt động.

Với Commerce Demo, cài dependency nếu cần:

```bash
make install
```

## 4. Developer — bắt đầu từ clean `main`

### 4.1 Đồng bộ repository

```bash
git switch main
git pull --ff-only origin main
git status --short
```

Checkpoint:

- `git status --short` không in gì.
- Runtime `catalog/` chưa tồn tại.
- Không database nào đang enabled.

```bash
test ! -e catalog && echo "catalog chưa được tạo"
./scripts/metadata list-databases
```

Ở clean-slate, kết quả đúng là:

```text
catalog chưa được tạo
```

`list-databases` không in database nào.

### 4.2 Tạo branch onboarding

```bash
git switch -c onboarding/commerce-demo
```

Không chạy pipeline trực tiếp trên `main`.

## 5. Developer — cấu hình database và tbls

### 5.1 Database profile

Kiểm tra `config/databases/commerce_demo/database.yml`:

```yaml
enabled: false
key: commerce_demo
display_name: Commerce Demo
clickhouse_database: commerce_demo
description: Local deterministic ClickHouse fixture used by the metadata pipeline tests.
tables:
  - customers
  - order_items
  - orders
```

`key` là tên lowercase dùng trong repository. `clickhouse_database` là tên database thực tế.
`tables` là allowlist, không phải danh sách tbls tự tìm và tự điền.

### 5.2 tbls config

Kiểm tra `config/databases/commerce_demo/tbls.yml`:

```yaml
name: commerce_demo
dsn: ${TBLS_DSN}
docPath: ${TBLS_DOC_PATH}

include:
  - customers
  - order_items
  - orders
```

Developer tự viết file này. tbls chỉ đọc cấu hình; tbls không tự điền database, table allowlist hoặc
logical relationship vào `tbls.yml`.

Nếu có quan hệ logic:

```yaml
relations:
  - table: orders
    columns: [customer_id]
    parentTable: customers
    parentColumns: [customer_id]
    def: orders.customer_id -> customers.customer_id
```

Thiếu `relations` không ngăn tbls đọc table/column. Nó chỉ làm tài liệu thiếu các relationship mà
ClickHouse không cung cấp như foreign key metadata.

## 6. Developer — tạo raw schema bằng tbls

### 6.1 Khởi động Commerce Demo

Các lệnh này dành cho Docker fixture của dự án, không dùng nguyên trạng với production:

```bash
make db-reset
make db-up
make db-check
```

### 6.2 Extract và lint

```bash
make schema-check DATABASE=commerce_demo
```

Lệnh này thực hiện:

```text
wait ClickHouse
  -> tbls doc
  -> sinh raw Markdown + schema.json
  -> tbls lint table/column comment
  -> pytest schema integration
```

Checkpoint:

```bash
find catalog/commerce_demo/generated/raw -maxdepth 1 -type f -print | sort
```

Phải có tối thiểu:

```text
catalog/commerce_demo/generated/raw/README.md
catalog/commerce_demo/generated/raw/customers.md
catalog/commerce_demo/generated/raw/order_items.md
catalog/commerce_demo/generated/raw/orders.md
catalog/commerce_demo/generated/raw/schema.json
```

`schema-check` chỉ sinh raw output. Nó không sinh reviewer YAML và không gọi LLM.

## 7. Developer — sinh reviewer YAML template

Đây là bước bắt buộc sau `schema-check`:

```bash
make review-draft DATABASE=commerce_demo
```

Checkpoint:

```bash
find catalog/commerce_demo/review -maxdepth 1 -type f -print | sort
```

Phải có:

```text
catalog/commerce_demo/review/customers.yml
catalog/commerce_demo/review/order_items.yml
catalog/commerce_demo/review/orders.yml
```

Sau đó validate trong khi profile vẫn `enabled: false`:

```bash
make review-validate DATABASE=commerce_demo
make catalog-check DATABASE=commerce_demo
```

Warning về metadata chưa được reviewer xác nhận có thể xuất hiện. Các error như `unknown_table`,
`unknown_column`, `missing_review_files` hoặc sai schema contract phải được xử lý trước khi tiếp tục.

### Lỗi `missing_review_files`

Triệu chứng:

```text
error: missing_review_files: no .yml or .yaml reviewer files found
```

Nguyên nhân: raw schema đã tồn tại nhưng `make review-draft` chưa chạy, nên
`catalog/<database>/review` chưa có YAML.

Cách sửa:

```bash
make review-draft DATABASE=commerce_demo
make review-validate DATABASE=commerce_demo
```

Không tự tạo file rỗng và không copy YAML từ `tests/fixtures`.

## 8. Developer — bật CI automation

Chỉ thực hiện sau khi mục 6 và 7 pass.

Đổi trong `config/databases/commerce_demo/database.yml`:

```yaml
enabled: true
```

Kiểm tra database đã tham gia automation:

```bash
./scripts/metadata list-databases
```

Kết quả phải có:

```text
commerce_demo
```

Chạy gate lần cuối:

```bash
make review-validate DATABASE=commerce_demo
make catalog-check-all
git status --short
```

Kết quả mong đợi của catalog check:

```text
catalog validation passed: commerce_demo (3 table(s), enabled)
catalog validation skipped: urcard (onboarding disabled)
catalog validation skipped: urgift (onboarding disabled)
```

## 9. Developer — commit input và mở Draft PR

Developer chỉ stage config, raw và reviewer template:

```bash
git add \
  config/databases/commerce_demo/database.yml \
  config/databases/commerce_demo/tbls.yml \
  catalog/commerce_demo/generated/raw \
  catalog/commerce_demo/review

git diff --cached --stat
git commit -m "feat(metadata): onboard commerce demo"
git push -u origin onboarding/commerce-demo
```

Mở Draft PR:

```bash
gh pr create \
  --draft \
  --base main \
  --head onboarding/commerce-demo \
  --title "feat(metadata): onboard commerce demo" \
  --body "Extract ClickHouse schema and create reviewer metadata templates."
```

Developer không stage `generated/structured` hoặc `generated/published`; hai khu vực đó do bot quản
lý.

## 10. GitHub Actions và metadata bot

Khi PR được mở hoặc có commit mới:

```text
Metadata PR / pr-gate
  -> classify changed paths
  -> catalog-check-all
  -> validate reviewer YAML
  -> candidate-sync với GENERATOR_MODE=live
  -> gọi OpenAI-compatible LiteLLM gateway
  -> bot commit structured JSON + published Markdown
  -> workflow chạy lại ở validate-only mode
```

Repository cần cấu hình trong **Settings -> Secrets and variables -> Actions**.

Secrets:

```text
METADATA_BOT_TOKEN
OPENAI_API_KEY
```

Variables:

```text
METADATA_BOT_LOGIN
OPENAI_BASE_URL=https://ai-gateway.dev/v1
OPENAI_MODEL=gpt-5.4-nano
OPENAI_RESPONSE_FORMAT=json_schema
OPENAI_PROMPT_VERSION=workflow-neutral-narrative-v2
METADATA_GENERATOR_MODE=live
```

Kiểm tra tên cấu hình, không hiển thị giá trị secret:

```bash
gh secret list
gh variable list
```

GitHub Actions không đọc file `.env` trên laptop. `.env` chỉ dành cho developer chạy local UAT.

## 11. Reviewer — chỉ sửa YAML trên GitHub

Reviewer không cần clone repository hoặc chạy command.

### 11.1 Bổ sung business metadata

1. Mở Draft PR.
2. Mở `catalog/commerce_demo/review/<table>.yml`.
3. Chọn **Edit this file**.
4. Điền các thông tin có thể xác nhận.
5. Giữ `document_status: needs_review`.
6. Commit vào đúng branch của PR.

Ví dụ:

```yaml
columns:
  total_amount:
    description: Total amount charged after discounts, excluding refunds.
    unit: VND
    caveats:
      - Exclude cancelled orders when calculating completed revenue.
```

### 11.2 Xem output của bot

Chờ `Metadata PR / pr-gate`. Bot sẽ cập nhật:

```text
catalog/commerce_demo/generated/structured/<table>.json
catalog/commerce_demo/generated/published/<table>.md
```

Reviewer đọc Markdown trong PR diff hoặc link ở Actions summary.

- Chưa đúng: sửa lại YAML, vẫn giữ `needs_review`, rồi commit.
- Đúng: chuyển sang bước approve.
- Không sửa generated Markdown trực tiếp.

### 11.3 Approve đúng candidate đã xem

Tạo một commit riêng chỉ đổi:

```yaml
document_status: approved
```

Reviewer không phải đổi từng `evidence.status` từ `proposed` sang `confirmed`. Evidence status là
thông tin provenance; chỉ evidence `conflicting` phải được xử lý trước approval.

Không sửa business content trong commit approval. Bot kiểm tra fingerprint và promote đúng candidate
đã được xem mà không gọi LLM lần nữa. Nếu vừa sửa content vừa approve, CI phải chặn.

## 12. Merge và output cuối

Khi tất cả check xanh và candidate ở trạng thái promoted:

1. Chuyển Draft PR thành Ready for review.
2. Reviewer approve PR.
3. Merge vào `main`.
4. `Index Manifest` chạy khi structured/published output thay đổi.

Output chuẩn cuối cùng:

```text
catalog/<database>/generated/published/<table>.md
```

Chỉ document `approved` mới đủ điều kiện index. Document `needs_review` vẫn là preview.

## 13. Khi nào CI chạy?

| Workflow | Trigger | Hành vi |
|---|---|---|
| `Quality` | Mọi PR và push vào `main` | Kiểm tra code; không yêu cầu runtime catalog cho database disabled |
| `Metadata PR` | PR opened, synchronize, reopened, ready | Validate/generate khi metadata input thay đổi |
| `Schema Sync` | Manual hoặc schedule được bật | Extract schema và mở Draft PR khi có schema drift |
| `Index Manifest` | Push `main` thay đổi structured/published | Build approved-only manifest |

Nếu mọi profile đều disabled, `Metadata PR` và `Quality` vẫn phải pass nhưng không gọi LLM.

## 14. Checklist trước khi bàn giao cho reviewer

- [ ] `database.yml` có đúng database name và table allowlist.
- [ ] `tbls.yml` không dùng wildcard ngoài phạm vi cho phép.
- [ ] `schema-check` pass.
- [ ] Raw `schema.json` và table Markdown đã được kiểm tra.
- [ ] `review-draft` đã tạo đủ một YAML cho mỗi table.
- [ ] `review-validate` không còn error.
- [ ] `enabled: true` chỉ được bật sau các bước trên.
- [ ] PR không chứa secret hoặc production rows.
- [ ] Reviewer được yêu cầu chỉ sửa YAML.
- [ ] Bot token, gateway secret và variables đã được cấu hình.

## 15. Lệnh kiểm tra nhanh theo từng vai trò

Developer trước khi mở PR:

```bash
make schema-check DATABASE=commerce_demo
make review-draft DATABASE=commerce_demo
make review-validate DATABASE=commerce_demo
make catalog-check-all
git status --short
```

Reviewer:

```text
Edit YAML -> Commit -> Wait for pr-gate -> Review Markdown
          -> Edit YAML again, hoặc status-only approved
```

Developer/maintainer trước merge:

```bash
gh pr checks <PR_NUMBER>
```
