"""Platform adapters."""

from __future__ import annotations

from confluo_scout.config import Secrets


def build_adapters(secrets: Secrets) -> dict:
    from confluo_scout.adapters.aaai import AAAIAdapter
    from confluo_scout.adapters.acl import ACLAdapter
    from confluo_scout.adapters.cvf import CVFAcceptedAdapter, CVFAdapter
    from confluo_scout.adapters.ecva import ECVAAdapter
    from confluo_scout.adapters.ijcai import IJCAIAdapter
    from confluo_scout.adapters.openreview import OpenReviewAdapter
    from confluo_scout.adapters.pmlr import PMLRAdapter

    adapters = [OpenReviewAdapter(secrets), CVFAdapter(), CVFAcceptedAdapter(), ECVAAdapter(), ACLAdapter(),
                PMLRAdapter(), AAAIAdapter(), IJCAIAdapter()]
    return {a.name: a for a in adapters}
