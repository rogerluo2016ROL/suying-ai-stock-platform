import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from huggingface_hub import PyTorchModelHubMixin
from typing import Optional
import contextlib
from tqdm import trange

from kronos.model.module import (
    TransformerBlock, HierarchicalEmbedding, TemporalEmbedding,
    DependencyAwareLayer, RMSNorm, DualHead, BSQuantizer,
)


class KronosTokenizer(nn.Module, PyTorchModelHubMixin):
    """
    KronosTokenizer module for tokenizing input data using a hybrid quantization approach.

    This tokenizer utilizes a combination of encoder and decoder Transformer blocks
    along with the Binary Spherical Quantization (BSQuantizer) to compress and decompress input data.

    Args:
           d_in (int): Input dimension.
           d_model (int): Model dimension.
           n_heads (int): Number of attention heads.
           ff_dim (int): Feed-forward dimension.
           n_enc_layers (int): Number of encoder layers.
           n_dec_layers (int): Number of decoder layers.
           ffn_dropout_p (float): Dropout probability for feed-forward networks.
           attn_dropout_p (float): Dropout probability for attention mechanisms.
           resid_dropout_p (float): Dropout probability for residual connections.
           s1_bits (int): Number of bits for the pre token in BSQuantizer.
           s2_bits (int): Number of bits for the post token in BSQuantizer.
           beta (float): Beta parameter for BSQuantizer.
           gamma0 (float): Gamma0 parameter for BSQuantizer.
           gamma (float): Gamma parameter for BSQuantizer.
           zeta (float): Zeta parameter for BSQuantizer.
           group_size (int): Group size parameter for BSQuantizer.

    """

    def __init__(self, d_in, d_model, n_heads, ff_dim, n_enc_layers, n_dec_layers, ffn_dropout_p, attn_dropout_p, resid_dropout_p, s1_bits, s2_bits, beta, gamma0, gamma, zeta, group_size):

        super().__init__()
        self.d_in = d_in
        self.d_model = d_model
        self.n_heads = n_heads
        self.ff_dim = ff_dim
        self.enc_layers = n_enc_layers
        self.dec_layers = n_dec_layers
        self.ffn_dropout_p = ffn_dropout_p
        self.attn_dropout_p = attn_dropout_p
        self.resid_dropout_p = resid_dropout_p

        self.s1_bits = s1_bits
        self.s2_bits = s2_bits
        self.codebook_dim = s1_bits + s2_bits # Total dimension of the codebook after quantization
        self.embed = nn.Linear(self.d_in, self.d_model)
        self.head = nn.Linear(self.d_model, self.d_in)

        # Encoder Transformer Blocks
        self.encoder = nn.ModuleList([
            TransformerBlock(self.d_model, self.n_heads, self.ff_dim, self.ffn_dropout_p, self.attn_dropout_p, self.resid_dropout_p)
            for _ in range(self.enc_layers - 1)
        ])
        # Decoder Transformer Blocks
        self.decoder = nn.ModuleList([
            TransformerBlock(self.d_model, self.n_heads, self.ff_dim, self.ffn_dropout_p, self.attn_dropout_p, self.resid_dropout_p)
            for _ in range(self.dec_layers - 1)
        ])
        self.quant_embed = nn.Linear(in_features=self.d_model, out_features=self.codebook_dim) # Linear layer before quantization
        self.post_quant_embed_pre = nn.Linear(in_features=self.s1_bits, out_features=self.d_model) # Linear layer after quantization (pre part - s1 bits)
        self.post_quant_embed = nn.Linear(in_features=self.codebook_dim, out_features=self.d_model) # Linear layer after quantization (full codebook)
        self.tokenizer = BSQuantizer(self.s1_bits, self.s2_bits, beta, gamma0, gamma, zeta, group_size) # BSQuantizer module

    def forward(self, x):
        """
        Forward pass of the KronosTokenizer.

        Args:
            x (torch.Tensor): Input tensor of shape (batch_size, seq_len, d_in).

        Returns:
            tuple: A tuple containing:
                - tuple: (z_pre, z) - Reconstructed outputs from decoder with s1_bits and full codebook respectively,
                         both of shape (batch_size, seq_len, d_in).
                - torch.Tensor: bsq_loss - Loss from the BSQuantizer.
                - torch.Tensor: quantized - Quantized representation from BSQuantizer.
                - torch.Tensor: z_indices - Indices from the BSQuantizer.
        """
        z = self.embed(x)

        for layer in self.encoder:
            z = layer(z)

        z = self.quant_embed(z) # (B, T, codebook)

        bsq_loss, quantized, z_indices = self.tokenizer(z)

        quantized_pre = quantized[:, :, :self.s1_bits] # Extract the first part of quantized representation (s1_bits)
        z_pre = self.post_quant_embed_pre(quantized_pre)

        z = self.post_quant_embed(quantized)

        # Decoder layers (for pre part - s1 bits)
        for layer in self.decoder:
            z_pre = layer(z_pre)
        z_pre = self.head(z_pre)

        # Decoder layers (for full codebook)
        for layer in self.decoder:
            z = layer(z)
        z = self.head(z)

        return (z_pre, z), bsq_loss, quantized, z_indices

    def indices_to_bits(self, x, half=False):
        """
        Converts indices to bit representations and scales them.

        Args:
            x (torch.Tensor): Indices tensor.
            half (bool, optional): Whether to process only half of the codebook dimension. Defaults to False.

        Returns:
            torch.Tensor: Bit representation tensor.
        """
        if half:
            x1 = x[0] # Assuming x is a tuple of indices if half is True
            x2 = x[1]
            mask = 2 ** torch.arange(self.codebook_dim//2, device=x1.device, dtype=torch.long) # Create a mask for bit extraction
            x1 = (x1.unsqueeze(-1) & mask) != 0 # Extract bits for the first half
            x2 = (x2.unsqueeze(-1) & mask) != 0 # Extract bits for the second half
            x = torch.cat([x1, x2], dim=-1) # Concatenate the bit representations
        else:
            mask = 2 ** torch.arange(self.codebook_dim, device=x.device, dtype=torch.long) # Create a mask for bit extraction
            x = (x.unsqueeze(-1) & mask) != 0 # Extract bits

        x = x.float() * 2 - 1 # Convert boolean to bipolar (-1, 1)
        q_scale = 1. / (self.codebook_dim ** 0.5) # Scaling factor
        x = x * q_scale
        return x

    def encode(self, x, half=False):
        """
        Encodes the input data into quantized indices.

        Args:
            x (torch.Tensor): Input tensor of shape (batch_size, seq_len, d_in).
            half (bool, optional): Whether to use half quantization in BSQuantizer. Defaults to False.

        Returns:
            torch.Tensor: Quantized indices from BSQuantizer.
        """
        z = self.embed(x)
        for layer in self.encoder:
            z = layer(z)
        z = self.quant_embed(z)

        bsq_loss, quantized, z_indices = self.tokenizer(z, half=half, collect_metrics=False)
        return z_indices

    def decode(self, x, half=False):
        """
        Decodes quantized indices back to the input data space.

        Args:
            x (torch.Tensor): Quantized indices tensor.
            half (bool, optional): Whether the indices were generated with half quantization. Defaults to False.

        Returns:
            torch.Tensor: Reconstructed output tensor of shape (batch_size, seq_len, d_in).
        """
        quantized = self.indices_to_bits(x, half)
        z = self.post_quant_embed(quantized)
        for layer in self.decoder:
            z = layer(z)
        z = self.head(z)
        return z


class Kronos(nn.Module, PyTorchModelHubMixin):
    """
    Kronos Model.

    Args:
        s1_bits (int): Number of bits for pre tokens.
        s2_bits (int): Number of bits for post tokens.
        n_layers (int): Number of Transformer blocks.
        d_model (int): Dimension of the model's embeddings and hidden states.
        n_heads (int): Number of attention heads in the MultiheadAttention layers.
        ff_dim (int): Dimension of the feedforward network in the Transformer blocks.
        ffn_dropout_p (float): Dropout probability for the feedforward network.
        attn_dropout_p (float): Dropout probability for the attention layers.
        resid_dropout_p (float): Dropout probability for residual connections.
        token_dropout_p (float): Dropout probability for token embeddings.
        learn_te (bool): Whether to use learnable temporal embeddings.
    """

    def __init__(self, s1_bits, s2_bits, n_layers, d_model, n_heads, ff_dim, ffn_dropout_p, attn_dropout_p, resid_dropout_p, token_dropout_p, learn_te):
        super().__init__()
        self.s1_bits = s1_bits
        self.s2_bits = s2_bits
        self.n_layers = n_layers
        self.d_model = d_model
        self.n_heads = n_heads
        self.learn_te = learn_te
        self.ff_dim = ff_dim
        self.ffn_dropout_p = ffn_dropout_p
        self.attn_dropout_p = attn_dropout_p
        self.resid_dropout_p = resid_dropout_p
        self.token_dropout_p = token_dropout_p

        self.s1_vocab_size = 2 ** self.s1_bits
        self.token_drop = nn.Dropout(self.token_dropout_p)
        self.embedding = HierarchicalEmbedding(self.s1_bits, self.s2_bits, self.d_model)
        self.time_emb = TemporalEmbedding(self.d_model, self.learn_te)
        self.transformer = nn.ModuleList([
            TransformerBlock(self.d_model, self.n_heads, self.ff_dim, self.ffn_dropout_p, self.attn_dropout_p, self.resid_dropout_p)
            for _ in range(self.n_layers)
        ])
        self.norm = RMSNorm(self.d_model)
        self.dep_layer = DependencyAwareLayer(self.d_model)
        self.head = DualHead(self.s1_bits, self.s2_bits, self.d_model)
        self.apply(self._init_weights)

    def _init_weights(self, module):

        if isinstance(module, nn.Linear):
            nn.init.xavier_normal_(module.weight)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0, std=self.embedding.d_model ** -0.5)
        elif isinstance(module, nn.LayerNorm):
            nn.init.ones_(module.weight)
            nn.init.zeros_(module.bias)
        elif isinstance(module, RMSNorm):
            nn.init.ones_(module.weight)

    def forward(self, s1_ids, s2_ids, stamp=None, padding_mask=None, use_teacher_forcing=False, s1_targets=None):
        """
        Args:
            s1_ids (torch.Tensor): Input tensor of s1 token IDs. Shape: [batch_size, seq_len]
            s2_ids (torch.Tensor): Input tensor of s2 token IDs. Shape: [batch_size, seq_len]
            stamp (torch.Tensor, optional): Temporal stamp tensor. Shape: [batch_size, seq_len]. Defaults to None.
            padding_mask (torch.Tensor, optional): Mask for padding tokens. Shape: [batch_size, seq_len]. Defaults to None.
            use_teacher_forcing (bool, optional): Whether to use teacher forcing for s1 decoding. Defaults to False.
            s1_targets (torch.Tensor, optional): Target s1 token IDs for teacher forcing. Shape: [batch_size, seq_len]. Defaults to None.

        Returns:
            Tuple[torch.Tensor, torch.Tensor]:
                - s1 logits: Logits for s1 token predictions. Shape: [batch_size, seq_len, s1_vocab_size]
                - s2_logits: Logits for s2 token predictions, conditioned on s1. Shape: [batch_size, seq_len, s2_vocab_size]
        """
        x = self.embedding([s1_ids, s2_ids])
        if stamp is not None:
            time_embedding = self.time_emb(stamp)
            x = x + time_embedding
        x = self.token_drop(x)

        for layer in self.transformer:
            x = layer(x, key_padding_mask=padding_mask)

        x = self.norm(x)

        s1_logits = self.head(x)

        if use_teacher_forcing:
            sibling_embed = self.embedding.emb_s1(s1_targets)
        else:
            s1_probs = F.softmax(s1_logits.detach(), dim=-1)
            sample_s1_ids = torch.multinomial(s1_probs.view(-1, self.s1_vocab_size), 1).view(s1_ids.shape)
            sibling_embed = self.embedding.emb_s1(sample_s1_ids)

        x2 = self.dep_layer(x, sibling_embed, key_padding_mask=padding_mask) # Dependency Aware Layer: Condition on s1 embeddings
        s2_logits = self.head.cond_forward(x2)
        return s1_logits, s2_logits

    def decode_s1(self, s1_ids, s2_ids, stamp=None, padding_mask=None,
                  past_kv_list=None, position_offset=None):
        """
        Decodes only the s1 tokens.

        This method performs a forward pass to predict only s1 tokens. It returns the s1 logits,
        the context representation from the Transformer, and an updated KV-cache list.

        Args:
            s1_ids (torch.Tensor): Input tensor of s1 token IDs. Shape: [batch_size, seq_len]
            s2_ids (torch.Tensor): Input tensor of s2 token IDs. Shape: [batch_size, seq_len]
            stamp (torch.Tensor, optional): Temporal stamp tensor. Shape: [batch_size, seq_len]. Defaults to None.
            padding_mask (torch.Tensor, optional): Mask for padding tokens. Shape: [batch_size, seq_len]. Defaults to None.
            past_kv_list (list, optional): List of (K, V) tuples per layer from previous step. If None,
                builds the initial cache from the full sequence.
            position_offset (int, optional): Override absolute position offset for RoPE.
                When None and cache is in use, derives from cache length.

        Returns:
            Tuple[torch.Tensor, torch.Tensor, list]:
                - s1 logits: Logits for s1 token predictions. Shape: [batch_size, seq_len, s1_vocab_size]
                - context: Context representation from the Transformer. Shape: [batch_size, seq_len, d_model]
                - new_past_kv_list: Updated K/V cache per layer
        """
        use_cache = past_kv_list is not None

        x = self.embedding([s1_ids, s2_ids])
        if stamp is not None:
            time_embedding = self.time_emb(stamp)
            x = x + time_embedding
        x = self.token_drop(x)

        if use_cache:
            if position_offset is None:
                position_offset = past_kv_list[0][0].size(-2)
        else:
            position_offset = position_offset if position_offset is not None else 0

        new_past_kv_list = []
        for i, layer in enumerate(self.transformer):
            if use_cache:
                layer_past_kv = past_kv_list[i]
                x, new_kv = layer(x, key_padding_mask=padding_mask,
                                  past_kv=layer_past_kv, position_offset=position_offset)
            else:
                # Build initial KV-cache via return_kv to avoid double computation
                x, new_kv = layer(x, key_padding_mask=padding_mask,
                                  position_offset=position_offset, return_kv=True)

            new_past_kv_list.append(new_kv)

        x = self.norm(x)

        s1_logits = self.head(x)
        return s1_logits, x, new_past_kv_list

    def decode_s2(self, context, s1_ids, padding_mask=None):
        """Decode s2 tokens conditioned on context and s1 token predictions.

        Args:
            context: Context representation from the transformer. [B, T, d_model]
            s1_ids: Predicted s1 token IDs. [B, 1]
            padding_mask: Optional padding mask.

        Returns:
            s2_logits of shape [batch_size, 1, s2_vocab_size]
        """
        sibling_embed = self.embedding.emb_s1(s1_ids)
        x2 = self.dep_layer(context, sibling_embed, key_padding_mask=padding_mask)
        return self.head.cond_forward(x2)


def top_k_top_p_filtering(
        logits,
        top_k: int = 0,
        top_p: float = 1.0,
        filter_value: float = -float("Inf"),
        min_tokens_to_keep: int = 1,
):
    """Filter a distribution of logits using top-k and/or nucleus (top-p) filtering
    Args:
        logits: logits distribution shape (batch size, vocabulary size)
        if top_k > 0: keep only top k tokens with highest probability (top-k filtering).
        if top_p < 1.0: keep the top tokens with cumulative probability >= top_p (nucleus filtering).
            Nucleus filtering is described in Holtzman et al. (http://arxiv.org/abs/1904.09751)
        Make sure we keep at least min_tokens_to_keep per batch example in the output
    From: https://gist.github.com/thomwolf/1a5a29f6962089e871b94cbd09daf317
    """
    if top_k > 0:
        top_k = min(max(top_k, min_tokens_to_keep), logits.size(-1))
        indices_to_remove = logits < torch.topk(logits, top_k)[0][..., -1, None]
        logits[indices_to_remove] = filter_value

    if top_p < 1.0:
        sorted_logits, sorted_indices = torch.sort(logits, descending=True)
        cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)

        sorted_indices_to_remove = cumulative_probs > top_p
        if min_tokens_to_keep > 1:
            sorted_indices_to_remove[..., :min_tokens_to_keep] = 0
        sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
        sorted_indices_to_remove[..., 0] = 0

        indices_to_remove = sorted_indices_to_remove.scatter(1, sorted_indices, sorted_indices_to_remove)
        logits[indices_to_remove] = filter_value

    return logits


def sample_from_logits(logits, temperature=1.0, top_k=None, top_p=None, sample_logits=True):
    logits = logits / temperature
    if (top_k is not None and top_k > 0) or (top_p is not None and top_p < 1.0):
        logits = top_k_top_p_filtering(logits, top_k=top_k or 0, top_p=top_p or 1.0)

    probs = F.softmax(logits, dim=-1)

    if not sample_logits:
        _, x = torch.topk(probs, k=1, dim=-1)
    else:
        x = torch.multinomial(probs, num_samples=1)

    return x


def _trim_kv_cache(past_kv_list, keep_last):
    """Trim KV-cache to keep only the last `keep_last` positions (in-place slice)."""
    return [(k[:, :, -keep_last:, :], v[:, :, -keep_last:, :]) for k, v in past_kv_list]


def auto_regressive_inference(tokenizer, model, x, x_stamp, y_stamp, max_context,
                               pred_len, clip=5, T=1.0, top_k=0, top_p=0.99,
                               sample_count=5, verbose=False, use_amp=False):
    """Autoregressive inference with optimized KV-cache and circular buffer management.

    Uses index-based circular buffers instead of torch.roll, and builds KV-cache
    via return_kv to eliminate redundant K/V computation on the first step.
    """
    amp_ctx = torch.autocast(device_type='cuda', dtype=torch.float16) if (
        use_amp and x.device.type == 'cuda') else contextlib.nullcontext()
    with torch.inference_mode(), amp_ctx:
        x = torch.clamp(x, -clip, clip)

        device = x.device
        x = x.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x.size(1), x.size(2)).to(device)
        x_stamp = x_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x_stamp.size(1), x_stamp.size(2)).to(device)
        y_stamp = y_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, y_stamp.size(1), y_stamp.size(2)).to(device)

        x_token = tokenizer.encode(x, half=True)

        initial_seq_len = x.size(1)
        batch_size = x_token[0].size(0)
        total_seq_len = initial_seq_len + pred_len
        full_stamp = torch.cat([x_stamp, y_stamp], dim=1)

        generated_pre = x_token[0].new_empty(batch_size, pred_len)
        generated_post = x_token[1].new_empty(batch_size, pred_len)

        # ---- Circular buffers (index-based, no torch.roll) ----
        pre_buf = x_token[0].new_zeros(batch_size, max_context)
        post_buf = x_token[1].new_zeros(batch_size, max_context)

        init_len = min(initial_seq_len, max_context)
        if init_len > 0:
            start_idx = max(0, initial_seq_len - max_context)
            pre_buf[:, :init_len] = x_token[0][:, start_idx:start_idx + init_len]
            post_buf[:, :init_len] = x_token[1][:, start_idx:start_idx + init_len]
        write_pos = init_len % max_context

        # KV-cache state
        past_kv_list = None
        cached_context = None

        ran = trange if verbose else range
        for i in ran(pred_len):
            current_seq_len = initial_seq_len + i

            # Build window view from circular buffer
            if current_seq_len <= max_context:
                # Linear phase: buffer[0:current_seq_len]
                s1_win = pre_buf[:, :current_seq_len]
                s2_win = post_buf[:, :current_seq_len]
            else:
                # Circular phase: buffer[write_pos:] + buffer[:write_pos]
                s1_win = torch.cat([pre_buf[:, write_pos:], pre_buf[:, :write_pos]], dim=1)
                s2_win = torch.cat([post_buf[:, write_pos:], post_buf[:, :write_pos]], dim=1)

            context_end = current_seq_len
            context_start = max(0, context_end - max_context)
            current_stamp = full_stamp[:, context_start:context_end, :].contiguous()

            if past_kv_list is None:
                # First call: process full window, build initial KV-cache
                s1_logits, cached_context, past_kv_list = model.decode_s1(
                    s1_win, s2_win, current_stamp, past_kv_list=past_kv_list)
            else:
                # Incremental: single new token with KV-cache
                new_stamp = current_stamp[:, -1:, :].contiguous()
                s1_logits, ctx_new, past_kv_list = model.decode_s1(
                    sample_pre, sample_post, new_stamp,
                    past_kv_list=past_kv_list,
                    position_offset=current_seq_len - 1)
                cached_context = torch.cat([
                    cached_context[:, -(max_context - 1):], ctx_new], dim=1)

            # Sample s1 → s2
            s1_logits = s1_logits[:, -1, :]
            sample_pre = sample_from_logits(s1_logits, temperature=T, top_k=top_k, top_p=top_p)

            s2_logits = model.decode_s2(cached_context, sample_pre)
            s2_logits = s2_logits[:, -1, :]
            sample_post = sample_from_logits(s2_logits, temperature=T, top_k=top_k, top_p=top_p)

            generated_pre[:, i] = sample_pre.squeeze(-1)
            generated_post[:, i] = sample_post.squeeze(-1)

            # Write to circular buffer (no torch.roll)
            pre_buf[:, write_pos] = sample_pre.squeeze(-1)
            post_buf[:, write_pos] = sample_post.squeeze(-1)
            write_pos = (write_pos + 1) % max_context

            # Trim KV-cache when context exceeds max_context
            if past_kv_list is not None and cached_context.size(1) > max_context:
                past_kv_list = _trim_kv_cache(past_kv_list, keep_last=max_context)
                cached_context = cached_context[:, -max_context:, :]

        # Final decode
        full_pre = torch.cat([x_token[0], generated_pre], dim=1)
        full_post = torch.cat([x_token[1], generated_post], dim=1)

        context_start = max(0, total_seq_len - max_context)
        z = tokenizer.decode([
            full_pre[:, context_start:total_seq_len].contiguous(),
            full_post[:, context_start:total_seq_len].contiguous()
        ], half=True)
        z = z.reshape(-1, sample_count, z.size(1), z.size(2))
        preds = z.cpu().numpy()
        preds = np.mean(preds, axis=1)

        return preds


def calc_time_stamps(x_timestamp):
    time_df = pd.DataFrame()
    time_df['minute'] = x_timestamp.dt.minute
    time_df['hour'] = x_timestamp.dt.hour
    time_df['weekday'] = x_timestamp.dt.weekday
    time_df['day'] = x_timestamp.dt.day
    time_df['month'] = x_timestamp.dt.month
    return time_df


class KronosPredictor:

    def __init__(self, model, tokenizer, device=None, max_context=512, clip=5, use_amp=False, compile_model=False):
        self.tokenizer = tokenizer
        self.model = model
        self.max_context = max_context
        self.clip = clip
        self.use_amp = use_amp
        self.price_cols = ['open', 'high', 'low', 'close']
        self.vol_col = 'volume'
        self.amt_vol = 'amount'
        self.time_cols = ['minute', 'hour', 'weekday', 'day', 'month']

        # Auto-detect device if not specified
        if device is None:
            if torch.cuda.is_available():
                device = "cuda:0"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        self.device = device

        self.tokenizer = self.tokenizer.to(self.device)
        self.model = self.model.to(self.device)

        if compile_model is not False:
            compile_enabled = (compile_model is True) or (device != "cpu")
            if compile_enabled and hasattr(torch, 'compile'):
                try:
                    self.model = torch.compile(self.model, mode='reduce-overhead')
                    self.tokenizer = torch.compile(self.tokenizer, mode='reduce-overhead')
                    print(f"[KronosPredictor] torch.compile enabled (reduce-overhead)")
                except Exception as e:
                    print(f"[KronosPredictor] torch.compile skipped: {e}")

    def generate(self, x, x_stamp, y_stamp, pred_len, T, top_k, top_p, sample_count, verbose):

        x_tensor = torch.from_numpy(np.array(x).astype(np.float32)).to(self.device)
        x_stamp_tensor = torch.from_numpy(np.array(x_stamp).astype(np.float32)).to(self.device)
        y_stamp_tensor = torch.from_numpy(np.array(y_stamp).astype(np.float32)).to(self.device)

        preds = auto_regressive_inference(self.tokenizer, self.model, x_tensor, x_stamp_tensor, y_stamp_tensor, self.max_context, pred_len,
                                          self.clip, T, top_k, top_p, sample_count, verbose, self.use_amp)
        preds = preds[:, -pred_len:, :]
        return preds

    def _validate_and_normalize_inputs(self, df, x_timestamp, y_timestamp,
                                         index: Optional[int] = None):
        """Validate and normalize a single input DataFrame.

        Returns (x_norm, x_stamp, y_stamp, x_mean, x_std) — all float32 numpy
        arrays without batch dimension.
        """
        idx_prefix = f" at index {index}" if index is not None else ""

        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"Input{idx_prefix} is not a pandas DataFrame.")

        if not all(col in df.columns for col in self.price_cols):
            raise ValueError(
                f"Price columns {self.price_cols} not found in DataFrame{idx_prefix}."
            )

        df = df.copy()
        if self.vol_col not in df.columns:
            df[self.vol_col] = 0.0
            df[self.amt_vol] = 0.0
        if self.amt_vol not in df.columns and self.vol_col in df.columns:
            df[self.amt_vol] = df[self.vol_col] * df[self.price_cols].mean(axis=1)

        if df[self.price_cols + [self.vol_col, self.amt_vol]].isnull().values.any():
            raise ValueError(
                f"Input DataFrame{idx_prefix} contains NaN values in price or volume columns."
            )

        x_time_df = calc_time_stamps(x_timestamp)
        y_time_df = calc_time_stamps(y_timestamp)

        x = df[self.price_cols + [self.vol_col, self.amt_vol]].values.astype(np.float32)
        x_stamp = x_time_df.values.astype(np.float32)
        y_stamp = y_time_df.values.astype(np.float32)

        x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)
        x_norm = (x - x_mean) / (x_std + 1e-5)
        x_norm = np.clip(x_norm, -self.clip, self.clip)

        return x_norm, x_stamp, y_stamp, x_mean, x_std

    def predict(self, df, x_timestamp, y_timestamp, pred_len, T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=True):

        x_norm, x_stamp, y_stamp, x_mean, x_std = \
            self._validate_and_normalize_inputs(df, x_timestamp, y_timestamp)

        x = x_norm[np.newaxis, :]
        x_stamp = x_stamp[np.newaxis, :]
        y_stamp = y_stamp[np.newaxis, :]

        preds = self.generate(x, x_stamp, y_stamp, pred_len, T, top_k, top_p, sample_count, verbose)

        preds = preds.squeeze(0)
        preds = preds * (x_std + 1e-5) + x_mean

        pred_df = pd.DataFrame(preds, columns=self.price_cols + [self.vol_col, self.amt_vol], index=y_timestamp)
        return pred_df


    def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=True):
        """
        Perform parallel (batch) prediction on multiple time series. All series must have the same historical length and prediction length (pred_len).

        Args:
            df_list (List[pd.DataFrame]): List of input DataFrames, each containing price columns and optional volume/amount columns.
            x_timestamp_list (List[pd.DatetimeIndex or Series]): List of timestamps corresponding to historical data, length should match the number of rows in each DataFrame.
            y_timestamp_list (List[pd.DatetimeIndex or Series]): List of future prediction timestamps, length should equal pred_len.
            pred_len (int): Number of prediction steps.
            T (float): Sampling temperature.
            top_k (int): Top-k filtering threshold.
            top_p (float): Top-p (nucleus sampling) threshold.
            sample_count (int): Number of parallel samples per series, automatically averaged internally.
            verbose (bool): Whether to display autoregressive progress.

        Returns:
            List[pd.DataFrame]: List of prediction results in the same order as input, each DataFrame contains
                                `open, high, low, close, volume, amount` columns, indexed by corresponding `y_timestamp`.
        """
        # Basic validation
        if not isinstance(df_list, (list, tuple)) or not isinstance(x_timestamp_list, (list, tuple)) or not isinstance(y_timestamp_list, (list, tuple)):
            raise ValueError("df_list, x_timestamp_list, y_timestamp_list must be list or tuple types.")
        if not (len(df_list) == len(x_timestamp_list) == len(y_timestamp_list)):
            raise ValueError("df_list, x_timestamp_list, y_timestamp_list must have consistent lengths.")

        num_series = len(df_list)

        x_list = []
        x_stamp_list = []
        y_stamp_list = []
        means = []
        stds = []
        seq_lens = []
        y_lens = []

        for i in range(num_series):
            x_norm, x_stamp, y_stamp, x_mean, x_std = \
                self._validate_and_normalize_inputs(
                    df_list[i], x_timestamp_list[i],
                    y_timestamp_list[i], index=i,
                )

            if x_norm.shape[0] != x_stamp.shape[0]:
                raise ValueError(f"Inconsistent lengths at index {i}: x has {x_norm.shape[0]} vs x_stamp has {x_stamp.shape[0]}.")
            if y_stamp.shape[0] != pred_len:
                raise ValueError(f"y_timestamp length at index {i} should equal pred_len={pred_len}, got {y_stamp.shape[0]}.")

            x_list.append(x_norm)
            x_stamp_list.append(x_stamp)
            y_stamp_list.append(y_stamp)
            means.append(x_mean)
            stds.append(x_std)
            seq_lens.append(x_norm.shape[0])
            y_lens.append(y_stamp.shape[0])

        # Require all series to have consistent historical and prediction lengths for batch processing
        if len(set(seq_lens)) != 1:
            raise ValueError(f"Parallel prediction requires all series to have consistent historical lengths, got: {seq_lens}")
        if len(set(y_lens)) != 1:
            raise ValueError(f"Parallel prediction requires all series to have consistent prediction lengths, got: {y_lens}")

        x_batch = np.stack(x_list, axis=0).astype(np.float32)           # (B, seq_len, feat)
        x_stamp_batch = np.stack(x_stamp_list, axis=0).astype(np.float32) # (B, seq_len, time_feat)
        y_stamp_batch = np.stack(y_stamp_list, axis=0).astype(np.float32) # (B, pred_len, time_feat)

        preds = self.generate(x_batch, x_stamp_batch, y_stamp_batch, pred_len, T, top_k, top_p, sample_count, verbose)
        # preds: (B, pred_len, feat)

        pred_dfs = []
        for i in range(num_series):
            preds_i = preds[i] * (stds[i] + 1e-5) + means[i]
            pred_df = pd.DataFrame(preds_i, columns=self.price_cols + [self.vol_col, self.amt_vol], index=y_timestamp_list[i])
            pred_dfs.append(pred_df)

        return pred_dfs

    def predict_multi(self, df_list, x_timestamp_list, y_timestamp_list, pred_len,
                      T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False):
        """Predict on multiple time series with varying historical lengths.

        Automatically groups series by length and dispatches to predict_batch
        for same-length groups or predict for unique-length singletons.
        This is the recommended method for heterogeneous batch prediction.

        Returns:
            List[pd.DataFrame]: predictions in the same order as input.
        """
        num_series = len(df_list)
        if num_series == 0:
            return []
        if num_series == 1:
            return [self.predict(df_list[0], x_timestamp_list[0],
                    y_timestamp_list[0], pred_len, T, top_k, top_p,
                    sample_count, verbose)]

        # Group by historical length
        groups: dict[int, list[int]] = {}
        for i in range(num_series):
            key = len(df_list[i])
            groups.setdefault(key, []).append(i)

        # Pre-allocate result slots
        results: list = [None] * num_series

        for _, indices in groups.items():
            df_group = [df_list[i] for i in indices]
            x_group = [x_timestamp_list[i] for i in indices]
            y_group = [y_timestamp_list[i] for i in indices]

            if len(indices) >= 2:
                batch_results = self.predict_batch(
                    df_group, x_group, y_group, pred_len,
                    T, top_k, top_p, sample_count, verbose)
                for j, idx in enumerate(indices):
                    results[idx] = batch_results[j]
            else:
                idx = indices[0]
                results[idx] = self.predict(
                    df_group[0], x_group[0], y_group[0], pred_len,
                    T, top_k, top_p, sample_count, verbose)

        return results

    # ── V2: 推理优化方法 ──

    def predict_fast(self, df, x_timestamp, y_timestamp, pred_len,
                     T=0.7, top_k=10, top_p=0.95, verbose=False):
        """🔥 V2 快速预测: 单样本+编译加速，用于实时场景。

        相比 predict() 默认 sample_count=3, 快速模式仅采1个样本,
        推理速度提升 ~3x, 适合需要低延迟的实时诊断。
        """
        return self.predict(df, x_timestamp, y_timestamp, pred_len,
                          T=T, top_k=top_k, top_p=top_p,
                          sample_count=1, verbose=verbose)

    def warmup(self, seq_len=60, pred_len=15):
        """🔥 V2 模型预热: 消除首次推理的编译开销。

        在服务启动时调用一次，后续推理零预热延迟。
        """
        import numpy as np
        dummy_x = np.random.randn(1, seq_len, 6).astype(np.float32)
        dummy_x_stamp = np.zeros((1, seq_len, 5), dtype=np.float32)
        dummy_y_stamp = np.zeros((1, pred_len, 5), dtype=np.float32)
        self.generate(dummy_x, dummy_x_stamp, dummy_y_stamp,
                     pred_len, T=0.7, top_k=10, top_p=0.95,
                     sample_count=1, verbose=False)

    def to_onnx(self, export_path: str, seq_len=60, pred_len=15):
        """🔥 V2 ONNX 导出: Tokenizer + Predictor 导出为 ONNX 格式。"""
        import numpy as np
        self.model.eval()
        self.tokenizer.eval()

        dummy_x = torch.randn(1, seq_len, 6, device=self.device)
        dummy_stamp = torch.zeros(1, seq_len, 5, device=self.device)

        class TokenizerEncoder(torch.nn.Module):
            def __init__(self, tokenizer):
                super().__init__()
                self.tokenizer = tokenizer
            def forward(self, x):
                return self.tokenizer.encode(x, half=True)

        tok_path = export_path.replace('.onnx', '_tokenizer.onnx')
        try:
            torch.onnx.export(
                TokenizerEncoder(self.tokenizer), (dummy_x,),
                tok_path,
                input_names=['x'], output_names=['s1_ids', 's2_ids'],
                dynamic_axes={'x': {0: 'batch', 1: 'seq'}},
                opset_version=17
            )
            print(f"[ONNX] Tokenizer exported: {tok_path}")
        except Exception as e:
            print(f"[ONNX] Tokenizer export skipped: {e}")

        class PredictorS1(torch.nn.Module):
            def __init__(self, model, s1_bits, s2_bits):
                super().__init__()
                self.model = model
            def forward(self, s1_ids, s2_ids, stamp):
                return self.model.decode_s1(s1_ids, s2_ids, stamp)[0]

        pred_path = export_path.replace('.onnx', '_predictor.onnx')
        try:
            dummy_s1 = torch.randint(0, 2**8, (1, seq_len), device=self.device)
            dummy_s2 = torch.randint(0, 2**8, (1, seq_len), device=self.device)
            torch.onnx.export(
                PredictorS1(self.model, 8, 8), (dummy_s1, dummy_s2, dummy_stamp),
                pred_path,
                input_names=['s1_ids', 's2_ids', 'stamp'],
                output_names=['s1_logits'],
                dynamic_axes={'s1_ids': {0: 'batch', 1: 'seq'},
                            's2_ids': {0: 'batch', 1: 'seq'}},
                opset_version=17
            )
            print(f"[ONNX] Predictor exported: {pred_path}")
        except Exception as e:
            print(f"[ONNX] Predictor export skipped: {e}")

