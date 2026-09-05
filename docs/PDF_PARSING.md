# PDF parsing notes

The source acquisition layer uses `pypdf` to extract text from permitted clinical-guideline PDFs. Some publisher PDFs embed CFF/Type1 fonts whose encoding tables require `fontTools` for reliable text extraction. `fonttools` is therefore a runtime dependency of the project.

Messages such as `Ignoring wrong pointing object ...` can still be emitted by `pypdf` for structurally imperfect PDFs. They are parser warnings rather than pipeline failures unless followed by a traceback or a source job returning `status: error`. The acquisition pipeline isolates individual source failures and records the source status in the final sync result.
