import os
import uuid
from io import BytesIO
from ftplib import FTP
 
FTP_HOSTINGER_HOSTNAME = os.environ.get("FTP_HOSTINGER_HOSTNAME")
FTP_HOSTINGER_USERNAME = os.environ.get("FTP_HOSTINGER_USERNAME")
FTP_HOSTINGER_PASSWORD = os.environ.get("FTP_HOSTINGER_PASSWORD")
 
# Egen mappe til fakturaer på FTP
FTP_INVOICE_FOLDER = "/invoices"
PUBLIC_BASE_URL    = "https://kroatiskvin.dk/invoices"
 
 
def upload_bytes_to_ftp(data: bytes, filename: str, folder: str = FTP_INVOICE_FOLDER) -> str:
    """
    Uploader bytes til FTP-server og returnerer den offentlige URL.
    Sørg for at folder findes på serveren (lav den manuelt første gang).
    """
    ftp = FTP(FTP_HOSTINGER_HOSTNAME)
    ftp.login(user=FTP_HOSTINGER_USERNAME, passwd=FTP_HOSTINGER_PASSWORD)
 
    # Skift til mappe - opret hvis den ikke findes
    try:
        ftp.cwd(folder)
    except Exception:
        ftp.mkd(folder)
        ftp.cwd(folder)
 
    bio = BytesIO(data)
    ftp.storbinary(f"STOR {filename}", bio)
    ftp.quit()
 
    # Hvis folder er "/invoices" -> PUBLIC_BASE_URL allerede inkluderer det.
    base = PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/{filename}"
 
 
