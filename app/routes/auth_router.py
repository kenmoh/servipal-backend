from os import name

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from app.services import user_service
from app.schemas.user_schemas import UserCreate, LoginRequest, TokenResponse, UserProfileResponse
from app.database.supabase import get_supabase_client, get_supabase_admin_client
from app.config.logging import logger
from app.dependencies import auth
from supabase import AsyncClient

from app.utils.utils import send_otp, verify_otp

class OTPRequest(BaseModel):
    otp: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')

class OTPResponse(BaseModel):
    message: str
    status: str
    

class OTPVerifyResponse(BaseModel):
    message: str
    phone_verified: bool
    account_status: str

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/signup", response_model=TokenResponse)
async def signup(
    user_data: UserCreate, request: Request, supabase=Depends(get_supabase_admin_client)
):
    """
    Register a new user account.

    Args:
        user_data (UserCreate): The user registration details.

    Returns:
        TokenResponse: Access token and user profile information.
    """
    logger.info(
        "signup_endpoint_called",
        email=user_data.email,
        user_type=user_data.user_type.value,
    )
    return await user_service.create_user_account(user_data, supabase, request)


@router.post("/login", response_model=UserProfileResponse)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,                          # inject Response to set cookies
    supabase=Depends(get_supabase_client),
):
    result = await user_service.login_user(login_data, supabase, request)

    # is_prod = settings.ENVIRONMENT == "production"

    response.set_cookie(
        key="access_token",
        value=result["access_token"],
        httponly=True,                           
        secure=True,                         
        samesite="strict",                       
        max_age=result["expires_in"],
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=result["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=60 * 60 * 24 * 12,              
        path="/auth/refresh",                    
    )

    return result["user"]


# @router.post("/login", response_model=TokenResponse)
# async def login(
#     login_data: LoginRequest, request: Request, supabase=Depends(get_supabase_client)
# ):
#     """
#     Authenticate a user and return access token.

#     Args:
#         login_data (LoginRequest): Email and password.

#     Returns:
#         TokenResponse: Access token and user profile information.
#     """
#     logger.info("login_endpoint_called", email=login_data.email)
#     return await user_service.login_user(login_data, supabase, request)


@router.post("/logout")
async def logout(response: Response, supabase=Depends(get_supabase_client)):
    await supabase.auth.sign_out()
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=UserProfileResponse)
async def refresh(
    request: Request,
    response: Response,
    supabase=Depends(get_supabase_client),
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token provided.")

    try:
        session = await supabase.auth.refresh_session(refresh_token)
    except Exception:
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    # is_prod = settings.ENVIRONMENT == "production"

    response.set_cookie(
        key="access_token",
        value=session.session.access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=session.session.expires_in,
        path="/",
    )

    return session.user

@router.post("/token", response_model=TokenResponse, include_in_schema=False)
async def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    supabase=Depends(get_supabase_client),
):
    """OAuth2 compatible token endpoint for Swagger UI authentication."""
    logger.info("token_endpoint_called", username=form_data.username)
    login_data = LoginRequest(email=form_data.username, password=form_data.password)

    return await user_service.login_user(login_data, supabase, request)
    
    response.set_cookie(
        key="access_token",
        value=result["access_token"],
        httponly=True,                           
        secure=True,                         
        samesite="strict",                       
        max_age=result["expires_in"],
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=result["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=60 * 60 * 24 * 12,              
        path="/auth/refresh",                    
    )
    return TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        token_type="bearer",
        user=result["user"],
        expires_in=result["expires_in"],
    )


@router.post(
    "/forgot-password", status_code=status.HTTP_200_OK, include_in_schema=False
)
async def forgot_password(
    data: auth.ForgotPasswordRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await auth.forgot_password(data, supabase)


@router.post("/reset-password", status_code=status.HTTP_200_OK, include_in_schema=False)
async def reset_password(
    data: auth.ResetPasswordRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await auth.reset_password(data, supabase)


@router.put("/change-password", status_code=status.HTTP_200_OK, include_in_schema=False)
async def change_password(
    data: auth.ChangePasswordRequest,
    current_user: dict = Depends(auth.get_current_user),
    supabase: AsyncClient = Depends(get_supabase_client),
) -> auth.Status:
    
    return auth.change_password(data, current_user, supabase)


@router.post("/request-otp", status_code=status.HTTP_200_OK)
async def reques_otp(
    current_user: dict = Depends(auth.get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
) -> OTPResponse:
    
    phone_number = current_user.get("phone_number")
    email = current_user.get("email")
    name_from_email = email.split("@")[0] if email else "User"
    name = current_user.get("full_name") or current_user.get("business_name") or current_user.get("store_name") or name_from_email
    
    return await send_otp(name=name, email=email, phone=phone_number, supabase=supabase, user_id=current_user.get("id"))


@router.post("/verify-otp", status_code=status.HTTP_200_OK)
async def confirm_phone_number(
    data: OTPRequest,
    current_user: dict = Depends(auth.get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
) -> OTPVerifyResponse:
    
    
    return await verify_otp(otp=data.otp, supabase=supabase, user_id=current_user.get("id"))