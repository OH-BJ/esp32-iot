import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
JWT_SECRET = os.environ["JWT_SECRET"]
DEVICE_API_KEY = os.environ["DEVICE_API_KEY"]
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "24"))
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

app = FastAPI(title="XIAO ESP32S3 IoT API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
bearer = HTTPBearer()


# ---------- models ----------
class AuthIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=4, max_length=72)


class LedIn(BaseModel):
    device_id: str = "xiao-s3-01"
    state: bool


class SensorIn(BaseModel):
    device_id: str
    temperature: float | None = None
    analog: int | None = None
    rssi: int | None = None


# ---------- auth helpers ----------
def make_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        return jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "토큰이 유효하지 않습니다")


def device_auth(x_device_key: str = Header(...)):
    if x_device_key != DEVICE_API_KEY:
        raise HTTPException(401, "잘못된 디바이스 키")


# ---------- routes ----------
@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/api/auth/signup")
def signup(body: AuthIn):
    exists = sb.table("users").select("id").eq("username", body.username).execute()
    if exists.data:
        raise HTTPException(409, "이미 존재하는 아이디입니다")
    pw_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    res = sb.table("users").insert({"username": body.username, "password_hash": pw_hash}).execute()
    user = res.data[0]
    return {"token": make_token(user["id"], user["username"]), "username": user["username"]}


@app.post("/api/auth/login")
def login(body: AuthIn):
    res = sb.table("users").select("*").eq("username", body.username).execute()
    if not res.data or not bcrypt.checkpw(body.password.encode(), res.data[0]["password_hash"].encode()):
        raise HTTPException(401, "아이디 또는 비밀번호가 틀렸습니다")
    user = res.data[0]
    return {"token": make_token(user["id"], user["username"]), "username": user["username"]}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return {"id": user["sub"], "username": user["username"]}


@app.get("/api/devices")
def devices(user: dict = Depends(current_user)):
    return sb.table("led_state").select("*").order("device_id").execute().data


@app.get("/api/sensor/latest")
def sensor_latest(device_id: str = "xiao-s3-01", user: dict = Depends(current_user)):
    res = (
        sb.table("sensor_data").select("*").eq("device_id", device_id)
        .order("created_at", desc=True).limit(1).execute()
    )
    return res.data[0] if res.data else None


@app.get("/api/sensor/history")
def sensor_history(
    device_id: str = "xiao-s3-01",
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(current_user),
):
    res = (
        sb.table("sensor_data").select("*").eq("device_id", device_id)
        .order("created_at", desc=True).limit(limit).execute()
    )
    return list(reversed(res.data))


@app.get("/api/led")
def led_get(device_id: str = "xiao-s3-01", user: dict = Depends(current_user)):
    res = sb.table("led_state").select("*").eq("device_id", device_id).execute()
    if not res.data:
        raise HTTPException(404, "디바이스가 없습니다")
    return res.data[0]


@app.post("/api/led")
def led_set(body: LedIn, user: dict = Depends(current_user)):
    now = datetime.now(timezone.utc).isoformat()
    res = sb.table("led_state").upsert(
        {"device_id": body.device_id, "state": body.state, "updated_at": now}
    ).execute()
    return res.data[0]


# ---------- device (ESP32) routes ----------
@app.post("/api/device/data", dependencies=[Depends(device_auth)])
def device_data(body: SensorIn):
    """ESP32가 센서값을 올리고, 응답으로 현재 LED 명령을 받는다 (폴링 1회로 양방향 처리)."""
    sb.table("sensor_data").insert(body.model_dump()).execute()
    now = datetime.now(timezone.utc).isoformat()
    res = sb.table("led_state").select("state").eq("device_id", body.device_id).execute()
    if res.data:
        sb.table("led_state").update({"last_seen": now}).eq("device_id", body.device_id).execute()
        led = res.data[0]["state"]
    else:
        sb.table("led_state").insert({"device_id": body.device_id, "state": False, "last_seen": now}).execute()
        led = False
    return {"led": led}


@app.get("/api/device/led", dependencies=[Depends(device_auth)])
def device_led(device_id: str = "xiao-s3-01"):
    res = sb.table("led_state").select("state").eq("device_id", device_id).execute()
    return {"led": res.data[0]["state"] if res.data else False}
