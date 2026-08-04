"""
管理后台统计接口（聚合全量数据）。

权限：本模块所有接口均要求管理员角色(role='admin')，普通用户访问返回 403。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.stats_service import StatsService
from app.utils.dependencies import get_current_admin
from app.models.user import User
from app.core.response import ApiResponse
from app.core.tracing import span

router = APIRouter(tags=["admin-stats"])


@router.get("/overview", response_model=ApiResponse)
async def stats_overview(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """概览统计：会话数 / 消息数 / 反馈数 / 点赞 / 点踩。"""
    with span("stats_overview"):
        data = StatsService.overview(db)
        return ApiResponse.ok(data=data)


@router.get("/sessions", response_model=ApiResponse)
async def stats_sessions(
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """全量会话记录（含每会话问答数、最后更新时间）。"""
    with span("stats_sessions"):
        data = StatsService.session_list(db, skip, limit)
        return ApiResponse.ok(data=data)


@router.get("/daily-qa", response_model=ApiResponse)
async def stats_daily_qa(
    days: int = Query(14, ge=1, le=90, description="统计天数（默认近 14 天）"),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """日均问答量时间序列（供折线图）。"""
    with span("stats_daily_qa"):
        data = StatsService.daily_qa(db, days)
        return ApiResponse.ok(data=data)


@router.get("/feedbacks", response_model=ApiResponse)
async def stats_feedbacks(
    days: int = Query(14, ge=1, le=90, description="统计天数（默认近 14 天）"),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """用户反馈按日期分布（每日点赞 / 点踩）。"""
    with span("stats_feedbacks"):
        data = StatsService.feedback_stats(db, days)
        return ApiResponse.ok(data=data)
