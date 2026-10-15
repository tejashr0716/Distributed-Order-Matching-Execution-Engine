from fastapi import APIRouter, HTTPException
from datetime import datetime
from ..schemas.account import TraderAccountResponse, DepositWithdrawRequest
from ..services.database_service import db_service
from ..services.matching_engine_wrapper import matching_engine

router = APIRouter(prefix="/accounts", tags=["Accounts"])

@router.get("/{account_id}", response_model=TraderAccountResponse)
async def get_account_profile(account_id: str):
    acc = await db_service.get_account(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found.")
    
    # Calculate estimated equity in USD assuming BTC ~$60,000 or current mid_price
    depth = matching_engine.get_market_depth("BTC-USD", max_depth=1)
    btc_price = depth["mid_price"] if depth["mid_price"] > 0 else 60000.0
    
    fiat = float(acc["fiat_balance"])
    asset = float(acc["asset_balance"])
    locked_f = float(acc["locked_fiat"])
    locked_a = float(acc["locked_asset"])
    total_equity = fiat + locked_f + (asset + locked_a) * btc_price

    return TraderAccountResponse(
        account_id=acc["account_id"],
        username=acc["username"],
        fiat_balance=fiat,
        asset_balance=asset,
        locked_fiat=locked_f,
        locked_asset=locked_a,
        total_equity_usd=round(total_equity, 2),
        updated_at=acc["updated_at"] or datetime.utcnow()
    )

@router.post("/deposit")
async def deposit_funds(req: DepositWithdrawRequest):
    acc = await db_service.get_account(req.account_id)
    if not acc:
        raise HTTPException(status_code=404, detail=f"Account '{req.account_id}' not found.")
    
    fiat_delta = req.amount if req.asset_type.upper() == "USD" else 0.0
    asset_delta = req.amount if req.asset_type.upper() in ("BTC", "ETH") else 0.0

    success = await db_service.adjust_balance(req.account_id, fiat_delta, asset_delta)
    if not success:
        raise HTTPException(status_code=400, detail="Deposit failed.")

    updated = await db_service.get_account(req.account_id)
    return {
        "success": True,
        "account_id": req.account_id,
        "fiat_balance": float(updated["fiat_balance"]),
        "asset_balance": float(updated["asset_balance"])
    }
