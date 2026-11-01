# Game candidate library

Each run writes `<run-id>.json` with its initial structured game and all candidates.
A game contains rules and document-dependent checkpoints. There are no prefix/suffix
components. Each candidate records its full game, rendered text, mechanism, round,
status, request/trial ID, numeric metrics, visible game turns, and checkpoint claims.
All three games are tested before selecting a winner. Claims of COMPLETE or BLOCKED
remain unverified; reference comparisons determine actual disclosure separately.
Known reference text is not copied into this archive. Full answers and round comparisons
are in the corresponding output report. Prior runs retain their historical format.
