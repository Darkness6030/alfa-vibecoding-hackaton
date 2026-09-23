"""Create local demo credentials and a self-signed IP certificate, never print keys."""

import argparse
import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

parser = argparse.ArgumentParser()
parser.add_argument("--env", default=".env")
parser.add_argument("--ip", default="127.0.0.1")
parser.add_argument("--cert-dir", default=".secrets/tls")
args = parser.parse_args()
env = Path(args.env)
if env.exists():
    parser.error("Environment file exists; refusing to rotate keys or overwrite it")
address = ipaddress.ip_address(args.ip)
cert_dir = Path(args.cert_dir)
key_path = cert_dir / "key.pem"
cert_path = cert_dir / "cert.pem"
if key_path.exists() or cert_path.exists():
    parser.error("TLS files already exist; refusing to overwrite")
cert_dir.mkdir(parents=True, exist_ok=True)
cert_dir.chmod(0o700)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(address))])
now = datetime.now(timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=5))
    .not_valid_after(now + timedelta(days=7))
    .add_extension(
        x509.SubjectAlternativeName(
            [x509.IPAddress(address), x509.DNSName("localhost")]
        ),
        critical=False,
    )
    .sign(key, hashes.SHA256())
)
key_path.write_bytes(
    key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
)
key_path.chmod(0o600)
cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
values = {
    "ALFAGEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    **{
        k: secrets.token_urlsafe(24)
        for k in [
            "ALFAGEN_CRM_API_KEY",
            "ALFAGEN_ANALYTICS_API_KEY",
            "ALFAGEN_METRICS_API_KEY",
        ]
    },
    "ALFAGEN_WORKERS": "2",
    "ALFAGEN_PORT": "8000",
}
with env.open("x") as f:
    env.chmod(0o600)
    f.write("".join(k + "=" + v + "\n" for k, v in values.items()))
print(f"Created {env} and TLS certificate in {cert_dir}. Credentials were not printed.")
