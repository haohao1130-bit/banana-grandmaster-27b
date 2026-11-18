"""Verify the isolated 27B studio's RTX CUDA runtime.

A standalone script avoids Windows PowerShell 5.1 quote escaping in python -c.
Only tests the independent runtime's PyTorch GPU; does not modify other studios.
"""
import sys


def main():
    try:
        import torch

        print("PyTorch:", torch.__version__, flush=True)
        print("PyTorch CUDA build:", torch.version.cuda, flush=True)
        cuda_version = str(torch.version.cuda or "")
        if not cuda_version.startswith("13."):
            raise RuntimeError("Expected PyTorch CUDA 13.x, got " + repr(cuda_version))
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA device unavailable to this Python environment")
        device = torch.cuda.get_device_properties(0)
        print("CUDA GPU:", device.name, flush=True)
        print("CUDA capability:", torch.cuda.get_device_capability(0), flush=True)
        print("GPU VRAM GiB:", round(device.total_memory / (1024 ** 3), 2), flush=True)
        # Check that a tiny kernel actually executes, not just that a driver is visible.
        tensor = torch.ones(16, device="cuda")
        result = (tensor * 2).sum().item()
        if result != 32.0:
            raise RuntimeError("Unexpected result from CUDA tensor operation")
        print("CUDA13 GPU smoke test: PASS", flush=True)
    except Exception as exc:
        print("CUDA13 GPU smoke test: FAIL - " + str(exc), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
