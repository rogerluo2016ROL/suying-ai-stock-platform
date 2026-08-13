"""Kronos 模型核心纯函数 + tokenizer 前向形状契约测试。

注意：kronos.model.kronos 顶层 import torch，本地无 torch 时整个模块 skip；
prediction-service 容器（含 torch）内会真实运行。
"""
import pytest

pytest.importorskip("torch")

import pandas as pd
import torch

from kronos.model.kronos import (
    calc_time_stamps,
    top_k_top_p_filtering,
    sample_from_logits,
)


def test_calc_time_stamps_extracts_all_time_fields():
    """时间戳 → 5 个时间维字段（分钟/小时/星期/日/月）的编码契约。"""
    ts = pd.Series(pd.to_datetime(["2024-01-01 09:05:00"]))  # 2024-01-01 是周一
    df = calc_time_stamps(ts)
    assert list(df.columns) == ["minute", "hour", "weekday", "day", "month"]
    assert int(df.loc[0, "minute"]) == 5
    assert int(df.loc[0, "hour"]) == 9
    assert int(df.loc[0, "weekday"]) == 0  # Monday=0
    assert int(df.loc[0, "day"]) == 1
    assert int(df.loc[0, "month"]) == 1


def test_top_k_top_p_filtering_keeps_top_k_tokens():
    """top_k 只保留概率最高的 k 个 token，其余置 -inf。"""
    logits = torch.tensor([[0.1, 0.5, 0.2, 0.9, 0.3]])
    filtered = top_k_top_p_filtering(logits.clone(), top_k=2)
    assert filtered[0, 3].item() == pytest.approx(0.9)
    assert filtered[0, 1].item() == pytest.approx(0.5)
    assert filtered[0, 0].item() == float("-inf")
    assert filtered[0, 2].item() == float("-inf")
    assert filtered[0, 4].item() == float("-inf")


def test_top_k_top_p_filtering_noop_without_filters():
    """top_k=0 且 top_p=1.0 时不做任何过滤。"""
    logits = torch.tensor([[1.0, 2.0, 3.0]])
    filtered = top_k_top_p_filtering(logits.clone(), top_k=0, top_p=1.0)
    assert torch.equal(filtered, logits)


def test_sample_from_logits_returns_valid_indices():
    """采样返回 (batch, 1) 的合法 token 索引。"""
    torch.manual_seed(0)
    logits = torch.randn(4, 16)
    x = sample_from_logits(logits, temperature=0.8, top_k=3)
    assert x.shape == (4, 1)
    assert (x >= 0).all() and (x < 16).all()


def test_sample_from_logits_argmax_when_not_sampling():
    """sample_logits=False 时取 argmax（确定性）。"""
    torch.manual_seed(0)
    logits = torch.tensor([[0.1, 5.0, 0.2, 1.0]])
    x = sample_from_logits(logits, sample_logits=False)
    assert x.shape == (1, 1)
    assert x[0, 0].item() == 1  # 最大 logit 在 index 1


def test_tokenizer_forward_shapes():
    """KronosTokenizer 前向：输入 (B,T,d_in) → 输出重建 (B,T,d_in)。"""
    from kronos.model.kronos import KronosTokenizer

    tok = KronosTokenizer(
        d_in=4, d_model=16, n_heads=2, ff_dim=32,
        n_enc_layers=2, n_dec_layers=2,
        ffn_dropout_p=0.0, attn_dropout_p=0.0, resid_dropout_p=0.0,
        s1_bits=8, s2_bits=8, beta=0.25, gamma0=0.1, gamma=0.1, zeta=1.0, group_size=4,
    )
    x = torch.randn(2, 8, 4)
    (z_pre, z), bsq_loss, quantized, z_indices = tok(x)
    assert z_pre.shape == (2, 8, 4)
    assert z.shape == (2, 8, 4)
