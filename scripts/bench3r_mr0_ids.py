from __future__ import annotations

MERGE_SHA = "731de9de429589f468d6cb577bdeab11932c2bc8"
MEM = "MR-" + "MEM-"
ROUTE = "MR-" + "ROUTE-"
MEMORY_CASES = [
    MEM + "003-session-recall",
    MEM + "008-child-proposal-parent-write",
    MEM + "010-injection-reject",
    MEM + "012-unsupported-recall",
]
ROUTING_CASES = [
    ROUTE + "003-code-patch-test",
    ROUTE + "006-context-insufficient",
    ROUTE + "009-semantic-no-reroute",
    ROUTE + "012-no-eligible-route",
]
SENTINELS = [MEM + "001-user-preference", ROUTE + "002-general-synthesis"]
SEED_DERIVATION = "split BENCH-3 merge SHA into consecutive 8-hex chunks, convert to unsigned integers, then take modulo 1000000"
SEEDS = [340254, 96436]
RESERVED_SEED = 907223
FORBIDDEN_SEEDS = [
    17, 42, 271828, 314159, 8675309,
    371872, 665465, 623659, 849690, 603823, 413360,
]
