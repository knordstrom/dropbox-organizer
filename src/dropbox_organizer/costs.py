"""Cost estimation for Claude API calls.

Token counts and pricing are approximations. Actual costs may vary based on
exact image dimensions (unknown without downloading) and model behaviour.
"""

from dataclasses import dataclass

# (input_usd_per_million, output_usd_per_million)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-5":            (15.00, 75.00),
    "claude-sonnet-4-6":          ( 3.00, 15.00),
    "claude-haiku-4-5":           ( 0.80,  4.00),
    "claude-haiku-4-5-20251001":  ( 0.80,  4.00),
}

# Conservative fallback for unknown models
_FALLBACK_PRICING = (15.00, 75.00)

# Anthropic resizes images so neither side exceeds 1568px before tokenising.
_MAX_PIXELS = 1568 * 1568
_PIXELS_PER_TOKEN = 750

# Rough compressed bytes-per-pixel by format.
_BYTES_PER_PIXEL: dict[str, float] = {
    ".jpg":  3.0,
    ".jpeg": 3.0,
    ".png":  1.0,
    ".webp": 2.0,
    ".gif":  1.5,
}

# Typical tokens in our structured JSON response.
TYPICAL_OUTPUT_TOKENS = 300


def estimate_image_tokens(file_size_bytes: int, extension: str) -> int:
    bpp = _BYTES_PER_PIXEL.get(extension.lower(), 2.0)
    pixels = min(file_size_bytes / bpp, _MAX_PIXELS)
    return max(1, int(pixels / _PIXELS_PER_TOKEN))


def estimate_prompt_tokens(prompt_text: str) -> int:
    # ~4 characters per token is a reasonable approximation for English prose.
    return max(1, len(prompt_text) // 4)


@dataclass
class CostEstimate:
    path: str
    file_size_bytes: int
    input_tokens: int
    output_tokens: int
    cost_usd: float

    @property
    def file_size_kb(self) -> float:
        return self.file_size_bytes / 1024


def estimate(
    path: str,
    file_size_bytes: int,
    prompt_text: str,
    model: str,
    output_tokens: int = TYPICAL_OUTPUT_TOKENS,
) -> CostEstimate:
    ext = path[path.rfind("."):].lower() if "." in path else ""
    image_tokens = estimate_image_tokens(file_size_bytes, ext)
    prompt_tokens = estimate_prompt_tokens(prompt_text)
    total_input = image_tokens + prompt_tokens

    input_price, output_price = MODEL_PRICING.get(model, _FALLBACK_PRICING)
    cost = (total_input / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
    return CostEstimate(
        path=path,
        file_size_bytes=file_size_bytes,
        input_tokens=total_input,
        output_tokens=output_tokens,
        cost_usd=cost,
    )


def format_cost(usd: float) -> str:
    if usd < 0.001:
        return f"${usd * 1000:.4f}m"   # show in milli-dollars
    return f"${usd:.4f}"
