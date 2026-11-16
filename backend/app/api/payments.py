from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.api.auth import get_current_user
from backend.app.models.user import User
from backend.app.models.order import Order
from backend.app.models.payment import Payment
from backend.app.services.payment import get_payment_provider

router = APIRouter(prefix="/api/payments", tags=["payments"])

@router.post("/checkout")
async def create_payment_checkout(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Order).where(Order.id == order_id))
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    if order.is_paid:
        return {"success": True, "message": "Order is already paid", "is_paid": True}

    provider = get_payment_provider()
    checkout = await provider.create_checkout(order_id=order.id, amount=order.price_som)

    return {
        "success": True,
        "order_id": order.id,
        "amount": order.price_som,
        "currency": "UZS",
        "checkout_url": checkout.payment_url,
        "payment_id": checkout.payment_id
    }

@router.post("/webhook/{provider_name}")
async def payment_webhook(
    provider_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    body = await request.json()
    headers = dict(request.headers)

    provider = get_payment_provider(provider_name)
    result = await provider.process_webhook(body, headers)

    if not result.valid:
        raise HTTPException(status_code=400, detail=result.message or "Invalid webhook signature")

    # Idempotency check: prevent duplicate credit or processing
    res_existing = await db.execute(
        select(Payment).where(
            Payment.provider == provider_name,
            Payment.provider_transaction_id == result.transaction_id,
            Payment.status == "paid"
        )
    )
    existing_payment = res_existing.scalar_one_or_none()
    if existing_payment:
        return {"ok": True, "message": "Transaction already processed (idempotent)"}

    # Fetch order
    res_order = await db.execute(select(Order).where(Order.id == result.order_id))
    order = res_order.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Record payment
    payment = Payment(
        order_id=order.id,
        provider=provider_name,
        provider_transaction_id=result.transaction_id,
        amount=result.amount,
        currency="UZS",
        status="paid",
        confirmed_at=datetime.utcnow()
    )
    db.add(payment)

    # Mark order as paid and queued
    order.is_paid = True
    if order.status == "payment_required":
        order.status = "queued"

    await db.commit()

    return {"ok": True, "order_id": order.id, "status": "confirmed"}
