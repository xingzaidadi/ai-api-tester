from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel, Field

app = FastAPI()
router = APIRouter(prefix="/orders")


def current_user():
    return {"id": 1}


class CreateOrderRequest(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)


@router.post("")
async def create_order(payload: CreateOrderRequest, user=Depends(current_user)):
    return {"data": {"orderId": 1, "quantity": payload.quantity}}


@router.get("/{order_id}")
async def get_order(order_id: int, user=Depends(current_user)):
    return {"data": {"orderId": order_id}}


app.include_router(router, prefix="/api/v1")
