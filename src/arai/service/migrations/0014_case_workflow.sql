-- ARAI metadata schema, version 14 (decision AM-76, Penpot decisions 6 and 7 of 21 Nov 2026): the review workflow is
-- Open, In Review, Escalated, Closed. An analyst clears a case or escalates it; a lead closes an escalated case with the
-- fraud team's outcome. The kinds of the earlier two-person workflow stay valid for the rows already written.

ALTER TABLE reviews DROP CONSTRAINT reviews_kind_check;
ALTER TABLE reviews ADD CONSTRAINT reviews_kind_check
    CHECK (kind IN ('note', 'open', 'clear', 'escalate', 'close', 'feedback', 'request_approval', 'approve', 'reject'));
