"""
管理后台统计服务：聚合全量会话 / 消息 / 反馈数据。

安全说明：当前项目未实现独立 admin 角色，本模块直接返回全量数据，用于
演示与故障排查。生产环境应在路由层补充管理员鉴权（例如依赖 get_current_admin
而非 get_current_user），避免任意登录用户看到全量业务数据。
"""
from datetime import date, timedelta
from typing import Dict, Any, List

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.models.session import Session as SessionModel
from app.models.message import Message
from app.models.feedback import Feedback


class StatsService:
    """全量业务指标聚合（无用户隔离，供管理后台使用）。"""

    @staticmethod
    def overview(db: DBSession) -> Dict[str, Any]:
        """概览数字：会话数 / 消息数 / 反馈数 / 点赞 / 点踩。"""
        total_sessions = db.query(SessionModel).count()
        total_messages = db.query(Message).count()
        total_feedbacks = db.query(Feedback).count()
        like_count = db.query(Feedback).filter(Feedback.rating == 1).count()
        dislike_count = db.query(Feedback).filter(Feedback.rating == -1).count()
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "total_feedbacks": total_feedbacks,
            "like_count": like_count,
            "dislike_count": dislike_count,
        }

    @staticmethod
    def session_list(db: DBSession, skip: int = 0, limit: int = 50) -> Dict[str, Any]:
        """全量会话列表（含每会话的问答数 / 最后更新时间），按更新时间倒序。"""
        sq = (
            db.query(
                SessionModel.id,
                SessionModel.title,
                SessionModel.user_id,
                SessionModel.updated_at,
                func.count(Message.id).label("msg_count"),
            )
            .outerjoin(Message, Message.session_id == SessionModel.id)
            .group_by(
                SessionModel.id,
                SessionModel.title,
                SessionModel.user_id,
                SessionModel.updated_at,
            )
            .order_by(SessionModel.updated_at.desc())
        )
        total = db.query(SessionModel).count()
        rows = sq.offset(skip).limit(limit).all()
        items = [
            {
                "id": r.id,
                "title": r.title,
                "user_id": r.user_id,
                "msg_count": r.msg_count,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
        return {"items": items, "total": total}

    @staticmethod
    def daily_qa(db: DBSession, days: int = 14) -> List[Dict[str, Any]]:
        """按日期聚合 assistant 消息数（即「日均问答量」），缺失日期补 0 保证连续。"""
        since = date.today() - timedelta(days=days - 1)
        day_expr = func.date(Message.created_at)
        rows = (
            db.query(day_expr.label("day"), func.count(Message.id).label("cnt"))
            .filter(Message.role == "assistant", Message.created_at >= since)
            .group_by(day_expr)
            .order_by(day_expr)
            .all()
        )
        present = {r.day: r.cnt for r in rows}
        result = []
        for i in range(days):
            d = (since + timedelta(days=i)).isoformat()
            result.append({"date": d, "count": present.get(d, 0)})
        return result

    @staticmethod
    def feedback_stats(db: DBSession, days: int = 14) -> Dict[str, Any]:
        """反馈按日期分布：每日点赞 / 点踩计数，缺失日期补 0。"""
        since = date.today() - timedelta(days=days - 1)
        day_expr = func.date(Feedback.created_at)
        rows = (
            db.query(day_expr.label("day"), Feedback.rating, func.count(Feedback.id).label("cnt"))
            .filter(Feedback.created_at >= since)
            .group_by(day_expr, Feedback.rating)
            .all()
        )
        series: Dict[str, Dict[str, int]] = {}
        for r in rows:
            series.setdefault(r.day, {"like": 0, "dislike": 0})
            if r.rating == 1:
                series[r.day]["like"] += r.cnt
            elif r.rating == -1:
                series[r.day]["dislike"] += r.cnt
        daily = [
            {"date": d, **series.get(d, {"like": 0, "dislike": 0})}
            for d in [(since + timedelta(days=i)).isoformat() for i in range(days)]
        ]
        return {"daily": daily}
