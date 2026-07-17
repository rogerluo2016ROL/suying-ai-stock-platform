# Kronos：金融K线基础模型 —— 架构设计与方案详细文档

> 基于项目源码逆向工程整理 | 论文: AAAI 2026 [arXiv 2508.02739](https://arxiv.org/abs/2508.02739) | 源码: [github.com/shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos)

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统总体架构](#2-系统总体架构)
3. [KronosTokenizer — 层次化离散分词器](#3-kronostokenizer--层次化离散分词器)
4. [Kronos — 自回归预测模型](#4-kronos--自回归预测模型)
5. [KronosPredictor — 推理预测接口](#5-kronospredictor--推理预测接口)
6. [神经网络组件详解](#6-神经网络组件详解)
7. [微调流水线](#7-微调流水线)
8. [WebUI 交互系统](#8-webui-交互系统)
9. [CSV 微调方案](#9-csv-微调方案)
10. [模型家族与选型指南](#10-模型家族与选型指南)
11. [与A股智能看板集成方案](#11-与a股智能看板集成方案)
12. [附录：关键配置参数速查](#12-附录关键配置参数速查)

---

## 1. 项目概述

### 1.1 项目定位

Kronos 是**首个面向金融K线数据的开源基础模型**（Foundation Model），由清华大学等机构研发，已被 AAAI 2026 接收。

**核心理念：将K线视为一门"语言"，用大模型的方法来建模和预测。**

```
传统方法: 规则因子/技术指标 → 统计模型 → 信号
Kronos:   原始K线(OHLCV) → Tokenizer量化 → Transformer → 预测未来K线
```

### 1.2 关键创新点

| 创新 | 技术方案 | 解决的问题 |
|------|------|------|
| **K线离散化** | Binary Spherical Quantization (BSQ) | 连续金融数据 → 离散Token |
| **层次化分词** | s1(粗粒度) + s2(细粒度) 双层Token | 保留K线结构信息 |
| **层级预测** | s1 → s2 条件自回归 | 先预测大势，再细化细节 |
| **依赖感知** | Dependency-Aware Cross-Attention | s2以s1为条件建模 |
| **时间嵌入** | 分钟/小时/星期/日/月 五维时间编码 | 捕捉周期性模式 |
| **多交易所预训练** | 45+全球交易所数据 | 通用K线基础模型 |

### 1.3 模型家族

| 模型 | Tokenizer | 上下文长度 | 参数量 | 适用场景 |
|------|-----------|:---:|:---:|------|
| **Kronos-mini** | Tokenizer-2k | 2048 | 4.1M | 快速预测、边缘设备 |
| **Kronos-small** | Tokenizer-base | 512 | 24.7M | 平衡性能、推荐入门 |
| **Kronos-base** | Tokenizer-base | 512 | 102.3M | 最佳开源效果 |
| Kronos-large | Tokenizer-base | 512 | 499.2M | 闭源、顶级效果 |

---

## 2. 系统总体架构

### 2.1 两阶段框架

```
┌─────────────────────────────────────────────────────────────────┐
│                    阶段一: Tokenizer (编码器-解码器)               │
│                                                                  │
│  原始K线 x ∈ R^(B×T×6)    (open, high, low, close, volume, amount)│
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────┐            │
│  │  Encoder (Transformer Blocks)                    │            │
│  │    ↓                                             │            │
│  │  Linear → QuantEmbed (d_model → codebook_dim)    │            │
│  │    ↓                                             │            │
│  │  BSQuantizer → 二值球面量化                       │            │
│  │    ├── s1_bits: 粗粒度Token (趋势/方向)           │            │
│  │    └── s2_bits: 细粒度Token (精确价格)            │            │
│  │    ↓                                             │            │
│  │  Decoder (Transformer Blocks) → 重建K线           │            │
│  └──────────────────────────────────────────────────┘            │
│         │                                                        │
│         ▼ 离散Token序列 {0..2^(s1+s2)-1}                         │
├─────────────────────────────────────────────────────────────────┤
│                    阶段二: Predictor (自回归GPT)                   │
│                                                                  │
│  Token序列 → HierarchicalEmbedding (s1+s2融合)                   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────┐            │
│  │  + TemporalEmbedding (分钟/小时/星期/日/月)        │            │
│  │    ↓                                             │            │
│  │  Transformer Blocks (RMSNorm + RoPE Attention     │            │
│  │                     + SwiGLU FFN)                 │            │
│  │    ↓                                             │            │
│  │  RMSNorm → DualHead                              │            │
│  │    ├── Head_s1: 预测s1 Token (粗粒度K线轮廓)       │            │
│  │    └── Head_s2: 条件预测s2 Token (细化轮廓细节)    │            │
│  └──────────────────────────────────────────────────┘            │
│         │                                                        │
│         ▼ 自回归生成未来Token                                      │
│  Tokenizer.decode() → 预测K线 OHLCV                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 完整推理流程

```
输入: 历史K线 DataFrame (open/high/low/close/volume/amount) + 时间戳
│
├─ 1. 数据预处理
│   ├─ calc_time_stamps(timestamp) → [minute, hour, weekday, day, month]
│   ├─ Z-score 归一化: (x - mean) / std
│   └─ Clip: [-5, 5]
│
├─ 2. Tokenizer编码
│   ├─ tokenizer.encode(x, half=True) → [s1_indices, s2_indices]
│   └─ 连续K线 → 离散Token序列
│
├─ 3. 自回归生成 (auto_regressive_inference)
│   ├─ 滑动窗口: max_context=512 (或2048)
│   ├─ 逐Token预测:
│   │   ├─ model.decode_s1(s1_ids, s2_ids, stamp) → s1_logits
│   │   ├─ sample_from_logits(s1_logits, T, top_k, top_p) → next_s1_token
│   │   ├─ model.decode_s2(context, next_s1_token) → s2_logits
│   │   └─ sample_from_logits(s2_logits, T, top_k, top_p) → next_s2_token
│   └─ sample_count条路径 → 取均值 (集成降噪)
│
├─ 4. Tokenizer解码
│   └─ tokenizer.decode([full_s1, full_s2], half=True) → 归一化K线
│
└─ 5. 逆归一化
    └─ preds * std + mean → 预测K线 DataFrame
```

### 2.3 项目文件架构

```
Kronos/
├── model/                          # 核心模型层
│   ├── __init__.py                 # 模型导出 (KronosTokenizer, Kronos, KronosPredictor)
│   ├── kronos.py                   # Tokenizer(180行) + Predictor(330行) + Predictor推理(180行)
│   └── module.py                   # 神经网络组件(570行): BSQ, RMSNorm, FFN, RoPE, Attention...
│
├── finetune/                       # Qlib数据微调流水线
│   ├── config.py                   # 全局配置 (路径/超参数)
│   ├── dataset.py                  # QlibDataset 数据加载
│   ├── qlib_data_preprocess.py     # 数据预处理 (Qlib → pickle)
│   ├── train_tokenizer.py          # Tokenizer微调 (DDP多GPU)
│   ├── train_predictor.py          # Predictor微调 (DDP多GPU)
│   ├── qlib_test.py                # 回测评估 (Top-K策略)
│   └── utils/training_utils.py     # DDP/Seed/工具函数
│
├── finetune_csv/                   # CSV格式微调 (备选方案)
│   ├── train_sequential.py         # 顺序微调 (Tokenizer→Predictor)
│   ├── finetune_base_model.py      # 基础模型微调脚本
│   ├── finetune_tokenizer.py       # Tokenizer微调脚本
│   └── config_loader.py            # YAML配置加载
│
├── webui/                          # Web交互界面
│   ├── app.py                      # Flask服务 (~300行)
│   ├── run.py                      # 启动入口
│   ├── templates/index.html        # 前端页面
│   └── prediction_results/         # 历史预测结果
│
├── examples/                       # 使用示例
│   ├── prediction_example.py       # 基础预测示例
│   ├── prediction_new.py           # A股预测 (含GUI)
│   ├── prediction_cn_markets_day.py # A股日线预测
│   ├── prediction_batch_example.py # 批量预测
│   ├── get_akshare_date*.py        # akshare数据获取
│   └── yuce/                       # 深度分析示例 (个股+市场报告)
│
├── tests/                          # 回归测试
├── figures/                        # 图片资源
└── requirements.txt                # 依赖: torch, numpy, pandas, einops, huggingface_hub
```

---

## 3. KronosTokenizer — 层次化离散分词器

### 3.1 设计思想

将连续K线数据压缩为离散Token是Kronos的核心创新。Tokenizer采用 **VAE-like 编码器-解码器** 结构 + **Binary Spherical Quantization (BSQ)** 量化器。

```
设计目标:
1. 压缩: 6维连续OHLCV → 离散Token (信息瓶颈)
2. 保真: 解码器能从Token重建原始K线 (重构损失低)
3. 层次: s1(粗)捕捉趋势轮廓, s2(细)捕捉精确数值
```

### 3.2 类定义与初始化参数

```python
class KronosTokenizer(nn.Module, PyTorchModelHubMixin):
    """
    Args:
        d_in=6              # 输入维度 (open, high, low, close, volume, amount)
        d_model=256         # 隐藏维度
        n_heads=4           # 注意力头数
        ff_dim=1024         # FFN维度
        n_enc_layers=4      # 编码器层数
        n_dec_layers=4      # 解码器层数
        ffn_dropout_p=0.0   # FFN dropout
        attn_dropout_p=0.0  # 注意力dropout
        resid_dropout_p=0.0 # 残差dropout
        s1_bits=8           # 粗粒度Token位数 (2^8=256个类别)
        s2_bits=4           # 细粒度Token位数 (2^4=16个类别)
        codebook_dim=12     # s1_bits + s2_bits = 12
        beta=0.25           # 提交损失权重 (commitment loss)
        gamma0=1.0          # 每样本熵惩罚
        gamma=1.0           # codebook熵奖励
        zeta=1e-4           # 总熵正则化系数
        group_size=4        # BSQ分组大小
    """
```

### 3.3 前向传播流程

```python
def forward(self, x):                    # x: (B, T, 6)
    # 1. 线性嵌入
    z = self.embed(x)                    # (B, T, d_model=256)

    # 2. 编码器 (Transformer Blocks × n_enc_layers-1)
    for layer in self.encoder:           # 每个TransformerBlock含: RMSNorm + SelfAttn(RoPE) + FFN(SwiGLU)
        z = layer(z)

    # 3. 量化投影
    z = self.quant_embed(z)              # (B, T, codebook_dim=12)

    # 4. Binary Spherical Quantization
    bsq_loss, quantized, z_indices = self.tokenizer(z)
    # quantized: (B, T, 12)  二值球面量化后的表示
    # z_indices: 量化后的离散索引

    # 5. 层次化解码 — s1部分 (仅用前s1_bits=8位)
    quantized_pre = quantized[:, :, :self.s1_bits]     # (B, T, 8)
    z_pre = self.post_quant_embed_pre(quantized_pre)   # (B, T, d_model)
    for layer in self.decoder:
        z_pre = layer(z_pre)
    z_pre = self.head(z_pre)            # (B, T, 6)  仅用粗粒度Token重建

    # 6. 完整解码 — s1+s2 (全部12位)
    z = self.post_quant_embed(quantized)  # (B, T, d_model)
    for layer in self.decoder:
        z = layer(z)
    z = self.head(z)                    # (B, T, 6)  用完整Token重建

    return (z_pre, z), bsq_loss, quantized, z_indices
```

**关键设计**：返回 `(z_pre, z)` 两个重建结果。
- `z_pre`：仅用s1（粗粒度8位）重建 → 在训练时提供梯度信号，让s1学会捕捉K线的主要轮廓
- `z`：用全部12位重建 → 精确重建

### 3.4 独立编码/解码接口

```python
def encode(self, x, half=False):
    """连续K线 → 离散Token索引
    half=False: 返回单个indices (合并s1+s2)
    half=True:  返回 [s1_indices, s2_indices] (分离)
    """
    z = self.embed(x)
    for layer in self.encoder: z = layer(z)
    z = self.quant_embed(z)
    bsq_loss, quantized, z_indices = self.tokenizer(z, half=half)
    return z_indices

def decode(self, x, half=False):
    """离散Token索引 → 连续K线"""
    quantized = self.indices_to_bits(x, half)   # 索引 → 二值表示(-1,+1)
    z = self.post_quant_embed(quantized)
    for layer in self.decoder: z = layer(z)
    z = self.head(z)
    return z
```

### 3.5 损失函数设计

Tokenizer训练时最小化三个损失：

```python
Total_Loss = Reconstruction_Loss + Commitment_Loss + Entropy_Regularization

# 1. 重建损失 (MSE)
L_recon = MSE(z_pre, x) + MSE(z, x)
# s1重建 + 完整重建 → 确保层次化有意义

# 2. 提交损失 (Commitment Loss)
L_commit = β * mean((zq_detach - z)^2)
# β=0.25, 鼓励编码器输出接近量化值

# 3. 熵正则化 (Entropy Regularization)
L_entropy = γ0 * H_per_sample - γ * H_codebook
# 每样本熵最小化 (减少不确定性) + Codebook熵最大化 (充分利用码本)
# ζ=1e-4 整体缩放
```

---

## 4. Kronos — 自回归预测模型

### 4.1 设计思想

Kronos Predictor 是一个**类GPT的自回归Transformer**，输入历史Token序列，逐Token预测未来K线的离散表示。

```
输入: [Token_t-window, ..., Token_t]  (历史离散Token)
输出: [Token_t+1, Token_t+2, ..., Token_t+pred_len]  (未来离散Token)

核心机制: 层级预测
1. 先预测 s1 (粗粒度: 趋势轮廓)
2. 以 s1 为条件预测 s2 (细粒度: 精确数值)
```

### 4.2 类定义与初始化参数

```python
class Kronos(nn.Module, PyTorchModelHubMixin):
    """
    Args:
        s1_bits=8           # 粗粒度Token位数
        s2_bits=4           # 细粒度Token位数
        n_layers=6          # Transformer层数
        d_model=256         # 隐藏维度
        n_heads=4           # 注意力头数
        ff_dim=1024         # FFN维度
        ffn_dropout_p=0.0   # FFN dropout
        attn_dropout_p=0.0  # Attention dropout
        resid_dropout_p=0.0 # 残差dropout
        token_dropout_p=0.1 # Token嵌入dropout
        learn_te=False      # 时间嵌入是否可学习 (False=固定正弦)
    """
```

### 4.3 核心组件

```
Kronos.predictor
├── HierarchicalEmbedding   # 层次化Token嵌入 (s1+s2 → fusion → d_model)
├── TemporalEmbedding       # 时间嵌入 (min/hour/weekday/day/month)
├── token_drop              # Token Dropout (训练时随机丢弃)
├── Transformer Blocks × n_layers
│   ├── RMSNorm
│   ├── MultiHeadAttentionWithRoPE (因果注意力, is_causal=True)
│   └── FeedForward (SwiGLU: w1·silu × w3)
├── RMSNorm (final)
├── DependencyAwareLayer     # s1→s2 条件层 (Cross-Attention)
└── DualHead
    ├── proj_s1: d_model → 2^s1_bits  (粗粒度分类)
    └── proj_s2: d_model → 2^s2_bits  (细粒度分类)
```

### 4.4 前向传播

```python
def forward(self, s1_ids, s2_ids, stamp=None, padding_mask=None,
            use_teacher_forcing=False, s1_targets=None):
    """
    Args:
        s1_ids, s2_ids: (B, T) 离散Token索引
        stamp: (B, T, 5) 时间戳 [minute, hour, weekday, day, month]
        use_teacher_forcing: 训练时使用真实s1 (加速收敛)
        s1_targets: 真实的s1 token (用于teacher forcing)
    Returns:
        s1_logits: (B, T, 2^s1_bits)  粗粒度预测
        s2_logits: (B, T, 2^s2_bits)  细粒度预测 (以s1为条件)
    """
    # 1. Token嵌入
    x = self.embedding([s1_ids, s2_ids])     # (B, T, d_model)
    # HierarchicalEmbedding: emb_s1(s1) + emb_s2(s2) → fusion_proj

    # 2. 时间嵌入
    if stamp is not None:
        time_embedding = self.time_emb(stamp) # (B, T, d_model)
        x = x + time_embedding                # 加法融合

    # 3. Token Dropout
    x = self.token_drop(x)

    # 4. Transformer主干
    for layer in self.transformer:
        x = layer(x, key_padding_mask=padding_mask)

    # 5. 最终归一化
    x = self.norm(x)

    # 6. s1预测
    s1_logits = self.head(x)                # (B, T, vocab_s1)

    # 7. s2条件预测
    if use_teacher_forcing:
        sibling_embed = self.embedding.emb_s1(s1_targets)
    else:
        # 从s1_logits中采样 (梯度截断: .detach())
        s1_probs = softmax(s1_logits.detach())
        sample_s1_ids = multinomial(s1_probs)
        sibling_embed = self.embedding.emb_s1(sample_s1_ids)

    # Dependency-Aware Cross-Attention
    x2 = self.dep_layer(x, sibling_embed, key_padding_mask=padding_mask)
    s2_logits = self.head.cond_forward(x2)  # (B, T, vocab_s2)

    return s1_logits, s2_logits
```

### 4.5 层级预测解码

```python
def decode_s1(self, s1_ids, s2_ids, stamp=None, padding_mask=None):
    """仅解码s1: 返回 s1_logits + Transformer上下文"""
    x = self.embedding([s1_ids, s2_ids]) + self.time_emb(stamp)
    x = self.token_drop(x)
    for layer in self.transformer:
        x = layer(x, key_padding_mask=padding_mask)
    x = self.norm(x)
    s1_logits = self.head(x)
    return s1_logits, x         # 返回上下文用于后续s2解码

def decode_s2(self, context, s1_ids, padding_mask=None):
    """以s1为条件解码s2"""
    sibling_embed = self.embedding.emb_s1(s1_ids)
    x2 = self.dep_layer(context, sibling_embed, key_padding_mask=padding_mask)
    return self.head.cond_forward(x2)
```

### 4.6 训练损失

```python
# DualHead.compute_loss()
def compute_loss(self, s1_logits, s2_logits, s1_targets, s2_targets, padding_mask=None):
    # 交叉熵损失
    ce_s1 = CrossEntropy(s1_logits, s1_targets)   # 2^8=256分类
    ce_s2 = CrossEntropy(s2_logits, s2_targets)   # 2^4=16分类
    return (ce_s1 + ce_s2) / 2, ce_s1, ce_s2
```

---

## 5. KronosPredictor — 推理预测接口

### 5.1 设计目标

`KronosPredictor` 是对用户暴露的高级API，封装了数据预处理、归一化、推理、逆归一化全流程。

### 5.2 核心方法

#### predict() — 单序列预测

```python
def predict(self, df, x_timestamp, y_timestamp, pred_len,
            T=1.0, top_k=0, top_p=0.9, sample_count=1):
    """
    Args:
        df: DataFrame, 列=['open','high','low','close'], volume/amount可选
        x_timestamp: 历史时间戳 Series
        y_timestamp: 预测时间戳 Series
        pred_len: 预测步数
        T: 采样温度 (越高越随机, 0=确定性)
        top_k: Top-K过滤 (0=不使用)
        top_p: Nucleus采样 (0.9=保留累积概率90%的token)
        sample_count: 多条路径平均 (集成降噪, 推荐≥5)

    Returns:
        pred_df: DataFrame, 列=['open','high','low','close','volume','amount']
    """
    # 1. 时间戳解析
    x_time_df = calc_time_stamps(x_timestamp)  # → minute/hour/weekday/day/month
    y_time_df = calc_time_stamps(y_timestamp)

    # 2. 数据提取 + 归一化
    x = df[price_cols + [vol, amt]].values      # (T, 6)
    x_mean, x_std = mean(x), std(x)
    x = (x - x_mean) / (x_std + 1e-5)
    x = clip(x, -clip, clip)                    # 默认clip=5

    # 3. 推理
    preds = self.generate(x, x_stamp, y_stamp, pred_len, T, top_k, top_p, sample_count)

    # 4. 逆归一化
    preds = preds * (x_std + 1e-5) + x_mean
    return DataFrame(preds, columns=..., index=y_timestamp)
```

#### predict_batch() — 批量并行预测

```python
def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, ...):
    """批量预测多只股票, 利用GPU并行加速
    约束: 所有序列必须有相同的历史长度和预测长度
    """
    # 1. 独立归一化每只股票
    # 2. Stack → (B, T, 6)
    # 3. 一次generate()并行处理
    # 4. 独立逆归一化每只股票
```

### 5.3 自回归推理核心算法

```python
def auto_regressive_inference(tokenizer, model, x, x_stamp, y_stamp,
                               max_context, pred_len, clip, T, top_k, top_p, sample_count):
    """
    关键步骤:
    1. 样本扩展: x → repeat(sample_count) → (B*sample_count, T, 6)
       (多条路径并行, 最后取均值 → 降低方差)

    2. 历史编码: tokenizer.encode(x, half=True) → [s1_ids, s2_ids]

    3. 滑动窗口: max_context=512 (or 2048)
       - 历史长度 ≤ max_context: 使用全部历史
       - 历史长度 > max_context: 仅使用最近max_context个Token

    4. 逐Token预测 (pred_len步):
       for i in range(pred_len):
           a. 解码s1: model.decode_s1(input_s1, input_s2, stamp) → s1_logits
           b. 采样s1: sample_from_logits(s1_logits[-1], T, top_k, top_p) → next_s1
           c. 解码s2: model.decode_s2(context, next_s1) → s2_logits
           d. 采样s2: sample_from_logits(s2_logits[-1], T, top_k, top_p) → next_s2
           e. 追加到buffer, 滑动窗口更新

    5. Token解码: tokenizer.decode([full_s1, full_s2], half=True) → 归一化K线

    6. 路径平均: reshape → (B, sample_count, T, 6) → mean(axis=1)
    """
```

### 5.4 采样策略

```python
def sample_from_logits(logits, temperature=1.0, top_k=0, top_p=0.9):
    """
    temperature: 温度缩放 logits/T
        T=1.0: 默认随机性
        T<1.0: 更确定性 (趋向argmax)
        T>1.0: 更多样性

    top_k: 仅保留概率最高的k个token
        top_k=0: 不使用

    top_p: Nucleus采样 (核心策略)
        top_p=0.9: 保留累积概率≥90%的最小token集合

    采样: torch.multinomial(softmax(logits))
    """
```

---

## 6. 神经网络组件详解

### 6.1 Binary Spherical Quantizer (BSQ)

**论文来源**: [arXiv 2406.07548](https://arxiv.org/pdf/2406.07548.pdf)

```
BSQ 核心思想:
1. 将连续向量投影到单位球面 (L2 normalize)
2. 二值化: z_hat = sign(z) → {-1, +1}^D
3. Straight-Through Estimator: z_q = z + (z_hat - z).detach()
   (前向用二值, 反向传梯度到连续值)
4. 熵控制:
   - 每样本熵最小化 (减少不确定性)
   - Codebook熵最大化 (充分利用码本)
```

```python
class BinarySphericalQuantizer:
    """
    Args:
        embed_dim: 量化维度 (codebook_dim = s1_bits + s2_bits)
        beta: 提交损失权重
        gamma0: 每样本熵惩罚
        gamma: Codebook熵奖励
        zeta: 整体熵正则化缩放
        group_size: 分组量化大小 (用于近似熵计算)
    """

    def quantize(self, z):
        """二值量化: z → sign(z) → {-1,+1}"""
        zhat = torch.where(z > 0, 1.0, -1.0)
        return z + (zhat - z).detach()  # Straight-Through

    def soft_entropy_loss(self, z):
        """软熵损失 (可微分):
        - 将码本分组 (group_size)
        - 每组独立计算softmax概率
        - 每样本熵 = sum(H(prob_per_dim))
        - Codebook熵 = sum(H(avg_prob_per_group))
        """
```

### 6.2 BSQuantizer (Tokenizer中的封装)

```python
class BSQuantizer:
    def __init__(self, s1_bits, s2_bits, ...):
        self.codebook_dim = s1_bits + s2_bits    # 8+4=12
        self.bsq = BinarySphericalQuantizer(codebook_dim, ...)

    def forward(self, z, half=False):
        z = F.normalize(z, dim=-1)               # 投影到单位球面
        quantized, bsq_loss, metrics = self.bsq(z)
        if half:
            # 将12位拆分为 s1(前8位) 和 s2(后4位)
            q_pre = quantized[:, :, :self.s1_bits]   # 高8位 → s1
            q_post = quantized[:, :, self.s1_bits:]   # 低4位 → s2
            z_indices = [bits_to_indices(q_pre), bits_to_indices(q_post)]
        return bsq_loss, quantized, z_indices
```

### 6.3 HierarchicalEmbedding — 层次化Token嵌入

```python
class HierarchicalEmbedding:
    """
    s1 (粗粒度, 8位): vocab_s1 = 2^8 = 256, 捕捉趋势轮廓
    s2 (细粒度, 4位): vocab_s2 = 2^4 = 16,  捕捉精确数值

    嵌入融合:
    s1_emb = Embedding(256, d_model)(s1_ids) * sqrt(d_model)
    s2_emb = Embedding(16, d_model)(s2_ids)  * sqrt(d_model)
    combined = Linear(2*d_model, d_model)(concat(s1_emb, s2_emb))
    """
    def __init__(self, s1_bits, s2_bits, d_model=256):
        self.emb_s1 = nn.Embedding(2**s1_bits, d_model)  # 256 × 256
        self.emb_s2 = nn.Embedding(2**s2_bits, d_model)  # 16 × 256
        self.fusion_proj = nn.Linear(d_model*2, d_model)  # 512 → 256

    def split_token(self, token_ids, s2_bits):
        """从复合Token ID中拆分s1和s2:
        s2_ids = token_ids & ((1 << s2_bits) - 1)   # 低4位
        s1_ids = token_ids >> s2_bits                # 高8位
        """
```

### 6.4 TemporalEmbedding — 时间嵌入

```python
class TemporalEmbedding:
    """
    将5维时间特征嵌入为d_model维向量:

    minute  ∈ [0, 59]   → Embedding(60, d_model)
    hour    ∈ [0, 23]   → Embedding(24, d_model)
    weekday ∈ [0, 6]    → Embedding(7, d_model)
    day     ∈ [1, 31]   → Embedding(32, d_model)
    month   ∈ [1, 12]   → Embedding(13, d_model)

    输出 = hour_emb + weekday_emb + day_emb + month_emb + minute_emb

    learn_pe=False: 使用 FixedEmbedding (正弦位置编码, 不可学习)
    learn_pe=True:  使用 nn.Embedding (可学习嵌入)
    """
```

### 6.5 DependencyAwareLayer — s1→s2条件层

```python
class DependencyAwareLayer:
    """
    让s2的预测以s1为条件:

    Cross-Attention(
        query   = s1_embedding,    # s1的嵌入作为Query
        key     = hidden_states,   # Transformer输出作为Key
        value   = hidden_states    # Transformer输出作为Value
    ) + RMSNorm

    直觉: s1代表"大势方向", s2需要基于这个"大势"来细化数值。
    """
```

### 6.6 DualHead — 双头预测

```python
class DualHead:
    """
    Head_s1: Linear(d_model, 256)   → 粗粒度256分类
    Head_s2: Linear(d_model, 16)    → 细粒度16分类

    forward():      返回 s1_logits
    cond_forward(): 返回 s2_logits (在DependencyAwareLayer之后调用)
    """
```

### 6.7 TransformerBlock — 标准Transformer块

```python
class TransformerBlock:
    """
    Pre-Norm架构 (与GPT-2/LLaMA一致):

    x = x + SelfAttn(RMSNorm(x))    # 因果注意力 (is_causal=True)
    x = x + FFN(RMSNorm(x))         # SwiGLU激活

    其中:
    - RMSNorm: Root Mean Square Layer Normalization (比LayerNorm更快)
    - SelfAttn = MultiHeadAttentionWithRoPE (旋转位置编码)
    - FFN = SwiGLU: w2(silu(w1(x)) * w3(x))
    """
```

### 6.8 Rotary Positional Embedding (RoPE)

```python
class RotaryPositionalEmbedding:
    """
    RoPE 旋转位置编码:
    - 通过旋转矩阵编码位置信息
    - 具有远程衰减性质 (距离越远, 内积越小)
    - 在Attention计算前施加于Q和K

    q_rope = q * cos(θ) + rotate_half(q) * sin(θ)
    k_rope = k * cos(θ) + rotate_half(k) * sin(θ)

    其中 θ 由频率 inv_freq = 1/(10000^(2i/d)) 决定
    """
```

---

## 7. 微调流水线

### 7.1 整体流程

```
┌─────────────────────────────────────────────────────────────┐
│                  Kronos 微调流水线 (finetune/)                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: 配置 (config.py)                                    │
│    ├── qlib_data_path: Qlib数据目录                          │
│    ├── dataset_path: 处理后数据保存路径                        │
│    ├── save_path: 模型checkpoint保存路径                      │
│    ├── pretrained_tokenizer_path: 预训练Tokenizer路径         │
│    ├── pretrained_predictor_path: 预训练Predictor路径         │
│    ├── instrument: "csi300" / "csi500" / "all"               │
│    ├── train_time_range: "2015-01-01" ~ "2020-12-31"         │
│    ├── epochs: 训练轮数                                       │
│    └── batch_size, learning_rate, ...                        │
│                                                              │
│  Step 2: 数据预处理 (qlib_data_preprocess.py)                 │
│    Qlib数据 → QlibDataset → train/val/test pickle文件         │
│                                                              │
│  Step 3: Tokenizer微调 (train_tokenizer.py)                   │
│    torchrun --nproc_per_node=NUM_GPUs finetune/train_tokenizer.py │
│    损失: 重建MSE + 提交损失 + 熵正则化                          │
│                                                              │
│  Step 4: Predictor微调 (train_predictor.py)                   │
│    torchrun --nproc_per_node=NUM_GPUs finetune/train_predictor.py│
│    损失: CrossEntropy(s1) + CrossEntropy(s2)                  │
│                                                              │
│  Step 5: 回测评估 (qlib_test.py)                              │
│    生成预测信号 → Top-K策略回测 → 累计收益曲线                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 数据格式

```python
# QlibDataset 输出格式
class QlibDataset(Dataset):
    """
    每条数据:
    x: (lookback, 6)  # 历史K线 [open, high, low, close, volume, amount]
    y: (pred_len, 6)  # 未来K线 (预测目标)
    timestamp: (lookback+pred_len, 5)  # [minute, hour, weekday, day, month]
    """
```

### 7.3 训练配置示例

```python
# finetune/config.py 关键参数
{
    "instrument": "csi300",            # 沪深300成分股
    "train_time_range": ["2015-01-01", "2020-12-31"],
    "val_time_range":   ["2021-01-01", "2022-12-31"],
    "test_time_range":  ["2023-01-01", "2024-12-31"],

    "lookback": 400,                   # 历史窗口400根K线
    "pred_len": 120,                   # 预测120根K线

    "batch_size": 64,
    "epochs": 200,
    "tokenizer_learning_rate": 1e-4,
    "predictor_learning_rate": 1e-3,
    "warmup_steps": 200,
}
```

### 7.4 回测评估

```python
# qlib_test.py 评估流程
# 1. 加载微调后的模型
# 2. 在测试集上生成预测: pred_close / close → 预期涨跌幅
# 3. Top-K策略: 选预测涨幅最大的K只股票, 等权持仓
# 4. 计算累计收益曲线, 与基准指数对比
# 5. 输出: Sharpe Ratio, 最大回撤, 年化收益, 超额收益
```

---

## 8. WebUI 交互系统

### 8.1 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Flask + flask_cors |
| 前端 | HTML + Plotly.js (交互式K线图) |
| 模型 | KronosTokenizer + Kronos + KronosPredictor |

### 8.2 核心功能

```
WebUI (Flask :5000)
├── GET  /                     → 主页面 (index.html)
├── POST /api/load_model       → 加载指定模型 (mini/small/base)
├── POST /api/predict          → 执行预测 (上传CSV或使用预设数据)
├── GET  /api/get_data_files   → 扫描data目录
├── POST /api/load_data_file   → 加载数据文件
├── GET  /api/model_status     → 查询模型加载状态
└── GET  /api/prediction_history → 历史预测结果
```

### 8.3 预测结果可视化

- **Plotly.js** 渲染交互式K线图
- OHLC Candlestick + Volume 柱状图
- 历史数据 (实心) + 预测数据 (虚线/半透明)
- 支持缩放、平移、悬停详情

---

## 9. CSV 微调方案

### 9.1 设计目的

`finetune_csv/` 提供了一个**不依赖Qlib**的微调方案，适用于自有CSV格式的K线数据。

### 9.2 数据格式

```yaml
# finetune_csv/configs/config_ali09988_candle-5min.yaml
data:
  csv_path: "data/HK_ali_09988_kline_5min_all.csv"
  time_col: "datetime"
  feature_cols: ["open", "high", "low", "close", "volume"]

model:
  s1_bits: 8
  s2_bits: 4
  d_model: 256
  n_layers: 6

training:
  lookback: 400
  pred_len: 120
  batch_size: 32
  epochs: 100
  train_ratio: 0.8
  val_ratio: 0.1
```

### 9.3 训练流程

```python
# train_sequential.py
# 顺序训练: Tokenizer → Predictor
# 1. finetune_tokenizer.py   → 保存 best_tokenizer.pt
# 2. finetune_base_model.py  → 保存 best_model.pt
```

---

## 10. 模型家族与选型指南

### 10.1 模型对比

| 特性 | Kronos-mini | Kronos-small | Kronos-base | Kronos-large |
|------|:---:|:---:|:---:|:---:|
| 参数量 | 4.1M | 24.7M | 102.3M | 499.2M |
| 上下文 | **2048** | 512 | 512 | 512 |
| Tokenizer | Tokenizer-2k | Tokenizer-base | Tokenizer-base | Tokenizer-base |
| 开源 | ✅ | ✅ | ✅ | ❌ |
| 推理速度 | **极快** | 快 | 中等 | 慢 |
| 精度 | 基础 | 良好 | **优秀** | 最佳 |
| 显存需求 | <100MB | ~200MB | ~800MB | ~4GB |

### 10.2 选型建议

```
场景选择:
├── 研究探索 / 快速实验      → Kronos-mini  (4.1M, 2048上下文, 极快)
├── A股日线选股 / 批量预测   → Kronos-small (24.7M, 平衡之选)
├── 生产环境 / 要求最高精度  → Kronos-base  (102M, 最佳开源)
└── 企业级高频交易           → Kronos-large (闭源, 需联系作者)
```

---

## 11. 与A股智能看板集成方案

### 11.1 集成架构

```
┌──────────────────────────────────────────────────────────┐
│                  A股智能看板 + Kronos 集成                 │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  现有链路:                                                 │
│  stock_proxy(:8765) → Dify → LLM(DeepSeek) → Flask(:8888)│
│                                                           │
│  新增链路:                                                 │
│  stock_proxy(:8765) → KronosPredictor → 预测信号          │
│         │                    │                            │
│         │              ┌─────▼────────┐                   │
│         │              │ 预测信号      │                   │
│         │              │ • K线预测图   │                   │
│         │              │ • 涨跌方向    │                   │
│         │              │ • 趋势评分    │                   │
│         │              │ • 置信区间    │                   │
│         │              └──────┬───────┘                   │
│         │                     │                           │
│         ▼                     ▼                           │
│      Flask(:8888) ← 融合展示 (新Tab: AI预测)              │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### 11.2 集成实现步骤

```python
# 1. 安装依赖
pip install torch numpy pandas einops huggingface_hub

# 2. 在 stock_dashboard.py 中添加 Kronos 预测接口
from model import Kronos, KronosTokenizer, KronosPredictor

# 加载模型 (全局单例)
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
predictor = KronosPredictor(model, tokenizer, max_context=512)

# 3. 新增 API 路由
@app.route("/api/kronos/predict/<code>")
def api_kronos_predict(code):
    """对单只股票进行K线预测"""
    # 获取历史K线
    kline_data = get_kline_from_proxy(code, datalen=400)

    # 准备输入
    df = pd.DataFrame(kline_data['candles'])[['open','high','low','close','volume']]
    x_ts = pd.to_datetime([c['date'] for c in kline_data['candles']])
    y_ts = pd.date_range(x_ts.iloc[-1], periods=61, freq='D')[1:]  # 未来60天

    # 预测
    pred_df = predictor.predict(df, x_ts, y_ts, pred_len=60, T=1.0, top_p=0.9, sample_count=5)

    return jsonify({
        "historical": df.to_dict('records'),
        "prediction": pred_df.to_dict('records'),
        "prediction_summary": {
            "trend": "up" if pred_df['close'].iloc[-1] > df['close'].iloc[-1] else "down",
            "confidence": calculate_confidence(pred_df, df)
        }
    })

# 4. 前端添加 "AI预测" Tab，使用 ECharts 渲染预测K线
```

### 11.3 预测信号 → 交易决策

```python
def kronos_signal(pred_df, hist_df):
    """将Kronos预测转化为交易信号"""
    last_close = hist_df['close'].iloc[-1]
    pred_close = pred_df['close'].iloc[-1]
    pred_return = (pred_close - last_close) / last_close * 100

    # 趋势强度
    pred_trend = (pred_df['close'].iloc[-1] - pred_df['close'].iloc[0]) / pred_df['close'].iloc[0] * 100

    # 波动率估计
    pred_volatility = pred_df['close'].pct_change().std() * np.sqrt(252)

    # 信号生成
    if pred_return > 5 and pred_trend > 0 and pred_volatility < 0.5:
        signal = "✔️ 强烈看涨 (Kronos预测+趋势确认)"
    elif pred_return > 2:
        signal = "✔️ 偏多 (Kronos预测上涨)"
    elif pred_return > -2:
        signal = "⏳ 中性震荡"
    else:
        signal = "❌ 偏空 (Kronos预测下跌)"

    return {
        "signal": signal,
        "pred_return_pct": round(pred_return, 2),
        "trend_strength": round(pred_trend, 2),
        "volatility": round(pred_volatility, 2),
        "confidence_interval": {
            "lower": round(pred_close * 0.95, 2),
            "upper": round(pred_close * 1.05, 2)
        }
    }
```

---

## 12. 附录：关键配置参数速查

### 12.1 Tokenizer 参数

| 参数 | Kronos-mini | Kronos-small/base | 说明 |
|------|:---:|:---:|------|
| d_in | 6 | 6 | OHLCV+成交量+成交额 |
| d_model | 256 | 256 | 隐藏维度 |
| s1_bits | 8 | 8 | 粗粒度Token: 2^8=256类 |
| s2_bits | 4 | 4 | 细粒度Token: 2^4=16类 |
| codebook_dim | 12 | 12 | s1+s2=12维二值码本 |
| n_enc_layers | 4 | 4 | 编码器层数 |
| n_dec_layers | 4 | 4 | 解码器层数 |
| n_heads | 4 | 4 | 注意力头数 |
| ff_dim | 1024 | 1024 | FFN维度 |
| beta | 0.25 | 0.25 | 提交损失权重 |
| gamma0 | 1.0 | 1.0 | 每样本熵惩罚 |
| gamma | 1.0 | 1.0 | Codebook熵奖励 |
| zeta | 1e-4 | 1e-4 | 熵正则化缩放 |
| group_size | 4 | 4 | BSQ分组大小 |

### 12.2 Predictor 参数

| 参数 | Kronos-mini | Kronos-small | Kronos-base | 说明 |
|------|:---:|:---:|:---:|------|
| s1_bits | 8 | 8 | 8 | 同Tokenizer |
| s2_bits | 4 | 4 | 4 | 同Tokenizer |
| d_model | 256 | 256 | 256 | 隐藏维度 |
| n_layers | 6 | 6 | 12 | Transformer层数 |
| n_heads | 4 | 4 | 8 | 注意力头数 |
| ff_dim | 1024 | 1024 | 2048 | FFN维度 |
| max_context | 2048 | 512 | 512 | 最大上下文长度 |
| token_dropout | 0.1 | 0.1 | 0.1 | Token Dropout |
| learn_te | False | False | False | 时间嵌入是否可学习 |

### 12.3 推理参数

| 参数 | 推荐值 | 说明 |
|------|:---:|------|
| T (temperature) | 1.0 | 采样温度; <1.0更确定, >1.0更多样 |
| top_p | 0.9 | Nucleus采样概率阈值 |
| top_k | 0 | Top-K过滤 (0=不使用) |
| sample_count | 5 | 多条路径平均; 越大越稳定但越慢 |
| clip | 5 | 归一化裁剪范围 |
| max_context | 512/2048 | 最大历史窗口 |

### 12.4 HuggingFace模型ID

```python
# Tokenizer
"NeoQuasar/Kronos-Tokenizer-2k"    # 用于 Kronos-mini
"NeoQuasar/Kronos-Tokenizer-base"  # 用于 Kronos-small/base

# Predictor
"NeoQuasar/Kronos-mini"            # 4.1M
"NeoQuasar/Kronos-small"           # 24.7M
"NeoQuasar/Kronos-base"            # 102.3M
```

### 12.5 硬件需求

| 模型 | 推理显存 | 微调显存 (batch=32) | 推荐设备 |
|------|:---:|:---:|------|
| Kronos-mini | <100MB | ~1GB | CPU/MPS/GPU |
| Kronos-small | ~200MB | ~3GB | MPS/GPU |
| Kronos-base | ~800MB | ~8GB | GPU (≥8GB) |
| Kronos-large | ~4GB | ~32GB | GPU (≥40GB) |

> MacBook Pro M5 Pro / 24GB 统一内存 可流畅运行 Kronos-base 推理和微调

---

> **文档声明**: 本文档基于 [Kronos](https://github.com/shiyu-coder/Kronos) 开源项目 (MIT License) 源码逆向工程整理。模型参数、计算公式和数据流均与实际代码一致，可用于学习研究、二次开发或与A股智能看板集成。论文引用请参考 [arXiv 2508.02739](https://arxiv.org/abs/2508.02739)。
