"""D4-T2 License 测试。"""

import base64
import json
from pathlib import Path
from typing import Optional


def _make_test_license(
    license_path: Path,
    plan: str = "standard",
    trial: bool = False,
    expires_at: Optional[str] = None,
    overrides: dict | None = None,
) -> str:
    """写入测试 License 文件，带有效 RSA 签名。返回 public_pem。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    data = {
        "plan": plan,
        "company": "测试公司",
        "issued_at": "2026-01-01T00:00:00+00:00",
        "expires_at": expires_at or "2027-01-01T00:00:00+00:00",
        "max_concurrent": 5,
        "max_monthly_reviews": 50,
        "features": ["offline_export", "correction_docx"],
        "trial": trial,
    }
    if overrides:
        data.update(overrides)

    payload = {k: v for k, v in data.items() if k != "signature"}
    payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    signature = private_key.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())
    data["signature"] = base64.b64encode(signature).decode()

    license_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return public_pem


def test_license_manager_no_file(tmp_path):
    """无 license 文件 → 降级为 free。"""
    from src.baa_engine.license import LicenseManager

    mgr = LicenseManager(license_path=tmp_path / "nonexistent.json", online=False)
    info = mgr.validate()
    assert info.plan == "free"
    assert info.signature_valid is False


def test_license_manager_standard(tmp_path):
    """标准 License 解析正确。"""
    from src.baa_engine.license import LicenseManager

    lic = tmp_path / "license.json"
    pub = _make_test_license(lic, plan="standard")
    mgr = LicenseManager(license_path=lic, public_key_pem=pub, online=False)
    info = mgr.validate()
    assert info.plan == "standard"
    assert info.company == "测试公司"
    assert info.max_concurrent == 5
    assert info.max_monthly_reviews == 50
    assert "offline_export" in info.features
    assert info.signature_valid is True


def test_license_manager_expired(tmp_path):
    """过期 License → 降级为 free。"""
    from src.baa_engine.license import LicenseManager

    lic = tmp_path / "license.json"
    pub = _make_test_license(lic, plan="standard", expires_at="2020-01-01T00:00:00+00:00")
    mgr = LicenseManager(license_path=lic, public_key_pem=pub, online=False)
    info = mgr.validate()
    assert info.plan == "free"
    assert info.error == "license_expired"


def test_license_permission_mapping():
    """plan → permission 映射正确。"""
    from src.baa_engine.license import LicenseManager

    mgr = LicenseManager(online=False)
    assert mgr.get_permission() in ("free", "limited")


def test_license_manager_singleton_reset():
    """reset 后新实例不同。"""
    from src.baa_engine.license import get_license_manager, reset_license_manager_for_test

    m1 = get_license_manager(online=False)
    reset_license_manager_for_test()
    m2 = get_license_manager(online=False)
    assert m1 is not m2
    reset_license_manager_for_test()


def test_license_enterprise_features(tmp_path):
    """企业版含全部 feature。"""
    from src.baa_engine.license import LicenseManager

    lic = tmp_path / "license.json"
    pub = _make_test_license(
        lic,
        plan="enterprise",
        overrides={"features": ["offline_export", "correction_docx", "recheck_opinion", "custom_template"]},
    )
    mgr = LicenseManager(license_path=lic, public_key_pem=pub, online=False)
    info = mgr.validate()
    assert info.plan == "enterprise"
    assert len(info.features) == 4
    assert info.signature_valid is True


def test_license_trial_flag(tmp_path):
    """trial=true + 未过期 → trial active。"""
    from src.baa_engine.license import LicenseManager

    lic = tmp_path / "license.json"
    pub = _make_test_license(
        lic, plan="standard", trial=True, expires_at="2027-12-31T00:00:00+00:00"
    )
    mgr = LicenseManager(license_path=lic, public_key_pem=pub, online=False)
    info = mgr.validate()
    assert info.trial is True
    assert mgr.trial_expires_in_days() > 0


def test_license_wrong_signature(tmp_path):
    """签名不匹配 → signature_valid=False，但 plan 仍解析。"""
    from src.baa_engine.license import LicenseManager

    lic = tmp_path / "license.json"
    pub = _make_test_license(lic, plan="standard")
    # 用另一个密钥对的公钥 → 签名失败
    wrong_pub = _make_test_license(tmp_path / "enterprise.json", plan="enterprise")
    mgr = LicenseManager(license_path=lic, public_key_pem=wrong_pub, online=False)
    info = mgr.validate()
    assert info.signature_valid is False
    assert info.plan == "standard"
