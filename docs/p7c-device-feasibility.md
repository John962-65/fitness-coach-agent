# P7-C 设备数据接入——技术可行性审计与第一阶段交付

> 基线：`d09d487`｜ 日期：2026-10-27

## 1. 可行性审计（不做不可行的承诺）

| 平台/路径 | PWA 浏览器可达？ | 结论 |
|---|---|---|
| Apple HealthKit | 否——需要原生 App 容器（Swift）+ 系统授权弹窗 | 需原生桥接层；不伪造 |
| Android Health Connect | 否——需原生层或受支持的 WebView 桥 | 需原生桥接层；不伪造 |
| 可穿戴厂商 Web 端导出 | 是（用户手动导出文件） | **第一阶段：通用文件导入** |
| Apple Health 导出 XML | 是（用户导出 export.zip） | 后续：解析 export.xml（当前先支持 CSV/JSON） |
| 手动 CSV/JSON | 是 | **已交付** |

**不得假定普通浏览器能够直接访问全部手机健康数据。** 真实平台连接在
确定原生桥接可行（PWA → 可安装 TWA/Capacitor 壳）后实施；在此之前只
交付文件导入，不虚构设备集成。

## 2. 第一阶段交付：只读通用文件导入

- 指标白名单：weight(kg) / sleep_hours(h) / heart_rate(bpm) /
  exercise_minutes(min) / steps(count) / distance(m)；仅白名单内确定性
  换算（lb→kg、斤→kg、min→h、km/mi→m、h/s→min）；未知指标/单位拒绝。
- 每条记录保存 `source_platform / source_device / source_record_id /
  measured_at / imported_at / value / unit / measurement_method`
  （表 `imported_device_records`，UNIQUE(user_id, platform, record_id)）。
- 去重：按平台记录 ID 幂等；重复导入全部跳过。
- **不与手动记录混算**：独立表存储，绝不与 body_measurements/checkins
  相加（防重复统计）；不同设备估算值保留来源，不默认可比。
- 撤销授权数据：按 source_platform 删除（`DELETE …/device-import/records`）。
- 时区：measured_at 要求 ISO 带时区或本地时间（按原样保存，不做隐式
  转换；报告侧按日期聚合）。

API：`POST …/device-import/preview`（不写库）→ `POST …/apply`
（confirmed=true）→ `GET …/records` / `DELETE …/records`。

## 3. 后续（真实平台连接时）

HealthKit/Health Connect 原生桥 → 同步器复用本模块的规范化与去重
（source_platform=真实平台），增量同步按平台游标；断联重试与冲突处理
沿用"来源保留、不合并"原则。
