"""Dynamic pricing information for OpenAI models."""

import re
from typing import Dict, Optional, Tuple


# Base pricing per 1M tokens (Input, Output) - Updated 2026-01-26
# Source: https://platform.openai.com/docs/pricing
_MODEL_PRICING = {
    # GPT-5 Series (Standard tier)
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5.2-pro": (21.00, 168.00),
    "gpt-5-pro": (15.00, 120.00),
    "gpt-5.2-codex": (1.75, 14.00),
    "gpt-5.1-codex": (1.25, 10.00),
    "gpt-5-codex": (1.25, 10.00),
    # GPT-4.1 Series
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    # GPT-4o Series
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # o-Series (Reasoning models)
    "o4-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o3-pro": (20.00, 80.00),
    "o1": (15.00, 60.00),
    "o1-mini": (1.10, 4.40),
    "o1-pro": (150.00, 600.00),
    # Legacy models
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}


def get_model_pricing(model_id: str) -> Optional[Tuple[float, float]]:
    """Get pricing for a model (input, output) per 1M tokens.
    
    Returns:
        Tuple of (input_price, output_price) or None if not found.
    """
    # Direct match
    if model_id in _MODEL_PRICING:
        return _MODEL_PRICING[model_id]
    
    # Try to match base model (remove date suffix like -2024-08-06)
    base_model = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model_id)
    if base_model in _MODEL_PRICING:
        return _MODEL_PRICING[base_model]
    
    # Try to match family prefix (e.g., gpt-4o-mini-xyz -> gpt-4o-mini)
    for known_model in _MODEL_PRICING:
        if model_id.startswith(known_model + "-"):
            return _MODEL_PRICING[known_model]
    
    return None


def calculate_cost_tier(model_id: str) -> str:
    """Calculate the cost tier for a model based on its pricing.
    
    Returns a string like "$", "$$", "$$$", or "$$$$" to indicate relative cost.
    Uses dynamic percentile-based categorization to remain future-proof.
    """
    pricing = get_model_pricing(model_id)
    if pricing is None:
        return ""  # Unknown pricing
    
    input_price, output_price = pricing
    # Weight output tokens more heavily (typical ratio is 1:3 input:output)
    # This approximates the cost of a typical conversation
    estimated_cost = input_price * 0.25 + output_price * 0.75
    
    # Get all known costs for percentile calculation
    all_costs = []
    for model, (inp, out) in _MODEL_PRICING.items():
        # Skip pro models for baseline calculation (they're outliers)
        if "pro" not in model.lower():
            all_costs.append(inp * 0.25 + out * 0.75)
    
    all_costs.sort()
    
    # Calculate percentile thresholds
    p25 = all_costs[len(all_costs) // 4]
    p50 = all_costs[len(all_costs) // 2]
    p75 = all_costs[len(all_costs) * 3 // 4]
    
    # Categorize based on percentiles
    if estimated_cost <= p25:
        return "$"  # Bottom 25% - Very cheap
    elif estimated_cost <= p50:
        return "$$"  # 25-50% - Affordable
    elif estimated_cost <= p75:
        return "$$$"  # 50-75% - Moderate
    else:
        return "$$$$"  # Top 25% - Expensive


def format_model_with_cost(model_id: str) -> str:
    """Format a model name with its cost tier indicator.
    
    Example: "gpt-5.2 ($$$$)" or "gpt-5-nano ($)"
    """
    cost_tier = calculate_cost_tier(model_id)
    if cost_tier:
        return f"{model_id} ({cost_tier})"
    return model_id


def get_cost_info(model_id: str) -> Dict[str, any]:
    """Get detailed cost information for a model.
    
    Returns:
        Dict with keys: tier, input_price, output_price, estimated_cost
    """
    pricing = get_model_pricing(model_id)
    if pricing is None:
        return {
            "tier": "",
            "input_price": None,
            "output_price": None,
            "estimated_cost": None,
        }
    
    input_price, output_price = pricing
    estimated_cost = input_price * 0.25 + output_price * 0.75
    
    return {
        "tier": calculate_cost_tier(model_id),
        "input_price": input_price,
        "output_price": output_price,
        "estimated_cost": estimated_cost,
    }
