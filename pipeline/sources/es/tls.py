"""Certificates some Spanish and EU publishers' TLS chains need beyond the system bundle (each checked with openssl
against the issuer's published fingerprint before it was added)."""

from pathlib import Path

CERTS = Path(__file__).parent / "certs"
HARICA_ROOT = CERTS / "harica-tls-rsa-root-ca-2021.pem"  # IDEE (CORINE WMS)
SECTIGO_R46_DV_R36 = CERTS / "sectigo-r46-dv-r36.pem"  # Sectigo R46 root + DV R36 intermediate: OAPN, IDENA
GLOBALSIGN_R46 = CERTS / "globalsign-root-r46.pem"  # European Commission webgate (eAmbrosia)
FNMT_SERVIDORES_SEGUROS = CERTS / "fnmt-rcm-servidores-seguros.pem"  # AC RAIZ FNMT-RCM SERVIDORES SEGUROS: Junta de Extremadura
