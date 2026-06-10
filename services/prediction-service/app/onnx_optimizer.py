"""ONNX/INT8 Optimization for Kronos — per refactoring plan §八"""
import os, logging
from typing import Optional

logger = logging.getLogger("prediction.onnx")

ONNX_AVAILABLE = False
try:
    import onnx  # type: ignore
    ONNX_AVAILABLE = True
except ImportError:
    logger.warning("onnx not installed — ONNX optimization unavailable")

ONNXRUNTIME_AVAILABLE = False
try:
    import onnxruntime  # type: ignore
    ONNXRUNTIME_AVAILABLE = True
except ImportError:
    logger.warning("onnxruntime not installed — ONNX inference unavailable")

def export_to_onnx(model_path: str, output_path: str, quantize: bool = False) -> str:
    """Export PyTorch model to ONNX format.
    
    Args:
        model_path: Path to Kronos PyTorch checkpoint
        output_path: ONNX output path
        quantize: Apply INT8 quantization if True
    
    Returns:
        ONNX model path, or raises if ONNX unavailable
    """
    if not ONNX_AVAILABLE:
        raise RuntimeError("ONNX export unavailable — install onnx")
    # Placeholder: actual export uses torch.onnx.export with Kronos model
    logger.info("ONNX export: %s → %s (quantize=%s)", model_path, output_path, quantize)
    return output_path

def optimize_for_inference(onnx_path: str) -> str:
    """Apply ONNX Runtime graph optimizations."""
    if not ONNXRUNTIME_AVAILABLE:
        raise RuntimeError("ONNX Runtime unavailable — install onnxruntime")
    # Placeholder: onnxruntime.SessionOptions graph optimization
    return onnx_path

def quantize_int8(onnx_path: str, output_path: str) -> str:
    """INT8 quantization via ONNX Runtime."""
    if not ONNXRUNTIME_AVAILABLE:
        raise RuntimeError("ONNX Runtime unavailable — install onnxruntime")
    # Placeholder: onnxruntime.quantization.quantize_dynamic
    logger.info("INT8 quantize: %s → %s", onnx_path, output_path)
    return output_path

def get_optimization_status() -> dict:
    """Report optimization readiness."""
    return {
        "onnx_available": ONNX_AVAILABLE,
        "onnxruntime_available": ONNXRUNTIME_AVAILABLE,
        "mps_available": False,  # Apple Silicon
        "cuda_available": False,
        "batch_inference_supported": True,
    }
