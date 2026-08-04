"""
管理后台反馈管理接口

集中展示并筛选全量用户反馈（点赞/点踩 + 结构化原因 reason + 文字评论），
供管理员定位失败 case、分析优化方向。所有端点均要求管理员角色。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.feedback import AdminFeedbackItem, AdminFeedbackSummary
from app.services.feedback_service import FeedbackService
from app.utils.dependencies import get_current_admin
from app.models.user import User
from app.core.response import ApiResponse, PaginatedResponse
from app.core.exceptions import BaseAppException

router = APIRouter(tags=["admin-feedbacks"])


@router.get("/api/admin/feedbacks/summary", response_model=ApiResponse[AdminFeedbackSummary])
async def feedback_summary(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """管理后台反馈汇总：总数 / 点赞 / 点踩 / 按原因分布。"""
    summary = FeedbackService.feedback_summary(db)
    return ApiResponse.ok(data=AdminFeedbackSummary(**summary))


@router.get("/api/admin/feedbacks", response_model=PaginatedResponse[AdminFeedbackItem])
async def list_admin_feedbacks(
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    rating: Optional[int] = Query(None, ge=-1, le=1, description="1=点赞, -1=点踩"),
    reason: Optional[str] = Query(None, description="结构化原因过滤(答非所问/事实错误/没召回/太啰嗦/其他)"),
    keyword: Optional[str] = Query(None, description="反馈内容关键词(模糊匹配 comment)"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD(含当天)"),
    sort_by: str = Query("created_at", pattern="^(created_at|rating|id)$", description="排序字段"),
    order: str = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """管理后台：列出全量用户反馈，支持类型/原因/关键词/日期筛选与排序。"""
    try:
        items, total = FeedbackService.list_all_feedbacks(
            db,
            skip=skip,
            limit=limit,
            rating=rating,
            reason=reason,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
            order=order,
        )
        return PaginatedResponse.ok(
            data=[AdminFeedbackItem(**it) for it in items],
            total=total,
            page=skip // limit + 1,
            page_size=limit,
        )
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
