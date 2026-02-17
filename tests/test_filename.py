import pytest
from pathlib import Path
from filename import (
    build_filename,
    IdentityPolicy,
    PrefixPolicy,
    SuffixPolicy,
    RandomHexPolicy,
    TimestampPolicy,
    IncrementPolicy,
    UUIDPolicy,
    HostnamePolicy,
    MetadataHashPolicy,
    CompositePolicy,
    policy_from_dict
)

def test_identity_policy():
    policy = IdentityPolicy()
    name = build_filename(policy, "test", ".txt")
    assert name == "test.txt"

def test_timestamp_policy():
    policy = TimestampPolicy(fmt="%Y")
    name = build_filename(policy, "test", ".txt")
    import datetime
    expected = f"test_{datetime.datetime.now().year}.txt"
    assert name == expected


def test_prefix_policy():
    policy = PrefixPolicy(prefix="pre_")
    name = build_filename(policy, "test", ".txt")
    assert name == "pre_test.txt"


def test_suffix_policy():
    policy = SuffixPolicy(suffix="_suf")
    name = build_filename(policy, "test", ".txt")
    assert name == "test_suf.txt"


def test_random_hex_policy():
    policy = RandomHexPolicy(length=6)
    name = build_filename(policy, "test", ".txt")
    assert name.startswith("test_")
    assert name.endswith(".txt")
    assert len(name) == len("test_") + 6 + len(".txt")

def test_increment_policy(tmp_path):
    policy = IncrementPolicy(width=2, start=1)

    # First call
    name1 = build_filename(policy, "test", ".txt", directory=tmp_path)
    assert name1 == "test_01.txt"

    # Create file
    (tmp_path / "test_01.txt").touch()

    # Second call
    name2 = build_filename(policy, "test", ".txt", directory=tmp_path)
    assert name2 == "test_02.txt"

def test_uuid_policy():
    policy = UUIDPolicy()
    name = build_filename(policy, "test", ".txt")
    assert name.startswith("test_")
    assert len(name) > 10

def test_hostname_policy():
    policy = HostnamePolicy()
    name = build_filename(policy, "test", ".txt")
    assert name.startswith("test_")

def test_metadata_hash_policy():
    policy = MetadataHashPolicy(key="id", length=8)
    metadata = {"id": 12345}
    name = build_filename(policy, "test", ".txt", metadata=metadata)
    assert name.startswith("test_")
    assert len(name) == 5 + 8 + 4 # test_ + 8 chars + .txt

def test_composite_policy():
    p1 = IdentityPolicy()
    p2 = IdentityPolicy()
    policy = CompositePolicy(policies=[p1, p2])
    name = build_filename(policy, "test", ".txt")
    assert name == "test.txt"

def test_serialization():
    data = {"type": "timestamp", "fmt": "%H"}
    policy = policy_from_dict(data)
    assert isinstance(policy, TimestampPolicy)
    assert policy.fmt == "%H"
    assert policy.to_dict() == data
