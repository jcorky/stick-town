# Mesa (projectmesa, Apache-2.0, 5451086)

Our `fauna.agents.run()` steps agents in fixed order (predator always before prey); Mesa's `AgentSet.shuffle_do`
(`mesa/agentset.py:703`) reshuffles each step. `ContinuousSpace` keeps positions in one numpy array and answers
radius / k-nearest queries with vectorised distances + `argpartition` — our `threats()` and flocking are O(N²) loops.
`DataCollector` and the heap event list (`mesa/time/events.py`) suit logging and sleeping/bedded animals.
**Queued:** keyed per-step shuffle; vectorised neighbour queries.
