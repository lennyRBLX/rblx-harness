"""frame_census scope knowledge, shipped as code: scope|group|spike-cause|remedy
rows, plus the exclusion set, the container set, and the thread class. A row
exists only where a remedy was established; a name-derived guess resolves to
advice|void, which tells the optimizer to profile rather than trust a
plausible string."""

# idle — excluded from ranking. waitOnGpu and waitUntilCompleted are excluded
# from ranking but LOAD-BEARING for attribution: Render time that is mostly
# those two means gpu-bound, not render-bound.
EXCLUDED_IDLE = {
    "Sleep",
    "waitOnGpu",
    "waitUntilCompleted",
    "waitUntilEmpty",
    "acquireFramebuffer",
}

# diagnostic waits: excluded from CPU-work ranking, but their SIZE is itself
# the signal
DIAGNOSTIC_WAITS = {
    "waitOnGpu": "gpu-bound - reduce draw calls, texture size, shadows, overdraw",
    "waitUntilCompleted": "gpu-bound - reduce draw calls, texture size, shadows, overdraw",
    "Wait for Render Thread": "main serialized behind render - check what Main feeds Render per frame",
    "WaitingHybridScriptJob": "script-resume budget saturated - too many waiting or long-running scripts",
    "LegacyLock": "stop-the-world serialization - report high values",
    "Write Marshalled": "DataModel lock contention",
    "Read Marshalled": "DataModel lock contention",
}

# containers are always >= the sum of their children; ranking one names the
# wrapper
CONTAINERS = {
    "runJob",
    "Worker::runJob",
    "Thread (FG)",
    "Thread (BG)",
    "TS::JobStep",
    "TS::ArbiterStep",
    "TS::Step",
    "parallelFor",
    "UpdateView",
    "PreRender",
    "deferredThreads",
    "Heartbeat",
    "Stepped",
    "RenderStepped",
    "Render",
    "Simulation",
    "frame",
}

# async/worker scopes: width is occupancy, not critical path
WORKER_CLASS = {
    "VisibleQuery",
    "CullJob",
    "Parallel FastClusters",
}

# the $-families the exporter clones parent stats onto: collapse in the
# aggregate table and recompute from the per-marker detail log
DOLLAR_FAMILIES = ("$Script", "$newindex", "$index", "$namecall", "$call")

# scope|group|spike-cause|remedy — remedies established from the creator-docs
# tag table and the audited microprofiler references; everything else is
# advice|void
ROWS = [
    ("updateInvalidatedFastClusters", "Simulation", "avatar/MeshPart churn >4ms", "reduce per-frame avatar and MeshPart mutation"),
    ("stepWorldThrottled", "Simulation", "physics throttling engaged", "watched qualitatively - reduce simulated assemblies"),
    ("updateBroadphase", "Simulation", "collision broadphase load", "fewer moving assemblies, simpler collision"),
    ("worldStep", "Simulation", "physics step", "reduce assemblies, anchor static parts"),
    ("preContactStepSleepStage", "Simulation", "touch sleep determination", "advice|void"),
    ("computeLightingPerform", "Render", "lighting recompute every client frame", "reduce dynamic lights and shadow casters"),
    ("Pass3dAdorn", "Render", "3D world GUI (Billboard/Surface/Humanoid labels)", "fewer BillboardGuis and name labels in view"),
    ("Prepare", "Render", "scene prep exceeding budget", "reduce instance churn reaching the render thread"),
    ("Perform", "Render", "draw submission", "reduce draw calls and material variety"),
    ("Present", "Render", "swap wait", "gpu-bound when waitUntilCompleted dominates"),
    ("ShadowsRender", "Render", "shadow map cost", "CastShadow=false on filler geometry"),
    ("UI,Layout", "UI", "relayout storm from a LayerCollector", "batch GUI property writes; cache text bounds"),
    ("Layout", "UI", "relayout storm from a LayerCollector", "batch GUI property writes; cache text bounds"),
    ("newindex_CFrame", "LuaBridge", "per-instance CFrame writes", "batch into one workspace:BulkMoveTo"),
    ("newindex", "LuaBridge", "property write volume", "batch writes; cache instance references"),
    ("index", "LuaBridge", "property read volume", "cache reads in locals outside loops"),
    ("namecall", "LuaBridge", "method call volume", "hoist repeated calls; cache results"),
    ("Script", "Scripts", "script CPU", "luau_hotspot names the function; OPT1's ladder"),
    ("deferredThreads", "Scripts", "deferred signal resumption", "attribute to the scripts inside, never the wrapper"),
    ("WaitingHybridScriptJob", "Scripts", "script-resume budget saturated", "fewer waiting scripts; shorter resumes"),
    ("RunService.Heartbeat", "Scripts", "per-frame connections", "profile labels per OPT20; batch work"),
    ("GC", "Engine", "garbage collection pressure", "reduce per-frame allocation; reuse tables and buffers"),
    ("Net", "Network", "replication volume", "incremental replication per BC2; smaller payloads"),
    ("Replicator", "Network", "replication packet processing", "fewer changing instances; batch state"),
]


def lookup(scope_name):
    """Best-established row for a scope name; advice|void when nothing was."""
    for name, group, cause, remedy in ROWS:
        if scope_name == name or scope_name.startswith(name):
            return group, cause, remedy
    return "void", "advice", "void"
