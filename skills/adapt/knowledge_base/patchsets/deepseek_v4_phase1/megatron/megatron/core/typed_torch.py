# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

# Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

"""Utilities for improved type hinting with torch interfaces."""

from collections.abc import Callable
from typing import Generic, Protocol, TypeVar

import torch

R_co = TypeVar("R_co", covariant=True)
T = TypeVar("T")


class _Module(Generic[R_co], Protocol):
    """Protocol allowing modules to be used through their forward signature."""

    def forward(self, *args, **kwargs) -> R_co:
        """Forward method of the matching torch.nn.Module."""
        ...


def apply_module(module: _Module[R_co], *, check_subclass: bool = True) -> Callable[..., R_co]:
    """Return the module with a callable type hint for its forward method."""
    if check_subclass and not issubclass(type(module), torch.nn.Module):
        raise TypeError(f"{type(module)} is not a subclass of torch.nn.Module")
    return module


def not_none(value: T | None) -> T:
    """Assert value is not None and return it."""
    if value is None:
        raise ValueError("Expected value to be not None")
    return value
