# Large HRX files and memory

- When streaming large HRX/XML files with `lxml.etree.iterparse`, clear processed
  elements and delete their preceding siblings from the parent. Keep a subtree
  intact until it has been processed if its descendants are needed.
- Run large-model inspection scripts and tests as separate processes with a
  memory limit where practical. On systems with a working user systemd bus,
  `systemd-run --user --scope -p MemoryMax=8G ...` limits the process group.
  An independent terminal by itself is not a memory limit.
- If a user systemd scope is unavailable, `prlimit --as=8589934592 -- ...` can
  limit a single process's virtual address space. This differs from a resident
  memory limit and may need adjustment for workloads that reserve large virtual
  address ranges. Preserve the caller's other limits and report failures.
- Prefer streaming summaries or compact fixtures to loading whole large HRX
  result files into memory. Use full-tree parsing only when the task requires it
  and the available memory has been considered.
