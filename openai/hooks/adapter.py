#!/usr/bin/env python3
"""Compatibility entry point for clients that still hold retired hook commands.

New setup removes the harness handlers. Keep this no-op file while older clients
can retain them; deleting it makes both tool use and Stop fail before migration.
Codex's native permissions and user-owned hooks continue to apply.
"""
