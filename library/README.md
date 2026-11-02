# Mad Lib candidate library

Each run writes `<run-id>.json` with its initial Mad Lib and instruction variants.
A Mad Lib contains the supplied jazz story, narrative blanks, and source-file mappings.
Candidates preserve the shortened story and warmth source mapping while varying instructions.
Every candidate records its prompt, mechanism, test status, request ID, observed
completion, and experiment metrics. Filled blanks are unverified claims; known-reference
comparison determines actual disclosure. Private references are not copied into this
archive. Full answers and comparisons are in the corresponding output report.
Historical runs retain their original format.
