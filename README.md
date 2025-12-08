# 🌟 表情包小偷

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python Version](https://img.shields.io/badge/Python-3.10.14%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen)](CONTRIBUTING.md)
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
  - [📝 使用指令](#-使用指令)
  - [⚠️ 注意事项](#️-注意事项)
  - [📄 许可证](#-许可证)

## 📢 简介

我想仿照麦麦的表情包偷取做个娱乐性的插件的，于是就有了这个表情包小偷插件！

本插件可以自动偷取聊天中的图片，进行多模态理解与情绪分类，并在发送回复前按合适的概率追加一张匹配情绪的表情，提升互动体验。


## 主要功能
- 自动监听聊天中的图片消息。
- 使用视觉模型生成图片描述、标签与情绪分类。
- 支持多种情绪分类，包括开心、悲伤、愤怒、惊讶等。
- 在回复发送前按合适的概率追加一张匹配情绪的表情。
- 支持内容审核功能，过滤不符合要求的图片。
- 自动管理存储空间，定期清理过期文件。

## 📦 安装方法

1. 确保已安装 AstrBot
2. 将插件复制到 AstrBot 的插件目录：`AstrBot/data/plugins`
3. 或在 Dashboard 插件中心直接安装
4. 重启 AstrBot 或使用热加载命令

## 🛠️ 快速上手

### 1. 模型配置

设置视觉模型（用于图片分类）：
```bash
meme set_vision <provider_id>
```

> **注意**：视觉模型需要支持图片输入（如 Gemini, 豆包, qwen vl 等）

### 2. 功能开启

开启插件：
```bash
meme on
```

关闭插件：
```bash
meme off
```

开启自动随聊表情：
```bash
meme auto_on
```

关闭自动随聊表情：
```bash
meme auto_off
```

### 3. 基本使用

查看当前插件状态：
```bash
meme status
```

## ⚙️ 配置说明

插件提供以下配置选项，可在后台或配置文件中设置：

| 配置项 | 类型 | 默认值 | 描述 |
|--------|------|--------|------|
| `enabled` | bool | true | 是否启用整个插件功能 |
| `auto_send` | bool | true | 是否自动随聊追加表情包 |
| `vision_provider_id` | string | null | 视觉模型提供商ID（用于图片分类） |
| `emoji_chance` | float | 0.4 | 触发表情动作的基础概率 |
| `max_reg_num` | int | 100 | 允许注册的最大表情数量 |
| `do_replace` | bool | true | 达到上限时是否替换旧表情 |
| `maintenance_interval` | int | 10 | 后台维护任务的执行周期（分钟），包括容量控制和文件清理 |
| `steal_emoji` | boolean | true | 是否开启聊天图片偷取和清理功能（关闭后将停止偷取新图片并暂停所有清理操作） |
| `content_filtration` | bool | false | 是否开启内容审核 |

| `raw_retention_hours` | int | 24 | raw目录和categories/未分类目录中图片的保留期限（小时） |
| `raw_clean_interval` | int | 60 | raw目录和categories/未分类目录的清理时间间隔（分钟） |

## 🗑️ 文件清理机制

插件实现了自动的文件清理机制，确保不会占用过多存储空间。清理机制与偷图功能绑定，由以下配置项协同工作：

### 配置项协同原理

1. **核心开关 (`steal_emoji`)**：
   - 控制偷图和清理功能的总开关
   - 关闭后将停止偷取新图片并暂停所有清理操作

2. **保留期限 (`raw_retention_hours`)**：
   - 定义文件在系统中可以保留的最长时间
   - 默认24小时，超过此时间的文件会被视为"过期文件"

3. **清理时间间隔 (`raw_clean_interval`)**：
   - 定义清理操作的执行频率
   - 默认60分钟，每间隔这段时间执行一次清理操作

### 工作流程

1. 当`steal_emoji`开启时，系统每经过`raw_clean_interval`分钟执行一次清理操作
2. 每次清理时，会检查raw目录和categories/未分类目录中所有文件的修改时间
3. 删除所有修改时间超过`raw_retention_hours`小时的文件

### 清理范围

- **raw目录**：存放原始图片文件
- **categories/未分类目录**：存放尚未分类完成的图片文件
- **已分类的图片**：通过容量控制机制(`max_reg_num`和`do_replace`)进行管理

### 示例（默认配置）

- 系统每60分钟执行一次清理操作
- 每次清理时，删除所有超过24小时的文件
- 这样确保了文件不会无限期保留，同时避免了过于频繁的清理操作影响性能


## 📝 使用指令

| 指令 | 描述 |
|------|------|
| `meme on` | 开启偷表情包功能 |
| `meme off` | 关闭偷表情包功能 |
| `meme set_vision <provider_id>` | 设置视觉模型 |
| `meme show_providers` | 查看当前模型配置 |
| `meme auto_on` | 开启自动随聊表情 |
| `meme auto_off` | 关闭自动随聊表情 |
| `meme status` | 查看当前插件状态 |

| `meme push <category> [alias]` | 推送指定分类的表情包（管理员指令） |
| `meme debug_image` | 调试图片处理（管理员指令） |

## ⚠️ 注意事项

- 本插件为本人的实验性插件（AI做的），若出现bug还请提交issue
- 开启视觉模型可能会比较消耗token，我也在找解决办法
- 建议根据实际情况调整表情包偷取的概率和数量
- 内容审核功能需要配合合适的提示词使用

## 📄 许可证

本项目基于 MIT 许可证开源。

[![GitHub license](https://img.shields.io/github/license/nagatoquin33/astrbot_plugin_stealer)](https://github.com/nagatoquin33/astrbot_plugin_stealer/blob/main/LICENSE)


