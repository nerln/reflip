-- One row per day and combination of allowed values, holding only a count.
-- There is no column a sentence could go into, and no row per visit.
CREATE TABLE IF NOT EXISTS counts (
  day TEXT NOT NULL,
  e TEXT NOT NULL,
  f TEXT NOT NULL,
  m TEXT NOT NULL,
  n INTEGER NOT NULL,
  PRIMARY KEY (day, e, f, m)
);
