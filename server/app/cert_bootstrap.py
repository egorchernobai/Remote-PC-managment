import ipaddress
import os
import shutil
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


CA_DAYS = 3650
LEAF_DAYS = 825


def ensure_certificates(config) -> dict[str, object]:
    force = _env_bool("CERT_FORCE_RENEW", False)

    server_cert = Path(config["SERVER_CERT"])
    server_key = Path(config["SERVER_KEY"])
    ca_cert = Path(config["AGENT_CA"])
    cert_dir = server_cert.parent
    cert_dir.mkdir(parents=True, exist_ok=True)

    ca_key = Path(os.environ.get("CA_KEY", cert_dir / "ca.key"))
    agent_export_dir = Path(
        os.environ.get("AGENT_CERT_EXPORT_DIR", config.get("AGENT_CERT_EXPORT_DIR", ""))
    )
    if not str(agent_export_dir):
        agent_export_dir = Path(config["PROJECT_ROOT"]) / "agent" / "certs"

    agent_cert = Path(os.environ.get("AGENT_CERT", agent_export_dir / "agent.crt"))
    agent_key = Path(os.environ.get("AGENT_KEY", agent_export_dir / "agent.key"))
    agent_ca = agent_cert.parent / ca_cert.name

    hosts = _certificate_hosts()

    if force or not ca_cert.exists() or not ca_key.exists():
        ca_key_obj = _new_key()
        ca_cert_obj = _create_ca(ca_key_obj)
        _write_key(ca_key, ca_key_obj)
        _write_cert(ca_cert, ca_cert_obj)
    else:
        ca_key_obj = _load_key(ca_key)
        ca_cert_obj = _load_cert(ca_cert)

    if force or not server_cert.exists() or not server_key.exists() or not _cert_covers_hosts(server_cert, hosts):
        server_key_obj = _new_key()
        server_cert_obj = _create_leaf_cert(
            common_name="rmm-server",
            key=server_key_obj,
            ca_key=ca_key_obj,
            ca_cert=ca_cert_obj,
            hosts=hosts,
            usages=[ExtendedKeyUsageOID.SERVER_AUTH],
        )
        _write_key(server_key, server_key_obj)
        _write_cert(server_cert, server_cert_obj)

    if force or not agent_cert.exists() or not agent_key.exists():
        agent_key_obj = _new_key()
        agent_cert_obj = _create_leaf_cert(
            common_name="rmm-agent",
            key=agent_key_obj,
            ca_key=ca_key_obj,
            ca_cert=ca_cert_obj,
            hosts=[],
            usages=[ExtendedKeyUsageOID.CLIENT_AUTH],
        )
        _write_key(agent_key, agent_key_obj)
        _write_cert(agent_cert, agent_cert_obj)

    if force or not agent_ca.exists():
        agent_ca.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ca_cert, agent_ca)

    return {
        "ca_cert": str(ca_cert),
        "server_cert": str(server_cert),
        "server_key": str(server_key),
        "agent_ca": str(agent_ca),
        "agent_cert": str(agent_cert),
        "agent_key": str(agent_key),
        "hosts": hosts,
    }


def _certificate_hosts() -> list[str]:
    hosts = {"localhost", socket.gethostname(), socket.getfqdn()}
    hosts.update({"127.0.0.1", "::1"})

    local_ip = _detect_primary_ip()
    if local_ip:
        hosts.add(local_ip)

    for value in (
        os.environ.get("SERVER_PUBLIC_HOSTS", ""),
        os.environ.get("CERT_EXTRA_HOSTS", ""),
    ):
        for host in value.split(","):
            host = host.strip()
            if host:
                hosts.add(host)

    return sorted(hosts)


def _cert_covers_hosts(cert_path: Path, hosts: list[str]) -> bool:
    if not cert_path.exists():
        return False

    try:
        cert = _load_cert(cert_path)
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (OSError, ValueError, x509.ExtensionNotFound):
        return False

    dns_names = set(san.get_values_for_type(x509.DNSName))
    ip_addresses = {str(value) for value in san.get_values_for_type(x509.IPAddress)}
    for host in hosts:
        try:
            if str(ipaddress.ip_address(host)) not in ip_addresses:
                return False
        except ValueError:
            if host not in dns_names:
                return False
    return True


def _detect_primary_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def _new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _create_ca(key):
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "RMM Local CA"),
    ])
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )


def _create_leaf_cert(common_name: str, key, ca_key, ca_cert, hosts: list[str], usages: list):
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=LEAF_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage(usages), critical=False)
    )

    san_names = [_san_name(host) for host in hosts]
    if san_names:
        builder = builder.add_extension(x509.SubjectAlternativeName(san_names), critical=False)

    return builder.sign(ca_key, hashes.SHA256())


def _san_name(host: str):
    try:
        return x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        return x509.DNSName(host)


def _load_key(path: Path):
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _load_cert(path: Path):
    return x509.load_pem_x509_certificate(path.read_bytes())


def _write_key(path: Path, key) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    _chmod_private(path)


def _write_cert(path: Path, cert) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _chmod_private(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
