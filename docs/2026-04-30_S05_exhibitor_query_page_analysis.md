# S06 · 展商查询页分析 & 三端集成关系梳理

**日期**：2026-04-30  
**前置文档**：S04（展商秀）/ S05（慕渊会展云 + 双SaaS比对）  
**目标页面**：展商查询公开页（ExhibitorServiceCenterQuery）  
**URL**：[https://exhibitor.expo2345.com/findAnExhibitor/exhibitorQuery?organizerId=...&projectId=...&exhibitionId=](https://exhibitor.expo2345.com/findAnExhibitor/exhibitorQuery?organizerId=...&projectId=...&exhibitionId=)...  
**页面性质**：无需登录的公开展商目录，设计用途为对外嵌入/分发

---

## 1. 页面基本特征


| 维度         | 内容                                                                                     |
| ---------- | -------------------------------------------------------------------------------------- |
| 页面标题       | 第110届中国国际劳动保护用品交易会                                                                     |
| 路由         | `/findAnExhibitor/exhibitorQuery`（SaaS-B 同域路由，非独立域名）                                   |
| 登录要求       | **无**（公开访问，客户端自动获取 token）                                                              |
| 是否在 iframe | 否（`window.self === window.top`），但设计形态为可嵌入组件                                            |
| JS bundle  | `index-689ef808.js`（**与 SaaS-B 展商后台完全相同**，同一 SPA 不同路由）                                 |
| CSS 额外引入   | `mQrcode-d4d7a48f.css`（二维码样式）/ `posterDislog-80622f78.css`（海报弹窗）/ `index-b2c2eb32.css` |
| 页面高度       | 约 900px（无顶部导航，无底部分页控件可见）                                                               |


---

## 2. 页面功能

### 2.1 可见内容

```
[搜索框]  请搜索展商或展位号

[表格]
  展商名称 | 展区 | 展位号 | 下载邀请函
  ─────────────────────────────────────
  梅思安（中国）安全设备有限公司 | E1，E7 | 1B11，7F18 | ↓ 下载
  江苏恒辉安防集团股份有限公司   | E4，E7 | 4A02，7E18 | ↓ 下载
  ...（共 1,260 条展商记录）
```

### 2.2 用户操作路径

1. **搜索**：输入展商名或展位号过滤列表
2. **下载邀请函**：点击「下载」→ 弹出该展商的海报（含展商二维码，供观众扫码预注册）
3. 无其他操作：无点击展商进入详情页，无筛选/排序，无展商介绍/展品展示

---

## 3. 技术架构分析

### 3.1 认证方式（关键异常）

```
POST /connect/token
grant_type=client_credentials
client_id=synair.expocloud.api
client_secret=synair.expocloud_2fFoJvSWBzPaQ3NmuVzcbWIR3nXEJf   ← 硬编码在 JS bundle 中
scope=IdentityServerApi
```

- 使用 **OAuth2 Client Credentials Grant**（机器对机器），不代表任何用户身份
- client_secret **明文嵌入前端 JS 包**，任何人可通过 DevTools 提取
- 生成的 Token 无 role/exhibitorId/tenantId Claims，仅有 `scope=IdentityServerApi`
- 结论：此 Token 理论上可被任意第三方用于调用 `api.expo2345.com` 的 GraphQL 接口

### 3.2 GraphQL 调用链（共 5 次）


| 顺序  | 操作                                                                   | 数据内容                              |
| --- | -------------------------------------------------------------------- | --------------------------------- |
| ①   | `featureManagement.featuresByGroupName(ExhibitorServiceCenterQuery)` | 功能开关：IsEnabled=true，Banners=图片URL |
| ②   | `exhibition.get`                                                     | 展会基本信息（名称/日期/地点/标准展位面积）           |
| ③   | `exhibitionArea.all`                                                 | 全部展区列表（E1~E7+，含负责销售人员 ownersJson） |
| ④   | `exhibitor.viewPage(page:1, size:20, sorting:...)`                   | 展商分页列表，**totalCount=1,260**       |
| ⑤   | （第158号请求，未详细检查，推测为后续分页或搜索请求）                                         | —                                 |


### 3.3 展商数据字段（公开页仅返回最小集）

```graphql
items {
  id
  name
  nameEn
  exhibitorBoothArea    # 展区，可多个（逗号分隔）
  exhibitorBoothNo      # 展位号，可多个（逗号分隔）
}
```

对比 SaaS-B 展商后台调用的 `exhibitor.view`（约50个字段），此页仅暴露 5 个字段。

### 3.4 功能旗标（Exhibition 级别，区别于 S05 的 Tenant 级别）

```
featuresByGroupName(providerName:"Exhibition", providerKey:"{exhibitionId}", groupName:"ExhibitorServiceCenterQuery")
→ ExhibitorServiceCenterQuery.IsEnabled = true
→ ExhibitorServiceCenterQuery.Banners  = "https://source.expo2345.com/expocloud/image/202509/15/ADYT92CP_系统banner1920X360.jpg"
```

Banner 图片 URL 已配置，但**页面未渲染该 banner**（Bug，见第4节）。

---

## 4. 已发现的 Bug 与异常

### Bug 1：顶部 Banner 不渲染

- Feature Flag 返回了 banner 图片 URL，但页面顶部完全没有 banner 展示区
- 页面从表格头部开始，CIOSH 视觉品牌完全缺失
- 推断：Vue 组件中 banner 渲染逻辑存在条件判断错误，或 CSS 隐藏了该区域

### Bug 2：双重表头（DOM 异常）

- a11y 快照中表头文字出现两次（`uid=21_5~8` 与 `uid=21_9~12` 均为「展商名称/展区/展位号/下载邀请函」）
- 推断：粘性表头（sticky header）与数据表格的列头组件重复渲染，无实际功能影响但说明组件层次有问题

### Bug 3：client_secret 明文暴露

- `synair.expocloud_2fFoJvSWBzPaQ3NmuVzcbWIR3nXEJf` 可从任意浏览器 DevTools 提取
- 该 secret 理论上允许任何人冒充此客户端调用 `api.expo2345.com` 的受保护接口
- 严重程度：中（因 IdentityServerApi scope 权限有限，但仍是不规范做法）

### Bug 4：页面无任何 CIOSH 品牌化

- 没有展会 Logo、主视觉、导航栏，完全是裸表格
- 与该页面设计定位（嵌入 ciosh.com 的「查找展商」工具）严重不符

---

## 5. 集成关系梳理：为什么三端都没法整合好

### 5.1 当前实际架构图

```
ciosh.com（主办官网）
  └─ 链接/嵌入 → exhibitor.expo2345.com/findAnExhibitor/...（本页，SaaS-B 子路由）
                    ↑ 同一SPA，同一bundle
SaaS-B 展商后台 → exhibitor.expo2345.com/exhibitor/home
SaaS-A 展商秀   → console.zhanshangxiu.com/ex-live（完全独立系统）
```

### 5.2 SaaS-A（展商秀）与本页的关系


| 维度               | 现状                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------- |
| 数据连通             | **零**。本页的 1,260 条展商数据全部来自 SaaS-B（ExpoCloud）的 `exhibitor.viewPage`，与 SaaS-A 数据库毫无关联 |
| 展品/活动展示          | **无**。SaaS-A 的展品管理、活动申请、公司 Logo/Banner 在本页完全不存在                                    |
| 跳转链接             | **无**。点击展商行只能下载邀请函，无法跳转到 SaaS-A 的 H5 展台（m2.zhanshangxiu.com）                       |
| ExhibitorShow 功能 | SaaS-B 已内置 ExhibitorShow 功能旗标，但当前 CIOSH 实例未开通（IsEnabled=false），导致展商秀内容无法在此聚合       |
| 根本原因             | SaaS-A 和 SaaS-B 是两家不同的 SaaS 厂商，本页是 SaaS-B 的原生页面，SaaS-A 无集成接口                       |


### 5.3 SaaS-B（慕渊会展云）与本页的关系


| 维度     | 现状                                                                           |
| ------ | ---------------------------------------------------------------------------- |
| 技术同源   | **是**。同一 Vue 3 SPA，同一 API 域名，本页是 SaaS-B 的一个公开路由                              |
| 数据丰富度  | **被人为裁剪**。SaaS-B 后台可查看展商的 50+ 字段，但本页只暴露 5 个字段（名称/展区/展位）                      |
| 展商详情页  | **缺失**。SaaS-B 有完整展商资料（Logo/简介/展品/联系人），但本页无跳转入口                               |
| 观众流量闭环 | **断裂**。展商在 SaaS-B 海报邀请中设置了自定义展位图+产品图，但这些内容不出现在本页的「下载邀请函」弹窗中（只有通用 CIOSH 海报模板） |
| 根本原因   | 本页是 SaaS-B 的「公开嵌入组件」定位，被设计为最小化的展商目录，而非展商展示平台                                 |


### 5.4 集成失败的核心矛盾

```
SaaS-A 定位：展商品牌营销（展品/活动/直播/H5展台）
SaaS-B 定位：展会运营管理（合同/付款/观众邀请/数据统计）
本页定位：公开展商查询工具（观众找展商用）

三者本应形成：
  SaaS-B（运营管理）→ 本页（公开目录）→ SaaS-A（品牌展示）
  即：展商在SaaS-B完成报名 → 数据同步到本页目录 → 点击展商进入SaaS-A展台

实际现状：
  ① SaaS-B → 本页：数据已同步（1260展商），但只有名称+展位，无详情跳转
  ② 本页 → SaaS-A：完全断链，两个系统无任何接口互通
  ③ 技术断层：SaaS-A（Vue 2/REST）与 SaaS-B（Vue 3/GraphQL）架构完全不同，
     实时数据同步需要双方提供 API 且需主办方协调，当前未实现
```

---

## 6. 对小程序合并方案的影响

### 6.1 本页可直接被小程序替代的功能


| 功能      | 小程序实现路径              | 数据来源                                           |
| ------- | -------------------- | ---------------------------------------------- |
| 展商目录列表  | 小程序列表页 + 搜索          | SaaS-B `exhibitor.viewPage` GraphQL（已知 schema） |
| 按展区筛选   | 小程序 Tab 或下拉筛选        | SaaS-B `exhibitionArea.all`（已知 schema）         |
| 展商邀请函下载 | 小程序内生成海报 → 分享/保存     | SaaS-B 海报生成逻辑（与展商端海报邀请同源）                      |
| 展商详情页   | **SaaS-A 无法直接用，需重建** | SaaS-B `exhibitor.view`（字段齐全）                  |


### 6.2 本页暴露的小程序集成机会

1. **client_credentials 模式可供小程序复用**：小程序可用同样的 client_credentials 获取匿名 token，无需展商/观众登录即可展示全量展商目录——**这是合理的公开查询场景**。
2. **1,260展商全量数据已在 SaaS-B**：小程序只需对接 SaaS-B 的 `exhibitor.viewPage` 即可完整替代本页，且可加上展品/公司简介等 SaaS-A 功能（需单独对接 SaaS-A 或将内容迁移）。
3. **展商秀 ExhibitorShow 开通后**：若主办方开通 ExhibitorShow 功能（IsEnabled=true），SaaS-B 可能自动聚合 SaaS-A 展品数据，届时 SaaS-B GraphQL 应当能返回更丰富的展商展示内容。

### 6.3 需要主办方（枯联）协调解决的前提


| 前提                   | 当前状态                           | 解决路径                           |
| -------------------- | ------------------------------ | ------------------------------ |
| ExhibitorShow 开通     | ❌ IsEnabled=false              | 联系枯联开通 ExhibitorShow 功能旗标      |
| 小程序域名加入 CORS 白名单     | ❌ 当前只允许 exhibitor.expo2345.com | 向枯联申请将小程序域名加入白名单               |
| client_secret 换成安全方案 | ❌ 明文在 JS 中                     | 枯联应提供专用的小程序 AppKey，或换成 PKCE 流程 |
| SaaS-A 展品数据导出/对接     | ❌ 无接口                          | 向展商秀申请数据导出 API 或由主办方提供同步方案     |


---

## 7. 简要结论

本页是**慕渊会展云（SaaS-B）的同域公开路由**，与 SaaS-B 展商后台共享同一 Vue 3 SPA，设计定位为「嵌入 CIOSH 官网的展商查询小工具」。

当前状态：

- **功能极简**：只有展商名称+展位+下载邀请函，无品牌内容
- **SaaS-A 完全缺失**：展商秀的展品/活动/公司介绍在此页零存在
- **4个可见 Bug**：Banner 不渲染、双重表头、client_secret 暴露、无品牌化
- **集成断链**：三个系统（ciosh.com / SaaS-A / SaaS-B）之间均无真正的数据/跳转互通

**对小程序方案的核心判断**：本页代表的「公开展商目录」功能**完全可以由小程序替代**，且小程序版本可以做得更好（加展商详情/展品/筛选/地图定位），数据来源已确认为 SaaS-B 的 `exhibitor.viewPage` GraphQL 接口，技术路径清晰。SaaS-A 展商内容的整合需要额外的数据迁移或接口对接工作，不能依赖现有的 ExhibitorShow feature flag（当前未开通）。

---

*文档为单次调研快照，由 cc 完成页面分析后输出 Max Wang校验审核。*