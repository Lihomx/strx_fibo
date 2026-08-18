# RQC 海外仓退检系统 — 开发规范与实现文档

> **文档版本**：v1.0 (Based on Architecture V16 Final)  
> **目标读者**：前后端开发工程师、系统架构师  
> **目标**：指导 RQC 系统（PDA移动端 + WMS管理端 + OMS客户端）的具体代码实现。

---

## 1. 工程架构与目录规范

系统由三个主要工程模块组成：

```
wms-app/
├── app/                         # WMS 管理端 & OMS 客户端 (Next.js App Router)
│   ├── api/
│   │   └── rqc/                 # RQC 专用后端 API 路由
│   │       ├── oss-sts/         # OSS STS 临时 Token 签发
│   │       ├── pda-login/       # PDA Firebase Auth 换权接口
│   │       ├── receipts/        # 收货记录接口
│   │       ├── qc/              # 质检记录提交接口 (实时累加RI)
│   │       ├── claims/          # IC 认领单管理接口
│   │       ├── cron/sla-check/  # SLA + IC 过期定时检查任务
│   │       └── ocr-dict/        # OCR 店铺/客户匹配字典拉取
│   ├── portal-warehouse/
│   │   └── warehouse/rqc/       # WMS 仓库管理端 RQC 视图页面
│   └── portal-client/
│       └── returns/             # OMS 客户端退件管理页面
├── lib/
│   ├── rqc-pocketbase.ts        # PocketBase RQC 模块数据操作封装
│   └── rqc-oss.ts               # 阿里云 OSS STS Token 签发封装
└── wms-pda/                     # PDA 移动端应用 (Vite + React + TS)
    └── src/
        ├── lib/
        │   ├── firebase-auth.ts # Firebase Auth 逻辑
        │   ├── ocr.ts           # Tesseract.js 离线 OCR 识别引擎
        │   ├── idb-queue.ts     # IndexedDB 离线队列与自动重试同步
        │   └── oss-uploader.ts  # STS 临时 Token 直传 OSS 工具
        └── pages/
            ├── RqcReceiptPage.tsx # PDA 退件接收页面
            └── RqcQcPage.tsx      # PDA 拆包质检页面
```

---

## 2. PocketBase Schema 定义代码

在 PocketBase 初始化或 Migration 中执行以下 10 个集合结构创建：

```typescript
// lib/rqc-schema.ts
export const RQC_COLLECTIONS = [
  {
    name: 'rqc_return_orders',
    type: 'base',
    schema: [
      { name: 'return_no', type: 'text', required: true, unique: true },
      { name: 'source', type: 'select', options: { values: ['lingxing_sync', 'oms_manual', 'claim_converted'] } },
      { name: 'warehouse_id', type: 'text', required: true },
      { name: 'customer_code', type: 'text', required: true },
      { name: 'tenant_id', type: 'text' },
      { name: 'return_type', type: 'select', options: { values: ['buyer_return', 'carrier_return', 'fba_return', 'service_return'] } },
      { name: 'return_reason_id', type: 'text' },
      { name: 'sku_list', type: 'json' }, // [{ sku, name, qty_expected, qty_received, qty_good, qty_bad }]
      { name: 'total_qty_expected', type: 'number' },
      { name: 'total_qty_received', type: 'number' },
      { name: 'total_qty_good', type: 'number' },
      { name: 'total_qty_bad', type: 'number' },
      { name: 'status', type: 'select', options: { values: ['pending', 'processing', 'completed', 'cancelled'] } },
      { name: 'warehouse_suggestion', type: 'select', options: { values: ['restock', 'destroy'] } },
      { name: 'photos', type: 'json' },
      { name: 'lingxing_order_no', type: 'text' },
      { name: 'lingxing_sync', type: 'bool' },
      { name: 'lingxing_sync_status', type: 'select', options: { values: ['not_applicable', 'pending', 'synced', 'failed'] } },
      { name: 'rma_code', type: 'text' },
      { name: 'notes', type: 'text' }
    ]
  },
  {
    name: 'rqc_claim_orders',
    type: 'base',
    schema: [
      { name: 'claim_no', type: 'text', required: true, unique: true },
      { name: 'tracking_no', type: 'text', required: true },
      { name: 'warehouse_id', type: 'text', required: true },
      { name: 'customer_code', type: 'text' },
      { name: 'designated_customer', type: 'text' },
      { name: 'temp_location', type: 'text' },
      { name: 'status', type: 'select', options: { values: ['pending', 'claimed', 'processed', 'cancelled', 'expired'] } },
      { name: 'expire_at', type: 'date' },
      { name: 'photos', type: 'json' },
      { name: 'initial_notes', type: 'text' },
      { name: 'related_return_no', type: 'text' },
      { name: 'operator', type: 'text' }
    ]
  },
  {
    name: 'rqc_receipts',
    type: 'base',
    schema: [
      { name: 'tracking_no', type: 'text', required: true },
      { name: 'rma_verified', type: 'bool' },
      { name: 'rma_code_used', type: 'text' },
      { name: 'customer_code', type: 'text' },
      { name: 'warehouse_id', type: 'text', required: true },
      { name: 'temp_location', type: 'text' },
      { name: 'photos', type: 'json' },
      { name: 'status', type: 'select', options: { values: ['pending_qc', 'pending_assignment', 'qc_done'] } },
      { name: 'related_claim_no', type: 'text' },
      { name: 'related_return_no', type: 'text' },
      { name: 'received_by', type: 'text' },
      { name: 'received_at', type: 'date' },
      { name: 'ocr_raw_text', type: 'text' },
      { name: 'ocr_match_source', type: 'select', options: { values: ['shop_match', 'customer_match', 'manual'] } }
    ]
  },
  {
    name: 'rqc_qc_records',
    type: 'base',
    schema: [
      { name: 'return_no', type: 'text', required: true },
      { name: 'receipt_id', type: 'text' },
      { name: 'warehouse_id', type: 'text', required: true },
      { name: 'sku', type: 'text', required: true },
      { name: 'sku_name', type: 'text' },
      { name: 'qty_good', type: 'number', required: true },
      { name: 'qty_bad', type: 'number', required: true },
      { name: 'sort_grade', type: 'number' }, // 1-4
      { name: 'disposition', type: 'select', options: { values: ['refurbish', 'relabel', 'resell', 'destroy'] } },
      { name: 'warehouse_suggestion', type: 'select', options: { values: ['restock', 'destroy'] } },
      { name: 'photos', type: 'json' },
      { name: 'notes', type: 'text' },
      { name: 'sku_status', type: 'select', options: { values: ['confirmed', 'pending_sku_confirm', 'no_sku'] } },
      { name: 'processed_by', type: 'text' },
      { name: 'processed_at', type: 'date' }
    ]
  },
  {
    name: 'rqc_rma_codes',
    type: 'base',
    schema: [
      { name: 'customer_code', type: 'text', required: true },
      { name: 'shop_id', type: 'text' },
      { name: 'shop_name', type: 'text' },
      { name: 'warehouse_id', type: 'text', required: true },
      { name: 'rma_code', type: 'text', required: true },
      { name: 'valid_date', type: 'date', required: true }
    ]
  },
  {
    name: 'rqc_return_reasons',
    type: 'base',
    schema: [
      { name: 'name', type: 'text', required: true },
      { name: 'sort_order', type: 'number' },
      { name: 'is_active', type: 'bool' }
    ]
  },
  {
    name: 'rqc_shops',
    type: 'base',
    schema: [
      { name: 'shop_id', type: 'text', required: true },
      { name: 'shop_name', type: 'text' },
      { name: 'customer_code', type: 'text', required: true },
      { name: 'tenant_id', type: 'text' },
      { name: 'platform', type: 'text' },
      { name: 'is_active', type: 'bool' }
    ]
  },
  {
    name: 'rqc_delivery_attempts',
    type: 'base',
    schema: [
      { name: 'tracking_no', type: 'text', required: true },
      { name: 'customer_code', type: 'text' },
      { name: 'shop_id', type: 'text' },
      { name: 'warehouse_id', type: 'text', required: true },
      { name: 'photo_url', type: 'text' },
      { name: 'ocr_extracted_text', type: 'text' },
      { name: 'attempted_at', type: 'date' },
      { name: 'attempted_by', type: 'text' },
      { name: 'notified_at', type: 'date' }
    ]
  },
  {
    name: 'rqc_operation_logs',
    type: 'base',
    schema: [
      { name: 'operation_type', type: 'text', required: true },
      { name: 'operator_id', type: 'text', required: true },
      { name: 'operator_name', type: 'text' },
      { name: 'target_type', type: 'select', options: { values: ['ri', 'ic', 'receipt'] } },
      { name: 'target_id', type: 'text', required: true },
      { name: 'old_value', type: 'json' },
      { name: 'new_value', type: 'json' },
      { name: 'note', type: 'text' },
      { name: 'operated_at', type: 'date' }
    ]
  },
  {
    name: 'rqc_pda_users',
    type: 'base',
    schema: [
      { name: 'firebase_email', type: 'text', required: true, unique: true },
      { name: 'firebase_uid', type: 'text', required: true },
      { name: 'role', type: 'select', options: { values: ['admin', 'operator'] } },
      { name: 'warehouse_id', type: 'text', required: true },
      { name: 'warehouse_name', type: 'text' },
      { name: 'is_active', type: 'bool' }
    ]
  }
]
```

---

## 3. 关键后端 API 路由规范

### 3.1 `POST /api/rqc/pda-login`
* **功能**：PDA 客户端通过 Firebase Auth 登录后，获取 Token 并换取 PocketBase 权限与绑定的仓库信息。
* **Request Body**:
  ```json
  { "idToken": "firebase_id_token_string" }
  ```
* **Response**:
  ```json
  {
    "success": true,
    "user": {
      "uid": "fb_uid_123",
      "email": "pda01@ofeta.cc",
      "role": "operator",
      "warehouseId": "WH-MEX-01",
      "warehouseName": "LIHO仓库1"
    }
  }
  ```

### 3.2 `GET /api/rqc/oss-sts`
* **功能**：PDA 获取直传阿里云 OSS 的 STS 临时凭证。
* **Response**:
  ```json
  {
    "accessKeyId": "STS.LTAI...",
    "accessKeySecret": "...",
    "securityToken": "...",
    "expiration": "2026-07-21T14:30:00Z",
    "bucket": "wms-rqc-photos",
    "region": "oss-us-west-1"
  }
  ```

### 3.3 `POST /api/rqc/qc`
* **功能**：PDA 提交一条 SKU 质检记录，并在后端同步更新对应 RI 退件单的数量汇总。
* **Request Body**:
  ```json
  {
    "returnNo": "RI-260721-A17-001",
    "receiptId": "rec_88921",
    "warehouseId": "WH-MEX-01",
    "sku": "SKU-SHOES-RED-42",
    "skuName": "红色运动鞋 42码",
    "qtyGood": 2,
    "qtyBad": 1,
    "sortGrade": 2,
    "disposition": "relabel",
    "warehouseSuggestion": "restock",
    "photos": ["https://oss.example.com/rqc/WH-MEX-01/2026-07/qc/1721692800.jpg"],
    "notes": "鞋盒破损，鞋子无损",
    "skuStatus": "confirmed"
  }
  ```
* **后端核心逻辑**:
  1. 插入一条 `rqc_qc_records` 记录。
  2. 统计 `rqc_qc_records` 中属于 `returnNo` 的所有记录的 `qty_good` 与 `qty_bad` 总和。
  3. 更新 `rqc_return_orders`:
     `total_qty_good` = sum(qty_good), `total_qty_bad` = sum(qty_bad), `total_qty_received` = sum(qty_good + qty_bad), `status` = 'processing'。

### 3.4 `GET /api/rqc/cron/sla-check`
* **功能**：由 VPS Linux Crontab 定时运行（每天凌晨 2 点），执行 SLA 自动确认与 IC 到期失效。
* **后端逻辑**:
  1. 查询 `rqc_return_orders` 中 `status = 'processing'` 且 `updated_at < (now - 7 days)` 的订单，将其 `status` 改为 `completed`，并生效 `warehouse_suggestion`。
  2. 查询 `rqc_claim_orders` 中 `status = 'pending'` 且 `expire_at < now` 的订单，将其 `status` 改为 `expired`。
  3. 为以上更改记录写入 `rqc_operation_logs`。

---

## 4. 前端关键核心逻辑实现

### 4.1 Tesseract.js 离线 OCR 解析 Pipeline (`wms-pda/src/lib/ocr.ts`)

```typescript
import { createWorker } from 'tesseract.js'

let worker: Tesseract.Worker | null = null

export async function initOcrEngine() {
  if (!worker) {
    worker = await createWorker(['eng', 'spa'])
  }
  return worker
}

export async function recognizeParcelLabel(imageBlob: Blob): Promise<{
  rawText: string
  matchedShopId?: string
  matchedCustomerCode?: string
  trackingNo?: string
}> {
  const engine = await initOcrEngine()
  const { data: { text } } = await engine.recognize(imageBlob)
  
  // 从文本中正规匹配跟踪号与店铺字典
  const trackingNo = extractTrackingNo(text)
  const matchResult = matchCustomerAndShop(text)

  return {
    rawText: text,
    trackingNo,
    matchedShopId: matchResult.shopId,
    matchedCustomerCode: matchResult.customerCode
  }
}

function extractTrackingNo(text: string): string | undefined {
  // 正则提取常见物流单号 (Mercado, DHL, Fedex, Estafeta)
  const match = text.match(/(1Z[A-Z0-9]{16}|MEX[A-Z0-9]+|\d{10,14})/)
  return match ? match[0] : undefined
}

function matchCustomerAndShop(text: string) {
  // 从本地 IDB 缓存的 shopDict 中字典匹配
  // 逻辑: 检查 shop_name/shop_id 是否出现在 OCR rawText 中
  return { shopId: undefined, customerCode: undefined }
}
```

### 4.2 PDA 弱网 IndexedDB 离线队列 (`wms-pda/src/lib/idb-queue.ts`)

```typescript
import { openDB } from 'idb'

const RQC_QUEUE_DB = 'rqc-offline-db'

export async function getRqcDb() {
  return openDB(RQC_QUEUE_DB, 1, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('pending_sync')) {
        db.createObjectStore('pending_sync', { keyPath: 'id', autoIncrement: true })
      }
    }
  })
}

export async function enqueueRqcAction(type: 'receipt' | 'qc', payload: any) {
  const db = await getRqcDb()
  await db.add('pending_sync', { type, payload, createdAt: Date.now() })
  
  // 若网络在线，尝试触发立即同步
  if (navigator.onLine) {
    flushRqcQueue()
  }
}

export async function flushRqcQueue() {
  const db = await getRqcDb()
  const allPending = await db.getAll('pending_sync')
  
  for (const item of allPending) {
    try {
      const url = item.type === 'receipt' ? '/api/rqc/receipts' : '/api/rqc/qc'
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item.payload)
      })
      if (res.ok) {
        await db.delete('pending_sync', item.id)
      }
    } catch {
      console.warn('Network offline, sync will retry next time.')
      break
    }
  }
}
```

---

## 5. 开发阶段与里程碑排期 (Milestones)

| 阶段 | 交付目标 | 核心工作项 | 估算工时 |
|---|---|---|---|
| **Phase 1** | 基础设施 & 数据库 Schema | 1. 部署 10 个 PocketBase Collections<br>2. 实现 `/api/rqc/oss-sts` 临时凭证接口<br>3. 编写 `rqc_pda_users` 账号仓库绑定管理 | 2 天 |
| **Phase 2** | PDA 退件接收模块 (Stage 1) | 1. Tesseract.js 离线 OCR eng+spa 整合<br>2. PDA 拍照直传 OSS & IndexedDB 离线队列<br>3. RMA 码验证逻辑与 IC 认领单/拒收单生成 | 4 天 |
| **Phase 3** | PDA 拆包质检 & 智能匹配 (Stage 2) | 1. SKU 扫码录入 (良品/不良品分列录入)<br>2. 质检记录提交 + 后端实时累加 RI 统计<br>3. 无 SKU 辅助标识描述录入流程 | 3 天 |
| **Phase 4** | WMS & OMS 控制台与 SLA 定时任务 | 1. OMS 客户端 RMA 每日录入与退件单手动创建（调用领星 API `/v1/returnOrder/create`）<br>2. OMS 客户端 IC 认领与 7天 SLA 建议确认<br>3. WMS 待分配包裹指派与 Cron SLA 定时任务 | 4 天 |

---

## 6. 测试用例清单 (Test Cases)

1. **OCR 离线识别测试**：在 PDA 断开网络连接的情况下，拍摄一张含西文地址与物流跟踪号的面单图片，验证识别率与从 IndexedDB 匹配店铺字典的准确度。
2. **多 SKU 质检数量累加测试**：对同一个 RI 单依次提交 2 个良品 SKU-A 与 1 个不良品 SKU-B，检查 `rqc_return_orders` 中的 `total_qty_good` 与 `total_qty_bad` 是否正确更新为 2 和 1。
3. **断网暂存与恢复测试**：PDA 开启飞行模式完成一次质检提交，验证数据进入 IndexedDB；恢复网络后，验证队列自动清空且服务器数据成功更新。
4. **SLA 7天自动执行测试**：将某处于 `processing` 状态的 RI 单 `updated_at` 手动调至 8 天前，手动触发 `/api/rqc/cron/sla-check`，验证状态自动变为 `completed` 并写入 `rqc_operation_logs`。
