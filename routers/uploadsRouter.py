from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import uuid, os
from PIL import Image
from ftplib import FTP

router = APIRouter(prefix="/upload", tags=["Upload"])

# Miljøvariabler til FTP-login
FTP_HOSTINGER_HOSTNAME = os.environ.get("FTP_HOSTINGER_HOSTNAME")
FTP_HOSTINGER_USERNAME = os.environ.get("FTP_HOSTINGER_USERNAME")
FTP_HOSTINGER_PASSWORD = os.environ.get("FTP_HOSTINGER_PASSWORD")

# Mappen på FTP-serveren, du uploader til
FTP_UPLOAD_FOLDER = "/uploads"

# Base URL der matcher serverens offentlige sti
PUBLIC_BASE_URL = "https://kroatiskvin.dk/uploads"


@router.post("/")
async def upload_to_ftp(file: UploadFile = File(...)):
    try:
        # Gem midlertidig fil
        file_ext = file.filename.split(".")[-1]
        temp_filename = f"temp_{uuid.uuid4()}.{file_ext}"

        with open(temp_filename, "wb") as f:
            f.write(await file.read())

        # Konverter til PNG hvis nødvendigt
        converted_filename = temp_filename
        try:
            with Image.open(temp_filename) as img:
                if img.format != "PNG":
                    converted_filename = temp_filename.rsplit('.', 1)[0] + ".png"
                    img.save(converted_filename, "PNG")
        except Exception as e:
            os.remove(temp_filename)
            raise HTTPException(status_code=400, detail=f"Billedbehandling fejlede: {e}")

        # Upload til FTP-server
        ftp = FTP(FTP_HOSTINGER_HOSTNAME)
        ftp.login(user=FTP_HOSTINGER_USERNAME, passwd=FTP_HOSTINGER_PASSWORD)
        ftp.cwd(FTP_UPLOAD_FOLDER)

        unique_filename = f"{uuid.uuid4()}.png"
        with open(converted_filename, "rb") as f:
            ftp.storbinary(f"STOR {unique_filename}", f)

        ftp.quit()

        # Ryd op
        os.remove(temp_filename)
        if converted_filename != temp_filename:
            os.remove(converted_filename)

        # Returner offentlig URL
        image_url = f"{PUBLIC_BASE_URL}/{unique_filename}"
        return {"url": image_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
