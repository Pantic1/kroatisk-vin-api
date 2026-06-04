from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.email_service import send_email

router = APIRouter()


class OrderNotifyPayload(BaseModel):
    to_email: str
    to_name: str
    order_url: str
    order_id: str | int


@router.post("/notifyOrder")
def notify_order(payload: OrderNotifyPayload):
    subject = f"Ny ordre #{payload.order_id} klar til gennemsyn"

    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a1a2e;margin-bottom:8px;">Hej {payload.to_name} 👋</h2>
      <p style="font-size:15px;color:#444;line-height:1.6;">
        Der er en ny ordre klar til dig. Klik på knappen nedenfor for at se ordren.
      </p>
      <a href="{payload.order_url}"
         style="display:inline-block;margin:20px 0;padding:13px 28px;
                background:#0846A8;color:#fff;border-radius:8px;
                text-decoration:none;font-weight:600;font-size:15px;">
        Se ordre #{payload.order_id} →
      </a>
      <p style="font-size:12px;color:#aaa;margin-top:16px;">
        Eller kopiér dette link:<br/>
        <span style="color:#555;">{payload.order_url}</span>
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0;"/>
      <p style="font-size:11px;color:#bbb;">Kroatisk Vin · kroatiskvin.dk</p>
    </div>
    """

    try:
        send_email(subject, payload.to_email, html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mailfejl: {e}")

    return {"ok": True, "message": f"Mail sendt til {payload.to_email}"}
