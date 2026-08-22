"""Phase B service: org-chart collaboration (the Paperclip layer).

Pure logic shared by routes and the agent engine:
- org tree: build the reports_to hierarchy, validate no cycles
- delegation: a manager agent assigns a task to a direct report
- goals: create/decompose goals into tasks, roll up progress
- notifications: fan-out to human members (the bell)
- comments: threaded discussion on tasks with @mention resolution
"""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.events import bus
from truss_kernel.models.agent import Agent, AgentStatus, AgentTask, TaskStatus
from truss_kernel.models.org import Goal, GoalStatus, Notification, TaskComment
from truss_kernel.models.tenant import Membership, TenantRole, User


class OrgError(ValueError):
    pass


# ---------- org tree ----------

async def set_reports_to(db: AsyncSession, tenant_id: uuid.UUID,
                         agent: Agent, manager_agent_id: uuid.UUID | None,
                         manager_user_id: uuid.UUID | None) -> None:
    """Point an agent at a manager (agent or human). Rejects cycles + self-report."""
    if manager_agent_id and manager_user_id:
        raise OrgError("set exactly one of manager_agent_id / manager_user_id")
    if manager_agent_id == agent.id:
        raise OrgError("an agent cannot report to itself")

    if manager_agent_id:
        mgr = (await db.execute(select(Agent).where(
            Agent.id == manager_agent_id, Agent.tenant_id == tenant_id
        ))).scalar_one_or_none()
        if mgr is None:
            raise OrgError("manager agent not found")
        # walk up from the proposed manager; if we reach `agent`, it's a cycle
        seen = {agent.id}
        cur = mgr
        while cur is not None:
            if cur.id in seen:
                raise OrgError("reporting cycle detected")
            seen.add(cur.id)
            cur_id = cur.reports_to_agent_id
            cur = None
            if cur_id:
                cur = (await db.execute(select(Agent).where(
                    Agent.id == cur_id, Agent.tenant_id == tenant_id
                ))).scalar_one_or_none()

    agent.reports_to_agent_id = manager_agent_id
    agent.reports_to_user_id = manager_user_id


async def build_org_tree(db: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    """Return the org chart as a forest of nodes (roots = agents with no manager)."""
    agents = (await db.execute(
        select(Agent).where(Agent.tenant_id == tenant_id).order_by(Agent.created_at)
    )).scalars().all()
    users = (await db.execute(
        select(User).join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id)
    )).scalars().all()
    user_name = {u.id: u.full_name or u.email for u in users}

    nodes = {}
    for a in agents:
        nodes[str(a.id)] = {
            "id": str(a.id),
            "kind": "agent",
            "name": a.name,
            "role": a.role,
            "icon": a.icon,
            "status": a.status.value,
            "reports_to_agent": str(a.reports_to_agent_id) if a.reports_to_agent_id else None,
            "reports_to_user": str(a.reports_to_user_id) if a.reports_to_user_id else None,
            "children": [],
        }
    roots = []
    for a in agents:
        node = nodes[str(a.id)]
        if a.reports_to_agent_id and str(a.reports_to_agent_id) in nodes:
            nodes[str(a.reports_to_agent_id)]["children"].append(node)
        else:
            # reports to a human (or nobody) -> root, label the human manager
            if a.reports_to_user_id:
                node["manager_name"] = user_name.get(a.reports_to_user_id, "")
            roots.append(node)
    return roots


async def direct_reports(db: AsyncSession, tenant_id: uuid.UUID, manager: Agent) -> list[Agent]:
    rows = (await db.execute(select(Agent).where(
        Agent.tenant_id == tenant_id,
        Agent.reports_to_agent_id == manager.id,
        Agent.status != AgentStatus.terminated,
    ))).scalars().all()
    return list(rows)


# ---------- delegation ----------

async def delegate_task(db: AsyncSession, tenant_id: uuid.UUID, manager: Agent,
                        report: Agent, title: str, description: str = "",
                        goal_id: uuid.UUID | None = None, needs_review: bool = False,
                        priority: int = 0) -> AgentTask:
    """A manager agent assigns a task to a direct report.

    The report must actually report to the manager. Delegated tasks respect
    the same approval gate: needs_review=True -> proposed (human must approve).
    """
    if report.reports_to_agent_id != manager.id:
        raise OrgError(f"'{report.name}' does not report to '{manager.name}'")
    if report.status == AgentStatus.terminated:
        raise OrgError(f"'{report.name}' is terminated")

    t = AgentTask(
        tenant_id=tenant_id,
        agent_id=report.id,
        title=title,
        description=description,
        needs_review=needs_review,
        priority=priority,
        created_by=manager.id,
        delegated_by_agent_id=manager.id,
        goal_id=goal_id,
        status=TaskStatus.proposed if needs_review else TaskStatus.approved,
        approved_by=None if needs_review else manager.id,
    )
    db.add(t)
    await db.flush()
    await bus.emit(db, tenant_id=tenant_id, event_type="agent.task_delegated",
                   payload={"manager_id": str(manager.id), "manager": manager.name,
                            "agent_id": str(report.id), "agent": report.name,
                            "task_id": str(t.id), "title": title,
                            "needs_review": needs_review, "actor_type": "agent"},
                   actor_id=manager.id)
    return t


# ---------- goals ----------

async def create_goal(db: AsyncSession, tenant_id: uuid.UUID, *, title: str,
                      description: str = "", metric: str = "", target_value: float = 0.0,
                      unit: str = "", owner_agent_id=None, owner_user_id=None,
                      parent_goal_id=None, created_by=None, due_at: str = "") -> Goal:
    if not owner_agent_id and not owner_user_id:
        raise OrgError("a goal needs an owner (agent or user)")
    if owner_agent_id and owner_user_id:
        raise OrgError("set exactly one owner")
    g = Goal(
        tenant_id=tenant_id, title=title, description=description,
        metric=metric, target_value=target_value, unit=unit,
        owner_agent_id=owner_agent_id, owner_user_id=owner_user_id,
        parent_goal_id=parent_goal_id, created_by=created_by, due_at=due_at,
    )
    db.add(g)
    await db.flush()
    await bus.emit(db, tenant_id=tenant_id, event_type="goal.created",
                   payload={"goal_id": str(g.id), "title": title, "actor_type": "user"},
                   actor_id=created_by)
    return g


def goal_progress(g: Goal) -> float:
    """0..1 progress toward the target (clamped)."""
    if g.target_value <= 0:
        return 0.0
    return max(0.0, min(1.0, g.current_value / g.target_value))


async def roll_up_progress(db: AsyncSession, tenant_id: uuid.UUID, goal: Goal) -> None:
    """If the goal has sub-goals, set current_value = sum of children progress * target."""
    children = (await db.execute(select(Goal).where(
        Goal.tenant_id == tenant_id, Goal.parent_goal_id == goal.id,
        Goal.status == GoalStatus.active,
    ))).scalars().all()
    if not children:
        return
    frac = sum(goal_progress(c) for c in children) / len(children)
    goal.current_value = round(frac * goal.target_value, 4)
    if goal.target_value > 0 and goal.current_value >= goal.target_value:
        goal.status = GoalStatus.achieved


# ---------- notifications ----------

async def notify(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, *,
                 kind: str, title: str, body: str = "", link: str = "",
                 actor_id=None, actor_type: str = "system") -> Notification:
    n = Notification(
        tenant_id=tenant_id, user_id=user_id, kind=kind, title=title,
        body=body, link=link, actor_id=actor_id, actor_type=actor_type,
    )
    db.add(n)
    await db.flush()
    return n


async def notify_admins(db: AsyncSession, tenant_id: uuid.UUID, *, kind: str,
                        title: str, body: str = "", link: str = "",
                        actor_id=None, actor_type: str = "system") -> int:
    """Fan a notification out to all owner/admin members. Returns count."""
    admins = (await db.execute(
        select(Membership.user_id).where(
            Membership.tenant_id == tenant_id,
            Membership.role.in_([TenantRole.owner, TenantRole.admin]),
        )
    )).scalars().all()
    for uid in admins:
        await notify(db, tenant_id, uid, kind=kind, title=title, body=body,
                     link=link, actor_id=actor_id, actor_type=actor_type)
    return len(admins)


# ---------- comments + mentions ----------

MENTION_RE = re.compile(r"@([A-Za-z0-9_.\-]+)")


async def resolve_mentions(db: AsyncSession, tenant_id: uuid.UUID, body: str) -> list[uuid.UUID]:
    """Resolve @name tokens to member user ids (match on name or email local-part)."""
    names = set(MENTION_RE.findall(body))
    if not names:
        return []
    members = (await db.execute(
        select(User).join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id)
    )).scalars().all()
    out = []
    for u in members:
        local = u.email.split("@")[0].lower()
        full = (u.full_name or "").lower().replace(" ", "")
        for n in names:
            if n.lower() in (local, full, u.email.lower()):
                out.append(u.id)
                break
    return out


async def add_comment(db: AsyncSession, tenant_id: uuid.UUID, task: AgentTask, *,
                      body: str, author_id, author_type: str = "user") -> TaskComment:
    mentions = await resolve_mentions(db, tenant_id, body)
    c = TaskComment(
        tenant_id=tenant_id, task_id=task.id, body=body,
        author_id=author_id, author_type=author_type,
        mentions=[str(m) for m in mentions],
    )
    db.add(c)
    await db.flush()
    # notify mentioned humans
    for uid in mentions:
        await notify(db, tenant_id, uid, kind="mention",
                     title=f"You were mentioned on task: {task.title}",
                     body=body[:200], link=f"/agents/{task.agent_id}",
                     actor_id=author_id, actor_type=author_type)
    await bus.emit(db, tenant_id=tenant_id, event_type="agent.task_commented",
                   payload={"task_id": str(task.id), "title": task.title,
                            "mentions": len(mentions), "actor_type": author_type},
                   actor_id=author_id)
    return c
