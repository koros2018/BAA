"""
协作模块路由（collab/*）
从 baa_api.py 拆分，使用 APIRouter 注册
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional

router = APIRouter(tags=["Collaboration"])

# lazy singleton: 共享给 baa_api.py 的模块级变量
_collab_manager = None


def get_collab_manager():
    global _collab_manager
    if _collab_manager is None:
        from src.baa_engine.team_collab import CollaborationManager

        _collab_manager = CollaborationManager()
    return _collab_manager


async def verify_collab_token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "status": "error",
                "error_code": "AUTH_REQUIRED",
                "message": "需要 Bearer token",
            },
        )
    token = auth[7:]
    cm = get_collab_manager()
    user_id = cm.verify_token(token)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={
                "status": "error",
                "error_code": "TOKEN_INVALID",
                "message": "token 无效或已过期",
            },
        )
    return user_id


@router.post("/collab/auth/register")
async def collab_register(body: dict):
    cm = get_collab_manager()
    username = body.get("username", "")
    password = body.get("password", "")
    email = body.get("email", "")
    display_name = body.get("display_name", "")
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "用户名和密码不能为空",
            },
        )
    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "密码长度至少6位",
            },
        )
    result, msg = cm.register_user(username, password, email, display_name)
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {
        "status": "success",
        "user": result,
        "token": result.get("token", ""),
        "message": msg,
    }


@router.post("/collab/auth/login")
async def collab_login(body: dict):
    cm = get_collab_manager()
    username = body.get("username", "")
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "用户名和密码不能为空",
            },
        )
    result, msg = cm.login_user(username, password)
    if not result:
        raise HTTPException(
            status_code=401,
            detail={
                "status": "error",
                "error_code": "AUTH_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "user": result, "token": result.get("token", "")}


@router.get("/collab/users/me")
async def collab_get_me(user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    user = cm.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "USER_NOT_FOUND",
                "message": "用户不存在",
            },
        )
    return {"status": "success", "user": user}


@router.put("/collab/users/me")
async def collab_update_me(body: dict, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    result, msg = cm.update_user(user_id, body)
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "user": result}


@router.get("/collab/users/search")
async def collab_search_users(
    query: str = "", limit: int = 20, _user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    users = cm.list_users(query, limit)
    return {"status": "success", "users": users}


@router.post("/collab/teams")
async def collab_create_team(body: dict, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    name = body.get("name", "")
    if not name:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "团队名称不能为空",
            },
        )
    result, msg = cm.create_team(
        name, user_id, body.get("description", ""), body.get("is_public", False)
    )
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "team": result}


@router.get("/collab/teams")
async def collab_list_teams(user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    teams = cm.list_user_teams(user_id)
    return {"status": "success", "teams": teams}


@router.get("/collab/teams/{team_id}")
async def collab_get_team(team_id: str, _user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    team = cm.get_team(team_id)
    if not team:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "TEAM_NOT_FOUND",
                "message": "团队不存在",
            },
        )
    return {"status": "success", "team": team}


@router.post("/collab/teams/{team_id}/members")
async def collab_add_team_member(
    team_id: str, body: dict, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    target_user_id = body.get("user_id", "")
    role = body.get("role", "member")
    if not target_user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "user_id 不能为空",
            },
        )
    result, msg = cm.add_team_member(team_id, user_id, target_user_id, role)
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "member": result}


@router.delete("/collab/teams/{team_id}/members/{target_id}")
async def collab_remove_team_member(
    team_id: str, target_id: str, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    ok, msg = cm.remove_team_member(team_id, user_id, target_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success"}


@router.post("/collab/projects")
async def collab_create_project(body: dict, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    name = body.get("name", "")
    if not name:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "项目名称不能为空",
            },
        )
    result, msg = cm.create_project(
        name,
        user_id,
        team_id=body.get("team_id", ""),
        description=body.get("description", ""),
        building_type=body.get("building_type", ""),
        building_area=body.get("building_area", 0.0),
    )
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "project": result}


@router.get("/collab/projects")
async def collab_list_projects(status: str = "active", user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    projects = cm.list_user_projects(user_id, status)
    return {"status": "success", "projects": projects}


@router.get("/collab/projects/{project_id}")
async def collab_get_project(project_id: str, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    project = cm.get_project(project_id, user_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "PROJECT_NOT_FOUND",
                "message": "项目不存在",
            },
        )
    return {"status": "success", "project": project}


@router.post("/collab/projects/{project_id}/members")
async def collab_add_project_member(
    project_id: str, body: dict, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    target_id = body.get("user_id", "")
    permission = body.get("permission", "view")
    if not target_id:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "user_id 不能为空",
            },
        )
    result, msg = cm.add_project_member(project_id, user_id, target_id, permission)
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "member": result}


@router.put("/collab/projects/{project_id}/members/{target_id}")
async def collab_update_project_member(
    project_id: str, target_id: str, body: dict, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    permission = body.get("permission", "")
    if not permission:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "permission 不能为空",
            },
        )
    ok, msg = cm.update_project_member_permission(project_id, user_id, target_id, permission)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success"}


@router.delete("/collab/projects/{project_id}/members/{target_id}")
async def collab_remove_project_member(
    project_id: str, target_id: str, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    ok, msg = cm.remove_project_member(project_id, user_id, target_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success"}


@router.get("/collab/teams/{team_id}/projects")
async def collab_list_team_projects(team_id: str, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    projects = cm.list_team_projects(team_id, user_id)
    return {"status": "success", "projects": projects}


@router.post("/collab/review-sessions")
async def collab_create_review_session(body: dict, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    project_id = body.get("project_id", "")
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "project_id 不能为空",
            },
        )
    result, msg = cm.create_review_session(
        project_id,
        user_id,
        name=body.get("name", ""),
        description=body.get("description", ""),
        file_ids=body.get("file_ids"),
    )
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "review_session": result}


@router.get("/collab/projects/{project_id}/review-sessions")
async def collab_list_review_sessions(project_id: str, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    sessions = cm.list_review_sessions(project_id, user_id)
    return {"status": "success", "review_sessions": sessions}


@router.get("/collab/review-sessions/{session_id}")
async def collab_get_review_session(session_id: str, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    rs = cm.get_review_session(session_id, user_id)
    if not rs:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "SESSION_NOT_FOUND",
                "message": "审查会话不存在",
            },
        )
    return {"status": "success", "review_session": rs}


@router.put("/collab/review-sessions/{session_id}/status")
async def collab_update_review_session_status(
    session_id: str, body: dict, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    status = body.get("status", "")
    if not status:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "status 不能为空",
            },
        )
    ok, msg = cm.update_review_session_status(session_id, user_id, status)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success"}


@router.post("/collab/review-sessions/{session_id}/comments")
async def collab_add_comment(
    session_id: str, body: dict, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    content = body.get("content", "")
    if not content:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "评论内容不能为空",
            },
        )
    result, msg = cm.add_comment(
        session_id,
        user_id,
        content,
        comment_type=body.get("comment_type", "note"),
        parent_id=body.get("parent_id", ""),
        clause_id=body.get("clause_id", ""),
        entity_id=body.get("entity_id", ""),
        severity=body.get("severity", "info"),
    )
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "comment": result}


@router.get("/collab/review-sessions/{session_id}/comments")
async def collab_list_comments(
    session_id: str, include_resolved: bool = True, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    comments = cm.list_comments(session_id, user_id, include_resolved)
    return {"status": "success", "comments": comments}


@router.put("/collab/comments/{comment_id}/resolve")
async def collab_resolve_comment(comment_id: str, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    ok, msg = cm.resolve_comment(comment_id, user_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return
    return {"status": "success"}


@router.post("/collab/review-sessions/{session_id}/approval-flow")
async def collab_create_approval_flow(
    session_id: str, body: dict, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    assignee_ids = body.get("assignee_ids", [])
    if not assignee_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_INPUT",
                "message": "assignee_ids 不能为空",
            },
        )
    result, msg = cm.create_approval_flow(
        session_id, user_id, name=body.get("name", "标准审批"), assignee_ids=assignee_ids
    )
    if not result:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success", "approval_flow": result}


@router.get("/collab/review-sessions/{session_id}/approval-flow")
async def collab_get_approval_flow(session_id: str, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    flow = cm.get_approval_flow(session_id)
    if not flow:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "error_code": "APPROVAL_NOT_FOUND",
                "message": "审批流不存在",
            },
        )
    return {"status": "success", "approval_flow": flow}


@router.post("/collab/approval-steps/{step_id}/approve")
async def collab_approve_step(
    step_id: str, body: dict, user_id: str = Depends(verify_collab_token)
):
    cm = get_collab_manager()
    ok, msg = cm.approve_step(step_id, user_id, body.get("comment", ""))
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success"}


@router.post("/collab/approval-steps/{step_id}/reject")
async def collab_reject_step(step_id: str, body: dict, user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    ok, msg = cm.reject_step(step_id, user_id, body.get("comment", ""))
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "OPERATION_FAILED",
                "message": msg,
            },
        )
    return {"status": "success"}


@router.get("/collab/stats")
async def collab_stats(_user_id: str = Depends(verify_collab_token)):
    cm = get_collab_manager()
    return {"status": "success", "stats": cm.get_stats()}
