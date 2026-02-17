from __future__ import annotations

__version__ = "0.1.0"

from dataclasses import dataclass, asdict, field
from pathlib import Path
from datetime import datetime
import uuid
import socket
import hashlib
import secrets
from typing import Any, Dict, Type, List, Optional, ClassVar, Protocol


# -----------------------------
# Core: Context & Base Policy
# -----------------------------

@dataclass
class FilenameContext:
    base: str
    ext: str
    directory: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_base(self, new_base: str) -> "FilenameContext":
        return FilenameContext(
            base=new_base,
            ext=self.ext,
            directory=self.directory,
            metadata=dict(self.metadata),
        )


class FilenamePolicy(Protocol):
    """
    Base class for all filename policies.

    Contract:
      - generate() returns a *basename without extension* OR a full filename?
        -> We define: generate() returns the *basename without extension*.
      - The extension is appended by the caller.
    """

    # Registration name for serialization
    type_name: ClassVar[str] = "base"

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializable representation of the policy.
        Must be extended by subclasses if they have their own fields.
        """
        return {"type": self.type_name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilenamePolicy":
        """
        Creates an instance from a serialized representation.
        Must be implemented by subclasses.
        """
        ...

    def generate(self, ctx: FilenameContext) -> str:
        """
        Generates a basename (without extension).
        """
        ...


# -----------------------------
# Policy registry
# -----------------------------

_POLICY_REGISTRY: Dict[str, Type[FilenamePolicy]] = {}


def register_policy(cls: Type[FilenamePolicy]) -> Type[FilenamePolicy]:
    if not hasattr(cls, "type_name"):
        raise ValueError(f"Policy {cls} must define class attribute 'type_name'")
    name = cls.type_name
    if name in _POLICY_REGISTRY:
        raise ValueError(f"Policy type_name '{name}' already registered")
    _POLICY_REGISTRY[name] = cls
    return cls


def policy_from_dict(data: Dict[str, Any]) -> FilenamePolicy:
    type_name = data.get("type")
    if not type_name:
        raise ValueError("Missing 'type' in policy config")
    cls = _POLICY_REGISTRY.get(type_name)
    if cls is None:
        raise ValueError(f"Unknown policy type '{type_name}'")
    return cls.from_dict(data)


# -----------------------------
# Concrete policies
# -----------------------------

@register_policy
class IdentityPolicy(FilenamePolicy):
    """
    Returns the base name as-is.
    """
    type_name: ClassVar[str] = "identity"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IdentityPolicy":
        return cls()

    def generate(self, ctx: FilenameContext) -> str:
        return ctx.base


@register_policy
class PrefixPolicy(FilenamePolicy):
    """
    Prepends a prefix to the base name.
    """
    type_name: ClassVar[str] = "prefix"

    def __init__(self, prefix: str):
        self.prefix = prefix

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["prefix"] = self.prefix
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PrefixPolicy":
        return cls(prefix=str(data.get("prefix", "")))

    def generate(self, ctx: FilenameContext) -> str:
        return f"{self.prefix}{ctx.base}"


@register_policy
class SuffixPolicy(FilenamePolicy):
    """
    Appends a suffix to the base name.
    """
    type_name: ClassVar[str] = "suffix"

    def __init__(self, suffix: str):
        self.suffix = suffix

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["suffix"] = self.suffix
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SuffixPolicy":
        return cls(suffix=str(data.get("suffix", "")))

    def generate(self, ctx: FilenameContext) -> str:
        return f"{ctx.base}{self.suffix}"


@register_policy
class RandomHexPolicy(FilenamePolicy):
    """
    Appends a random hex token to the base name.
    """
    type_name: ClassVar[str] = "random_hex"

    def __init__(self, length: int = 8):
        if length <= 0:
            raise ValueError("length must be positive")
        self.length = length

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["length"] = self.length
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RandomHexPolicy":
        return cls(length=int(data.get("length", 8)))

    def generate(self, ctx: FilenameContext) -> str:
        token = secrets.token_hex((self.length + 1) // 2)[: self.length]
        return f"{ctx.base}_{token}"


@register_policy
class TimestampPolicy(FilenamePolicy):
    """
    Appends a timestamp to the base name.
    """
    type_name: ClassVar[str] = "timestamp"

    def __init__(self, fmt: str = "%Y%m%d_%H%M%S"):
        self.fmt = fmt

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["fmt"] = self.fmt
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimestampPolicy":
        return cls(fmt=data.get("fmt", "%Y%m%d_%H%M%S"))

    def generate(self, ctx: FilenameContext) -> str:
        ts = datetime.now().strftime(self.fmt)
        return f"{ctx.base}_{ts}"


@register_policy
class IncrementPolicy(FilenamePolicy):
    """
    Finds the next available sequence number in the target directory.
    """
    type_name: ClassVar[str] = "increment"

    def __init__(self, width: int = 3, start: int = 1):
        self.width = width
        self.start = start

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["width"] = self.width
        data["start"] = self.start
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IncrementPolicy":
        return cls(
            width=int(data.get("width", 3)),
            start=int(data.get("start", 1)),
        )

    def generate(self, ctx: FilenameContext) -> str:
        if ctx.directory is None:
            raise ValueError("IncrementPolicy requires a directory in context")

        i = self.start
        while True:
            candidate_base = f"{ctx.base}_{i:0{self.width}d}"
            candidate = ctx.directory / f"{candidate_base}{ctx.ext}"
            if not candidate.exists():
                return candidate_base
            i += 1


@register_policy
class UUIDPolicy(FilenamePolicy):
    """
    Appends a UUID to the base name.
    """
    type_name: ClassVar[str] = "uuid"

    def __init__(self, version: int = 4):
        if version not in (1, 4):
            raise ValueError("Only UUID versions 1 and 4 are supported")
        self.version = version

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["version"] = self.version
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UUIDPolicy":
        return cls(version=int(data.get("version", 4)))

    def generate(self, ctx: FilenameContext) -> str:
        uid = uuid.uuid4() if self.version == 4 else uuid.uuid1()
        return f"{ctx.base}_{uid}"


@register_policy
class HostnamePolicy(FilenamePolicy):
    """
    Appends the host name to the base name.
    """
    type_name: ClassVar[str] = "hostname"

    def __init__(self, short: bool = True):
        self.short = short

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["short"] = self.short
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HostnamePolicy":
        return cls(short=bool(data.get("short", True)))

    def generate(self, ctx: FilenameContext) -> str:
        host = socket.gethostname()
        if self.short and "." in host:
            host = host.split(".", 1)[0]
        return f"{ctx.base}_{host}"


@register_policy
class MetadataHashPolicy(FilenamePolicy):
    """
    Generates a hash from metadata (or arbitrary data) in the context.
    """
    type_name: ClassVar[str] = "metadata_hash"

    def __init__(self, key: str = "params", algo: str = "sha256", length: int = 16):
        self.key = key
        self.algo = algo
        self.length = length

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "key": self.key,
            "algo": self.algo,
            "length": self.length,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetadataHashPolicy":
        return cls(
            key=data.get("key", "params"),
            algo=data.get("algo", "sha256"),
            length=int(data.get("length", 16)),
        )

    def generate(self, ctx: FilenameContext) -> str:
        value = ctx.metadata.get(self.key)
        if value is None:
            # Fallback: no change
            return ctx.base

        # Deterministic string representation
        raw = repr(value).encode("utf-8")
        try:
            h = hashlib.new(self.algo, raw).hexdigest()
        except ValueError as e:
            raise ValueError(f"Unknown hash algorithm '{self.algo}'") from e

        return f"{ctx.base}_{h[: self.length]}"


# -----------------------------
# Composition
# -----------------------------

@register_policy
class CompositePolicy(FilenamePolicy):
    """
    Applies multiple policies to the base name in sequence.
    Each policy receives a context with the current base name.
    """
    type_name: ClassVar[str] = "composite"

    def __init__(self, policies: List[FilenamePolicy]):
        self.policies = policies

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["policies"] = [p.to_dict() for p in self.policies]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompositePolicy":
        policies_data = data.get("policies", [])
        policies = [policy_from_dict(p) for p in policies_data]
        return cls(policies=policies)

    def generate(self, ctx: FilenameContext) -> str:
        current_ctx = ctx
        for p in self.policies:
            new_base = p.generate(current_ctx)
            current_ctx = current_ctx.with_base(new_base)
        return current_ctx.base


# -----------------------------
# High-level helper
# -----------------------------

def build_filename(
        policy: FilenamePolicy,
        base: str,
        ext: str,
        directory: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
) -> str:
    ctx = FilenameContext(
        base=base,
        ext=ext,
        directory=directory,
        metadata=metadata or {},
    )
    basename = policy.generate(ctx)
    return f"{basename}{ext}"
