# 🌟 表情包小偷

<div align="center">

<img src="https://count.getloli.com/@nagatoquin33?name=nagatoquin33&theme=rule34&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="Moe Counter">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python Version](https://img.shields.io/badge/Python-3.10.14%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)
[![Last Commit](https://img.shields.io/github/last-commit/nagatoquin33/astrbot_plugin_stealer)](https://github.com/nagatoquin33/astrbot_plugin_stealer/commits/main)

</div>

## 📑 目录

- [🌟 表情包小偷](#-表情包小偷)
  - [📑 目录](#-目录)
  - [📢 简介](#-简介)
  - [🚀 功能特点](#-功能特点)
  - [📦 安装方法](#-安装方法)
  - [🛠️ 快速上手](#️-快速上手)
  - [⚙️ 配置说明](#️-配置说明)
  - [🎮 使用指令](#-使用指令)
  - [🗑️ 文件清理机制](#️-文件清理机制)
  - [🎯 图片处理节流](#-图片处理节流)
  - [⚠️ 注意事项](#️-注意事项)
  - [📄 许可证](#-许可证)

## 📢 简介

我想仿照麦麦的表情包偷取做个娱乐性的插件的，于是就有了这个表情包小偷插件

全人机代码，不过本人一直在监工调试，但不保证什么问题都没有

我尽量做到在上架前让这个插件能正常工作

表情包小偷是一款基于多模态AI的娱乐性插件，能够自动偷取聊天中的图片，进行视觉理解与情绪分类，并在发送回复前按概率追加一张匹配情绪的表情，显著提升聊天互动体验。

如果偷够了可以金盆洗手，支持偷取功能单独开启或关闭

本插件设计灵活，支持自动使用当前会话的视觉模型，无需额外配置即可开始使用。

## 📝 更新历史
- **version: 1.0.2**：修改正则，现在应该不会吞掉换行和[]()这一类符号了，同时加强对&&的匹配
- **version: 1.0.3**：修复指令状态，去除无用指令，改进状态显示
- **version: 1.0.4**：修复vlm模型调用失败的问题
- **version: 2.0.0**：🎉 重大更新！新增增强存储系统，完全向后兼容，修复旧版本配置同步和使用统计问题
- **version: 2.0.1**：🔧 修复清理逻辑混乱和人格注入问题，优化表情包识别准确率
- **version: 2.0.3**：修复bug
- **version: 2.0.7**：🚀 全面代码重构和优化，移除冗余功能，提升性能和稳定性
- **version: 2.0.8**：✨ 根据AstrBot开发文档进行全面优化，提升代码质量和规范性
- **version: 2.0.9**： 优化注入的提示词，并对残缺标签进行加强处理


## 🚀 功能特点

### 核心功能
- **自动图片偷取**：实时监听聊天中的图片消息并自动保存
- **AI多模态理解**：使用视觉模型生成图片描述、标签与情绪分类
- **情绪智能匹配**：支持开心、悲伤、愤怒、惊讶等多种情绪分类（基于提示词，不保证真的100%准确）
- **自动表情追加**：发送回复前按概率追加匹配情绪的表情，提升互动性
- **内容安全审核**：可选开启内容审核功能，过滤不符合要求的图片
- **智能存储管理**：自动清理过期文件，优化存储空间使用

### 🆕 新功能

#### 🎯 智能节流系统
- **4种节流模式**：probability（概率）、interval（间隔）、cooldown（冷却）、always（总是）
- **大幅减少API消耗**：最高可减少90%的VLM调用
- **灵活配置**：可根据API额度和需求自由调整
- **实时生效**：无需重启，配置即时生效

#### 🔧 独立后台任务
- **Raw清理任务**：独立的原始图片清理任务，可单独配置周期和启用状态
- **容量控制任务**：独立的表情包数量控制任务，可单独配置周期和启用状态
- **灵活控制**：两个任务互不影响，可按需启用
- **精细调整**：分别设置不同的执行周期

#### 🚀 增强存储系统 (v2.0.0)
- **完全向后兼容**：无缝升级，保留所有旧数据和配置
- **智能文件生命周期管理**：自动跟踪文件从创建到删除的完整生命周期
- **全面统计监控**：实时处理事件记录、访问模式分析、性能指标收集
- **协调清理操作**：状态感知的智能清理，防止竞态条件和数据不一致
- **智能配额管理**：多策略配额执行，基于使用模式的优先级删除
- **修复旧版本问题**：解决配置同步不及时和使用次数统计失效的问题

#### ✨ 代码质量优化 (v2.0.8)
- **API调用规范化**：严格遵循AstrBot公开API，避免使用内部API
- **错误处理改进**：完善的异常处理机制，更准确的错误信息和日志记录
- **性能优化**：异步IO操作、智能缓存管理、资源自动清理
- **代码规范性**：符合AstrBot插件开发文档的所有要求和最佳实践
- **配置验证增强**：更严格的配置参数验证和自动修复机制
- **日志优化**：更合理的日志级别使用，提供更有用的调试信息

### 未来功能计划

我们计划在后续版本中添加以下功能：

- **自定义表情库**：支持用户上传和管理个人表情库，增加更多情感表达
- **手动调整表情的标签**：用户可以手动调整已偷取的图片的标签，修正分类错误

### 技术特性
- **自动模型选择**：未指定视觉模型时，自动使用当前会话的视觉模型
- **灵活配置选项**：支持通过指令或配置文件调整各项功能参数
- **后台维护机制**：定期执行容量控制和文件清理，确保系统稳定
- **完善错误处理**：规范的异常处理机制，符合AstrBot开发文档要求
- **智能人格注入**：自动为AI人格注入情绪选择能力，支持自动维护和手动控制
- **代码质量保证**：通过ruff格式化和检查，符合PEP8规范，遵循AstrBot插件开发规范
- **性能优化**：异步IO操作、智能缓存管理、资源自动清理
- **API调用规范**：严格遵循AstrBot公开API，避免使用内部API
- **企业级可靠性**：增强存储系统提供事务日志、自动修复、优雅降级等特性
- **零风险升级**：完全向后兼容，支持从任何旧版本无缝升级

## 🎭 人格注入系统

插件会自动为 AstrBot 的人格配置注入情绪选择提醒，让 AI 在回复时能够根据情绪选择合适的表情包。

### 特性
- **自动注入**: 插件启动时自动注入情绪选择提醒到所有人格
- **防重复注入**: 智能检测已注入的人格，避免重复注入
- **自动维护**: 每5分钟检查一次人格状态，确保注入持续有效
- **安全恢复**: 插件卸载时自动恢复原始人格配置
- **手动控制**: 提供管理员命令手动管理人格注入

### 管理命令
- `/meme reload_persona` - 手动重新注入人格（管理员）
- `/meme persona_status` - 查看人格注入状态（管理员）

### 工作原理
插件会在每个人格的系统提示词后添加情绪选择指导，让 AI 能够：
1. 识别用户消息中的情绪
2. 在回复前添加情绪标签（如 `&&happy&&`）
3. 触发插件发送对应情绪的表情包

注入的提示词会自动适配当前配置的情绪分类，确保 AI 能够准确识别和标记情绪。
- **企业级可靠性**：增强存储系统提供事务日志、自动修复、优雅降级等特性
- **零风险升级**：完全向后兼容，支持从任何旧版本无缝升级

## 📦 安装方法

### 全新安装
>>>>>>> 91e5d03 (feat(storage): 新增增强存储系统实现文件生命周期管理)
1. 确保已安装 AstrBot
2. 将插件复制到 AstrBot 的插件目录：`AstrBot/data/plugins`
3. 或在 Dashboard 插件中心直接安装
4. 重启 AstrBot 或使用热加载命令

### 从旧版本升级 🔄
**完全向后兼容，零风险升级！**

1. **备份数据**（推荐）：备份 `data/plugins/astrbot_plugin_stealer/` 目录
2. **直接替换**：用新版本文件替换旧版本
3. **重启AstrBot**：插件会自动检测并兼容旧数据
4. **验证功能**：使用 `/meme status` 检查插件状态

**升级后保留：**
- ✅ 所有表情包文件和分类
- ✅ 使用统计和配置设置  
- ✅ 用户自定义配置
- ✅ 完整的使用历史

**升级后修复：**
- ✅ 配置同步问题（指令修改后WebUI实时更新）
- ✅ 使用次数统计问题（正确记录和更新使用次数）
- ✅ 数据一致性问题（防止文件孤立和索引错误）

## 🛠️ 快速上手

### 1. 模型配置

设置视觉模型（用于图片分类）：

```bash
/meme set_vision <provider_id>
```

> **智能模型选择**：若未设置视觉模型，插件会自动使用当前会话的视觉模型，无需额外配置即可开始使用
> 
> **支持模型**：需要支持图片输入的视觉模型（如 Gemini, 豆包, qwen vl 等）

### 2. 功能开启

```bash
# 开启/关闭插件
/meme on
/meme off

# 开启/关闭自动随聊表情
/meme auto_on
/meme auto_off
```

### 3. 节流配置（推荐）✨

为了避免过度消耗API，建议配置节流：

```bash
# 推荐配置：概率模式，30%处理概率
/meme throttle_mode probability
/meme throttle_probability 0.3

# 查看节流状态
/meme throttle_status
```

### 4. 基本使用

```bash
# 查看插件状态
/meme status

# 查看后台任务状态
/meme task_status
```

## ⚙️ 配置说明

### 基础配置

| 配置项 | 类型 | 默认值 | 描述 |
|--------|------|--------|------|
| `auto_send` | bool | true | 是否自动随聊追加表情包 |
| `vision_provider_id` | string | null | 视觉模型提供商ID，未设置时自动使用当前会话模型 |
| `emoji_chance` | float | 0.4 | 触发表情动作的基础概率 |
| `max_reg_num` | int | 100 | 允许注册的最大表情数量 |
| `do_replace` | bool | true | 达到上限时是否替换旧表情 |
| `steal_emoji` | bool | true | 是否开启表情包偷取功能 |
| `content_filtration` | bool | false | 是否开启内容审核 |
| `raw_retention_minutes` | int | 60 | raw目录中图片的保留期限（分钟） |

### 节流配置 🆕

| 配置项 | 类型 | 默认值 | 描述 |
|--------|------|--------|------|
| `image_processing_mode` | string | probability | 图片处理模式：always/probability/interval/cooldown |
| `image_processing_probability` | float | 0.3 | 概率模式下的处理概率（0.0-1.0） |
| `image_processing_interval` | int | 60 | 间隔模式下的处理间隔（秒） |
| `image_processing_cooldown` | int | 30 | 冷却模式下的冷却时间（秒） |

### 后台任务配置 🆕

| 配置项 | 类型 | 默认值 | 描述 |
|--------|------|--------|------|
| `raw_cleanup_interval` | int | 30 | raw目录清理任务的执行周期（分钟） |
| `capacity_control_interval` | int | 60 | 容量控制任务的执行周期（分钟） |
| `enable_raw_cleanup` | bool | true | 是否启用raw目录自动清理 |
| `enable_capacity_control` | bool | true | 是否启用容量自动控制 |

### 增强存储系统配置 🆕

| 配置项 | 类型 | 默认值 | 描述 |
|--------|------|--------|------|
| `enable_lifecycle_tracking` | bool | true | 启用文件生命周期跟踪 |
| `enable_intelligent_cleanup` | bool | true | 启用智能清理管理 |
| `enable_statistics_tracking` | bool | true | 启用统计数据跟踪 |
| `enable_quota_management` | bool | true | 启用存储配额管理 |
| `enable_duplicate_detection` | bool | true | 启用增强重复检测 |
| `quota_strategy` | string | hybrid | 配额管理策略：count_based/size_based/hybrid |
| `max_total_size_mb` | int | 5000 | 最大总存储大小（MB） |
| `quota_warning_threshold` | float | 0.8 | 配额警告阈值（0.0-1.0） |
| `quota_critical_threshold` | float | 0.95 | 配额严重阈值（0.0-1.0） |
| `cleanup_check_interval` | int | 300 | 清理检查间隔（秒） |
| `statistics_aggregation_interval` | int | 3600 | 统计聚合间隔（秒） |
| `statistics_retention_days` | int | 90 | 统计数据保留天数 |
| `enable_transaction_logging` | bool | true | 启用事务日志记录 |
| `max_retry_attempts` | int | 3 | 最大重试次数 |
| `circuit_breaker_threshold` | int | 5 | 断路器失败阈值 |
| `enable_async_processing` | bool | true | 启用异步处理 |
| `processing_queue_size` | int | 100 | 处理队列大小 |
| `batch_operation_size` | int | 50 | 批量操作大小 |

## 🎮 使用指令

### 基础指令

| 指令 | 描述 |
|------|------|
| `/meme on` | 开启偷表情包功能 |
| `/meme off` | 关闭偷表情包功能 |
| `/meme auto_on` | 开启自动随聊表情 |
| `/meme auto_off` | 关闭自动随聊表情 |
| `/meme status` | 查看插件状态和表情包统计 |
| `/meme set_vision <provider_id>` | 设置视觉模型 |
| `/meme clean` | 清理raw目录中的所有文件（不影响已分类的表情包） |
| `/meme clean expired` | 只清理raw目录中过期的文件（按保留期限） |
| `/meme capacity` | 手动执行容量控制（删除最旧的表情包） |
| `/meme list [category] [limit]` | 列出表情包（显示图片） |
| `/meme list_text [category] [limit]` | 列出表情包（仅文本） |

### 高级配置指令

| 指令 | 描述 |
|------|------|
| `/meme throttle [action] [value]` | 配置图片处理节流 |
| `/meme task [type] [action] [value]` | 配置后台任务 |

#### 节流配置示例
```bash
/meme throttle                    # 查看节流状态
/meme throttle mode probability   # 设置概率模式
/meme throttle probability 0.3    # 设置30%处理概率
/meme throttle interval 60        # 设置60秒间隔
/meme throttle cooldown 30        # 设置30秒冷却
```

#### 任务配置示例
```bash
/meme task cleanup on             # 启用清理任务
/meme task cleanup interval 30    # 设置清理周期30分钟
/meme task capacity off           # 禁用容量控制
/meme task capacity interval 60   # 设置容量控制周期60分钟
```

#### 表情包管理示例
```bash
# 查看表情包（显示图片）
/meme list                        # 列出所有表情包（默认10张，显示图片）
/meme list happy                  # 列出happy分类的表情包（显示图片）
/meme list sad 20                 # 列出sad分类的前20张表情包（显示图片）

# 查看表情包（仅文本，适合快速浏览）
/meme list_text                   # 列出所有表情包（仅文件名）
/meme list_text happy 5           # 列出happy分类的前5张（仅文件名）

# 删除表情包
/meme delete 3                    # 删除列表中第3张表情包
/meme delete image_001.jpg        # 按文件名删除表情包

# 数据迁移（升级时使用）
/meme migrate                     # 迁移旧版本数据
```

### 管理员指令

| 指令 | 描述 |
|------|------|
| `/meme push <category> [alias]` | 推送指定分类的表情包 |
| `/meme debug_image` | 调试图片处理 |
| `/meme list [category] [limit]` | 列出表情包（显示图片） |
| `/meme list_text [category] [limit]` | 列出表情包（仅文本） |
| `/meme delete <序号\|文件名>` | 删除指定表情包 |
| `/meme migrate` | 迁移旧版本数据 |
| `/meme reload_persona` | 手动重新注入人格 |
| `/meme persona_status` | 查看人格注入状态 |

## 🗑️ 文件清理机制

插件实现了灵活的文件清理机制，确保不会占用过多存储空间。

### 🆕 独立任务系统

清理机制已拆分为两个独立任务：

#### 1. Raw目录清理任务 📁
- **功能**：定期清理过期的原始图片
- **默认周期**：30分钟
- **保留期限**：60分钟
- **控制**：可单独启用/禁用

#### 2. 容量控制任务 📊
- **功能**：定期检查并控制表情包数量
- **默认周期**：60分钟
- **数量上限**：100张
- **控制**：可单独启用/禁用

### 配置示例

```bash
# 只启用raw清理，不控制容量
/meme raw_cleanup on
/meme capacity_control off

# 设置不同的执行周期
/meme raw_cleanup_interval 15    # 15分钟清理一次
/meme capacity_interval 120      # 2小时控制一次
```

### 工作流程

1. **Raw清理任务**：
   - 每30分钟执行一次（可配置）
   - 删除超过60分钟的原始图片
   - **只清理raw目录**，不影响categories目录
   - 只在 `steal_emoji` 和 `enable_raw_cleanup` 都启用时执行

2. **容量控制任务**：
   - 每60分钟执行一次（可配置）
   - 检查表情包数量是否超过上限
   - **只删除categories目录中超出限制的表情包**
   - 按创建时间删除最旧的表情包
   - 只在 `steal_emoji` 和 `enable_capacity_control` 都启用时执行

### 🔧 任务职责分离

- **Raw清理**: 专门处理临时文件，基于文件年龄清理
- **容量控制**: 专门管理表情包数量，基于配额限制清理  
- **独立运行**: 两个任务互不干扰，确保清理逻辑清晰

## 🎯 图片处理节流

为了避免过度调用VLM API，插件提供了智能节流功能。

### 四种节流模式

| 模式 | 说明 | API消耗 | 适用场景 |
|-----|------|---------|---------|
| **probability** | 按概率随机处理 | ⭐⭐ 可控 | **日常使用（推荐）** |
| **interval** | 每N秒处理一次 | ⭐ 最低 | API额度紧张 |
| **cooldown** | 两次间隔至少N秒 | ⭐⭐ 较低 | 避免刷屏 |
| **always** | 每张都处理 | ⭐⭐⭐⭐⭐ 最高 | API充足 |

### 推荐配置 ✨

```bash
# 平衡模式（推荐）- 减少70%的API调用
/meme throttle_mode probability
/meme throttle_probability 0.3

# 节省模式 - 减少90%的API调用
/meme throttle_mode probability
/meme throttle_probability 0.1

# 严格限制 - 每5分钟最多处理一次
/meme throttle_mode interval
/meme throttle_interval 300
```

### 效果对比

假设每天收到100张图片：

| 配置 | 处理数量 | API节省 |
|-----|---------|---------|
| always | 100张 | 0% |
| probability 30% | ~30张 | 70% ⬇️ |
| probability 10% | ~10张 | 90% ⬇️ |
| interval 300秒 | 取决于分布 | 大幅减少 |

## ⚠️ 注意事项

- 插件支持自动使用当前会话的视觉模型，无需额外配置即可开始体验
- 视觉模型调用会消耗相应的API token，**强烈建议配置节流功能**以减少API消耗
- 实验性插件，不同的视觉模型对表情包分类的效果可能不同，建议根据实际情况选择合适的模型
- 如果有对我目前插件中提示词有优化想法的可以提个issue我测试测试
- 推荐使用 `probability` 模式 + 30%概率，可以在保持功能的同时大幅减少API消耗

### 🔄 升级相关
- **v2.0.8完全向后兼容**：可以直接从任何旧版本升级，无需担心数据丢失
- **代码质量优化**：根据AstrBot开发文档进行全面优化，提升稳定性和性能
- **API调用规范化**：严格遵循AstrBot公开API，避免使用内部API
- **错误处理改进**：完善的异常处理机制，更好的错误信息和日志记录
- **性能提升**：异步IO操作、智能缓存管理、资源自动清理
- **自动修复旧问题**：升级后会自动修复旧版本的配置同步和使用统计问题
- **渐进式迁移**：新功能会逐步生效，不影响现有功能的正常使用
- **优雅降级**：即使新功能出现问题，也会自动回退到旧版本逻辑

## 📚 详细文档

- [图片处理节流功能使用指南](image_processing_throttle_guide.md)
- [独立后台任务功能使用指南](independent_tasks_guide.md)
- [节流功能快速总结](throttle_feature_summary.md)

## 📄 许可证

本项目基于 MIT 许可证开源。

[![GitHub license](https://img.shields.io/github/license/nagatoquin33/astrbot_plugin_stealer)](https://github.com/nagatoquin33/astrbot_plugin_stealer/blob/main/LICENSE)

---

<div align="center">

**🎭 Happy meme collecting! 🎭**

**v2.0.8 - 代码质量优化，符合AstrBot开发规范！**

如果觉得这个插件有用，欢迎给个 ⭐ Star！

</div>





