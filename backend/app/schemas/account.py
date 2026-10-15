from pydantic import BaseModel, Field
from datetime import datetime

class TraderAccountResponse(BaseModel):
    account_id: str
    username: str
    fiat_balance: float
    asset_balance: float
    locked_fiat: float
    locked_asset: float
    total_equity_usd: float
    updated_at: datetime

class DepositWithdrawRequest(BaseModel):
    account_id: str
    amount: float = Field(..., gt=0)
    asset_type: str = Field(..., example="USD") # "USD" or "BTC"
