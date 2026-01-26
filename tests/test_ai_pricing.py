"""Tests for AI pricing module."""

import pytest
from RouterKing.ai.pricing import (
    get_model_pricing,
    calculate_cost_tier,
    format_model_with_cost,
    get_cost_info,
)


def test_get_model_pricing_direct_match():
    """Test direct model name match."""
    pricing = get_model_pricing("gpt-5.2")
    assert pricing == (1.75, 14.00)
    
    pricing = get_model_pricing("gpt-5-nano")
    assert pricing == (0.05, 0.40)


def test_get_model_pricing_with_date_suffix():
    """Test model name with date suffix."""
    pricing = get_model_pricing("gpt-4o-2024-08-06")
    assert pricing == (2.50, 10.00)


def test_get_model_pricing_with_variant_suffix():
    """Test model name with variant suffix."""
    pricing = get_model_pricing("gpt-4o-mini-realtime-preview")
    assert pricing == (0.15, 0.60)


def test_get_model_pricing_unknown():
    """Test unknown model returns None."""
    pricing = get_model_pricing("unknown-model-xyz")
    assert pricing is None


def test_calculate_cost_tier_cheap():
    """Test cost tier calculation for cheap models."""
    tier = calculate_cost_tier("gpt-5-nano")
    assert tier == "$"
    
    tier = calculate_cost_tier("gpt-4o-mini")
    assert tier == "$"


def test_calculate_cost_tier_moderate():
    """Test cost tier calculation for moderate models."""
    tier = calculate_cost_tier("gpt-5")
    assert tier in ["$$", "$$$"]
    
    tier = calculate_cost_tier("gpt-4o")
    assert tier in ["$$", "$$$"]


def test_calculate_cost_tier_expensive():
    """Test cost tier calculation for expensive models."""
    tier = calculate_cost_tier("gpt-5.2-pro")
    assert tier == "$$$$"
    
    tier = calculate_cost_tier("o1-pro")
    assert tier == "$$$$"


def test_calculate_cost_tier_unknown():
    """Test cost tier for unknown model."""
    tier = calculate_cost_tier("unknown-model")
    assert tier == ""


def test_format_model_with_cost():
    """Test model formatting with cost indicator."""
    formatted = format_model_with_cost("gpt-5-nano")
    assert "gpt-5-nano" in formatted
    assert "$" in formatted
    assert formatted.endswith(")")
    
    formatted = format_model_with_cost("gpt-5.2-pro")
    assert "gpt-5.2-pro" in formatted
    assert "$$$$" in formatted


def test_format_model_with_cost_unknown():
    """Test model formatting for unknown model."""
    formatted = format_model_with_cost("unknown-model")
    assert formatted == "unknown-model"


def test_get_cost_info():
    """Test detailed cost information."""
    info = get_cost_info("gpt-5.2")
    assert info["tier"] == "$$$$"
    assert info["input_price"] == 1.75
    assert info["output_price"] == 14.00
    assert info["estimated_cost"] > 0
    
    info = get_cost_info("gpt-5-nano")
    assert info["tier"] == "$"
    assert info["input_price"] == 0.05
    assert info["output_price"] == 0.40


def test_get_cost_info_unknown():
    """Test cost info for unknown model."""
    info = get_cost_info("unknown-model")
    assert info["tier"] == ""
    assert info["input_price"] is None
    assert info["output_price"] is None
    assert info["estimated_cost"] is None


def test_cost_tier_future_proof():
    """Test that cost tiers remain relative when new models are added."""
    # Get current tiers
    nano_tier = calculate_cost_tier("gpt-5-nano")
    pro_tier = calculate_cost_tier("gpt-5.2-pro")
    
    # Cheapest should be $, most expensive should be $$$$
    assert nano_tier == "$"
    assert pro_tier == "$$$$"
    
    # Middle tier models should be $$ or $$$
    mid_tier = calculate_cost_tier("gpt-5")
    assert mid_tier in ["$$", "$$$"]


def test_pricing_consistency():
    """Test that pricing is consistent across model variants."""
    # Base model and dated variant should have same pricing
    base_pricing = get_model_pricing("gpt-4o")
    dated_pricing = get_model_pricing("gpt-4o-2024-08-06")
    assert base_pricing == dated_pricing
    
    # Cost tiers should be the same
    base_tier = calculate_cost_tier("gpt-4o")
    dated_tier = calculate_cost_tier("gpt-4o-2024-08-06")
    assert base_tier == dated_tier
