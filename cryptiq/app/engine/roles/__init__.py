"""Roles: classify what a matched construct does cryptographically."""

from app.engine.roles.classifier import (
    CryptographicRole,
    RoleAssessment,
    classify,
)

__all__ = ["CryptographicRole", "RoleAssessment", "classify"]
