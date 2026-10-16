"""Six entry points and work-specific review policy; no queue/ACL side effects."""
ENTRY_POINTS = {
    'operations': 'clawdia-assistant', 'strategy': 'mako-marketing',
    'editorial': 'pixel-social-media', 'visual': 'canvas-designer',
    'engineering': 'bolt-executor', 'quality': 'oath-verifier',
}
QUALITY_COORDINATOR = 'oath-verifier'
REVIEW_POOLS = {
    'operations': ('raven-critic', 'oath-verifier'),
    'strategy': ('raven-critic', 'oath-verifier'),
    'editorial': ('oath-verifier', 'raven-critic'),
    'visual': ('oath-verifier', 'probe-qa'),
    'engineering': ('lens-reviewer', 'vault-security', 'oath-verifier'),
    'quality': ('raven-critic', 'lens-reviewer', 'probe-qa'),
}
SPECIALISTS = {
    'operations': ('atlas-project', 'helm-conductor'),
    'strategy': ('sage-strategy', 'nex-sales', 'dex-data', 'prism-scientist'),
    'editorial': ('mako-marketing', 'reels-copilot', 'canvas-designer'),
    'visual': ('bolt-executor', 'canvas-designer'),
    'engineering': ('helm-conductor', 'hawk-debugger', 'compass-planner', 'zen-simplifier'),
    'quality': ('lens-reviewer', 'probe-qa', 'raven-critic', 'vault-security'),
}


def work_policy(front):
    """Documented planning policy; dispatcher still owns enforcement and leases."""
    if front not in ENTRY_POINTS:
        raise ValueError('unknown_front')
    return dict(schema_version=2, front=front, entry_point=ENTRY_POINTS[front],
                quality_coordinator=QUALITY_COORDINATOR,
                reviewer_candidates=list(REVIEW_POOLS[front]), specialists=list(SPECIALISTS[front]),
                assignment='per_work_not_fixed_trio', coordinator_distinct_from_producer=True,
                reviewer_independent_of_contributors=True, producer_wip_limit=1,
                correction_cycle_limit=2, exhausted_action='escalate_without_replay',
                hierarchy='Mission -> GoalProject -> Goal -> Ticket',
                ticket_links=['project_id', 'goal_id'], legacy_goal_tasks='frozen_not_new_work',
                lease='existing_ticket_checkout_only', dispatch_enforced_here=False,
                evidence='artifact_ref+version+sha256+criteria+observations',
                completion='technical_acceptance_and_measured_objective_are_distinct')


def reviewer_candidates(front, *, contributors, authorized_available, active_work):
    """Filter trusted caller snapshots; never grant access or claim an assignment.

    Availability and loads must come from the queue owner's authenticated context.
    Missing/invalid load is unknown and excluded. No database/tool access here.
    """
    pool = work_policy(front)['reviewer_candidates']
    eligible = [slug for slug in pool if slug in authorized_available and slug not in contributors
                and type(active_work.get(slug)) is int and active_work[slug] == 0]
    return eligible  # Stable domain order; empty means escalate, never self-review.
